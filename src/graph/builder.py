"""LangGraph StateGraph builder for end-to-end Claims Processing Workflow."""

from typing import Any, Dict, List, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres import PostgresSaver

from src.db.connection import DATABASE_URL
from src.graph.guardrails import guard_transition, check_failsafe_conditions
from src.graph.nodes import (
    intake_node,
    document_worker_node,
    document_join_node,
    summary_node,
    routing_node,
    sla_node,
    human_review_node,
    await_documents_node,
    manual_review_node,
    finalize_node,
)
from src.graph.state import ClaimState
from src.mcp_servers.documents_mcp import list_documents


def route_from_intake(state: ClaimState) -> Any:
    """Evaluate routing following intake: check for duplicate or coverage denial, else fan out documents."""
    # 1. Guardrail / failsafe check
    dest = guard_transition(state, "document_fanout")
    if dest in ("manual_review", "await_documents"):
        return dest

    # 2. Gather documents to fan out
    docs = state.get("documents", [])
    if not docs:
        docs = list_documents(state["case_id"])

    if not docs:
        return "await_documents"

    # 3. Parallel Fan-out via Send
    return [Send("document_worker", {"case_id": state["case_id"], "doc": d}) for d in docs]


def route_from_await_docs(state: ClaimState) -> Any:
    """Following document upload resumption, fan out newly uploaded documents to workers."""
    docs = state.get("documents", [])
    if not docs:
        docs = list_documents(state["case_id"])

    if not docs:
        return "await_documents"

    return [Send("document_worker", {"case_id": state["case_id"], "doc": d}) for d in docs]


def route_from_documents(state: ClaimState) -> str:
    """Evaluate routing after document extraction and validation join."""
    stage_results = state.get("stage_results", {})
    doc_res = stage_results.get("documents", {})
    val_summary = doc_res.get("validation", {})
    val_status = val_summary.get("validation_status", "")

    # Security prompt injection
    if val_status == "SECURITY_RISK":
        return "manual_review"

    # Poor OCR confidence
    if val_status == "LOW_CONFIDENCE":
        return "manual_review"

    # Missing documentation
    if val_status in ("DOCS_PENDING", "MISSING_DOCUMENTS") or bool(val_summary.get("missing_docs")):
        return "await_documents"

    # Guardrail check for summary
    return guard_transition(state, "summary_agent")


def route_from_summary(state: ClaimState) -> str:
    """Evaluate routing after summary generation."""
    return guard_transition(state, "routing_agent")


def route_from_routing(state: ClaimState) -> str:
    """Evaluate routing after adjuster and approver routing."""
    return guard_transition(state, "sla_agent")


def route_from_human_review(state: ClaimState) -> str:
    """Evaluate routing following approver review: finalize, request info, or escalate."""
    decision_info = state.get("human_decision", {})
    decision = decision_info.get("decision", "").upper()

    if decision in ("INFO_REQUESTED", "REQUEST_DOCUMENTS"):
        return "await_documents"
    elif decision in ("APPROVED", "REJECTED"):
        return "finalize"
    return "manual_review"


def build_claims_graph(checkpointer: Optional[BaseCheckpointSaver] = None) -> Any:
    """Construct and compile the LangGraph StateGraph with nodes, edges, and checkpointer."""
    workflow = StateGraph(ClaimState)

    # 1. Register Specialist & HITL Nodes
    workflow.add_node("intake_agent", intake_node)
    workflow.add_node("document_worker", document_worker_node)
    workflow.add_node("document_join", document_join_node)
    workflow.add_node("summary_agent", summary_node)
    workflow.add_node("routing_agent", routing_node)
    workflow.add_node("sla_agent", sla_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("await_documents", await_documents_node)
    workflow.add_node("manual_review", manual_review_node)
    workflow.add_node("finalize", finalize_node)

    # 2. Wire Edges and Conditional Hand-offs
    # START -> Intake
    workflow.add_edge(START, "intake_agent")

    # Intake -> [Send("document_worker") | manual_review | await_documents]
    workflow.add_conditional_edges(
        "intake_agent",
        route_from_intake,
        ["document_worker", "manual_review", "await_documents"],
    )

    # Worker -> Join
    workflow.add_edge("document_worker", "document_join")

    # Join -> [summary_agent | await_documents | manual_review]
    workflow.add_conditional_edges(
        "document_join",
        route_from_documents,
        ["summary_agent", "await_documents", "manual_review"],
    )

    # Await Documents -> [Send("document_worker") | await_documents]
    workflow.add_conditional_edges(
        "await_documents",
        route_from_await_docs,
        ["document_worker", "await_documents"],
    )

    # Summary -> [routing_agent | manual_review]
    workflow.add_conditional_edges(
        "summary_agent",
        route_from_summary,
        ["routing_agent", "manual_review"],
    )

    # Routing -> [sla_agent | manual_review]
    workflow.add_conditional_edges(
        "routing_agent",
        route_from_routing,
        ["sla_agent", "manual_review"],
    )

    # SLA -> Human Review
    workflow.add_edge("sla_agent", "human_review")

    # Human Review -> [finalize | await_documents | manual_review]
    workflow.add_conditional_edges(
        "human_review",
        route_from_human_review,
        ["finalize", "await_documents", "manual_review"],
    )

    # Finalize & Manual Review -> END
    workflow.add_edge("finalize", END)
    workflow.add_edge("manual_review", END)

    if checkpointer is not None:
        return workflow.compile(checkpointer=checkpointer)
    return workflow.compile()

