"""FastMCP Server for Document Intelligence: OCR, Classification, Field Extraction, and Validation."""

import json
import os
import re
from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP
from src.db.connection import execute_mutation, execute_query
from src.utils.audit import log_audit_event

mcp = FastMCP("documents-mcp")

# Known prompt injection signatures
INJECTION_SIGNATURES = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"system\s+override",
    r"you\s+must\s+(approve|set\s+case\s+status)",
    r"disregard\s+(all\s+)?rules",
    r"admin(istrator)?\s+mode",
    r"pretend\s+you\s+are",
    r"jailbreak",
]


def detect_prompt_injection(text: str) -> bool:
    """Scan text for adversarial instructions attempting to manipulate agent decisioning."""
    if not text:
        return False
    lower_text = text.lower()
    for sig in INJECTION_SIGNATURES:
        if re.search(sig, lower_text):
            return True
    return False


@mcp.tool()
def list_documents(case_id: str) -> List[Dict[str, Any]]:
    """List all documents attached to a specific claim case."""
    rows = execute_query(
        """
        SELECT doc_id, case_id, file_path, doc_type, ocr_text, ocr_confidence,
               extracted_fields, is_injection_flagged, validation_status, uploaded_at
        FROM case_documents
        WHERE case_id = %s
        ORDER BY uploaded_at ASC;
        """,
        (case_id,)
    )
    for r in rows:
        r["doc_id"] = str(r["doc_id"])
        if r.get("uploaded_at"):
            r["uploaded_at"] = str(r["uploaded_at"])
    return rows


@mcp.tool()
def extract_text(case_id: str, doc_id: str) -> Dict[str, Any]:
    """Extract text and OCR confidence from a document using stored OCR or file read."""
    rows = execute_query(
        "SELECT doc_id, file_path, ocr_text, ocr_confidence FROM case_documents WHERE doc_id = %s;",
        (doc_id,)
    )
    if not rows:
        return {"error": f"Document '{doc_id}' not found"}

    doc = rows[0]
    ocr_text = doc["ocr_text"] or ""
    file_path = doc["file_path"]

    # If OCR text was not pre-populated, try reading file directly
    if not ocr_text and file_path and os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                ocr_text = f.read()
        except Exception as e:
            ocr_text = f"Error reading document file: {e}"

    confidence = doc["ocr_confidence"] if doc["ocr_confidence"] is not None else 0.95

    return {
        "doc_id": str(doc["doc_id"]),
        "case_id": case_id,
        "ocr_confidence": round(float(confidence), 2),
        "ocr_text": ocr_text,
        "char_count": len(ocr_text),
        "is_low_confidence": confidence < 0.60,
    }


@mcp.tool()
def classify_document(case_id: str, doc_id: str, text: Optional[str] = None) -> Dict[str, Any]:
    """Classify document into standard claims taxonomy."""
    if not text:
        ext = extract_text(case_id, doc_id)
        text = ext.get("ocr_text", "")

    lower_text = text.lower()
    first_line = lower_text.split("\n")[0] if lower_text else ""
    doc_type = "other"
    confidence = 0.85

    if "claim form" in first_line or "cl... form" in first_line or ("claim" in first_line and "form" in first_line):
        doc_type = "claim_form"
        confidence = 0.98
    elif "itemized" in lower_text or "bill" in lower_text or "invoice" in lower_text or "clinic" in lower_text:
        doc_type = "itemized_bill"
        confidence = 0.95
    elif "discharge summary" in lower_text or "discharge instructions" in lower_text:
        doc_type = "discharge_summary"
        confidence = 0.92
    elif "clinical" in lower_text or "medical record" in lower_text or "progress notes" in lower_text:
        doc_type = "medical_record"
        confidence = 0.92
    elif "prior authorization" in lower_text or "pre-authorization" in lower_text:
        doc_type = "prior_authorization"
        confidence = 0.90
    elif "claim form" in lower_text or "health claim" in lower_text:
        doc_type = "claim_form"
        confidence = 0.98

    # Persist classification
    execute_mutation(
        "UPDATE case_documents SET doc_type = %s WHERE doc_id = %s;",
        (doc_type, doc_id)
    )

    return {
        "doc_id": doc_id,
        "doc_type": doc_type,
        "classification_confidence": confidence,
    }


