"""FastMCP Server for Case Management and Summaries."""

import json
from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP
from src.db.connection import execute_mutation, execute_query
from src.utils.audit import log_audit_event

mcp = FastMCP("case-mcp")


@mcp.tool()
def get_case(case_id: str) -> Dict[str, Any]:
    """Retrieve full details of a specific claim case by ID."""
    rows = execute_query(
        """
        SELECT case_id, policy_id, claimant_name, status, total_amount,
               assigned_adjuster_id, assigned_approver_id, human_decision,
               decision_rationale, created_at, updated_at
        FROM cases WHERE case_id = %s;
        """,
        (case_id,)
    )
    if not rows:
        return {"error": f"Case '{case_id}' not found"}
    case_data = rows[0]
    # Format timestamps
    if case_data.get("created_at"):
        case_data["created_at"] = str(case_data["created_at"])
    if case_data.get("updated_at"):
        case_data["updated_at"] = str(case_data["updated_at"])
    if case_data.get("total_amount") is not None:
        case_data["total_amount"] = float(case_data["total_amount"])
    return case_data


@mcp.tool()
def list_cases(status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """List cases filtered optionally by status."""
    if status:
        query = """
            SELECT case_id, policy_id, claimant_name, status, total_amount,
                   assigned_adjuster_id, assigned_approver_id, created_at
            FROM cases WHERE status = %s ORDER BY created_at DESC LIMIT %s;
        """
        rows = execute_query(query, (status, limit))
    else:
        query = """
            SELECT case_id, policy_id, claimant_name, status, total_amount,
                   assigned_adjuster_id, assigned_approver_id, created_at
            FROM cases ORDER BY created_at DESC LIMIT %s;
        """
        rows = execute_query(query, (limit,))

    for r in rows:
        if r.get("created_at"):
            r["created_at"] = str(r["created_at"])
        if r.get("total_amount") is not None:
            r["total_amount"] = float(r["total_amount"])
    return rows


@mcp.tool()
def find_similar_cases(claimant_name: str, total_amount: Optional[float] = None) -> List[Dict[str, Any]]:
    """Search for potentially duplicate or matching historical claims by claimant name or amount."""
    query = """
        SELECT case_id, policy_id, claimant_name, status, total_amount, human_decision, created_at
        FROM cases
        WHERE LOWER(claimant_name) = LOWER(%s)
        ORDER BY created_at DESC LIMIT 5;
    """
    rows = execute_query(query, (claimant_name,))
    results = []
    for r in rows:
        item = dict(r)
        if item.get("created_at"):
            item["created_at"] = str(item["created_at"])
        if item.get("total_amount") is not None:
            item["total_amount"] = float(item["total_amount"])
        
        # Check amount similarity
        is_exact_amount_match = False
        if total_amount is not None and item.get("total_amount") is not None:
            if abs(item["total_amount"] - total_amount) < 1.0:
                is_exact_amount_match = True
        item["duplicate_warning"] = is_exact_amount_match
        results.append(item)
    return results


@mcp.tool()
def register_case(
    case_id: str,
    policy_id: str,
    claimant_name: str,
    total_amount: float = 0.0,
    actor: str = "intake_agent",
) -> Dict[str, Any]:
    """Register or initialize a claim case and log the event in the audit trail."""
    query = """
    INSERT INTO cases (case_id, policy_id, claimant_name, status, total_amount, created_at, updated_at)
    VALUES (%s, %s, %s, 'NEW', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    ON CONFLICT (case_id) DO UPDATE SET
        policy_id = EXCLUDED.policy_id,
        claimant_name = EXCLUDED.claimant_name,
        total_amount = EXCLUDED.total_amount,
        updated_at = CURRENT_TIMESTAMP
    RETURNING case_id, policy_id, claimant_name, status, total_amount;
    """
    res = execute_mutation(query, (case_id, policy_id, claimant_name, total_amount))
    if res:
        res["total_amount"] = float(res["total_amount"])
        log_audit_event(
            case_id=case_id,
            actor=actor,
            action="CASE_REGISTERED",
            before_state={},
            after_state=res,
        )
        return {"status": "success", "case": res}
    return {"status": "error", "message": "Failed to register case"}


@mcp.tool()
def save_summary(
    case_id: str,
    facts: Dict[str, Any],
    evidence: Dict[str, Any],
    missing_info: List[str],
    risks: List[Dict[str, Any]],
    policy_citations: List[Dict[str, Any]],
    next_action: str,
    actor: str = "summary_agent",
) -> Dict[str, Any]:
    """Save structured case summary and policy citations into PostgreSQL and audit log."""
    # Fetch prior summary for audit before_state
    prior = execute_query("SELECT * FROM case_summaries WHERE case_id = %s;", (case_id,))
    before_state = prior[0] if prior else {}

    query = """
    INSERT INTO case_summaries (
        case_id, facts, evidence, missing_info, risks, policy_citations, next_action, updated_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
    ON CONFLICT (case_id) DO UPDATE SET
        facts = EXCLUDED.facts,
        evidence = EXCLUDED.evidence,
        missing_info = EXCLUDED.missing_info,
        risks = EXCLUDED.risks,
        policy_citations = EXCLUDED.policy_citations,
        next_action = EXCLUDED.next_action,
        updated_at = CURRENT_TIMESTAMP
    RETURNING summary_id, case_id, next_action;
    """
    res = execute_mutation(query, (
        case_id,
        json.dumps(facts),
        json.dumps(evidence),
        missing_info,
        json.dumps(risks),
        json.dumps(policy_citations),
        next_action,
    ))

    if res:
        res["summary_id"] = str(res["summary_id"])
        log_audit_event(
            case_id=case_id,
            actor=actor,
            action="SUMMARY_SAVED",
            before_state={"facts": before_state.get("facts")},
            after_state={"summary_id": res["summary_id"], "next_action": next_action, "risks_count": len(risks)},
        )
        return {"status": "success", "summary": res}
    return {"status": "error", "message": "Failed to save summary"}


# --- FastMCP Resources ---

@mcp.resource("case://{case_id}")
def get_case_resource(case_id: str) -> str:
    """Read-only context resource returning full case data, documents, and summary."""
    case = get_case(case_id)
    summary_rows = execute_query("SELECT * FROM case_summaries WHERE case_id = %s;", (case_id,))
    doc_rows = execute_query(
        "SELECT doc_id, doc_type, ocr_confidence, validation_status, is_injection_flagged FROM case_documents WHERE case_id = %s;",
        (case_id,)
    )
    for d in doc_rows:
        d["doc_id"] = str(d["doc_id"])

    payload = {
        "case": case,
        "summary": summary_rows[0] if summary_rows else None,
        "documents": doc_rows,
    }
    return json.dumps(payload, indent=2, default=str)


@mcp.resource("case://{case_id}/timeline")
def get_case_timeline_resource(case_id: str) -> str:
    """Read-only audit timeline of all events and actor mutations for a case."""
    rows = execute_query(
        "SELECT audit_id, actor, action, before_state, after_state, timestamp FROM case_timeline_audit WHERE case_id = %s ORDER BY timestamp ASC;",
        (case_id,)
    )
    for r in rows:
        r["timestamp"] = str(r["timestamp"])
    return json.dumps(rows, indent=2)


# --- FastMCP Prompt ---

@mcp.prompt()
def case_summary(case_id: str) -> str:
    """Prompt template for Summary Agent synthesizing structured facts, citations, and next action."""
    return f"""You are the Summary Specialist Agent for UHG Claims Case {case_id}.
Review the extracted document evidence, policy terms, and risk factors.
Produce a structured synthesis including:
1. FACTS: Key clinical/service details (dates, diagnosis, total billed vs allowed).
2. EVIDENCE: Cited source documents supporting each claimed charge.
3. MISSING INFORMATION: Any required itemized invoices, prior auth, or doctor notes absent from the file.
4. RISKS & POLICY CITATIONS: Specific policy exclusions, limits, or mismatched claimant names, citing the exact clause from policy-mcp.
5. RECOMMENDED NEXT ACTION: Recommended disposition ('APPROVE', 'REJECT', 'MANUAL_REVIEW', or 'REQUEST_DOCUMENTS').

Format your synthesis cleanly so the Human Approver can make an informed final decision in seconds."""


if __name__ == "__main__":
    mcp.run()
