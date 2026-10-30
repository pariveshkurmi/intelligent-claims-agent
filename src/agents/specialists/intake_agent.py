"""Intake Specialist Agent: Verifies policy coverage and detects duplicate claims."""

from typing import Any, Dict, Optional
from src.agents.llm_factory import get_llm
from src.agents.middleware import PIIMiddleware, ToolCallLimitMiddleware, ToolRetryMiddleware
from src.agents.schemas import IntakeResult
from src.agents.tool_loader import get_intake_tools


class IntakeAgent:
    """Specialist agent responsible for policy verification and duplicate detection.
    
    Enforces least privilege: only permitted to use policy-mcp and case-mcp tools.
    """

    def __init__(
        self,
        rate_limiter: Optional[ToolCallLimitMiddleware] = None,
        retry_middleware: Optional[ToolRetryMiddleware] = None,
    ):
        self.rate_limiter = rate_limiter or ToolCallLimitMiddleware(max_tool_calls=6)
        self.retry_middleware = retry_middleware or ToolRetryMiddleware()
        self.llm = get_llm(model_size="small")
        self.tools = get_intake_tools(self.rate_limiter, self.retry_middleware)
        self.tools_by_name = {t.name: t for t in self.tools}

    def run(
        self,
        case_id: str,
        policy_id: str,
        claimant_name: str,
        date_of_service: str,
        total_amount: float,
    ) -> IntakeResult:
        """Execute intake evaluation against policy and historical database."""
        # Sanitize PII
        sanitized_name = PIIMiddleware.sanitize_text(claimant_name)

        # 1. Coverage Check via policy-mcp
        check_cov_tool = self.tools_by_name["check_coverage"]
        cov_res = check_cov_tool.invoke({
            "policy_number": policy_id,
            "claimant_name": claimant_name,
            "date_of_service": date_of_service,
        })

        is_covered = cov_res.get("covered", False)
        coverage_reason = cov_res.get("reason", "Coverage verified successfully.")

        # 2. Duplicate Detection via case-mcp
        find_sim_tool = self.tools_by_name["find_similar_cases"]
        sim_cases = find_sim_tool.invoke({
            "claimant_name": claimant_name,
            "total_amount": total_amount,
        })

        # Exclude current case and check if any historical case flagged duplicate warning
        duplicates = [
            c for c in sim_cases
            if c.get("case_id") != case_id and c.get("duplicate_warning") is True
        ]
        is_duplicate = len(duplicates) > 0
        dup_case_id = duplicates[0]["case_id"] if is_duplicate else None
        dup_reason = (
            f"Matches historical case {dup_case_id} (${duplicates[0]['total_amount']:.2f}) with identical claimant and amount."
            if is_duplicate
            else None
        )

        recommendation = "PROCEED"
        if not is_covered:
            recommendation = "REJECT_OUT_OF_POLICY"
        elif is_duplicate:
            recommendation = "FLAG_DUPLICATE"

        return IntakeResult(
            case_id=case_id,
            is_covered=is_covered,
            coverage_reason=coverage_reason,
            is_duplicate=is_duplicate,
            duplicate_case_id=dup_case_id,
            duplicate_reason=dup_reason,
            recommendation=recommendation,
        )
