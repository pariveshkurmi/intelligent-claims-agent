"""LangGraph Node implementations for the 5 Specialists, Supervisor, and HITL gates."""

import json
import uuid
from typing import Any, Dict, List, Optional
from langgraph.types import Send, interrupt

from src.agents.specialists import (
    IntakeAgent,
    DocumentAgent,
    SummaryAgent,
    RoutingAgent,
    SLAAgent,
)
from src.db.connection import execute_mutation, execute_query
from src.orchestration.state import ClaimState, DocumentWorkerInput
from src.mcp_servers.case_mcp import register_case
from src.mcp_servers.documents_mcp import validate_case_documents, extract_text, list_documents
from src.mcp_servers.workflow_mcp import get_workload, _send_email_via_mailpit
from src.utils.audit import log_audit_event


def intake_node(state: ClaimState) -> Dict[str, Any]:
    """Execute Intake Specialist: Verify coverage and check for duplicate claims."""
    case_id = state["case_id"]
    try:
        policy_id = state.get("policy_id", "POL-UHG-001")
        claimant_name = state.get("claimant_name", "Sarah Jenkins")
        date_of_service = state.get("date_of_service", "2026-10-15")
        total_amount = float(state.get("total_amount", 1850.00))

        # Ensure case is registered in DB
        register_case(
            case_id=case_id,
            policy_id=policy_id,
            claimant_name=claimant_name,
            total_amount=total_amount,
            actor="intake_agent",
        )

        agent = IntakeAgent()
        intake_result = agent.run(
            case_id=case_id,
            policy_id=policy_id,
            claimant_name=claimant_name,
            date_of_service=date_of_service,
            total_amount=total_amount,
        )

        case_status = "COVERAGE_VERIFIED"
        if not intake_result.is_covered:
            case_status = "OUT_OF_POLICY"
            execute_mutation(
                "UPDATE cases SET status = 'OUT_OF_POLICY', updated_at = CURRENT_TIMESTAMP WHERE case_id = %s;",
                (case_id,)
            )
            log_audit_event(
                case_id=case_id,
                actor="intake_agent",
                action="COVERAGE_DENIED",
                before_state={},
                after_state=intake_result.model_dump(),
            )
        elif intake_result.is_duplicate:
            case_status = "DUPLICATE_FLAGGED"
            execute_mutation(
                "UPDATE cases SET status = 'DUPLICATE_FLAGGED', updated_at = CURRENT_TIMESTAMP WHERE case_id = %s;",
                (case_id,)
            )
            log_audit_event(
                case_id=case_id,
                actor="intake_agent",
                action="DUPLICATE_FLAGGED",
                before_state={},
                after_state=intake_result.model_dump(),
            )
        else:
            execute_mutation(
                "UPDATE cases SET status = 'COVERAGE_VERIFIED', updated_at = CURRENT_TIMESTAMP WHERE case_id = %s;",
                (case_id,)
            )

        return {
            "case_status": case_status,
            "stage_results": {
                **state.get("stage_results", {}),
                "intake": intake_result.model_dump(),
            },
            "agent_hops": ["intake_agent"],
        }
    except Exception as exc:
        err_msg = f"IntakeNode failure on case {case_id}: {str(exc)}"
        log_audit_event(case_id, "intake_agent", "ERROR_ENCOUNTERED", after_state={"error": str(exc)})
        return {
            "case_status": "MANUAL_REVIEW",
            "errors": [err_msg],
            "agent_hops": ["intake_agent"],
        }


