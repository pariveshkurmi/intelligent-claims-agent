"""Page 1: Digital Intake, Document Drag-and-Drop, and Live Graph Streaming."""

import json
import time
import uuid
import streamlit as st

st.set_page_config(page_title="Submit Claim | UHG Claims Agent", page_icon="📥", layout="wide")

from src.db.connection import execute_query
from src.ui.auth import render_auth_sidebar
from src.ui.components import load_seed_pack_manifest, load_seed_pack_by_id, render_status_badge
from src.ui.engine import stream_claim_workflow

render_auth_sidebar()

st.title("📥 Digital Claim Intake & Multi-Agent Execution")
st.caption("Register new claims, ingest supporting documents, and trigger real-time LangGraph orchestration.")

st.markdown("---")

# Quick Scenario Pack Loader
manifest = load_seed_pack_manifest()
scenario_options = ["-- Select Scenario Preset (Optional) --"] + [
    f"{p['case_id']} - {p['scenario'].replace('_', ' ').title()} (${p['total_amount']:,.2f})"
    for p in manifest
]

col_scen, col_load, col_reset, col_clear = st.columns([3, 1, 1, 1])
with col_scen:
    selected_preset = st.selectbox(
        "⚡ Quick Test: Load from Golden Dataset (30 Scenarios)",
        options=scenario_options,
        index=0,
        help="Instantly load pre-configured test scenarios (Clean, Poor Scan, Missing Docs, Prompt Injection, Out-of-Policy, Duplicate).",
    )

if "form_data" not in st.session_state:
    fresh_cid = f"CASE-{uuid.uuid4().hex[:6].upper()}"
    st.session_state["form_data"] = {
        "case_id": fresh_cid,
        "policy_id": "POL-UHG-001",
        "claimant_name": "Sarah Jenkins",
        "claimant_email": "sarah.jenkins@example.com",
        "date_of_service": "2026-10-15",
        "total_amount": 1850.00,
        "documents": [
            {
                "doc_id": str(uuid.uuid4()),
                "doc_type": "claim_form",
                "ocr_confidence": 0.98,
                "file_path": "data/claim_form.txt",
                "ocr_text": "UNITEDHEALTHCARE HEALTH CLAIM FORM\nClaimant: Sarah Jenkins\nPolicy: POL-UHG-001\nDiagnosis: Acute Appendectomy\nClaimed: $1850.00\nProvider: St. Mary General Hospital",
            },
            {
                "doc_id": str(uuid.uuid4()),
                "doc_type": "itemized_bill",
                "ocr_confidence": 0.96,
                "file_path": "data/itemized_bill.txt",
                "ocr_text": "ST. MARY GENERAL HOSPITAL - ITEMIZED BILL\nPatient: Sarah Jenkins\nTotal Billed: $1850.00\nLine Items:\n- Operating Room: $1100.00\n- Anesthesia: $450.00\n- Pharmacy: $300.00",
            },
        ],
    }

with col_load:
    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    if st.button("Load Preset", use_container_width=True):
        if selected_preset != scenario_options[0]:
            cid = selected_preset.split(" - ")[0]
            pack = load_seed_pack_by_id(cid)
            if pack:
                st.session_state["form_data"] = {
                    "case_id": pack["case_id"],
                    "policy_id": pack["policy_id"],
                    "claimant_name": pack["claimant_name"],
                    "claimant_email": f"{pack['claimant_name'].lower().replace(' ', '.')}@example.com",
                    "date_of_service": "2026-10-15",
                    "total_amount": float(pack["total_amount"]),
                    "documents": pack.get("documents", []),
                    "notes": pack.get("notes", ""),
                    "scenario": pack.get("scenario", ""),
                }
                st.success(f"Loaded scenario '{pack.get('scenario')}' for {cid}!")
                st.rerun()

with col_reset:
    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    if st.button("➕ Sample Claim", use_container_width=True, help="Reset form with standard sample claim template"):
        fresh_cid = f"CASE-{uuid.uuid4().hex[:6].upper()}"
        st.session_state["form_data"] = {
            "case_id": fresh_cid,
            "policy_id": "POL-UHG-001",
            "claimant_name": "Sarah Jenkins",
            "claimant_email": "sarah.jenkins@example.com",
            "date_of_service": "2026-10-15",
            "total_amount": 1500.00,
            "documents": [
                {
                    "doc_id": str(uuid.uuid4()),
                    "doc_type": "claim_form",
                    "ocr_confidence": 0.98,
                    "file_path": f"data/{fresh_cid}_claim_form.txt",
                    "ocr_text": f"UNITEDHEALTHCARE HEALTH CLAIM FORM\nClaimant: Sarah Jenkins\nPolicy: POL-UHG-001\nDiagnosis: Outpatient Evaluation & Treatment\nClaimed: $1500.00\nProvider: City Medical Center",
                },
                {
                    "doc_id": str(uuid.uuid4()),
                    "doc_type": "itemized_bill",
                    "ocr_confidence": 0.96,
                    "file_path": f"data/{fresh_cid}_itemized_bill.txt",
                    "ocr_text": f"CITY MEDICAL CENTER - ITEMIZED BILL\nPatient: Sarah Jenkins\nTotal Billed: $1500.00\nLine Items:\n- Consultation: $300.00\n- Diagnostic Tests: $700.00\n- Medications: $500.00",
                },
            ],
        }
        st.success(f"Initialized fresh claim template ({fresh_cid})!")
        st.rerun()

