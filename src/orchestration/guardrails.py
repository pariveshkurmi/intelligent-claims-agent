"""Deterministic guardrails and state transition validation for claims graph."""

from typing import Any, Dict, List, Optional, Tuple
from src.orchestration.state import ClaimState


class GuardrailViolationError(Exception):
    """Raised when an out-of-order or invalid workflow transition is attempted."""
    pass


# Valid legal case statuses in the claims domain
VALID_CASE_STATUSES = {
    "NEW",
    "COVERAGE_VERIFIED",
    "DOCS_VALIDATED",
    "DOCS_PENDING",
    "SUMMARY_GENERATED",
    "ROUTED_FOR_APPROVAL",
    "READY_FOR_APPROVAL",
    "MANUAL_REVIEW",
    "APPROVED",
    "REJECTED",
}


def check_failsafe_conditions(state: ClaimState) -> Optional[str]:
    """Inspect state for anomalies that trigger safety overrides:
    - Repeated node errors (>= 2) -> manual_review
    - OCR confidence < 0.50 or LOW_CONFIDENCE -> manual_review
    - Adversarial prompt injection detected -> manual_review
    - Out of policy / non-covered claim -> manual_review
    - Duplicate claim match -> manual_review
    - Missing required documentation -> await_documents
    """
    errors = state.get("errors", [])
    if len(errors) >= 2:
        return "manual_review"

    stage_results = state.get("stage_results", {})

    # 1. Intake checks
    intake = stage_results.get("intake")
    if intake:
        if not intake.get("is_covered", True):
            return "manual_review"
        if intake.get("is_duplicate", False):
            return "manual_review"

    # 2. Document intelligence checks
    doc_results = stage_results.get("documents", {})
    val_summary = doc_results.get("validation", {})
    val_status = val_summary.get("validation_status", "")

    if val_status == "SECURITY_RISK":
        return "manual_review"
    if val_status == "LOW_CONFIDENCE":
        return "manual_review"
    if val_status in ("DOCS_PENDING", "MISSING_DOCUMENTS"):
        return "await_documents"

    # Also check extracted documents directly if available
    extracted_docs = state.get("extracted_documents", [])
    for d in extracted_docs:
        if d.get("is_injection_flagged", False):
            return "manual_review"
        if d.get("confidence", 1.0) < 0.50 or d.get("validation_status") == "LOW_CONFIDENCE":
            return "manual_review"

    return None


def validate_transition(state: ClaimState, target_node: str) -> Tuple[bool, Optional[str]]:
    """Verify that the proposed target node satisfies business process invariants."""
    stage_results = state.get("stage_results", {})
    case_status = state.get("case_status", "NEW")

    # 1. Intake Agent: only at beginning
    if target_node == "intake_agent":
        return True, None

    # 2. Document processing: intake must have run
    if target_node in ("document_fanout", "document_worker"):
        if "intake" not in stage_results:
            return False, "Out-of-order execution: document processing requires intake verification first."
        return True, None

    # 3. Summary Agent: documents must be validated
    if target_node == "summary_agent":
        if "documents" not in stage_results:
            return False, "Out-of-order execution: summary synthesis requires document extraction and validation."
        val_status = stage_results.get("documents", {}).get("validation", {}).get("validation_status", "")
        if val_status in ("DOCS_PENDING", "MISSING_DOCUMENTS"):
            return False, f"Out-of-order execution: cannot generate summary while documents are pending ({val_status})."
        return True, None

    # 4. Routing Agent: summary must exist
    if target_node == "routing_agent":
        if "summary" not in stage_results:
            return False, "Out-of-order execution: case routing requires structured summary brief."
        return True, None

    # 5. SLA & Comms Agent: routing must exist
    if target_node == "sla_agent":
        if "routing" not in stage_results:
            return False, "Out-of-order execution: SLA & comms dispatch requires case assignment."
        return True, None

    # 6. Human Review: routing and summary must exist
    if target_node == "human_review":
        if "routing" not in stage_results or "summary" not in stage_results:
            return False, "Out-of-order execution: human approval pause requires summary and routing."
        return True, None

    # 7. Finalize: requires human decision
    if target_node == "finalize":
        decision = state.get("human_decision")
        if not decision or not decision.get("decision"):
            return False, "Golden Rule Violation: case cannot be finalized without an authorized human decision."
        return True, None

    # 8. Pause / Failsafe nodes are always legal destinations
    if target_node in ("await_documents", "manual_review", "end"):
        return True, None

    return True, None


def guard_transition(state: ClaimState, proposed_target: str, raise_on_violation: bool = False) -> str:
    """Enforce guardrails on proposed next step:
    1. Check failsafes (returns override like 'manual_review' or 'await_documents' if tripped)
    2. Validate legal sequence
    3. Return valid target node or raise GuardrailViolationError
    """
    # Check if safety override is triggered
    override = check_failsafe_conditions(state)
    if override:
        return override

    is_valid, violation_reason = validate_transition(state, proposed_target)
    if not is_valid:
        if raise_on_violation:
            raise GuardrailViolationError(violation_reason)
        # Fall back to manual review with an recorded error
        return "manual_review"

    return proposed_target