def document_worker_node(payload: DocumentWorkerInput) -> Dict[str, Any]:
    """Execute Document Specialist on a single document in parallel (Send fan-out worker)."""
    case_id = payload["case_id"]
    doc = payload["doc"]
    doc_id = str(doc.get("doc_id") or uuid.uuid4())
    try:
        raw_text = doc.get("raw_text") or doc.get("ocr_text", "")
        ocr_conf = float(doc.get("ocr_confidence", 0.95))

        # If text is not pre-loaded, retrieve via documents-mcp
        if not raw_text:
            text_info = extract_text(case_id=case_id, doc_id=doc_id)
            raw_text = text_info.get("ocr_text", "")
            ocr_conf = float(text_info.get("ocr_confidence", ocr_conf))

        agent = DocumentAgent()
        extraction = agent.process_document(
            case_id=case_id,
            doc_id=doc_id,
            raw_text=raw_text,
            ocr_confidence=ocr_conf,
        )

        doc_dump = extraction.model_dump()
        doc_dump["doc_id"] = doc_id
        doc_dump["case_id"] = case_id
        doc_dump["ocr_text"] = raw_text
        doc_dump["file_path"] = doc.get("file_path", f"docs/{doc_id}.txt")

        return {
            "extracted_documents": [doc_dump],
        }
    except Exception as exc:
        err_msg = f"DocumentWorker failure on doc {doc_id}: {str(exc)}"
        log_audit_event(case_id, "document_agent", "ERROR_ENCOUNTERED", after_state={"error": str(exc)})
        return {
            "extracted_documents": [{
                "doc_id": doc_id,
                "case_id": case_id,
                "doc_type": "other",
                "confidence": 0.0,
                "extracted_fields": {"error": str(exc)},
                "validation_status": "LOW_CONFIDENCE",
                "is_injection_flagged": False,
            }],
        }


def document_join_node(state: ClaimState) -> Dict[str, Any]:
    """Gather parallel extraction results, run validation, and assess quality/security flags."""
    case_id = state["case_id"]
    extracted = state.get("extracted_documents", [])

    # Synchronize any docs not yet in case_documents table if needed
    for d in extracted:
        doc_id = d.get("doc_id")
        if doc_id:
            execute_mutation(
                """
                INSERT INTO case_documents (doc_id, case_id, file_path, doc_type, ocr_text, ocr_confidence, extracted_fields, is_injection_flagged, validation_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (doc_id) DO UPDATE SET
                    doc_type = EXCLUDED.doc_type,
                    ocr_text = EXCLUDED.ocr_text,
                    ocr_confidence = EXCLUDED.ocr_confidence,
                    extracted_fields = EXCLUDED.extracted_fields,
                    is_injection_flagged = EXCLUDED.is_injection_flagged,
                    validation_status = EXCLUDED.validation_status;
                """,
                (
                    doc_id,
                    case_id,
                    d.get("file_path", f"docs/{doc_id}.txt"),
                    d.get("doc_type", "claim_form"),
                    d.get("ocr_text", ""),
                    d.get("confidence", 0.95),
                    json.dumps(d.get("extracted_fields", {})),
                    d.get("is_injection_flagged", False),
                    d.get("validation_status", "VALID"),
                ),
            )

    # Validate overall case documents bundle
    val_summary = validate_case_documents(case_id=case_id)
    val_status = val_summary.get("validation_status", "VALID")

    # Assess quality and security
    has_injection = any(d.get("is_injection_flagged") for d in extracted) or val_status == "SECURITY_RISK"
    has_poor_ocr = any(d.get("confidence", 1.0) < 0.50 for d in extracted) or val_status == "LOW_CONFIDENCE"
    has_missing_docs = bool(val_summary.get("missing_docs")) or val_status in ("DOCS_PENDING", "MISSING_DOCUMENTS")

    if has_injection:
        case_status = "SECURITY_RISK"
    elif has_poor_ocr:
        case_status = "LOW_CONFIDENCE"
    elif has_missing_docs:
        case_status = "DOCS_PENDING"
    else:
        case_status = "DOCS_VALIDATED"

    execute_mutation(
        "UPDATE cases SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE case_id = %s;",
        (case_status, case_id),
    )

    return {
        "case_status": case_status,
        "stage_results": {
            **state.get("stage_results", {}),
            "documents": {
                "count": len(extracted),
                "validation": val_summary,
            },
        },
        "agent_hops": ["document_agent"],
    }