with col_clear:
    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    if st.button("🗑️ Blank Canvas", use_container_width=True, help="Clear all preloaded documents so you can paste fresh test data or upload .txt files"):
        fresh_cid = f"CASE-{uuid.uuid4().hex[:6].upper()}"
        st.session_state["form_data"] = {
            "case_id": fresh_cid,
            "policy_id": "POL-UHG-001",
            "claimant_name": "",
            "claimant_email": "",
            "date_of_service": "2026-10-15",
            "total_amount": 0.0,
            "documents": [],
        }
        st.success("Cleared all preloaded documents! Ready for fresh test data paste or drag-and-drop upload.")
        st.rerun()

st.markdown("### 📋 Claim Information")

with st.form("claim_intake_form"):
    col1, col2 = st.columns(2)
    with col1:
        case_id = st.text_input("Case ID", value=st.session_state["form_data"]["case_id"])
        claimant_name = st.text_input("Claimant Full Name", value=st.session_state["form_data"]["claimant_name"])
        claimant_email = st.text_input("Claimant Email", value=st.session_state["form_data"].get("claimant_email", "claimant@example.com"))

    with col2:
        # Load available policies from DB
        try:
            pol_rows = execute_query("SELECT policy_number, product_name, policyholder_name FROM policies;")
            pol_options = [r["policy_number"] for r in pol_rows] if pol_rows else ["POL-UHG-001"]
        except Exception:
            pol_options = ["POL-UHG-001", "POL-UHG-002", "POL-UHG-003"]

        cur_pol = st.session_state["form_data"].get("policy_id", "POL-UHG-001")
        pol_idx = pol_options.index(cur_pol) if cur_pol in pol_options else 0
        policy_id = st.selectbox("Policy ID", options=pol_options, index=pol_idx)

        date_of_service = st.text_input("Date of Service (YYYY-MM-DD)", value=st.session_state["form_data"]["date_of_service"])
        total_amount = st.number_input(
            "Total Claimed Amount ($)",
            min_value=0.0,
            value=float(st.session_state["form_data"]["total_amount"]),
            step=50.0,
        )

    st.markdown("### 📑 Supporting Claim Documents")
    st.caption("Documents loaded for ingestion into FastMCP `documents-mcp`:")

    cur_docs = st.session_state["form_data"].get("documents", [])
    if cur_docs:
        for idx, doc in enumerate(cur_docs):
            with st.expander(f"Document {idx + 1}: {doc.get('doc_type', 'Document').replace('_', ' ').title()} (OCR Conf: {float(doc.get('ocr_confidence', 0.95)) * 100:.1f}%)"):
                st.text_area(f"Doc {idx + 1} OCR Text", value=doc.get("ocr_text", ""), height=100, key=f"doc_text_{idx}")
    else:
        st.warning("No documents attached to this claim. (Will trigger MISSING_DOCUMENTS scenario).")

    # Document upload
    uploaded_files = st.file_uploader(
        "Add / Upload Supporting Documents (.txt, .pdf, or images)",
        accept_multiple_files=True,
    )
    replace_with_uploaded = True
    if uploaded_files:
        st.info(f"{len(uploaded_files)} file(s) queued for ingestion.")
        if cur_docs:
            replace_with_uploaded = st.checkbox(
                "Use uploaded files only (ignore preloaded template documents)",
                value=True,
                help="When checked, only your newly uploaded files will be sent to the agents, ignoring default sample documents."
            )

    submitted = st.form_submit_button("🚀 Submit Claim & Launch Agent Workflow", use_container_width=True, type="primary")

