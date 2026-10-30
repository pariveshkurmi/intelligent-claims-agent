"""Tests for Day 4 Streamlit Claims Workspace: Auth, Engine, Components, and Supervisor Chat."""

import json
import uuid
import pytest

from src.db.connection import execute_mutation, execute_query
from src.ui.auth import (
    DEFAULT_STAFF,
    can_approve,
    get_current_user,
    set_current_user,
)
from src.ui.components import (
    STATUS_COLORS,
    load_seed_pack_by_id,
    load_seed_pack_manifest,
    render_status_badge,
)
from src.ui.engine import (
    get_case_checkpoint_state,
    get_full_case_details,
    resume_claim_workflow,
    stream_claim_workflow,
)
from src.ui.supervisor_chat import ask_supervisor, generate_offline_supervisor_reply


@pytest.fixture(autouse=True)
def cleanup_ui_test_cases():
    """Ensure clean database state for UI test cases."""
    yield
    execute_mutation(
        "DELETE FROM cases WHERE case_id LIKE 'TEST-UI-%' OR case_id LIKE 'CASE-UI-%';"
    )


def test_auth_rbac_and_golden_rule_enforcement():
    """Test RBAC role switching and Golden Rule approval limit enforcement."""
    # 1. Tier 1 Approver (Limit $2,500)
    set_current_user("APP-201")
    user = get_current_user()
    assert user["staff_id"] == "APP-201"
    assert user["approval_limit"] == 2500.0

    # Under limit ($1,850) -> Authorized
    ok, msg = can_approve(1850.0)
    assert ok is True
    assert "Authorized" in msg

    # Over limit ($4,500) -> Unauthorized (Golden Rule Block)
    ok, msg = can_approve(4500.0)
    assert ok is False
    assert "exceeds your authorization limit" in msg

    # 2. Adjuster (Limit $0) -> Cannot approve any amount
    set_current_user("ADJ-101")
    user = get_current_user()
    assert user["role"] == "adjuster"
    ok, msg = can_approve(500.0)
    assert ok is False
    assert "not authorized to approve" in msg

    # 3. Tier 3 Director (Limit $100,000)
    set_current_user("APP-203")
    user = get_current_user()
    assert user["approval_limit"] == 100000.0
    ok, msg = can_approve(45000.0)
    assert ok is True


def test_components_badges_and_manifest():
    """Test badge generator and seed pack manifest loading."""
    # Badge rendering
    for st, (col, lbl) in STATUS_COLORS.items():
        badge_html = render_status_badge(st)
        assert col in badge_html
        assert lbl in badge_html

    # Manifest
    manifest = load_seed_pack_manifest()
    assert len(manifest) == 30
    first_pack = manifest[0]
    assert "case_id" in first_pack
    assert "scenario" in first_pack

    # Individual pack loading
    pack = load_seed_pack_by_id(first_pack["case_id"])
    assert pack is not None
    assert pack["case_id"] == first_pack["case_id"]
    assert len(pack["documents"]) >= 1