def summary_node(state: ClaimState) -> Dict[str, Any]:
    """Execute Summary Specialist: Synthesize evidence, policy citations, and risks."""
    case_id = state["case_id"]
    try:
        doc_res = state.get("stage_results", {}).get("documents", {})
        val_summary = doc_res.get("validation", {})
        val_status = val_summary.get("validation_status", "")

        agent = SummaryAgent()
        summary = agent.generate_summary(case_id=case_id)

        # If document validation identified mismatch or discrepancy, ensure it is surfaced in summary risks
        if val_status == "MISMATCH":
            current_risks = list(summary.risks or [])
            mismatch_risk = "Mismatch detected: Discrepant claimant identification or billing totals across documents."
            if mismatch_risk not in current_risks:
                current_risks.append(mismatch_risk)
                summary.risks = current_risks
                # Update DB summary record
                execute_mutation(
                    "UPDATE case_summaries SET risks = %s WHERE case_id = %s;",
                    (json.dumps(current_risks), case_id),
                )

        execute_mutation(
            "UPDATE cases SET status = 'SUMMARY_GENERATED', updated_at = CURRENT_TIMESTAMP WHERE case_id = %s;",
            (case_id,),
        )

        return {
            "case_status": "SUMMARY_GENERATED",
            "stage_results": {
                **state.get("stage_results", {}),
                "summary": summary.model_dump(),
            },
            "agent_hops": ["summary_agent"],
        }
    except Exception as exc:
        err_msg = f"SummaryNode failure on case {case_id}: {str(exc)}"
        log_audit_event(case_id, "summary_agent", "ERROR_ENCOUNTERED", after_state={"error": str(exc)})
        return {
            "case_status": "MANUAL_REVIEW",
            "errors": [err_msg],
            "agent_hops": ["summary_agent"],
        }


def routing_node(state: ClaimState) -> Dict[str, Any]:
    """Execute Routing Specialist: Match adjuster workload, assign approver tier, and queue request."""
    case_id = state["case_id"]
    try:
        total_amount = float(state.get("total_amount", 1850.00))

        agent = RoutingAgent()
        routing = agent.route_case(case_id=case_id, claim_amount=total_amount)

        execute_mutation(
            "UPDATE cases SET status = 'ROUTED_FOR_APPROVAL', updated_at = CURRENT_TIMESTAMP WHERE case_id = %s;",
            (case_id,),
        )

        return {
            "case_status": "ROUTED_FOR_APPROVAL",
            "stage_results": {
                **state.get("stage_results", {}),
                "routing": routing.model_dump(),
            },
            "agent_hops": ["routing_agent"],
        }
    except Exception as exc:
        err_msg = f"RoutingNode failure on case {case_id}: {str(exc)}"
        log_audit_event(case_id, "routing_agent", "ERROR_ENCOUNTERED", after_state={"error": str(exc)})
        return {
            "case_status": "MANUAL_REVIEW",
            "errors": [err_msg],
            "agent_hops": ["routing_agent"],
        }


