"""MCP Tool Loader & Least-Privilege Enforcer for Specialist Agents."""

from typing import List, Optional
from langchain_core.tools import BaseTool, StructuredTool

# Import raw FastMCP tool functions and prompt templates directly from module definitions
from src.mcp_servers.case_mcp import (
    get_case,
    list_cases,
    find_similar_cases,
    register_case,
    save_summary,
    case_summary,
)
from src.mcp_servers.policy_mcp import (
    get_policy,
    check_coverage,
    search_policy_wording,
)
from src.mcp_servers.documents_mcp import (
    list_documents,
    extract_text,
    classify_document,
    extract_fields,
    validate_case_documents,
)
from src.mcp_servers.workflow_mcp import (
    get_workload,
    assign_case,
    request_approval,
    schedule_sla,
    send_notification,
    request_documents,
    claimant_letter,
    approver_brief,
)
from src.agents.middleware import ToolCallLimitMiddleware, ToolRetryMiddleware


def _wrap_tool(func, rate_limiter: Optional[ToolCallLimitMiddleware] = None, retry_middleware: Optional[ToolRetryMiddleware] = None) -> BaseTool:
    """Wrap a tool function with optional rate limit and retry middleware, converting to StructuredTool."""
    target_func = func
    if retry_middleware:
        target_func = retry_middleware.wrap_tool(target_func)
    if rate_limiter:
        target_func = rate_limiter.wrap_tool(target_func)

    return StructuredTool.from_function(
        func=target_func,
        name=func.__name__,
        description=func.__doc__ or f"Execute {func.__name__}",
    )


# --- Least Privilege Tool Providers (Section 4.1) ---

def get_intake_tools(
    rate_limiter: Optional[ToolCallLimitMiddleware] = None,
    retry_middleware: Optional[ToolRetryMiddleware] = None,
) -> List[BaseTool]:
    """Return Intake Agent permitted tools:
    policy-mcp: get_policy, check_coverage
    case-mcp: find_similar_cases, register_case
    """
    return [
        _wrap_tool(get_policy, rate_limiter, retry_middleware),
        _wrap_tool(check_coverage, rate_limiter, retry_middleware),
        _wrap_tool(find_similar_cases, rate_limiter, retry_middleware),
        _wrap_tool(register_case, rate_limiter, retry_middleware),
    ]


def get_document_tools(
    rate_limiter: Optional[ToolCallLimitMiddleware] = None,
    retry_middleware: Optional[ToolRetryMiddleware] = None,
) -> List[BaseTool]:
    """Return Document Agent permitted tools:
    documents-mcp: list_documents, extract_text, classify_document, extract_fields, validate_case_documents
    """
    return [
        _wrap_tool(list_documents, rate_limiter, retry_middleware),
        _wrap_tool(extract_text, rate_limiter, retry_middleware),
        _wrap_tool(classify_document, rate_limiter, retry_middleware),
        _wrap_tool(extract_fields, rate_limiter, retry_middleware),
        _wrap_tool(validate_case_documents, rate_limiter, retry_middleware),
    ]


def get_summary_tools(
    rate_limiter: Optional[ToolCallLimitMiddleware] = None,
    retry_middleware: Optional[ToolRetryMiddleware] = None,
) -> List[BaseTool]:
    """Return Summary Agent permitted tools:
    case-mcp: get_case, save_summary
    documents-mcp: list_documents
    policy-mcp: search_policy_wording
    """
    return [
        _wrap_tool(get_case, rate_limiter, retry_middleware),
        _wrap_tool(save_summary, rate_limiter, retry_middleware),
        _wrap_tool(list_documents, rate_limiter, retry_middleware),
        _wrap_tool(search_policy_wording, rate_limiter, retry_middleware),
    ]


def get_routing_tools(
    rate_limiter: Optional[ToolCallLimitMiddleware] = None,
    retry_middleware: Optional[ToolRetryMiddleware] = None,
) -> List[BaseTool]:
    """Return Routing Agent permitted tools:
    workflow-mcp: get_workload, assign_case, request_approval
    """
    return [
        _wrap_tool(get_workload, rate_limiter, retry_middleware),
        _wrap_tool(assign_case, rate_limiter, retry_middleware),
        _wrap_tool(request_approval, rate_limiter, retry_middleware),
    ]


def get_sla_tools(
    rate_limiter: Optional[ToolCallLimitMiddleware] = None,
    retry_middleware: Optional[ToolRetryMiddleware] = None,
) -> List[BaseTool]:
    """Return SLA & Comms Agent permitted tools:
    workflow-mcp: schedule_sla, send_notification, request_documents
    """
    return [
        _wrap_tool(schedule_sla, rate_limiter, retry_middleware),
        _wrap_tool(send_notification, rate_limiter, retry_middleware),
        _wrap_tool(request_documents, rate_limiter, retry_middleware),
    ]


# --- MCP Prompt Loader Helpers ---

def load_case_summary_prompt(case_id: str) -> str:
    """Retrieve case_summary prompt template directly from case_mcp."""
    return case_summary(case_id)


def load_claimant_letter_prompt(case_id: str, claimant_name: str, missing_docs: str) -> str:
    """Retrieve claimant_letter prompt template directly from workflow_mcp."""
    return claimant_letter(case_id, claimant_name, missing_docs)


def load_approver_brief_prompt(case_id: str, claim_amount: float, risks: str) -> str:
    """Retrieve approver_brief prompt template directly from workflow_mcp."""
    return approver_brief(case_id, claim_amount, risks)