def test_supervisor_chat_offline_and_streaming():
    """Test contextual Supervisor AI replies against case facts, risks, and timeline."""
    case_data = {
        "case": {
            "case_id": "CASE-TEST-SUP",
            "claimant_name": "Eleanor Vance",
            "policy_id": "POL-UHG-001",
            "total_amount": 3450.0,
            "status": "MANUAL_REVIEW",
            "adjuster_name": "Alex Morgan",
            "approver_name": "Jordan Hayes",
            "approver_limit": 2500.0,
        },
        "summary": {
            "facts": {"diagnosis": "Acute Appendicitis", "procedure": "Laparoscopic Appendectomy"},
            "evidence": {"doc_1": "Itemized bill"},
            "missing_info": ["doctor_notes"],
            "risks": ["Low OCR confidence in itemized bill"],
            "policy_citations": ["Clause 4.1 Inpatient Care"],
            "next_action": "MANUAL_REVIEW",
        },
        "documents": [
            {
                "doc_id": "doc-01",
                "doc_type": "itemized_bill",
                "ocr_confidence": 0.65,
                "is_injection_flagged": False,
            }
        ],
        "timeline": [
            {"timestamp": "2026-10-30 10:00:00", "actor": "intake_agent", "action": "CASE_REGISTERED"},
            {"timestamp": "2026-10-30 10:01:00", "actor": "supervisor", "action": "ESCALATED_TO_MANUAL_REVIEW"},
        ],
    }

    # Status inquiry
    reply_status = generate_offline_supervisor_reply("CASE-TEST-SUP", "Why is this in manual review?", case_data)
    assert "MANUAL_REVIEW" in reply_status
    assert "Low OCR confidence" in reply_status

    # Missing docs inquiry
    reply_docs = generate_offline_supervisor_reply("CASE-TEST-SUP", "What documents are missing?", case_data)
    assert "doctor_notes" in reply_docs

    # Timeline inquiry
    reply_timeline = generate_offline_supervisor_reply("CASE-TEST-SUP", "Show me the audit timeline", case_data)
    assert "intake_agent" in reply_timeline
    assert "ESCALATED_TO_MANUAL_REVIEW" in reply_timeline

    # Approver limit inquiry
    reply_limit = generate_offline_supervisor_reply("CASE-TEST-SUP", "What is the approver limit?", case_data)
    assert "$2,500.00" in reply_limit
    assert "Exceeds Limit" in reply_limit


def test_ui_engine_workflow_streaming_and_resume():
    """Test full UI engine LangGraph execution, HITL interrupt, and resumption."""
    case_id = f"TEST-UI-{uuid.uuid4().hex[:8]}"

    initial_state = {
        "case_id": case_id,
        "policy_id": "POL-UHG-001",
        "claimant_name": "David Ross",
        "claimant_email": "david.ross@example.com",
        "date_of_service": "2026-10-15",
        "total_amount": 1650.00,
        "documents": [
            {
                "doc_id": str(uuid.uuid4()),
                "doc_type": "claim_form",
                "ocr_confidence": 0.98,
                "ocr_text": "UNITEDHEALTHCARE CLAIM FORM\nClaimant: David Ross\nPolicy: POL-UHG-001\nDiagnosis: Appendectomy\nClaimed: $1650.00",
            },
            {
                "doc_id": str(uuid.uuid4()),
                "doc_type": "itemized_bill",
                "ocr_confidence": 0.95,
                "ocr_text": "ST. MARY HOSPITAL - ITEMIZED BILL\nTotal Billed: $1650.00\n- Surgical Services: $1200.00\n- Pharmacy: $450.00",
            },
        ],
        "agent_hops": [],
        "stage_results": {},
        "errors": [],
    }

    # 1. Stream execution
    events = list(stream_claim_workflow(initial_state, case_id))
    nodes_traversed = [e["node"] for e in events]

    assert "intake_agent" in nodes_traversed
    assert "document_join" in nodes_traversed
    assert "summary_agent" in nodes_traversed
    assert "routing_agent" in nodes_traversed
    assert "sla_agent" in nodes_traversed

    # Last event should be the HITL interrupt
    last_event = events[-1]
    assert last_event["is_interrupt"] is True
    assert last_event["interrupt_data"]["status"] == "AWAITING_HUMAN_DECISION"

    # 2. Check full case details loaded by UI
    details = get_full_case_details(case_id)
    assert details["case"]["status"] == "READY_FOR_APPROVAL"
    assert len(details["documents"]) >= 2
    assert details["summary"] is not None
    assert len(details["timeline"]) >= 3

    # 3. Check checkpoint state
    ckpt = get_case_checkpoint_state(case_id)
    assert ckpt is not None
    assert ckpt["next"] == ("human_review",)

    # 4. Resume via Command(resume=...)
    resume_res = resume_claim_workflow(
        case_id,
        {
            "decision": "APPROVED",
            "rationale": "Charges adhere to PPO benefit schedule. Verified by Tier 1 Approver.",
            "approver_id": "APP-201",
        },
    )
    assert resume_res["values"]["case_status"] == "APPROVED"
    assert resume_res["values"]["human_decision"]["decision"] == "APPROVED"

    # Confirm final DB state
    updated_details = get_full_case_details(case_id)
    assert updated_details["case"]["status"] == "APPROVED"
    assert updated_details["case"]["human_decision"] == "APPROVED"

