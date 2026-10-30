"""Comprehensive test suite for the 4 FastMCP servers."""

import json
import pytest
from src.mcp_servers.case_mcp import (
    case_summary,
    find_similar_cases,
    get_case,
    get_case_resource,
    get_case_timeline_resource,
    list_cases,
    register_case,
    save_summary,
)
from src.mcp_servers.policy_mcp import (
    check_coverage,
    get_policy,
    get_policy_resource,
    get_policy_wording_resource,
    search_policy_wording,
)
from src.mcp_servers.documents_mcp import (
    classify_document,
    extract_fields,
    extract_text,
    get_document_resource,
    list_documents,
    validate_case_documents,
)
from src.mcp_servers.workflow_mcp import (
    approver_brief,
    assign_case,
    claimant_letter,
    get_sla_rules_resource,
    get_staff_directory_resource,
    get_workload,
    request_approval,
    request_documents,
    schedule_sla,
    send_notification,
)
from src.db.connection import execute_query


# ==========================================
# 1. CASE-MCP TESTS
# ==========================================

def test_case_mcp_get_and_list_cases():
    """Verify get_case and list_cases return seeded records."""
    cases = list_cases(limit=10)
    assert len(cases) > 0, "Expected at least 1 case in database"
    
    first_case_id = cases[0]["case_id"]
    case = get_case(first_case_id)
    assert case["case_id"] == first_case_id
    assert "status" in case
    assert "claimant_name" in case


def test_case_mcp_duplicate_detection():
    """Verify find_similar_cases detects the historical duplicate case."""
    similar = find_similar_cases(claimant_name="Robert Langdon", total_amount=1450.00)
    assert len(similar) >= 1
    match = similar[0]
    assert match["claimant_name"] == "Robert Langdon"
    assert match["duplicate_warning"] is True


def test_case_mcp_register_and_save_summary():
    """Verify case registration, summary persistence, and audit log entries."""
    test_case_id = "CASE-TEST-MCP-01"
    reg = register_case(
        case_id=test_case_id,
        policy_id="POL-UHG-001",
        claimant_name="Test Patient",
        total_amount=2500.00,
        actor="test_runner"
    )
    assert reg["status"] == "success"

    # Save summary
    summary = save_summary(
        case_id=test_case_id,
        facts={"diagnosis": "Appendectomy", "date": "2026-10-20"},
        evidence={"bill": "Verified"},
        missing_info=[],
        risks=[{"type": "Prior Auth", "note": "Verified approved"}],
        policy_citations=[{"section": "Section 1.1", "title": "Inpatient Hospital Care"}],
        next_action="APPROVE",
        actor="test_runner"
    )
    assert summary["status"] == "success"

    # Verify audit timeline recorded both actions
    timeline_str = get_case_timeline_resource(test_case_id)
    timeline = json.loads(timeline_str)
    actions = [e["action"] for e in timeline]
    assert "CASE_REGISTERED" in actions
    assert "SUMMARY_SAVED" in actions

    # Verify case resource
    res_str = get_case_resource(test_case_id)
    res = json.loads(res_str)
    assert res["case"]["case_id"] == test_case_id
    assert res["summary"]["next_action"] == "APPROVE"

    # Verify prompt
    prompt = case_summary(test_case_id)
    assert test_case_id in prompt
    assert "RECOMMENDED NEXT ACTION" in prompt


# ==========================================
# 2. POLICY-MCP TESTS
# ==========================================

def test_policy_mcp_get_and_check_coverage():
    """Verify get_policy and check_coverage validation."""
    pol = get_policy("POL-UHG-001")
    assert pol["policy_number"] == "POL-UHG-001"
    assert pol["status"] == "ACTIVE"
    assert pol["deductible"] == 1000.00

    # Happy path: matching claimant and valid date
    cov = check_coverage("POL-UHG-001", "Sarah Jenkins", "2026-06-15")
    assert cov["covered"] is True
    assert cov["name_match"] is True

    # Out of policy date
    cov_expired = check_coverage("POL-UHG-001", "Sarah Jenkins", "2028-01-01")
    assert cov_expired["covered"] is False
    assert "outside policy period" in cov_expired["reason"]


def test_policy_mcp_vector_search():
    """Verify pgvector cosine similarity search identifies the correct policy clauses."""
    # Search for cosmetic exclusion
    cosmetic_results = search_policy_wording("cosmetic rhinoplasty and elective surgery", "POL-UHG-001", top_k=2)
    assert len(cosmetic_results) > 0
    top_clause = cosmetic_results[0]
    assert "Cosmetic" in top_clause["clause_title"]
    assert top_clause["section_number"] == "Section 3.1"
    assert top_clause["similarity_score"] > 0.0

    # Search for prior authorization
    pa_results = search_policy_wording("prior authorization requirement for inpatient surgery", "POL-UHG-001", top_k=2)
    assert len(pa_results) > 0
    assert any("Prior Authorization" in c["clause_title"] for c in pa_results)

    # Resources
    pol_res = json.loads(get_policy_resource("POL-UHG-001"))
    assert pol_res["policy_number"] == "POL-UHG-001"

    wording_res = json.loads(get_policy_wording_resource("Choice"))
    assert len(wording_res) >= 8


# ==========================================
# 3. DOCUMENTS-MCP TESTS
# ==========================================

