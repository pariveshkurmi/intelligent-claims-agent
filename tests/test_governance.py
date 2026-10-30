"""Unit and Integration Tests for Day 5: Governance, Observability & Auditing."""

import os
import uuid
import pytest
from src.utils.audit import (
    get_case_audit_trail,
    log_audit_event,
    query_mailpit_messages,
    verify_case_audit_integrity,
)
from src.utils.tracing import (
    check_phoenix_health,
    get_tracer,
    init_tracing,
    trace_agent_hop,
    trace_mcp_call,
)
from src.evaluation.metrics import check_pii_leakage


def test_phoenix_tracing_initialization_and_spans():
    """Verify Arize Phoenix tracing initializes and exports spans."""
    initialized = init_tracing(force=True)
    assert initialized is True

    tracer = get_tracer()
    assert tracer is not None

    test_case_id = f"TEST-GOV-{uuid.uuid4().hex[:6]}"
    with trace_agent_hop("intake_agent", test_case_id, stage="intake") as span:
        assert span is not None

    with trace_mcp_call("case-mcp", "get_case", test_case_id, {"case_id": test_case_id}) as span:
        assert span is not None


def test_phoenix_health_endpoint():
    """Verify Arize Phoenix container on port 6006 is reachable and healthy."""
    health = check_phoenix_health()
    assert health["status"] in ("connected", "degraded")
    assert health["collector_endpoint"].endswith("/v1/traces")


def test_audit_timeline_recording_and_integrity():
    """Verify append-only audit trail records sequential events and verifies integrity."""
    from src.db.connection import execute_mutation
    test_case_id = f"TEST-AUDIT-{uuid.uuid4().hex[:6]}"

    # Ensure parent case exists in cases table
    execute_mutation(
        "INSERT INTO cases (case_id, policy_id, claimant_name, total_amount, status) VALUES (%s, 'POL-UHG-001', 'Test Claimant', 1000.0, 'NEW');",
        (test_case_id,),
    )

    try:
        # Record 3 sequential events: Intake -> Document -> Approver
        log_audit_event(
            case_id=test_case_id,
            actor="intake_agent",
            action="CASE_REGISTERED",
            before_state={"status": "NEW"},
            after_state={"status": "REGISTERED"},
        )
        log_audit_event(
            case_id=test_case_id,
            actor="document_agent",
            action="DOCUMENTS_VALIDATED",
            before_state={"status": "REGISTERED"},
            after_state={"status": "DOCS_VALIDATED"},
        )
        log_audit_event(
            case_id=test_case_id,
            actor="human_approver:APP-201",
            action="CLAIM_APPROVED",
            before_state={"status": "READY_FOR_APPROVAL"},
            after_state={"status": "APPROVED"},
        )

        timeline = get_case_audit_trail(test_case_id)
        assert len(timeline) == 3
        assert timeline[0]["action"] == "CASE_REGISTERED"
        assert timeline[1]["action"] == "DOCUMENTS_VALIDATED"
        assert timeline[2]["action"] == "CLAIM_APPROVED"

        integrity = verify_case_audit_integrity(test_case_id)
        assert integrity["has_records"] is True
        assert integrity["is_complete"] is True
        assert len(integrity["actors"]) == 3
    finally:
        execute_mutation("DELETE FROM cases WHERE case_id = %s;", (test_case_id,))


def test_mailpit_api_query_connectivity():
    """Verify Mailpit mock email server responds to query API."""
    messages = query_mailpit_messages()
    assert isinstance(messages, list)


def test_pii_redaction_regex_zero_leakage():
    """Verify PII leakage detector accurately catches raw SSNs and allows redacted placeholders."""
    # Clean text with redacted tokens
    safe_text = "Claimant SSN: [REDACTED_SSN] and phone: [REDACTED_PHONE]."
    assert check_pii_leakage(safe_text) == 0

    # Adversarial unredacted SSN
    leaked_ssn = "Customer SSN is 123-45-6789 and phone is 555-123-4567"
    assert check_pii_leakage(leaked_ssn) >= 1
