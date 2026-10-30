"""Authentication, Session Management, and Role-Based Access Control (RBAC)."""

import os
from typing import Any, Dict, Optional, Tuple
import streamlit as st
from src.db.connection import execute_query

# Predefined staff profiles matching seed data
DEFAULT_STAFF = [
    {
        "staff_id": "ADJ-101",
        "name": "Alex Morgan",
        "role": "adjuster",
        "tier": "Adjuster",
        "email": "alex.morgan@uhg-claims.example.com",
        "approval_limit": 0.00,
    },
    {
        "staff_id": "ADJ-102",
        "name": "Marcus Vance",
        "role": "adjuster",
        "tier": "Adjuster",
        "email": "marcus.vance@uhg-claims.example.com",
        "approval_limit": 0.00,
    },
    {
        "staff_id": "ADJ-103",
        "name": "Elena Rostova",
        "role": "adjuster",
        "tier": "Adjuster",
        "email": "elena.rostova@uhg-claims.example.com",
        "approval_limit": 0.00,
    },
    {
        "staff_id": "APP-201",
        "name": "Jordan Hayes",
        "role": "approver",
        "tier": "Approver Tier 1 (up to $2,500)",
        "email": "jordan.hayes@uhg-claims.example.com",
        "approval_limit": 2500.00,
    },
    {
        "staff_id": "APP-202",
        "name": "Claire Bennett",
        "role": "approver",
        "tier": "Approver Tier 2 (up to $10,000)",
        "email": "claire.bennett@uhg-claims.example.com",
        "approval_limit": 10000.00,
    },
    {
        "staff_id": "APP-203",
        "name": "David Sterling",
        "role": "approver",
        "tier": "Approver Tier 3 - Director (up to $100,000)",
        "email": "david.sterling@uhg-claims.example.com",
        "approval_limit": 100000.00,
    },
    {
        "staff_id": "SUP-001",
        "name": "Chief Supervisor",
        "role": "supervisor",
        "tier": "System Supervisor / Admin",
        "email": "supervisor@uhg-claims.example.com",
        "approval_limit": 1000000.00,
    },
]


def init_session():
    """Initialize session state defaults for auth and user context."""
    if "current_user" not in st.session_state:
        # Default to Tier 1 approver for immediate testing of approvals
        st.session_state["current_user"] = DEFAULT_STAFF[3]


def get_current_user() -> Dict[str, Any]:
    """Retrieve the active authenticated staff profile."""
    init_session()
    return st.session_state["current_user"]


def set_current_user(staff_id: str):
    """Switch active profile to a specific staff ID."""
    for s in DEFAULT_STAFF:
        if s["staff_id"] == staff_id:
            st.session_state["current_user"] = s
            return


def can_approve(claim_amount: float) -> Tuple[bool, str]:
    """
    Verify whether the active user satisfies the Golden Rule:
    - Must possess 'approver' or 'supervisor' role.
    - Claim total must not exceed the approver's assigned dollar authority limit.
    """
    user = get_current_user()
    role = user.get("role")
    limit = float(user.get("approval_limit", 0.0))

    if role not in ("approver", "supervisor"):
        return False, f"Current role '{role}' is not authorized to approve claims (Approver role required)."

    if claim_amount > limit:
        return (
            False,
            f"Claim amount (${claim_amount:,.2f}) exceeds your authorization limit (${limit:,.2f}). "
            f"Escalation to a higher tier approver is required.",
        )

    return True, f"Authorized (Limit: ${limit:,.2f} >= Claim: ${claim_amount:,.2f})"


def render_auth_sidebar():
    """Render user profile widget and role switcher in the Streamlit sidebar."""
    init_session()
    user = get_current_user()

    st.sidebar.markdown("### 👤 User & Role Identity")

    # Optional Keycloak / st.login hook if configured in environment
    if os.getenv("ENABLE_KEYCLOAK_AUTH", "false").lower() == "true":
        try:
            if hasattr(st, "login"):
                # If st.login is active in Streamlit
                st.sidebar.caption("Keycloak SSO Enabled")
        except Exception:
            pass

    # Quick Role Switcher
    options = [s["staff_id"] for s in DEFAULT_STAFF]
    labels = {
        s["staff_id"]: f"{s['name']} ({s['role'].title()} - ${s['approval_limit']:,.0f})"
        if s["role"] == "approver"
        else f"{s['name']} ({s['role'].title()})"
        for s in DEFAULT_STAFF
    }

    current_idx = options.index(user["staff_id"]) if user["staff_id"] in options else 0

    selected_id = st.sidebar.selectbox(
        "Active Persona",
        options=options,
        index=current_idx,
        format_func=lambda sid: labels[sid],
        help="Select which staff identity to act as in the Claims Workspace.",
    )

    if selected_id != user["staff_id"]:
        set_current_user(selected_id)
        st.rerun()

    # User Summary Badge
    role_color = (
        "green" if user["role"] == "approver" else "blue" if user["role"] == "adjuster" else "purple"
    )
    st.sidebar.info(
        f"**{user['name']}**  \n"
        f"ID: `{user['staff_id']}`  \n"
        f"Role: **{user['role'].upper()}**  \n"
        f"Auth Limit: **${user['approval_limit']:,.2f}**"
    )
    st.sidebar.markdown("---")

