"""Ingestion pipeline for insurance policies and semantic clause chunking into pgvector."""

import os
import sys
import uuid
from typing import Any, Dict, List

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
from src.db.connection import execute_mutation, execute_query, get_db_cursor
from src.utils.embeddings import get_embedding

TARGET_POLICY = {
    "policy_number": "POL-UHG-001",
    "product_name": "UHG Choice Plus PPO",
    "policyholder_name": "Sarah Jenkins",
    "effective_date": "2026-01-01",
    "expiry_date": "2026-12-31",
    "deductible": 1000.00,
    "out_of_pocket_max": 5000.00,
    "co_insurance_rate": 0.20,
    "status": "ACTIVE",
}

POLICY_CLAUSES = [
    {
        "section_number": "Section 1.1",
        "clause_title": "Inpatient Hospital Care and Room Coverage",
        "clause_text": (
            "Coverage is provided for medically necessary inpatient hospital services including "
            "semi-private room, board, general nursing services, operating room, and medical supplies. "
            "Inpatient hospital services require prior authorization at least 48 hours prior to non-emergency admission, "
            "or within 24 hours following emergency admission. Covered at 80% after deductible."
        ),
    },
    {
        "section_number": "Section 1.2",
        "clause_title": "Emergency Room Services & Urgent Medical Care",
        "clause_text": (
            "Emergency room services are covered 24/7 without prior authorization for acute conditions "
            "where delay would jeopardize the claimant's life or health. Emergency admissions must be reported "
            "to the plan within 24 hours of admission or as soon as medically practical. Deductible waived if admitted."
        ),
    },
    {
        "section_number": "Section 2.1",
        "clause_title": "Mandatory Prior Authorization for Elective and High-Cost Care",
        "clause_text": (
            "Prior authorization is strictly required for all elective surgical admissions, advanced radiology "
            "(MRI, CT, PET scans), inpatient hospital stays, and specialty pharmaceuticals exceeding $1,000. "
            "Failure to obtain prior authorization prior to receiving non-emergency care results in a 50% benefit reduction "
            "or total denial of claim reimbursement."
        ),
    },
    {
        "section_number": "Section 3.1",
        "clause_title": "General Exclusion: Cosmetic and Aesthetic Surgery",
        "clause_text": (
            "Services, procedures, surgeries, and related medical supplies performed primarily to reshape "
            "normal structures of the body in order to improve appearance or self-esteem (cosmetic surgery) are strictly "
            "excluded from coverage. This exclusion includes rhinoplasty, elective blepharoplasty, liposuction, and breast "
            "augmentation, unless directly reconstructing a bodily defect resulting from accidental injury or mastectomy."
        ),
    },
    {
        "section_number": "Section 3.2",
        "clause_title": "General Exclusion: Experimental, Unproven, and Investigational Treatments",
        "clause_text": (
            "Any medical intervention, procedure, device, drug, or clinical therapy that is not FDA approved "
            "for the specific indicated condition or is not established in peer-reviewed clinical guidelines is deemed "
            "experimental/investigational and is expressly excluded from coverage under this policy."
        ),
    },
    {
        "section_number": "Section 4.1",
        "clause_title": "Benefit Limits and Annual Maximum Allowances",
        "clause_text": (
            "The annual maximum out-of-pocket limit for an individual covered under this policy is $5,000 per calendar year. "
            "Once met, eligible in-network medical services are reimbursed at 100%. Physical therapy is capped at 30 visits "
            "per calendar year. Chiropractic care is capped at 20 visits per calendar year."
        ),
    },
    {
        "section_number": "Section 5.1",
        "clause_title": "Claim Filing Timelines, Proof of Loss, and Appeals",
        "clause_text": (
            "Claims for reimbursement must be submitted within 90 days of the date of service, accompanied by itemized bills, "
            "proof of payment, and supporting medical records. Incomplete claims will be paused for up to 7 business days "
            "pending receipt of required documentation. Appeals must be filed in writing within 180 days of claim determination."
        ),
    },
    {
        "section_number": "Section 6.1",
        "clause_title": "Coordination of Benefits and Duplicate Submissions",
        "clause_text": (
            "Claims submitted for services already reimbursed under this or another primary policy will be denied as duplicate. "
            "When two or more health benefit plans cover the claimant, coordination of benefits rules determine primary and "
            "secondary payer liabilities to prevent duplicate payout."
        ),
    },
]


def ingest_target_policy(policy_data: Dict[str, Any] = TARGET_POLICY, clauses: List[Dict[str, Any]] = POLICY_CLAUSES) -> None:
    """Ingest master policy and compute clause embeddings into policy_clauses table."""
    print(f"Ingesting policy {policy_data['policy_number']}: {policy_data['product_name']}...")
    
    # 1. Upsert Policy Record
    policy_upsert_query = """
    INSERT INTO policies (
        policy_number, product_name, policyholder_name, effective_date, expiry_date,
        deductible, out_of_pocket_max, co_insurance_rate, status
    ) VALUES (
        %(policy_number)s, %(product_name)s, %(policyholder_name)s, %(effective_date)s, %(expiry_date)s,
        %(deductible)s, %(out_of_pocket_max)s, %(co_insurance_rate)s, %(status)s
    )
    ON CONFLICT (policy_number) DO UPDATE SET
        product_name = EXCLUDED.product_name,
        policyholder_name = EXCLUDED.policyholder_name,
        effective_date = EXCLUDED.effective_date,
        expiry_date = EXCLUDED.expiry_date,
        deductible = EXCLUDED.deductible,
        out_of_pocket_max = EXCLUDED.out_of_pocket_max,
        co_insurance_rate = EXCLUDED.co_insurance_rate,
        status = EXCLUDED.status;
    """
    execute_mutation(policy_upsert_query, policy_data)
    
    # 2. Delete old clauses for clean re-ingestion
    execute_mutation(
        "DELETE FROM policy_clauses WHERE policy_number = %(policy_number)s",
        {"policy_number": policy_data["policy_number"]}
    )

    # 3. Compute Embeddings and Insert Clauses
    clause_insert_query = """
    INSERT INTO policy_clauses (
        clause_id, policy_number, section_number, clause_title, clause_text, embedding
    ) VALUES (
        %(clause_id)s, %(policy_number)s, %(section_number)s, %(clause_title)s, %(clause_text)s, %(embedding)s
    );
    """
    
    with get_db_cursor(commit=True) as cur:
        for clause in clauses:
            # Embed clause title + text together for maximum semantic context
            embed_text = f"{clause['clause_title']}\n{clause['clause_text']}"
            embedding_vec = get_embedding(embed_text)
            
            clause_id = str(uuid.uuid4())
            cur.execute(clause_insert_query, {
                "clause_id": clause_id,
                "policy_number": policy_data["policy_number"],
                "section_number": clause["section_number"],
                "clause_title": clause["clause_title"],
                "clause_text": clause["clause_text"],
                "embedding": embedding_vec,
            })
            print(f"  ✓ Ingested clause [{clause['section_number']}] {clause['clause_title']}")

    print(f"Successfully ingested {len(clauses)} clauses for policy {policy_data['policy_number']}.\n")


if __name__ == "__main__":
    ingest_target_policy()