def test_documents_mcp_lifecycle():
    """Verify document listing, OCR extraction, classification, injection detection, and validation."""
    # Find a clean scenario case
    clean_cases = execute_query(
        "SELECT c.case_id FROM cases c JOIN case_documents d ON c.case_id = d.case_id WHERE d.ocr_confidence >= 0.90 LIMIT 1;"
    )
    assert clean_cases, "Expected at least 1 clean case with documents"
    case_id = clean_cases[0]["case_id"]

    docs = list_documents(case_id)
    assert len(docs) >= 1
    doc_id = docs[0]["doc_id"]

    # Extract text
    text_data = extract_text(case_id, doc_id)
    assert "ocr_text" in text_data
    assert text_data["ocr_confidence"] >= 0.90

    # Classify
    classification = classify_document(case_id, doc_id)
    assert classification["doc_type"] in ["claim_form", "itemized_bill", "other"]

    # Extract fields
    extraction = extract_fields(case_id, doc_id)
    assert "extracted_fields" in extraction
    assert extraction["is_injection_flagged"] is False

    # Validation
    val = validate_case_documents(case_id)
    assert "validation_status" in val


def test_documents_mcp_injection_detection():
    """Verify that adversarial prompt injection is flagged and security alert logged."""
    inj_cases = execute_query(
        "SELECT c.case_id, d.doc_id FROM cases c JOIN case_documents d ON c.case_id = d.case_id WHERE d.is_injection_flagged = TRUE LIMIT 1;"
    )
    if inj_cases:
        case_id = inj_cases[0]["case_id"]
        doc_id = str(inj_cases[0]["doc_id"])
        
        extraction = extract_fields(case_id, doc_id)
        assert extraction["is_injection_flagged"] is True

        val = validate_case_documents(case_id)
        assert val["validation_status"] == "SECURITY_RISK"
        assert any("prompt injection" in issue.lower() for issue in val["issues"])


# ==========================================
# 4. WORKFLOW-MCP TESTS
# ==========================================

def test_workflow_mcp_workload_and_assignment():
    """Verify workload querying and adjuster assignment."""
    adjusters = get_workload("adjuster")
    assert len(adjusters) >= 3
    # Workload ordering test
    for i in range(len(adjusters) - 1):
        assert adjusters[i]["active_cases"] <= adjusters[i+1]["active_cases"]

    test_case_id = "CASE-TEST-MCP-02"
    register_case(test_case_id, "POL-UHG-001", "Workload Test Patient", 1200.00)

    # Assign to least loaded adjuster
    best_adj = adjusters[0]["staff_id"]
    assigned = assign_case(test_case_id, best_adj, "adjuster", actor="routing_agent")
    assert assigned["status"] == "success"
    assert assigned["staff_id"] == best_adj


def test_workflow_mcp_approval_limits_and_golden_rule():
    """Verify that approval requests enforce limit tiers and no approve tool exists."""
    # Check that workflow-mcp does NOT export an approve/reject tool
    from src.mcp_servers import workflow_mcp
    assert not hasattr(workflow_mcp, "approve_claim")
    assert not hasattr(workflow_mcp, "reject_claim")
    assert not hasattr(workflow_mcp, "settle_claim")

    test_case_id = "CASE-TEST-MCP-03"
    register_case(test_case_id, "POL-UHG-001", "Limit Test Patient", 8500.00)

    # APP-201 limit is $2,500. Claim is $8,500 -> Must reject with INSUFFICIENT_LIMIT
    res_low = request_approval(test_case_id, "APP-201", 8500.00)
    assert "error" in res_low
    assert res_low["error"] == "INSUFFICIENT_LIMIT"

    # APP-202 limit is $10,000. Claim is $8,500 -> Must succeed
    res_ok = request_approval(test_case_id, "APP-202", 8500.00)
    assert res_ok["status"] == "success"
    assert res_ok["case_status"] == "READY_FOR_APPROVAL"


def test_workflow_mcp_notifications_and_mailpit():
    """Verify SLA scheduling and email dispatch to Mailpit."""
    test_case_id = "CASE-TEST-MCP-04"
    register_case(test_case_id, "POL-UHG-001", "Notification Test Patient", 500.00)

    # Schedule SLA
    sla = schedule_sla(test_case_id, "Standard Claim")
    assert sla["turnaround_hours"] == 48
    assert "target_deadline" in sla

    # Send Notification via Mailpit
    notif = send_notification(
        case_id=test_case_id,
        recipient_email="claimant.test@example.com",
        subject="Status Update: Claim CASE-TEST-MCP-04",
        message="Your claim has been received and assigned to an adjuster.",
        actor="sla_agent"
    )
    assert notif["status"] in ["success", "warning"]

    # Request missing documents
    req_docs = request_documents(
        case_id=test_case_id,
        claimant_email="claimant.test@example.com",
        missing_docs=["itemized_bill", "doctor_referral"],
        actor="sla_agent"
    )
    assert req_docs["status"] == "success"
    assert req_docs["new_case_status"] == "DOCS_PENDING"

    # Resources
    staff_res = json.loads(get_staff_directory_resource())
    assert len(staff_res) >= 6

    sla_res = json.loads(get_sla_rules_resource())
    assert len(sla_res) >= 3

    # Prompts
    letter = claimant_letter(test_case_id, "Jane Doe", "Itemized hospital bill")
    assert "Jane Doe" in letter
    assert test_case_id in letter

    brief = approver_brief(test_case_id, 8500.00, "Potential cosmetic exclusion")
    assert "8,500.00" in brief
