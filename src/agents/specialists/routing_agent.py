"""Routing Specialist Agent: Adjuster workload balancing and approver tier routing."""

from typing import Any, Dict, List, Optional
from src.agents.llm_factory import get_llm
from src.agents.middleware import PIIMiddleware, ToolCallLimitMiddleware, ToolRetryMiddleware
from src.agents.schemas import RoutingResult
from src.agents.tool_loader import get_routing_tools


class RoutingAgent:
    """Specialist agent for claims routing and assignment.
    
    Enforces least privilege: permitted to use workflow-mcp tools (get_workload, assign_case, request_approval).
    CRITICAL GOLDEN RULE: Never approves, rejects, or settles claims. Prepares assignment for human sign-off.
    """

    def __init__(
        self,
        rate_limiter: Optional[ToolCallLimitMiddleware] = None,
        retry_middleware: Optional[ToolRetryMiddleware] = None,
    ):
        self.rate_limiter = rate_limiter or ToolCallLimitMiddleware(max_tool_calls=6)
        self.retry_middleware = retry_middleware or ToolRetryMiddleware()
        self.llm = get_llm(model_size="small")
        self.tools = get_routing_tools(self.rate_limiter, self.retry_middleware)
        self.tools_by_name = {t.name: t for t in self.tools}

    def route_case(
        self,
        case_id: str,
        claim_amount: float,
    ) -> RoutingResult:
        """Inspect staff directory, match adjuster workload, tier approver by limit, and request sign-off."""
        # 1. Fetch live workload from workflow-mcp for adjusters and approvers
        get_workload_tool = self.tools_by_name["get_workload"]
        adjusters = get_workload_tool.invoke({"role": "adjuster"})
        approvers = get_workload_tool.invoke({"role": "approver"})

        # 2. Pick adjuster with lowest active load
        if not adjusters:
            raise RuntimeError("No active adjusters found in staff directory")
        sorted_adjusters = sorted(adjusters, key=lambda a: a.get("active_cases", 0))
        selected_adjuster = sorted_adjusters[0]
        adjuster_id = selected_adjuster["staff_id"]

        # 3. Match approver whose limit covers the claim (pick lowest qualifying tier)
        eligible_approvers = [
            app for app in approvers
            if float(app.get("approval_limit", 0.0)) >= claim_amount
        ]
        if not eligible_approvers:
            # Fall back to highest limit approver (Director)
            sorted_approvers = sorted(approvers, key=lambda a: float(a.get("approval_limit", 0.0)), reverse=True)
            selected_approver = sorted_approvers[0]
        else:
            # Sort by lowest qualifying limit, then workload
            sorted_approvers = sorted(
                eligible_approvers,
                key=lambda a: (float(a.get("approval_limit", 0.0)), a.get("active_cases", 0))
            )
            selected_approver = sorted_approvers[0]

        approver_id = selected_approver["staff_id"]
        approver_limit = float(selected_approver.get("approval_limit", 0.0))

        # 4. Assign adjuster and approver to case
        assign_tool = self.tools_by_name["assign_case"]
        assign_tool.invoke({
            "case_id": case_id,
            "staff_id": adjuster_id,
            "role": "adjuster",
            "actor": "routing_agent",
        })
        assign_tool.invoke({
            "case_id": case_id,
            "staff_id": approver_id,
            "role": "approver",
            "actor": "routing_agent",
        })

        # 5. Request approval via workflow-mcp
        request_app_tool = self.tools_by_name["request_approval"]
        request_app_tool.invoke({
            "case_id": case_id,
            "approver_id": approver_id,
            "claim_amount": claim_amount,
            "actor": "routing_agent",
        })

        rationale = (
            f"Assigned to adjuster {selected_adjuster.get('name')} ({adjuster_id}, load: {selected_adjuster.get('active_cases')}) "
            f"and approver {selected_approver.get('name')} ({approver_id}) with limit ${approver_limit:,.2f}."
        )

        return RoutingResult(
            case_id=case_id,
            assigned_adjuster_id=adjuster_id,
            assigned_approver_id=approver_id,
            approver_limit=approver_limit,
            claim_amount=claim_amount,
            rationale=rationale,
            status="ROUTED_FOR_APPROVAL",
        )
