"""Page 2: Live Claims Queue & Workload Monitoring."""

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Case Queue | UHG Claims Agent", page_icon="📋", layout="wide")

from src.db.connection import execute_query
from src.ui.auth import render_auth_sidebar, get_current_user
from src.ui.components import render_status_badge

render_auth_sidebar()
user = get_current_user()

st.title("📋 Live Claims Queue & Workload Management")
st.caption("Real-time view of active claims, status lifecycle, assignments, and SLA turnaround.")

st.markdown("---")

# Query all cases with joins
query = """
    SELECT c.case_id, c.policy_id, c.claimant_name, c.total_amount, c.status,
           c.assigned_adjuster_id, c.assigned_approver_id, c.human_decision,
           c.created_at, c.updated_at,
           adj.name as adjuster_name,
           app.name as approver_name, app.approval_limit as approver_limit
    FROM cases c
    LEFT JOIN staff adj ON c.assigned_adjuster_id = adj.staff_id
    LEFT JOIN staff app ON c.assigned_approver_id = app.staff_id
    ORDER BY c.created_at DESC;
"""

try:
    all_cases = execute_query(query)
except Exception as e:
    st.error(f"Failed to query cases: {e}")
    all_cases = []

# Top KPI Filters
total_count = len(all_cases)
ready_count = sum(1 for c in all_cases if c["status"] == "READY_FOR_APPROVAL")
pending_docs_count = sum(1 for c in all_cases if c["status"] == "DOCS_PENDING")
manual_count = sum(1 for c in all_cases if c["status"] in ("MANUAL_REVIEW", "OUT_OF_POLICY", "DUPLICATE_FLAGGED"))
approved_count = sum(1 for c in all_cases if c["status"] == "APPROVED")

kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
kpi1.metric("All Cases", total_count)
kpi2.metric("Ready for Approval", ready_count)
kpi3.metric("Docs Pending", pending_docs_count)
kpi4.metric("Manual Review", manual_count)
kpi5.metric("Approved", approved_count)

st.markdown("---")

# Search and Filters Bar
f_col1, f_col2, f_col3 = st.columns([3, 2, 2])

with f_col1:
    search_term = st.text_input("🔍 Search Claimant, Case ID, or Policy", placeholder="e.g. Sarah Jenkins or CASE-2026-1001")

with f_col2:
    status_filter = st.selectbox(
        "Filter by Status",
        options=[
            "ALL",
            "READY_FOR_APPROVAL",
            "DOCS_PENDING",
            "MANUAL_REVIEW",
            "APPROVED",
            "REJECTED",
            "COVERAGE_VERIFIED",
            "OUT_OF_POLICY",
            "DUPLICATE_FLAGGED",
        ],
        index=0,
    )

with f_col3:
    assignee_filter = st.selectbox(
        "Filter by Assigned Staff",
        options=["ALL", "Assigned to Me", "Unassigned"],
        index=0,
    )

# Filter logic
filtered_cases = []
for c in all_cases:
    # Text search
    if search_term:
        term = search_term.lower()
        if not (
            term in c["case_id"].lower()
            or term in (c["claimant_name"] or "").lower()
            or term in (c["policy_id"] or "").lower()
        ):
            continue

    # Status filter
    if status_filter != "ALL" and c["status"] != status_filter:
        continue

    # Assignee filter
    if assignee_filter == "Assigned to Me":
        if c.get("assigned_adjuster_id") != user["staff_id"] and c.get("assigned_approver_id") != user["staff_id"]:
            continue
    elif assignee_filter == "Unassigned":
        if c.get("assigned_adjuster_id") or c.get("assigned_approver_id"):
            continue

    filtered_cases.append(c)

st.subheader(f"Displaying {len(filtered_cases)} of {total_count} Cases")

if not filtered_cases:
    st.info("No claims match the selected criteria.")
else:
    # Render rich cards
    for c in filtered_cases:
        amt = float(c.get("total_amount") or 0.0)
        cid = c["case_id"]
        status = c["status"]
        adj_display = c.get("adjuster_name") or c.get("assigned_adjuster_id") or "Unassigned"
        app_display = c.get("approver_name") or c.get("assigned_approver_id") or "Unassigned"

        with st.container():
            col_id, col_claimant, col_amount, col_status, col_assign, col_act = st.columns([2.5, 2.5, 1.8, 2.2, 2.5, 2.5])

            with col_id:
                st.markdown(f"**`{cid}`**")
                st.caption(f"Policy: `{c.get('policy_id')}`")

            with col_claimant:
                st.markdown(f"**{c.get('claimant_name')}**")
                st.caption(f"Created: {str(c.get('created_at', ''))[:10]}")

            with col_amount:
                st.markdown(f"**${amt:,.2f}**")

            with col_status:
                st.markdown(render_status_badge(status), unsafe_allow_html=True)

            with col_assign:
                st.caption(f"Adjuster: **{adj_display}**  \nApprover: **{app_display}**")

            with col_act:
                btn_cols = st.columns(2)
                with btn_cols[0]:
                    if st.button("Inspect", key=f"q_view_{cid}", use_container_width=True):
                        st.session_state["selected_case_id"] = cid
                        st.switch_page("pages/3_Case_Workspace.py")
                with btn_cols[1]:
                    if status == "READY_FOR_APPROVAL":
                        if st.button("Approve", key=f"q_app_{cid}", type="primary", use_container_width=True):
                            st.session_state["selected_approval_case_id"] = cid
                            st.switch_page("pages/4_Approvals.py")
                    elif status == "DOCS_PENDING":
                        if st.button("Upload", key=f"q_up_{cid}", use_container_width=True):
                            st.session_state["selected_case_id"] = cid
                            st.switch_page("pages/3_Case_Workspace.py")

            st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px solid #F3F4F6;' />", unsafe_allow_html=True)

