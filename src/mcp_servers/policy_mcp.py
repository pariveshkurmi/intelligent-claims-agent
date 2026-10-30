"""FastMCP Server for Policy Management and Semantic Clause Search with pgvector."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP
from src.db.connection import execute_query
from src.utils.embeddings import get_embedding

mcp = FastMCP("policy-mcp")


@mcp.tool()
def get_policy(policy_number: str) -> Dict[str, Any]:
    """Retrieve full terms, deductibles, and active status for a specific policy number."""
    rows = execute_query(
        """
        SELECT policy_number, product_name, policyholder_name, effective_date,
               expiry_date, deductible, out_of_pocket_max, co_insurance_rate, status
        FROM policies WHERE policy_number = %s;
        """,
        (policy_number,)
    )
    if not rows:
        return {"error": f"Policy '{policy_number}' not found"}
    pol = rows[0]
    pol["effective_date"] = str(pol["effective_date"])
    pol["expiry_date"] = str(pol["expiry_date"])
    pol["deductible"] = float(pol["deductible"])
    pol["out_of_pocket_max"] = float(pol["out_of_pocket_max"])
    pol["co_insurance_rate"] = float(pol["co_insurance_rate"])
    return pol


@mcp.tool()
def check_coverage(policy_number: str, claimant_name: str, date_of_service: str) -> Dict[str, Any]:
    """Verify if a claimant is covered under the policy on the specified service date."""
    pol = get_policy(policy_number)
    if "error" in pol:
        return {"covered": False, "reason": pol["error"]}

    if pol["status"] != "ACTIVE":
        return {"covered": False, "reason": f"Policy status is {pol['status']}, not ACTIVE."}

    # Verify name matching
    policyholder = pol["policyholder_name"].strip().lower()
    claimant = claimant_name.strip().lower()
    name_matched = (policyholder == claimant) or (claimant in policyholder)

    # Verify service date within coverage window
    try:
        dos = datetime.strptime(date_of_service, "%Y-%m-%d").date()
        eff = datetime.strptime(pol["effective_date"], "%Y-%m-%d").date()
        exp = datetime.strptime(pol["expiry_date"], "%Y-%m-%d").date()
        date_valid = (eff <= dos <= exp)
    except Exception as e:
        return {"covered": False, "reason": f"Invalid date_of_service format: {e}"}

    if not date_valid:
        return {
            "covered": False,
            "reason": f"Date of service {dos} is outside policy period ({eff} to {exp})."
        }

    return {
        "covered": True,
        "policy_number": policy_number,
        "product_name": pol["product_name"],
        "policyholder_name": pol["policyholder_name"],
        "name_match": name_matched,
        "warning": None if name_matched else f"Claimant '{claimant_name}' differs from policyholder '{pol['policyholder_name']}'",
        "deductible": pol["deductible"],
        "co_insurance_rate": pol["co_insurance_rate"],
    }


@mcp.tool()
def search_policy_wording(
    query: str,
    policy_number: Optional[str] = "POL-UHG-001",
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """Perform pgvector cosine similarity search across policy clauses to cite relevant wording."""
    query_vec = get_embedding(query)
    
    # Cosine distance operator is <=>
    if policy_number:
        sql = """
            SELECT clause_id, policy_number, section_number, clause_title, clause_text,
                   1 - (embedding <=> %s::vector) AS similarity_score
            FROM policy_clauses
            WHERE policy_number = %s
            ORDER BY embedding <=> %s::vector ASC
            LIMIT %s;
        """
        rows = execute_query(sql, (query_vec, policy_number, query_vec, top_k))
    else:
        sql = """
            SELECT clause_id, policy_number, section_number, clause_title, clause_text,
                   1 - (embedding <=> %s::vector) AS similarity_score
            FROM policy_clauses
            ORDER BY embedding <=> %s::vector ASC
            LIMIT %s;
        """
        rows = execute_query(sql, (query_vec, query_vec, top_k))
    
    results = []
    for r in rows:
        results.append({
            "clause_id": str(r["clause_id"]),
            "policy_number": r["policy_number"],
            "section_number": r["section_number"],
            "clause_title": r["clause_title"],
            "clause_text": r["clause_text"],
            "similarity_score": round(float(r["similarity_score"]), 4),
        })
    return results


# --- FastMCP Resources ---

@mcp.resource("policy://{policy_number}")
def get_policy_resource(policy_number: str) -> str:
    """Read-only resource returning policy terms and limits."""
    pol = get_policy(policy_number)
    return json.dumps(pol, indent=2)


@mcp.resource("policy-wording://{product}")
def get_policy_wording_resource(product: str) -> str:
    """Read-only resource returning all clauses for a product."""
    rows = execute_query(
        """
        SELECT pc.section_number, pc.clause_title, pc.clause_text
        FROM policy_clauses pc
        JOIN policies p ON pc.policy_number = p.policy_number
        WHERE LOWER(p.product_name) LIKE LOWER(%s)
        ORDER BY pc.section_number ASC;
        """,
        (f"%{product}%",)
    )
    return json.dumps(rows, indent=2)


if __name__ == "__main__":
    mcp.run()