# Execution Streaming Box
if submitted:
    st.markdown("---")
    st.subheader(f"⚡ Live Orchestration Progress: `{case_id}`")
    progress_bar = st.progress(0, text="Initializing LangGraph execution...")
    status_container = st.container()

    # Collect updated OCR text from the UI text areas (unless user wants uploaded files only)
    final_docs = []
    if not (uploaded_files and replace_with_uploaded):
        for idx, doc in enumerate(cur_docs):
            doc_copy = dict(doc)
            edited_text = st.session_state.get(f"doc_text_{idx}")
            if edited_text is not None and edited_text.strip():
                doc_copy["ocr_text"] = edited_text
            final_docs.append(doc_copy)

    # Process any newly uploaded files
    if uploaded_files:
        for uf in uploaded_files:
            try:
                content = uf.read().decode("utf-8", errors="ignore")
            except Exception:
                content = f"Uploaded binary document: {uf.name}"

            # Auto-detect OCR confidence & injection flags from file metadata and content
            ocr_conf = 0.95
            if any(k in uf.name.lower() for k in ("poor", "scan", "blur", "damaged")):
                ocr_conf = 0.42
            elif "[ocr confidence:" in content.lower():
                import re
                m = re.search(r"\[ocr confidence:\s*([0-9.]+)", content, re.IGNORECASE)
                if m:
                    try:
                        ocr_conf = float(m.group(1))
                    except ValueError:
                        pass

            is_inj = any(k in content.lower() for k in (
                "system override instruction",
                "ignore all previous policy rules",
                "attention ai agent",
                "set total amount to"
            ))

            final_docs.append({
                "doc_id": str(uuid.uuid4()),
                "doc_type": "itemized_bill" if "bill" in uf.name.lower() else "claim_form",
                "ocr_confidence": ocr_conf,
                "file_path": f"data/{case_id}_{uf.name}",
                "ocr_text": content,
                "is_injection_flagged": is_inj,
            })

    initial_state = {
        "case_id": case_id,
        "policy_id": policy_id,
        "claimant_name": claimant_name,
        "claimant_email": claimant_email,
        "date_of_service": str(date_of_service),
        "total_amount": float(total_amount),
        "documents": final_docs,
        "agent_hops": [],
        "stage_results": {},
        "errors": [],
    }

    step_weights = {
        "intake_agent": 20,
        "document_worker": 40,
        "document_join": 55,
        "summary_agent": 75,
        "routing_agent": 88,
        "sla_agent": 95,
        "human_review": 100,
        "await_documents": 100,
        "manual_review": 100,
        "finalize": 100,
    }

    try:
        current_progress = 10
        interrupt_info = None

        with status_container:
            for event in stream_claim_workflow(initial_state, case_id):
                node_name = event.get("node", "step")
                is_interrupt = event.get("is_interrupt", False)

                if is_interrupt:
                    interrupt_info = event.get("interrupt_data", {})
                    break

                prog = step_weights.get(node_name, current_progress + 10)
                current_progress = min(max(current_progress, prog), 98)
                progress_bar.progress(current_progress, text=f"Active Specialist: {node_name.replace('_', ' ').title()}...")

                # Display Node Update Card
                if node_name == "intake_agent":
                    st.success("✅ **Intake Agent**: Policy coverage validated & duplicate scan completed.")
                elif node_name == "document_worker":
                    st.info("📄 **Document Worker**: Parallel extraction executed with structured Pydantic schema.")
                elif node_name == "document_join":
                    st.info("🔗 **Document Join**: Aggregated multi-document validation and security check.")
                elif node_name == "summary_agent":
                    st.success("📝 **Summary Agent**: Synthesized clinical facts, missing info, and pgvector policy citations.")
                elif node_name == "routing_agent":
                    st.info("🎯 **Routing Agent**: Inspected adjuster workload and assigned approver tier.")
                elif node_name == "sla_agent":
                    st.success("⏰ **SLA Agent**: SLA deadline registered and notification sent via Mailpit.")

        # Post-Execution Disposition
        if interrupt_info:
            status = interrupt_info.get("status", "")
            if status == "AWAITING_HUMAN_DECISION":
                progress_bar.progress(100, text="Awaiting Human Decision (Paused at human_review)")
                st.warning(
                    f"⏸️ **HITL Pause (Golden Rule)**: Claim requires authorization from assigned approver `{interrupt_info.get('assigned_approver_id')}`."
                )
                st.info(f"Prompt: {interrupt_info.get('prompt')}")
                if st.button("👉 Proceed to Approvals Portal to Review and Authorize", type="primary", use_container_width=True):
                    st.session_state["selected_approval_case_id"] = case_id
                    st.switch_page("pages/4_Approvals.py")
            elif status == "DOCS_PENDING":
                progress_bar.progress(100, text="Awaiting Documents (Paused at await_documents)")
                st.warning(f"⏸️ **Missing Documents Pause**: Missing {interrupt_info.get('missing_docs')}. Claimant notified via Mailpit.")
                if st.button("👉 Open in Workspace to Upload Missing Documents", type="primary", use_container_width=True):
                    st.session_state["selected_case_id"] = case_id
                    st.switch_page("pages/3_Case_Workspace.py")
        else:
            progress_bar.progress(100, text="Workflow Complete")
            st.success(f"Claim `{case_id}` completed its pipeline trajectory!")
            if st.button("🔍 Open in Case Workspace", use_container_width=True):
                st.session_state["selected_case_id"] = case_id
                st.switch_page("pages/3_Case_Workspace.py")

    except Exception as e:
        progress_bar.progress(100, text="Execution Paused or Halted")
        st.error(f"Execution notice / error: {e}")
        st.info("Check Phoenix traces (http://localhost:6006) for deep telemetry.")

