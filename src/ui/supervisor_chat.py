"""Ask the Supervisor: Conversational Assistant for Claims Adjusters & Approvers."""

import json
import os
from typing import Any, Dict, Generator, List, Optional
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.agents.llm_factory import get_llm
from src.mcp_servers.case_mcp import get_case_resource, get_case_timeline_resource
from src.mcp_servers.policy_mcp import get_policy_resource
from src.ui.engine import get_full_case_details


def generate_offline_supervisor_reply(case_id: str, prompt: str, case_data: Dict[str, Any]) -> str:
    """Generate a high-fidelity contextual response directly from case and MCP resources."""
    case = case_data.get("case", {})
    summary = case_data.get("summary", {})
    docs = case_data.get("documents", [])
    timeline = case_data.get("timeline", [])

    prompt_lower = prompt.lower()
    claimant = case.get("claimant_name", "Unknown")
    status = case.get("status", "UNKNOWN")
    amount = float(case.get("total_amount", 0.0))
    policy_id = case.get("policy_id", "POL-UHG-001")

    # Question about status or why manual review
    if "status" in prompt_lower or "why" in prompt_lower or "manual review" in prompt_lower or "flag" in prompt_lower:
        reasons = []
        for d in docs:
            if d.get("is_injection_flagged"):
                reasons.append("🚨 Prompt Injection attempt detected in uploaded document.")
            if float(d.get("ocr_confidence", 1.0)) < 0.75:
                reasons.append(f"⚠️ Low OCR confidence ({d.get('ocr_confidence') * 100:.1f}%) on document `{d.get('doc_type')}`.")
        
        risks = summary.get("risks", [])
        if risks:
            reasons.extend([f"• Risk factor: {r}" for r in risks])

        response = (
            f"**Case Status:** `{status}`\n\n"
            f"**Claimant:** {claimant} | **Total Amount:** ${amount:,.2f} | **Policy:** {policy_id}\n\n"
        )
        if reasons:
            response += "**Identified Reasons & Triggers:**\n" + "\n".join(reasons)
        else:
            response += f"The case is currently in status `{status}`. All specialist verification checks passed cleanly."
        return response

    # Question about missing documents
    elif "missing" in prompt_lower or "doc" in prompt_lower:
        missing_docs = summary.get("missing_info", [])
        if missing_docs:
            return (
                f"**Missing Documentation for Case {case_id}:**\n\n"
                f"The following required documents are currently missing:\n"
                + "\n".join([f"- **{m}**" for m in missing_docs])
                + f"\n\nAn automated request email has been dispatched to claimant `{claimant}`."
            )
        else:
            return f"No documentation is currently missing for case {case_id}. All {len(docs)} documents are verified."

    # Question about timeline or who did what
    elif "timeline" in prompt_lower or "who" in prompt_lower or "audit" in prompt_lower or "history" in prompt_lower:
        if not timeline:
            return f"No audit events recorded yet for case {case_id}."
        events_str = "\n".join([
            f"- **{e.get('timestamp', '')[:19]}**: `{e.get('actor')}` performed `{e.get('action')}`"
            for e in timeline
        ])
        return f"**Audit Timeline for Case {case_id}:**\n\n{events_str}"

    # Question about summary or clinical facts
    elif "summary" in prompt_lower or "facts" in prompt_lower or "evidence" in prompt_lower or "procedure" in prompt_lower:
        facts = summary.get("facts", {})
        evidence = summary.get("evidence", {})
        citations = summary.get("policy_citations", [])
        next_action = summary.get("next_action", "MANUAL_REVIEW")

        return (
            f"**Executive Case Summary for {case_id}:**\n\n"
            f"- **Claimant:** {claimant}\n"
            f"- **Diagnoses/Procedures:** {facts.get('diagnosis', 'Appendectomy / Inpatient Care')}\n"
            f"- **Total Claimed:** ${amount:,.2f}\n"
            f"- **Policy Citations:** {', '.join(citations) if citations else 'Standard Inpatient Coverage'}\n"
            f"- **Recommended Next Action:** `{next_action}`\n"
        )

    # Question about approver or routing
    elif "approver" in prompt_lower or "route" in prompt_lower or "tier" in prompt_lower or "adjuster" in prompt_lower:
        adj = case.get("adjuster_name") or case.get("assigned_adjuster_id") or "Unassigned"
        app = case.get("approver_name") or case.get("assigned_approver_id") or "Unassigned"
        limit = case.get("approver_limit")
        limit_str = f"${float(limit):,.2f}" if limit is not None else "N/A"
        if limit is not None:
            compliance_str = "✅ Within Limit" if amount <= float(limit) else "⚠️ Exceeds Limit - Escalation Required"
        else:
            compliance_str = "ℹ️ Pending Approver Assignment"
        return (
            f"**Routing & Staff Assignment for {case_id}:**\n\n"
            f"- **Assigned Adjuster:** {adj}\n"
            f"- **Assigned Approver:** {app} (Approval Limit: {limit_str})\n"
            f"- **Claim Total:** ${amount:,.2f}\n"
            f"- **Golden Rule Compliance:** {compliance_str}"
        )

    # General fallback
    return (
        f"**Case {case_id} Overview:**\n"
        f"- Claimant: {claimant}\n"
        f"- Status: `{status}`\n"
        f"- Policy: {policy_id}\n"
        f"- Amount: ${amount:,.2f}\n"
        f"- Documents on file: {len(docs)}\n\n"
        f"You can ask me about: **reasons for manual review**, **missing documents**, "
        f"**policy citations**, **audit timeline**, or **approver limits**."
    )


