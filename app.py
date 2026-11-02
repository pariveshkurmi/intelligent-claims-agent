"""UHG Intelligent Claims Processing & Case Management Agent - Streamlit Workspace."""

import os
import streamlit as st

st.set_page_config(
    page_title="UHG Claims Agent Workspace",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.db.connection import execute_query
from src.ui.auth import get_current_user, render_auth_sidebar
from src.ui.components import render_status_badge
from src.utils.tracing import init_tracing

# Initialize Arize Phoenix OpenTelemetry tracing
init_tracing()

# Render Auth Persona Switcher
render_auth_sidebar()
user = get_current_user()

# Header
st.title("🏥 UHG Intelligent Claims Processing Workspace")
st.caption(
    "Multi-Agent Case Management System powered by LangGraph, FastMCP Servers, and Human-in-the-Loop Governance."
)

st.markdown("---")

# Query Live Database Metrics
try:
    counts_rows = execute_query(
        """
        SELECT 
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status = 'READY_FOR_APPROVAL') as ready,
            COUNT(*) FILTER (WHERE status = 'DOCS_PENDING') as pending,
            COUNT(*) FILTER (WHERE status = 'MANUAL_REVIEW') as manual,
            COUNT(*) FILTER (WHERE status = 'APPROVED') as approved
        FROM cases;
        """
    )
    if counts_rows:
        row = counts_rows[0]
        total_claims = row.get("total", 0)
        ready_approval = row.get("ready", 0)
        docs_pending = row.get("pending", 0)
        manual_review = row.get("manual", 0)
        approved_count = row.get("approved", 0)
    else:
        total_claims, ready_approval, docs_pending, manual_review, approved_count = 0, 0, 0, 0, 0
except Exception:
    total_claims, ready_approval, docs_pending, manual_review, approved_count = 0, 0, 0, 0, 0
    st.warning("⚠️ Could not connect to PostgreSQL on port 5432. Please ensure `docker compose up -d` is running.")

# Metric KPI Cards
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Total Claims", total_claims)
with col2:
    st.metric("Ready for Approval", ready_approval, delta="HITL Paused", delta_color="normal")
with col3:
    st.metric("Awaiting Docs", docs_pending, delta="Claimant Paused", delta_color="off")
with col4:
    st.metric("Manual Review", manual_review, delta="Escalated", delta_color="inverse")
with col5:
    st.metric("Approved", approved_count, delta="Finalized", delta_color="normal")

st.markdown("### 🚀 Workflow Navigation")

card_col1, card_col2, card_col3 = st.columns(3)

with card_col1:
    st.markdown(
        """
        <div style="border: 1px solid #E5E7EB; border-radius: 10px; padding: 18px; background: #FFFFFF; min-height: 180px;">
            <h4>📥 1. Submit Claim</h4>
            <p style="color: #4B5563; font-size: 0.9rem;">
                Register a new claim with documents, or test with any of the <b>30 synthetic scenario packs</b>. Watch live LangGraph streaming execution.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Go to Submit Claim", use_container_width=True, key="btn_nav_submit"):
        st.switch_page("pages/1_Submit_Claim.py")

with card_col2:
    st.markdown(
        """
        <div style="border: 1px solid #E5E7EB; border-radius: 10px; padding: 18px; background: #FFFFFF; min-height: 180px;">
            <h4>📋 2. Case Queue</h4>
            <p style="color: #4B5563; font-size: 0.9rem;">
                Live claims workbench with status filtering, SLA timers, duplicate warnings, and assigned adjusters & approver limit tiers.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Go to Case Queue", use_container_width=True, key="btn_nav_queue"):
        st.switch_page("pages/2_Case_Queue.py")

with card_col3:
    st.markdown(
        """
        <div style="border: 1px solid #E5E7EB; border-radius: 10px; padding: 18px; background: #FFFFFF; min-height: 180px;">
            <h4>🔍 3. Case Workspace</h4>
            <p style="color: #4B5563; font-size: 0.9rem;">
                In-depth investigation: Docling OCR confidence, prompt injection defense, policy vector citations, and replayable audit trail.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Go to Case Workspace", use_container_width=True, key="btn_nav_workspace"):
        st.switch_page("pages/3_Case_Workspace.py")

st.markdown("<br>", unsafe_allow_html=True)

card_col4, card_col5, card_col6 = st.columns(3)

with card_col4:
    st.markdown(
        """
        <div style="border: 1px solid #E5E7EB; border-radius: 10px; padding: 18px; background: #FFFFFF; min-height: 180px;">
            <h4>⚖️ 4. Approvals Portal</h4>
            <p style="color: #4B5563; font-size: 0.9rem;">
                Human-in-the-Loop decision gate enforcing the <b>Golden Rule</b>: strictly verifies approver limit against claim amount before authorizing.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Go to Approvals", use_container_width=True, key="btn_nav_approvals"):
        st.switch_page("pages/4_Approvals.py")

with card_col5:
    st.markdown(
        """
        <div style="border: 1px solid #E5E7EB; border-radius: 10px; padding: 18px; background: #FFFFFF; min-height: 180px;">
            <h4>💬 5. Ask the Supervisor</h4>
            <p style="color: #4B5563; font-size: 0.9rem;">
                Conversational assistant answering adjuster queries using live MCP resources: <code>case://{id}</code>, timeline, and policy wording.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Go to Ask Supervisor", use_container_width=True, key="btn_nav_supervisor"):
        st.switch_page("pages/5_Ask_Supervisor.py")

with card_col6:
    st.markdown(
        """
        <div style="border: 1px solid #E5E7EB; border-radius: 10px; padding: 18px; background: #F9FAFB; min-height: 180px;">
            <h4>📡 Infrastructure Services</h4>
            <p style="color: #4B5563; font-size: 0.85rem;">
                • <b>PostgreSQL + pgvector</b>: <code>localhost:5432</code><br>
                • <b>Mailpit SMTP Inbox</b>: <a href="http://localhost:8025" target="_blank">localhost:8025</a><br>
                • <b>Arize Phoenix Tracing</b>: <a href="http://localhost:6006" target="_blank">localhost:6006</a><br>
                • <b>Adminer DB UI</b>: <a href="http://localhost:5050" target="_blank">localhost:5050</a>
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("---")

# Recent Cases Quick View
st.subheader("⏱️ Recent Cases Activity")
try:
    recent_cases = execute_query(
        """
        SELECT case_id, claimant_name, policy_id, total_amount, status,
               assigned_adjuster_id, assigned_approver_id, created_at
        FROM cases ORDER BY created_at DESC LIMIT 5;
        """
    )
    if recent_cases:
        for r in recent_cases:
            c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 2])
            c1.markdown(f"**`{r['case_id']}`**  \n{r['claimant_name']}")
            c2.markdown(f"Policy: `{r['policy_id']}`  \nAmount: **${float(r['total_amount']):,.2f}**")
            c3.markdown(f"Status: {render_status_badge(r['status'])}", unsafe_allow_html=True)
            c4.markdown(f"Adj: `{r.get('assigned_adjuster_id') or 'Unassigned'}`  \nApp: `{r.get('assigned_approver_id') or 'Unassigned'}`")
            if c5.button("Inspect", key=f"inspect_{r['case_id']}"):
                st.session_state["selected_case_id"] = r["case_id"]
                st.switch_page("pages/3_Case_Workspace.py")
    else:
        st.info("No claims in database. Click 'Submit Claim' above to load a test scenario.")
except Exception as e:
    st.error(f"Error querying database: {e}")