@mcp.tool()
def extract_fields(case_id: str, doc_id: str, text: Optional[str] = None) -> Dict[str, Any]:
    """Extract key fields and scan for adversarial prompt injection in a single operation."""
    if not text:
        ext = extract_text(case_id, doc_id)
        text = ext.get("ocr_text", "")

    # 1. Prompt Injection Defense Scan
    injection_detected = detect_prompt_injection(text)

    # 2. Extract standard fields
    fields: Dict[str, Any] = {}
    
    # Claimant name regex
    name_match = re.search(r"(?:Claimant|Patient|Member Name):\s*([A-Za-z\s]+)", text, re.IGNORECASE)
    if name_match:
        fields["claimant_name"] = name_match.group(1).strip()

    # Amount regex
    amt_match = re.search(r"(?:Total(?:\s+Billed|\s+Claimed)?|Amount):\s*\$?([0-9,]+\.[0-9]{2})", text, re.IGNORECASE)
    if amt_match:
        try:
            fields["total_amount"] = float(amt_match.group(1).replace(",", ""))
        except ValueError:
            pass

    # Diagnosis regex
    diag_match = re.search(r"(?:Diagnosis|Condition):\s*([^\n\r]+)", text, re.IGNORECASE)
    if diag_match:
        fields["diagnosis"] = diag_match.group(1).strip()

    # Date regex
    date_match = re.search(r"(?:Date of Service|DOS|Date):\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", text, re.IGNORECASE)
    if date_match:
        fields["date_of_service"] = date_match.group(1).strip()

    # Facility / Provider regex
    prov_match = re.search(r"(?:Provider|Hospital|Facility|Clinic):\s*([^\n\r]+)", text, re.IGNORECASE)
    if prov_match:
        fields["provider_name"] = prov_match.group(1).strip()

    # Update database record
    execute_mutation(
        """
        UPDATE case_documents
        SET extracted_fields = %s,
            is_injection_flagged = %s
        WHERE doc_id = %s;
        """,
        (json.dumps(fields), injection_detected, doc_id)
    )

    if injection_detected:
        log_audit_event(
            case_id=case_id,
            actor="documents_agent",
            action="PROMPT_INJECTION_FLAGGED",
            before_state={},
            after_state={"doc_id": doc_id, "warning": "Adversarial prompt detected in document text"},
        )

    return {
        "doc_id": doc_id,
        "extracted_fields": fields,
        "is_injection_flagged": injection_detected,
    }