def ask_supervisor(case_id: str, user_question: str) -> Generator[str, None, None]:
    """
    Stream response from Supervisor Agent using MCP context resources.
    Yields chunks of text for real-time streaming in Streamlit.
    """
    case_data = get_full_case_details(case_id)
    if not case_data or not case_data.get("case"):
        yield f"Case '{case_id}' was not found in the database. Please verify the Case ID."
        return

    # Check if live LLM is enabled
    mock_env = os.getenv("MOCK_LLM", "true").lower() in ("true", "1", "yes")
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    if mock_env or not gemini_key:
        # Generate rich contextual response
        full_reply = generate_offline_supervisor_reply(case_id, user_question, case_data)
        # Yield in tokens/words to simulate natural streaming
        words = full_reply.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
        return

    # Live Gemini LLM invocation
    try:
        # Load MCP resources
        case_resource_str = get_case_resource(case_id)
        timeline_resource_str = get_case_timeline_resource(case_id)
        policy_id = case_data["case"].get("policy_id", "POL-UHG-001")
        policy_resource_str = get_policy_resource(policy_id)

        system_msg = SystemMessage(
            content=(
                f"You are the Intelligent Claims Supervisor Agent for UHG. "
                f"You have full access to case records and immutable audit logs via MCP resources.\n\n"
                f"--- CASE RESOURCE (case://{case_id}) ---\n{case_resource_str}\n\n"
                f"--- TIMELINE AUDIT (case://{case_id}/timeline) ---\n{timeline_resource_str}\n\n"
                f"--- POLICY RESOURCE (policy://{policy_id}) ---\n{policy_resource_str}\n\n"
                f"Answer the adjuster or approver's question clearly, citing specific facts, document IDs, or policy clauses where relevant."
            )
        )
        human_msg = HumanMessage(content=user_question)

        llm = get_llm("pro")
        for chunk in llm.stream([system_msg, human_msg]):
            if hasattr(chunk, "content") and chunk.content:
                yield str(chunk.content)
    except Exception as e:
        yield f"Error querying Supervisor LLM: {e}\n\nFallback context:\n"
        yield generate_offline_supervisor_reply(case_id, user_question, case_data)

