"""Page 3: Deep-Dive Claims Investigation, Document Intelligence & Live Trajectory."""

import json
import uuid
import streamlit as st

st.set_page_config(page_title="Case Workspace | UHG Claims Agent", page_icon="🔍", layout="wide")

from src.db.connection import execute_query, execute_mutation
from src.ui.auth import render_auth_sidebar, get_current_user
from src.ui.components import render_status_badge, render_timeline_component, render_document_card
from src.ui.engine import get_full_case_details, get_case_checkpoint_state, resume_claim_workflow, stream_claim_workflow

render_auth_sidebar()
user = get_current_user()

st.title("🔍 Comprehensive Case Workspace")
st.caption("Deep investigation workbench: Document intelligence, prompt injection defense, policy vector citations, and audit logs.")

st.markdown("---")

# Case Selector
try:
    case_id_rows = execute_query("SELECT case_id, claimant_name, status FROM cases ORDER BY created_at DESC;")
    case_ids = [r["case_id"] for r in case_id_rows]
except Exception:
    case_ids = []

if not case_ids:
    st.warning("No cases found in database. Please submit a claim first via the Submit Claim page.")
    st.stop()

# Determine selected case
default_cid = st.session_state.get("selected_case_id", case_ids[0])
idx = case_ids.index(default_cid) if default_cid in case_ids else 0

selected_case_id = st.selectbox(
    "Select Case ID to Inspect",
    options=case_ids,
    index=idx,
    format_func=lambda cid: f"{cid} - {[r['claimant_name'] for r in case_id_rows if r['case_id'] == cid][0]} ({[r['status'] for r in case_id_rows if r['case_id'] == cid][0]})",
)
st.session_state["selected_case_id"] = selected_case_id

# Load Case Details
case_data = get_full_case_details(selected_case_id)
case = case_data.get("case", {})
docs = case_data.get("documents", [])
summary = case_data.get("summary", {})
timeline = case_data.get("timeline", [])
checkpoint = get_case_checkpoint_state(selected_case_id)

if not case:
    st.error(f"Could not load details for case {selected_case_id}")
    st.stop()

# Top Metadata Card
status = case.get("status", "UNKNOWN")
amount = float(case.get("total_amount") or 0.0)

with st.container():
    c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
    with c1:
        st.markdown(f"### Claim: `{selected_case_id}`")
        st.markdown(f"**Claimant:** {case.get('claimant_name')}")
        st.caption(f"Policy: `{case.get('policy_id')}` | Date: {str(case.get('created_at', ''))[:10]}")
    with c2:
        st.markdown("#### Billed Total")
        st.markdown(f"<span style='font-size: 1.4rem; font-weight: 700; color: #1E3A8A;'>${amount:,.2f}</span>", unsafe_allow_html=True)
    with c3:
        st.markdown("#### Status")
        st.markdown(render_status_badge(status), unsafe_allow_html=True)
    with c4:
        st.markdown("#### Staff Assignment")
        adj = case.get("adjuster_name") or case.get("assigned_adjuster_id") or "Unassigned"
        app = case.get("approver_name") or case.get("assigned_approver_id") or "Unassigned"
        st.markdown(f"Adjuster: **{adj}**  \nApprover: **{app}** (Limit: ${case.get('approver_limit', 0):,.2f})")

st.markdown("---")

# Interactive Tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "📑 Document Intelligence",
    "📝 Case Summary & Citations",
    "⚡ Agent Trajectory & Replay",
    "📜 Immutable Audit Trail",
])

