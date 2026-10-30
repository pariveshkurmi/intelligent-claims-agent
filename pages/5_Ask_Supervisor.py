"""Page 5: Conversational Supervisor AI Assistant powered by FastMCP Resources."""

import streamlit as st

st.set_page_config(page_title="Ask Supervisor | UHG Claims Agent", page_icon="💬", layout="wide")

from src.db.connection import execute_query
from src.ui.auth import render_auth_sidebar, get_current_user
from src.ui.components import render_status_badge
from src.ui.supervisor_chat import ask_supervisor

render_auth_sidebar()
user = get_current_user()

st.title("💬 Ask the Claims Supervisor")
st.caption(
    "Interactive AI Assistant querying case facts, policy limits, and immutable audit logs via FastMCP context resources (`case://{id}`, `case://{id}/timeline`, `policy://{id}`)."
)

st.markdown("---")

# Select Case context
try:
    case_rows = execute_query(
        "SELECT case_id, claimant_name, policy_id, total_amount, status FROM cases ORDER BY created_at DESC;"
    )
except Exception:
    case_rows = []

if not case_rows:
    st.warning("No cases found in database. Please register a claim first.")
    st.stop()

case_ids = [r["case_id"] for r in case_rows]
default_cid = st.session_state.get("selected_case_id", case_ids[0])
idx = case_ids.index(default_cid) if default_cid in case_ids else 0

col_sel, col_info = st.columns([2, 3])
with col_sel:
    selected_case_id = st.selectbox(
        "Active Case Context",
        options=case_ids,
        index=idx,
        format_func=lambda cid: f"{cid} - {[r['claimant_name'] for r in case_rows if r['case_id'] == cid][0]}",
    )
    st.session_state["selected_case_id"] = selected_case_id

active_case = next((r for r in case_rows if r["case_id"] == selected_case_id), {})
with col_info:
    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    st.markdown(
        f"**Claimant:** {active_case.get('claimant_name')} | "
        f"**Amount:** ${float(active_case.get('total_amount', 0)):,.2f} | "
        f"**Status:** {render_status_badge(active_case.get('status', 'UNKNOWN'))}",
        unsafe_allow_html=True,
    )

st.markdown("---")

# Suggested Prompts Bar
st.caption("💡 Quick Suggestions:")
q_cols = st.columns(4)
quick_prompt = None

with q_cols[0]:
    if st.button("🔍 Why was this case flagged?", use_container_width=True):
        quick_prompt = "Why was this case flagged or what is the current case status?"
with q_cols[1]:
    if st.button("📑 Are any documents missing?", use_container_width=True):
        quick_prompt = "Are there any missing or incomplete documents for this claim?"
with q_cols[2]:
    if st.button("⚖️ What policy clauses were cited?", use_container_width=True):
        quick_prompt = "Summarize the clinical facts and cited policy clauses."
with q_cols[3]:
    if st.button("📜 Show the audit timeline", use_container_width=True):
        quick_prompt = "Show the audit timeline of who took what action."

# Manage Chat History per Case
history_key = f"chat_history_{selected_case_id}"
if history_key not in st.session_state:
    st.session_state[history_key] = [
        {
            "role": "assistant",
            "content": (
                f"Hello {user['name']}. I am the UHG Supervisor Agent. "
                f"I have loaded the live FastMCP resources for `{selected_case_id}`. "
                f"How can I assist your investigation or review today?"
            ),
        }
    ]

# Display Messages
for msg in st.session_state[history_key]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# User Input Handling
prompt = st.chat_input(f"Ask about case {selected_case_id}...") or quick_prompt

if prompt:
    # Append user question
    st.session_state[history_key].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Stream Supervisor Response
    with st.chat_message("assistant"):
        stream_gen = ask_supervisor(selected_case_id, prompt)
        full_response = st.write_stream(stream_gen)

    st.session_state[history_key].append({"role": "assistant", "content": full_response})

# Clear Chat History Button
if st.button("🗑️ Clear Chat History for This Case"):
    st.session_state[history_key] = []
    st.rerun()