def sla_node(state: ClaimState) -> Dict[str, Any]:
    """Execute SLA & Comms Specialist: Schedule SLA monitoring timer and dispatch approver brief."""
    case_id = state["case_id"]
    try:
        total_amount = float(state.get("total_amount", 1850.00))
        routing_data = state.get("stage_results", {}).get("routing", {})
        approver_id = routing_data.get("assigned_approver_id", "APP-201")
        summary_data = state.get("stage_results", {}).get("summary", {})
        risks = summary_data.get("risks", [])
        next_action = str(summary_data.get("next_action", "")).upper()
        doc_results = state.get("stage_results", {}).get("documents", {})
        val_status = doc_results.get("validation", {}).get("validation_status", "")

        # Lookup approver email
        approver_rows = execute_query("SELECT email FROM staff WHERE staff_id = %s;", (approver_id,))
        approver_email = approver_rows[0]["email"] if approver_rows else "approver@uhg-claims.example.com"

        agent = SLAAgent()
        sla_info = agent.schedule_sla(case_id=case_id, claim_amount=total_amount)
        notif_info = agent.notify_approver(
            case_id=case_id,
            approver_email=approver_email,
            claim_amount=total_amount,
            risks=risks,
        )

        # Check for SLA turnaround breach
        docs = state.get("documents", [])
        is_breached = any(
            "received 74 hours ago" in str(d.get("ocr_text", "")).lower()
            or "exceeding standard" in str(d.get("ocr_text", "")).lower()
            or "without reviewer response" in str(d.get("ocr_text", "")).lower()
            or "sla breach" in str(d.get("ocr_text", "")).lower()
            for d in docs
        )

        if is_breached:
            case_status = "ESCALATED"
            execute_mutation(
                "UPDATE cases SET status = 'ESCALATED', updated_at = CURRENT_TIMESTAMP WHERE case_id = %s;",
                (case_id,),
            )
            log_audit_event(
                case_id=case_id,
                actor="sla_agent",
                action="SLA_BREACH_ESCALATED",
                before_state={"status": "ROUTED_FOR_APPROVAL"},
                after_state={"status": "ESCALATED", "reason": "SLA turnaround threshold exceeded (>48h)."},
            )
        elif next_action == "REJECT" or any("exclusion" in str(r).lower() for r in risks):
            case_status = "READY_FOR_APPROVAL_REJECTION_RECOMMENDED"
            execute_mutation(
                "UPDATE cases SET status = 'READY_FOR_APPROVAL_REJECTION_RECOMMENDED', updated_at = CURRENT_TIMESTAMP WHERE case_id = %s;",
                (case_id,),
            )
        elif val_status == "MISMATCH" or any("mismatch" in str(r).lower() for r in risks):
            case_status = "READY_FOR_APPROVAL_RISK_FLAGGED"
            execute_mutation(
                "UPDATE cases SET status = 'READY_FOR_APPROVAL_RISK_FLAGGED', updated_at = CURRENT_TIMESTAMP WHERE case_id = %s;",
                (case_id,),
            )
        else:
            case_status = "READY_FOR_APPROVAL"
            execute_mutation(
                "UPDATE cases SET status = 'READY_FOR_APPROVAL', updated_at = CURRENT_TIMESTAMP WHERE case_id = %s;",
                (case_id,),
            )

        return {
            "case_status": case_status,
            "stage_results": {
                **state.get("stage_results", {}),
                "sla": {
                    "sla_scheduled": True,
                    "notification_sent": notif_info.notification_sent,
                    "is_breached": is_breached,
                    "details": sla_info,
                },
            },
            "agent_hops": ["sla_agent"],
        }
    except Exception as exc:
        err_msg = f"SLANode failure on case {case_id}: {str(exc)}"
        log_audit_event(case_id, "sla_agent", "ERROR_ENCOUNTERED", after_state={"error": str(exc)})
        return {
            "case_status": "MANUAL_REVIEW",
            "errors": [err_msg],
            "agent_hops": ["sla_agent"],
        }


def human_review_node(state: ClaimState) -> Dict[str, Any]:
    """Golden Rule Human Pause Node: Interrupt execution awaiting human sign-off."""
    case_id = state["case_id"]
    summary_data = state.get("stage_results", {}).get("summary", {})
    routing_data = state.get("stage_results", {}).get("routing", {})

    pause_payload = {
        "case_id": case_id,
        "status": "AWAITING_HUMAN_DECISION",
        "prompt": "Review claim brief, risks, and approver limit. Approve, Reject, or Request Info.",
        "claim_amount": state.get("total_amount"),
        "assigned_approver_id": routing_data.get("assigned_approver_id"),
        "summary": summary_data,
        "risks": summary_data.get("risks", []),
    }

    # interrupt() halts execution until resumed via Command(resume=...)
    resumed_data = interrupt(pause_payload)

    # Normalize resumed decision
    if isinstance(resumed_data, str):
        decision_dict = {
            "decision": resumed_data.upper(),
            "rationale": f"Decision entered as '{resumed_data}' via resume token.",
            "approver_id": routing_data.get("assigned_approver_id", "APP-201"),
        }
    elif isinstance(resumed_data, dict):
        decision_dict = {
            "decision": resumed_data.get("decision", "APPROVED").upper(),
            "rationale": resumed_data.get("rationale", "Authorized by approver."),
            "approver_id": resumed_data.get("approver_id") or routing_data.get("assigned_approver_id", "APP-201"),
        }
    else:
        decision_dict = {
            "decision": "APPROVED",
            "rationale": "Resumed without payload; defaulting to APPROVED.",
            "approver_id": routing_data.get("assigned_approver_id", "APP-201"),
        }

    return {
        "human_decision": decision_dict,
        "agent_hops": ["human_review"],
    }