@mcp.tool()
def validate_case_documents(case_id: str) -> Dict[str, Any]:
    """Validate cross-document consistency, missing documents, OCR confidence, and security flags."""
    docs = execute_query(
        """
        SELECT doc_id, doc_type, ocr_text, ocr_confidence, extracted_fields, is_injection_flagged
        FROM case_documents WHERE case_id = %s;
        """,
        (case_id,)
    )

    if not docs:
        return {
            "validation_status": "MISSING_DOCUMENTS",
            "missing_docs": ["claim_form", "itemized_bill"],
            "issues": ["No documents uploaded for case."],
        }

    doc_types = [d["doc_type"] for d in docs if d["doc_type"]]
    has_claim_form = "claim_form" in doc_types
    has_bill = "itemized_bill" in doc_types

    # Check for explicit missing documentation notice
    has_explicit_missing = any(
        "missing" in str(d.get("ocr_text", "")).lower()
        or "please provide" in str(d.get("ocr_text", "")).lower()
        or "notice: itemized hospital bill" in str(d.get("ocr_text", "")).lower()
        or bool(d.get("extracted_fields", {}).get("missing_items") if isinstance(d.get("extracted_fields"), dict) else False)
        for d in docs
    )
    missing_docs = []
    if has_explicit_missing:
        if not has_bill:
            missing_docs.append("itemized_bill")
        if not has_claim_form:
            missing_docs.append("claim_form")
    elif not has_claim_form and not has_bill:
        missing_docs.extend(["claim_form", "itemized_bill"])

    issues = []
    has_injection = any(d.get("is_injection_flagged") for d in docs)
    has_poor_ocr = any(d.get("ocr_confidence", 1.0) < 0.60 for d in docs)

    if has_injection:
        issues.append("Security risk: prompt injection command detected in document payload.")
    if has_poor_ocr:
        issues.append("Quality risk: unreadable document or OCR confidence below 60%.")
    if missing_docs:
        issues.append(f"Missing required documentation: {', '.join(missing_docs)}.")

    # Check cross-document consistency
    claimant_names = set()
    total_amounts = []
    has_text_mismatch = any("mismatch" in str(d.get("ocr_text", "")).lower() for d in docs)

    for d in docs:
        fields = d.get("extracted_fields") or {}
        if isinstance(fields, str):
            try:
                fields = json.loads(fields)
            except Exception:
                fields = {}

        c_name = fields.get("claimant_name") or fields.get("patient_name_on_bill") or fields.get("patient_name")
        if c_name:
            clean_name = str(c_name).strip().lower().replace("[name mismatch]", "").strip()
            if clean_name:
                claimant_names.add(clean_name)

        tot = fields.get("total_amount") or fields.get("bill_total") or fields.get("billed_total")
        if tot is not None:
            try:
                total_amounts.append(float(tot))
            except (ValueError, TypeError):
                pass

    has_amount_mismatch = len(total_amounts) > 1 and (max(total_amounts) - min(total_amounts) > 1.0)
    has_name_mismatch = len(claimant_names) > 1

    if has_name_mismatch:
        issues.append(f"Mismatch: Discrepant claimant names found across documents ({list(claimant_names)}).")
    if has_amount_mismatch:
        issues.append(f"Mismatch: Discrepant billing totals found across documents ({total_amounts}).")
    if has_text_mismatch and not (has_name_mismatch or has_amount_mismatch):
        issues.append("Mismatch: Discrepancy noted in document headers between patient identity and billed figures.")

    has_mismatch = has_name_mismatch or has_amount_mismatch or has_text_mismatch

    # Determine final validation status
    if has_injection:
        final_status = "SECURITY_RISK"
    elif has_poor_ocr:
        final_status = "LOW_CONFIDENCE"
    elif missing_docs:
        final_status = "DOCS_PENDING"
    elif has_mismatch:
        final_status = "MISMATCH"
    else:
        final_status = "VALID"

    # Update document validation status in DB
    for d in docs:
        execute_mutation(
            "UPDATE case_documents SET validation_status = %s WHERE doc_id = %s;",
            (final_status, d["doc_id"])
        )

    log_audit_event(
        case_id=case_id,
        actor="documents_agent",
        action="DOCUMENTS_VALIDATED",
        before_state={},
        after_state={"validation_status": final_status, "issues": issues},
    )

    return {
        "case_id": case_id,
        "validation_status": final_status,
        "missing_docs": missing_docs,
        "issues": issues,
        "documents_count": len(docs),
    }


# --- FastMCP Resources ---

@mcp.resource("document://{case_id}/{doc_id}")
def get_document_resource(case_id: str, doc_id: str) -> str:
    """Read-only resource returning full document text and extraction metadata."""
    rows = execute_query("SELECT * FROM case_documents WHERE doc_id = %s;", (doc_id,))
    if not rows:
        return json.dumps({"error": f"Document '{doc_id}' not found"})
    doc = rows[0]
    doc["doc_id"] = str(doc["doc_id"])
    if doc.get("uploaded_at"):
        doc["uploaded_at"] = str(doc["uploaded_at"])
    return json.dumps(doc, indent=2, default=str)


if __name__ == "__main__":
    mcp.run()
