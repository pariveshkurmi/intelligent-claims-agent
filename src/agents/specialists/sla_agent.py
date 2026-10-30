"""SLA & Communications Specialist Agent: SLA timers, Mailpit dispatch, and claimant letters."""

from typing import Any, Dict, List, Optional
from src.agents.llm_factory import get_llm
from src.agents.middleware import PIIMiddleware, ToolCallLimitMiddleware, ToolRetryMiddleware
from src.agents.schemas import SLACommsResult
from src.agents.tool_loader import (
    get_sla_tools,
    load_claimant_letter_prompt,
    load_approver_brief_prompt,
)


class SLAAgent:
    """Specialist agent for SLA scheduling and communications dispatch.
    
    Enforces least privilege: permitted to use workflow-mcp tools (schedule_sla, send_notification, request_documents).
    Loads prompt templates from FastMCP (`claimant_letter`, `approver_brief`).
    """

    def __init__(
        self,
        rate_limiter: Optional[ToolCallLimitMiddleware] = None,
        retry_middleware: Optional[ToolRetryMiddleware] = None,
    ):
        self.rate_limiter = rate_limiter or ToolCallLimitMiddleware(max_tool_calls=6)
        self.retry_middleware = retry_middleware or ToolRetryMiddleware()
        self.llm = get_llm(model_size="small")
        self.tools = get_sla_tools(self.rate_limiter, self.retry_middleware)
        self.tools_by_name = {t.name: t for t in self.tools}

    def schedule_sla(self, case_id: str, claim_amount: float, is_emergency: bool = False) -> Dict[str, Any]:
        """Configure automated SLA monitoring timer via workflow-mcp."""
        sched_tool = self.tools_by_name["schedule_sla"]
        return sched_tool.invoke({
            "case_id": case_id,
            "claim_amount": claim_amount,
            "is_emergency": is_emergency,
        })

    def request_missing_documents(
        self,
        case_id: str,
        claimant_name: str,
        claimant_email: str,
        missing_docs: List[str],
    ) -> SLACommsResult:
        """Load claimant letter prompt from MCP, format notification, and transition case to DOCS_PENDING."""
        docs_str = ", ".join(missing_docs)
        prompt_template = load_claimant_letter_prompt(case_id, claimant_name, docs_str)

        # Call request_documents tool in workflow-mcp
        req_tool = self.tools_by_name["request_documents"]
        tool_res = req_tool.invoke({
            "case_id": case_id,
            "claimant_email": claimant_email,
            "missing_docs": missing_docs,
            "actor": "sla_agent",
        })

        return SLACommsResult(
            case_id=case_id,
            sla_scheduled=False,
            notification_sent=tool_res.get("email_delivered", False),
            documents_requested=True,
            details=tool_res,
        )

    def notify_approver(
        self,
        case_id: str,
        approver_email: str,
        claim_amount: float,
        risks: List[str],
    ) -> SLACommsResult:
        """Prepare decision brief using MCP approver_brief prompt and dispatch to Mailpit."""
        risks_str = "\n".join([f"- {r}" for r in risks]) if risks else "No adverse policy risks identified."
        brief_prompt = load_approver_brief_prompt(case_id, claim_amount, risks_str)

        send_tool = self.tools_by_name["send_notification"]
        notif_res = send_tool.invoke({
            "case_id": case_id,
            "recipient_email": approver_email,
            "subject": f"Ready for Review: Claim {case_id} (${claim_amount:,.2f})",
            "message": brief_prompt,
            "notification_type": "APPROVAL_REQUIRED",
        })

        return SLACommsResult(
            case_id=case_id,
            sla_scheduled=False,
            notification_sent=notif_res.get("delivered", False),
            documents_requested=False,
            details=notif_res,
        )
