"""MCP Servers package for UHG Claims Agent."""

from src.mcp_servers.case_mcp import mcp as case_mcp
from src.mcp_servers.policy_mcp import mcp as policy_mcp
from src.mcp_servers.documents_mcp import mcp as documents_mcp
from src.mcp_servers.workflow_mcp import mcp as workflow_mcp

__all__ = ["case_mcp", "policy_mcp", "documents_mcp", "workflow_mcp"]
