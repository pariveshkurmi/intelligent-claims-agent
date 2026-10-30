"""Page 4: Dedicated Approver Portal & Golden Rule Authority Enforcement."""

import streamlit as st

st.set_page_config(page_title="Approvals Portal | UHG Claims Agent", page_icon="⚖️", layout="wide")

from src.db.connection import execute_query
from src.ui.auth import render_auth_sidebar, get_current_user, can_approve
from src.ui.components import render_status_badge
from src.ui.engine import get_full_case_details, resume_claim_workflow

render_auth_sidebar()
user = get_current_user()

st.title("⚖️ Human Approvals Portal")
st.caption(
    "Human-in-the-Loop Governance: Enforcing the Golden Rule (agents prepare, people decide, and approvers authorize only within their dollar limits)."
)

st.markdown("---")

# Active Approver Identity
st.subheader("👤 Active Approver Profile")
pcol1, pcol2, pcol3, pcol4 = st.columns(4)
with pcol1:
    st.markdown(f"**Name:** {user['name']}")
with pcol2:
    st.markdown(f"**Staff ID:** `{user['staff_id']}`")
with pcol3:
    st.markdown(f"**Role:** `{user['role'].upper()}`")
with pcol4:
    st.markdown(f"**Dollar Authority Limit:** <span style='font-weight:700; color:#1E3A8A;'>${user['approval_limit']:,.2f}</span>", unsafe_allow_html=True)

st.markdown("---")

# Query cases pending approval
try:
    pending_rows = execute_query(
        """
        SELECT c.case_id, c.claimant_name, c.policy_id, c.total_amount, c.status,
               c.assigned_approver_id, app.name as approver_name
        FROM cases c
        LEFT JOIN staff app ON c.assigned_approver_id = app.staff_id
        WHERE c.status = 'READY_FOR_APPROVAL'
        ORDER BY c.created_at DESC;
        """
    )
except Exception as e:
    st.error(f"Error querying pending approvals: {e}")
    pending_rows = []

if not pending_rows:
    st.info("🎉 No claims currently awaiting human approval. All claims are up to date!")
    st.markdown("To generate a claim awaiting approval, visit the **Submit Claim** page and run a clean claim scenario.")
    st.stop()

# Case Selection
case_options = [r["case_id"] for r in pending_rows]
default_cid = st.session_state.get("selected_approval_case_id", case_options[0])
idx = case_options.index(default_cid) if default_cid in case_options else 0

selected_case_id = st.selectbox(
    "Select Claim Case for Approval",
    options=case_options,
    index=idx,
    format_func=lambda cid: f"{cid} - {[r['claimant_name'] for r in pending_rows if r['case_id'] == cid][0]} (${float([r['total_amount'] for r in pending_rows if r['case_id'] == cid][0]):,.2f})",
)
st.session_state["selected_approval_case_id"] = selected_case_id

# Fetch Case & Summary
case_data = get_full_case_details(selected_case_id)
case = case_data.get("case", {})
summary = case_data.get("summary", {})
claim_amount = float(case.get("total_amount") or 0.0)

# Golden Rule Authority Verification
is_authorized, auth_msg = can_approve(claim_amount)

# Executive Claim Brief
st.subheader(f"📋 Executive Claim Brief: `{selected_case_id}`")

col_brief1, col_brief2 = st.columns([1, 1])

with col_brief1:
    st.markdown(f"**Claimant:** {case.get('claimant_name')}")
    st.markdown(f"**Policy:** `{case.get('policy_id')}`")
    st.markdown(f"**Total Claim Amount:** <span style='font-size: 1.3rem; font-weight: 700; color: #1E3A8A;'>${claim_amount:,.2f}</span>", unsafe_allow_html=True)
    st.markdown(f"**Assigned Approver:** `{case.get('assigned_approver_id')}` ({case.get('approver_name')})")

with col_brief2:
    st.markdown("#### 🚨 Risk Assessment & Citations")
    risks = summary.get("risks", [])
    if risks:
        for r in risks:
            st.error(f"⚠️ {r}")
    else:
        st.success("✅ No elevated risks identified by Summary Specialist.")

    citations = summary.get("policy_citations", [])
    if citations:
        st.caption("Citations:")
        for c in citations:
            st.info(f"📘 {c}")

st.markdown("---")

# Authority Limit Alert Banner
if not is_authorized:
    st.error(
        f"🚫 **GOLDEN RULE AUTHORITY BLOCK**: {auth_msg}  \n"
        f"You do not possess the required dollar limit to approve this claim.  \n"
        f"**Action Required**: Switch personas in the sidebar to a higher-tier approver (e.g. Tier 2 Claire Bennett or Tier 3 David Sterling)."
    )
else:
    st.success(f"✅ **GOLDEN RULE VERIFIED**: {auth_msg}")

# Approver Decision Form
st.subheader("✍️ Approver Sign-off & Final Disposition")

with st.form("approver_decision_form"):
    decision = st.radio(
        "Select Final Disposition",
        options=["APPROVED", "REJECTED", "INFO_REQUESTED"],
        index=0,
        help="Select decision to dispatch into LangGraph HITL interrupt resumption.",
    )

    rationale = st.text_area(
        "Decision Rationale (Mandatory for Compliance & Audit)",
        value="Medical necessity verified against policy inpatient surgical benefits. Charges adhere to allowed fee schedule.",
        height=100,
    )

    submit_disabled = (not is_authorized and decision == "APPROVED")

    submitted = st.form_submit_button(
        "🚀 Authorize & Resume LangGraph Workflow via Command(resume=...)",
        type="primary",
        disabled=submit_disabled,
        use_container_width=True,
    )

if submitted:
    if not rationale.strip():
        st.error("Please provide a decision rationale before authorizing.")
    else:
        with st.spinner("Resuming LangGraph execution to finalize claim and notify claimant..."):
            resume_payload = {
                "decision": decision,
                "rationale": rationale,
                "approver_id": user["staff_id"],
            }
            try:
                res = resume_claim_workflow(selected_case_id, resume_payload)
                st.balloons()
                st.success(
                    f"🎉 **Claim Finalized Successfully!**  \n"
                    f"Disposition: **{decision}**  \n"
                    f"Authorized By: **{user['name']} ({user['staff_id']})**  \n"
                    f"Notice email dispatched to claimant via Mailpit (http://localhost:8025)."
                )
                if st.button("Inspect Finalized Case Record"):
                    st.session_state["selected_case_id"] = selected_case_id
                    st.switch_page("pages/3_Case_Workspace.py")
            except Exception as e:
                st.error(f"Error finalizing claim: {e}")