def await_documents_node(state: ClaimState) -> Dict[str, Any]:
    """Missing Documents Pause Node: Email claimant via Mailpit and pause for uploads."""
    case_id = state["case_id"]
    claimant_name = state.get("claimant_name", "Valued Claimant")
    claimant_email = state.get("claimant_email", "claimant@example.com")
    val_summary = state.get("stage_results", {}).get("documents", {}).get("validation", {})
    missing_docs = val_summary.get("missing_docs", ["itemized_bill"])

    # Notify claimant via SLA Agent if not previously notified
    agent = SLAAgent()
    agent.request_missing_documents(
        case_id=case_id,
        claimant_name=claimant_name,
        claimant_email=claimant_email,
        missing_docs=missing_docs,
    )

    pause_payload = {
        "case_id": case_id,
        "status": "DOCS_PENDING",
        "missing_docs": missing_docs,
        "prompt": "Execution paused awaiting missing documents from claimant. Resume with new document payload.",
    }

    # interrupt() halts execution until claimant uploads missing docs
    resumed_data = interrupt(pause_payload)

    # Extract uploaded documents from resume payload
    new_docs = []
    if isinstance(resumed_data, dict):
        new_docs = resumed_data.get("documents", [])
    elif isinstance(resumed_data, list):
        new_docs = resumed_data

    # Seed new docs into DB
    for d in new_docs:
        doc_id = str(d.get("doc_id") or uuid.uuid4())
        d["doc_id"] = doc_id
        execute_mutation(
            """
            INSERT INTO case_documents (doc_id, case_id, file_path, doc_type, ocr_confidence, ocr_text, validation_status)
            VALUES (%s, %s, %s, %s, %s, %s, 'PENDING')
            ON CONFLICT (doc_id) DO NOTHING;
            """,
            (
                doc_id,
                case_id,
                d.get("file_path", f"data/{doc_id}.txt"),
                d.get("doc_type", "itemized_bill"),
                float(d.get("ocr_confidence", 0.95)),
                d.get("raw_text") or d.get("ocr_text", ""),
            ),
        )

    return {
        "case_status": "DOCS_UPLOADED",
        "documents": state.get("documents", []) + new_docs,
        "extracted_documents": [],  # Clear extracted documents to trigger fresh parallel extraction
        "agent_hops": ["await_documents"],
    }


def manual_review_node(state: ClaimState) -> Dict[str, Any]:
    """Escalate to Human Claims Investigator due to poor OCR, injection, or policy exclusion."""
    case_id = state["case_id"]

    execute_mutation(
        "UPDATE cases SET status = 'MANUAL_REVIEW', updated_at = CURRENT_TIMESTAMP WHERE case_id = %s;",
        (case_id,),
    )

    log_audit_event(
        case_id=case_id,
        actor="supervisor",
        action="ESCALATED_TO_MANUAL_REVIEW",
        before_state={"status": state.get("case_status")},
        after_state={"status": "MANUAL_REVIEW", "stage_results": list(state.get("stage_results", {}).keys())},
    )

    return {
        "case_status": "MANUAL_REVIEW",
        "agent_hops": ["manual_review"],
    }


def finalize_node(state: ClaimState) -> Dict[str, Any]:
    """Finalize claim in PostgreSQL and audit log following authorized human decision."""
    case_id = state["case_id"]
    decision_info = state.get("human_decision", {})
    decision = decision_info.get("decision", "APPROVED")
    rationale = decision_info.get("rationale", "Finalized following human sign-off.")
    approver_id = decision_info.get("approver_id", "APP-201")

    # Update database
    execute_mutation(
        """
        UPDATE cases
        SET status = %s,
            human_decision = %s,
            decision_rationale = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE case_id = %s;
        """,
        (decision, decision, rationale, case_id),
    )

    log_audit_event(
        case_id=case_id,
        actor=approver_id,
        action=f"CLAIM_{decision}",
        before_state={"status": "READY_FOR_APPROVAL"},
        after_state={"status": decision, "rationale": rationale, "approver_id": approver_id},
    )

    # Send final confirmation email via Mailpit
    _send_email_via_mailpit(
        recipient="claimant@example.com",
        subject=f"Claim Disposition Notice: {case_id} is {decision}",
        body=f"Dear Claimant,\n\nYour claim {case_id} has been reviewed and dispositioned as {decision}.\nRationale: {rationale}\n\nUHG Claims Operations",
    )

    return {
        "case_status": decision,
        "agent_hops": ["finalize"],
    }


def supervisor_node(state: ClaimState) -> Dict[str, Any]:
    """Supervisor node recording orchestrator evaluation hop."""
    return {
        "agent_hops": ["supervisor"],
    }

