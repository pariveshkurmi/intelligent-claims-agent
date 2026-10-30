"""LangGraph Execution Engine & Streamlit Interface."""

import json
import logging
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional, Tuple
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

from src.db.connection import DATABASE_URL, execute_query
from src.orchestration.builder import build_claims_graph
from src.orchestration.state import ClaimState

logger = logging.getLogger(__name__)


def stream_claim_workflow(
    initial_state: Dict[str, Any], case_id: str
) -> Generator[Dict[str, Any], None, None]:
    """
    Stream claim processing through the LangGraph workflow.
    Yields events with the active node, updated values, and whether an HITL interrupt occurred.
    """
    config = {"configurable": {"thread_id": case_id}}
    with PostgresSaver.from_conn_string(DATABASE_URL) as checkpointer:
        checkpointer.setup()
        graph = build_claims_graph(checkpointer=checkpointer)

        # Stream updates mode gives node-by-node state deltas
        for event in graph.stream(initial_state, config=config, stream_mode="updates"):
            for node_name, update_dict in event.items():
                yield {
                    "node": node_name,
                    "updates": update_dict,
                    "is_interrupt": False,
                }

        # Inspect if graph paused on interrupt
        state = graph.get_state(config)
        tasks = state.tasks
        if tasks and tasks[0].interrupts:
            interrupt_val = tasks[0].interrupts[0].value
            yield {
                "node": state.next[0] if state.next else "interrupt",
                "updates": state.values,
                "is_interrupt": True,
                "interrupt_data": interrupt_val,
            }


def resume_claim_workflow(case_id: str, resume_payload: Any) -> Dict[str, Any]:
    """Resume execution of a paused claim via Command(resume=...)."""
    config = {"configurable": {"thread_id": case_id}}
    with PostgresSaver.from_conn_string(DATABASE_URL) as checkpointer:
        checkpointer.setup()
        graph = build_claims_graph(checkpointer=checkpointer)

        resume_cmd = Command(resume=resume_payload)
        final_output = graph.invoke(resume_cmd, config=config)
        final_state = graph.get_state(config)

        return {
            "final_output": final_output,
            "values": final_state.values,
            "next": final_state.next,
        }


def get_case_checkpoint_state(case_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve the current LangGraph checkpoint state for a case."""
    try:
        config = {"configurable": {"thread_id": case_id}}
        with PostgresSaver.from_conn_string(DATABASE_URL) as checkpointer:
            checkpointer.setup()
            graph = build_claims_graph(checkpointer=checkpointer)
            state = graph.get_state(config)
            if state and state.values:
                return {
                    "values": state.values,
                    "next": state.next,
                    "tasks": [
                        {
                            "name": t.name,
                            "interrupts": [i.value for i in t.interrupts] if t.interrupts else [],
                        }
                        for t in (state.tasks or [])
                    ],
                }
    except Exception as e:
        logger.error(f"Error fetching checkpoint state for {case_id}: {e}")
    return None


def get_full_case_details(case_id: str) -> Dict[str, Any]:
    """Fetch complete case records from DB: case, summary, documents, and audit timeline."""
    case_rows = execute_query(
        """
        SELECT c.*,
               adj.name as adjuster_name, adj.email as adjuster_email,
               app.name as approver_name, app.approval_limit as approver_limit
        FROM cases c
        LEFT JOIN staff adj ON c.assigned_adjuster_id = adj.staff_id
        LEFT JOIN staff app ON c.assigned_approver_id = app.staff_id
        WHERE c.case_id = %s;
        """,
        (case_id,),
    )
    if not case_rows:
        return {}

    case_data = dict(case_rows[0])
    if case_data.get("total_amount") is not None:
        case_data["total_amount"] = float(case_data["total_amount"])

    # Documents
    doc_rows = execute_query(
        """
        SELECT doc_id, doc_type, file_path, ocr_confidence, validation_status,
               is_injection_flagged, extracted_fields, ocr_text, uploaded_at
        FROM case_documents WHERE case_id = %s ORDER BY uploaded_at ASC;
        """,
        (case_id,),
    )
    for d in doc_rows:
        d["doc_id"] = str(d["doc_id"])
        if d.get("ocr_confidence") is not None:
            d["ocr_confidence"] = float(d["ocr_confidence"])

    # Summary
    summary_rows = execute_query(
        "SELECT * FROM case_summaries WHERE case_id = %s;",
        (case_id,),
    )
    summary_data = dict(summary_rows[0]) if summary_rows else {}

    # Audit timeline
    audit_rows = execute_query(
        """
        SELECT audit_id, actor, action, before_state, after_state, timestamp
        FROM case_timeline_audit WHERE case_id = %s ORDER BY timestamp ASC;
        """,
        (case_id,),
    )
    for a in audit_rows:
        a["audit_id"] = str(a["audit_id"])
        a["timestamp"] = str(a["timestamp"])

    return {
        "case": case_data,
        "documents": doc_rows,
        "summary": summary_data,
        "timeline": audit_rows,
    }