# ----------------- TAB 1: DOCUMENTS -----------------
with tab1:
    st.subheader(f"Ingested Supporting Documents ({len(docs)})")

    if not docs:
        st.warning("⚠️ No documents are currently attached to this case record.")
    else:
        doc_col1, doc_col2 = st.columns([1, 1])
        for i, d in enumerate(docs):
            target_col = doc_col1 if i % 2 == 0 else doc_col2
            with target_col:
                render_document_card(d)

    # Missing Document Resumption Form (if DOCS_PENDING)
    if status == "DOCS_PENDING":
        st.markdown("---")
        st.warning("⏸️ **Execution Paused at `await_documents` Node**: The system is waiting for missing documentation from claimant.")
        
        with st.form("resume_missing_docs_form"):
            st.markdown("#### 📤 Upload Missing Document to Resume LangGraph Workflow")
            missing_type = st.selectbox(
                "Document Type to Submit",
                options=["itemized_bill", "prior_authorization", "doctor_notes", "medical_records"],
                index=0,
            )
            missing_text = st.text_area(
                "Document Text / OCR Ingestion Content",
                value=(
                    "ST. MARY GENERAL HOSPITAL - SUPPLEMENTAL ITEMIZED BILL\n"
                    f"Patient: {case.get('claimant_name')}\n"
                    f"Account Number: ACC-99214-UHG\n"
                    "Line Items:\n"
                    "- Operating Room Level 4: $1,100.00\n"
                    "- General Anesthesia: $450.00\n"
                    "- Post-Op Recovery Pharmacy: $300.00\n"
                    f"Total Invoiced: ${amount:,.2f}"
                ),
                height=140,
            )
            resume_btn = st.form_submit_button("🚀 Submit Missing Docs & Resume Execution via Command(resume=...)", type="primary")

        if resume_btn:
            new_doc = {
                "doc_id": str(uuid.uuid4()),
                "doc_type": missing_type,
                "ocr_confidence": 0.97,
                "file_path": f"data/{missing_type}_{selected_case_id}.txt",
                "ocr_text": missing_text,
            }
            with st.spinner("Resuming LangGraph execution with newly uploaded documents..."):
                try:
                    res = resume_claim_workflow(selected_case_id, {"documents": [new_doc]})
                    st.success("Claim resumed and processed through parallel Document Workers -> Summary -> Routing -> SLA!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to resume execution: {e}")

# ----------------- TAB 2: SUMMARY & CITATIONS -----------------
with tab2:
    st.subheader("Synthesis Brief & Vector Policy Citations")
    if not summary:
        st.info("No structured synthesis has been generated for this case yet.")
    else:
        scol1, scol2 = st.columns(2)
        with scol1:
            st.markdown("#### 🏥 Clinical & Billing Facts")
            st.json(summary.get("facts") or {"details": "No clinical facts recorded."})

            st.markdown("#### 🧾 Supporting Evidence")
            st.json(summary.get("evidence") or {"details": "No evidence cited."})

        with scol2:
            st.markdown("#### ⚖️ Policy Citations (pgvector Cosine Search)")
            citations = summary.get("policy_citations", [])
            if citations:
                for cit in citations:
                    st.info(f"📘 **Citation**: {cit}")
            else:
                st.caption("No specific exclusion or limit clauses cited.")

            st.markdown("#### 🚨 Identified Risks")
            risks = summary.get("risks", [])
            if risks:
                for r in risks:
                    st.error(f"⚠️ {r}")
            else:
                st.success("✅ No elevated risks detected.")

            st.markdown(f"#### 🎯 Recommended Action: `{summary.get('next_action', 'UNKNOWN')}`")

# ----------------- TAB 3: AGENT TRAJECTORY & REPLAY -----------------
with tab3:
    st.subheader("Orchestration State & Execution Trajectory")

    if checkpoint and checkpoint.get("values"):
        vals = checkpoint["values"]
        hops = vals.get("agent_hops", [])
        st.markdown("#### 📍 Chronological Agent Hops:")
        if hops:
            st.markdown(" ➡️ ".join([f"`{h}`" for h in hops]))
        else:
            st.caption("No hops recorded.")

        st.markdown(f"**Current State Next Node:** `{checkpoint.get('next')}`")

        with st.expander("Inspect Raw LangGraph Checkpoint State"):
            st.json(vals)
    else:
        st.caption("No durable checkpoint found in `PostgresSaver` for this thread ID.")

    st.markdown("---")
    st.markdown("#### 🔁 Re-run / Replay Workflow from START")
    st.caption("Re-evaluates the case through the 5-6 LLM call architecture.")

    if st.button("Run Full Workflow Replay", key="btn_replay_workflow"):
        with st.spinner("Replaying workflow through LangGraph..."):
            initial_state = {
                "case_id": selected_case_id,
                "policy_id": case.get("policy_id", "POL-UHG-001"),
                "claimant_name": case.get("claimant_name", "Sarah Jenkins"),
                "claimant_email": f"{case.get('claimant_name', 'claimant').lower().replace(' ', '.')}@example.com",
                "date_of_service": "2026-10-15",
                "total_amount": amount,
                "documents": [
                    {
                        "doc_id": d["doc_id"],
                        "doc_type": d["doc_type"],
                        "ocr_confidence": d["ocr_confidence"],
                        "ocr_text": d.get("ocr_text", ""),
                    }
                    for d in docs
                ],
                "agent_hops": [],
                "stage_results": {},
                "errors": [],
            }
            events = []
            for ev in stream_claim_workflow(initial_state, selected_case_id):
                events.append(ev.get("node"))
            st.success(f"Replay completed! Nodes traversed: {' -> '.join([str(e) for e in events])}")
            st.rerun()

# ----------------- TAB 4: AUDIT TIMELINE -----------------
with tab4:
    render_timeline_component(timeline)

