"""Supervisor logic enforcing lean 5-6 call architecture and structured routing."""

from typing import Any, Dict, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from src.agents.llm_factory import get_llm
from src.agents.schemas import Route
from src.graph.guardrails import guard_transition, check_failsafe_conditions
from src.graph.state import ClaimState


SUPERVISOR_SYSTEM_PROMPT = """You are the Central Claims Supervisor Agent for UHG.
Your role is to orchestrate the claims workflow among 5 specialist agents, human approvers, and exceptions.
Evaluate the current case status, stage results, document findings, and safety flags.
Choose the single most appropriate next step and explain your reasoning.

Destinations:
- 'intake_agent': Verify policy coverage and check for duplicate claims.
- 'document_fanout': Process, extract, and validate supporting documentation.
- 'summary_agent': Synthesize clinical facts and cite policy terms.
- 'routing_agent': Match adjuster workload and identify authorized approver tier.
- 'sla_agent': Schedule SLA deadlines and dispatch notification brief.
- 'human_review': Pause execution for human approver decision.
- 'await_documents': Pause execution waiting for missing documents from claimant.
- 'manual_review': Escalate to human claims investigator due to low confidence, injection, or policy exclusion.
- 'finalize': Finalize claim in records following human decision.
- 'end': Terminate execution.

Never approve claims autonomously. Respect stage order and safety boundaries."""


class SupervisorNode:
    """Supervisor orchestrator combining deterministic fast paths with LLM-backed decisioning."""

    def __init__(self):
        self.llm = get_llm(model_size="mid-size")
        self.structured_router = self.llm.with_structured_output(Route)

    def route_with_llm(self, state: ClaimState) -> Route:
        """Invoke Supervisor LLM for non-trivial branching decisions."""
        prompt = (
            f"Case ID: {state.get('case_id')}\n"
            f"Current Status: {state.get('case_status')}\n"
            f"Agent Hops: {state.get('agent_hops', [])}\n"
            f"Stage Results: {list(state.get('stage_results', {}).keys())}\n"
            f"Errors: {state.get('errors', [])}\n"
            f"Extracted Documents: {len(state.get('extracted_documents', []))}\n"
            f"Please determine the appropriate next hop."
        )

        decision: Route = self.structured_router.invoke([
            SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])

        # Pass through guardrail verification
        guarded_dest = guard_transition(state, decision.next)
        if guarded_dest != decision.next:
            return Route(
                next=guarded_dest,
                reason=f"Guardrail redirected from {decision.next} to {guarded_dest} to enforce policy/safety rules.",
            )
        return decision

    def decide_next(self, state: ClaimState) -> Route:
        """Evaluate next step with Lean 5-6 LLM Call Architecture:
        - Failsafes and happy paths are evaluated deterministically to prevent redundant LLM hops.
        - Supervisor LLM is reserved for ambiguous anomalies.
        """
        # 1. Failsafes check
        override = check_failsafe_conditions(state)
        if override:
            return Route(
                next=override,
                reason=f"Failsafe condition triggered direct routing to {override}.",
            )

        stage_results = state.get("stage_results", {})
        case_status = state.get("case_status", "NEW")

        # 2. Sequential pipeline deterministic paths (Section 8 Metric 5: Redundant Hops <= 1)
        if "intake" not in stage_results:
            return Route(next="intake_agent", reason="Initial intake and coverage lookup required.")

        if "documents" not in stage_results:
            return Route(next="document_fanout", reason="Intake verified; proceed to parallel document processing.")

        doc_summary = stage_results.get("documents", {}).get("validation", {})
        val_status = doc_summary.get("validation_status", "")
        if val_status in ("DOCS_PENDING", "MISSING_DOCUMENTS"):
            return Route(next="await_documents", reason="Documentation incomplete. Pausing for claimant submission.")
        if val_status in ("LOW_CONFIDENCE", "SECURITY_RISK"):
            return Route(next="manual_review", reason=f"Document validation flagged {val_status}.")

        if "summary" not in stage_results:
            return Route(next="summary_agent", reason="Documents validated. Ready for clinical synthesis.")

        if "routing" not in stage_results:
            return Route(next="routing_agent", reason="Summary brief generated. Ready for adjuster and approver routing.")

        if "sla" not in stage_results:
            return Route(next="sla_agent", reason="Staff routed. Ready for SLA timer and approver brief notification.")

        if state.get("human_decision") is None:
            return Route(next="human_review", reason="Workflow prepared. Pausing at interrupt() for human decision.")

        # Human decision present
        decision_val = state.get("human_decision", {}).get("decision", "").upper()
        if decision_val in ("INFO_REQUESTED", "REQUEST_DOCUMENTS"):
            return Route(next="await_documents", reason="Approver requested additional documents.")
        elif decision_val in ("APPROVED", "REJECTED"):
            return Route(next="finalize", reason=f"Approver decided: {decision_val}. Finalizing claim.")

        return Route(next="end", reason="Workflow completed.")

