"""Reusable UI Components and Visual Styling for Streamlit Claims Workspace."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import streamlit as st


STATUS_COLORS = {
    "INTAKE_PENDING": ("#6B7280", "Intake Pending"),
    "COVERAGE_VERIFIED": ("#3B82F6", "Coverage Verified"),
    "DOCS_PENDING": ("#F59E0B", "Awaiting Documents"),
    "DOCS_UPLOADED": ("#8B5CF6", "Documents Uploaded"),
    "SUMMARY_GENERATED": ("#6366F1", "Summary Generated"),
    "ROUTED_FOR_APPROVAL": ("#06B6D4", "Routed for Approval"),
    "READY_FOR_APPROVAL": ("#EAB308", "Ready for Approval"),
    "AWAITING_HUMAN_DECISION": ("#F97316", "Awaiting Approver"),
    "APPROVED": ("#10B981", "Approved"),
    "REJECTED": ("#EF4444", "Rejected"),
    "MANUAL_REVIEW": ("#DC2626", "Escalated to Manual Review"),
    "OUT_OF_POLICY": ("#991B1B", "Out of Policy"),
    "DUPLICATE_FLAGGED": ("#B45309", "Duplicate Flagged"),
}


def render_status_badge(status: str) -> str:
    """Return HTML formatted badge for a case status."""
    color, label = STATUS_COLORS.get(status, ("#4B5563", status))
    return (
        f'<span style="background-color: {color}; color: white; padding: 4px 10px; '
        f'border-radius: 9999px; font-size: 0.82rem; font-weight: 600; text-transform: uppercase;">'
        f'{label}</span>'
    )


def load_seed_pack_manifest() -> List[Dict[str, Any]]:
    """Load the manifest of 30 test scenarios."""
    manifest_path = Path("data/seed_packs/manifest.json")
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def load_seed_pack_by_id(case_id: str) -> Optional[Dict[str, Any]]:
    """Load a specific scenario pack JSON."""
    file_path = Path(f"data/seed_packs/{case_id}.json")
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def render_timeline_component(timeline_events: List[Dict[str, Any]]):
    """Render the append-only audit trail in a structured visual timeline."""
    if not timeline_events:
        st.info("No audit events recorded for this case yet.")
        return

    st.markdown("#### 📜 Chronological Audit Trail (Immutable)")
    for i, event in enumerate(reversed(timeline_events)):
        actor = event.get("actor", "system")
        action = event.get("action", "UNKNOWN")
        ts = event.get("timestamp", "")
        before = event.get("before_state")
        after = event.get("after_state")

        badge_color = (
            "🟢" if "APPROVE" in action or "VERIFIED" in action
            else "🔴" if "REJECT" in action or "ESCALAT" in action or "MANUAL" in action
            else "🟡" if "PENDING" in action or "PAUSE" in action
            else "🔵"
        )

        with st.expander(f"{badge_color} **{action}** by `{actor}` — {ts}", expanded=(i == 0)):
            col1, col2 = st.columns(2)
            with col1:
                st.caption("State Before:")
                st.json(before if before else {"state": "initial"})
            with col2:
                st.caption("State After:")
                st.json(after if after else {"state": "updated"})


def render_document_card(doc: Dict[str, Any]):
    """Render a single document preview card with OCR confidence & security indicators."""
    doc_type = doc.get("doc_type", "document").replace("_", " ").title()
    conf = float(doc.get("ocr_confidence", 0.0))
    is_injection = doc.get("is_injection_flagged", False)
    val_status = doc.get("validation_status", "PENDING")

    # Determine confidence badge color
    conf_color = "green" if conf >= 0.85 else "orange" if conf >= 0.70 else "red"

    st.markdown(
        f"""
        <div style="border: 1px solid #E5E7EB; border-radius: 8px; padding: 12px; margin-bottom: 12px; background: #FFFFFF;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 700; font-size: 1rem; color: #111827;">📄 {doc_type}</span>
                <span style="color: {conf_color}; font-weight: 600; font-size: 0.85rem;">OCR Conf: {conf * 100:.1f}%</span>
            </div>
            <div style="margin-top: 6px; font-size: 0.82rem; color: #6B7280;">
                ID: <code>{doc.get('doc_id', '')[:8]}...</code> | Status: <b>{val_status}</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if is_injection:
        st.error("🚨 **Prompt Injection Defense Triggered**: Suspicious prompt instruction was detected and safely quarantined.")

    if conf < 0.75:
        st.warning(f"⚠️ **Low OCR Confidence ({conf * 100:.1f}%)**: Scan quality degraded; escalated to human review.")

    with st.expander(f"View Raw Text ({doc_type})"):
        st.text(doc.get("ocr_text", "No raw text available"))
        if doc.get("extracted_fields"):
            st.caption("Extracted Structured Fields:")
            st.json(doc["extracted_fields"])

