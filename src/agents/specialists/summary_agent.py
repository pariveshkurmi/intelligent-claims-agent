"""Summary Specialist Agent: Structured claim synthesis and policy clause citation."""

from typing import Any, Dict, List, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from src.agents.llm_factory import get_llm
from src.agents.middleware import PIIMiddleware, ToolCallLimitMiddleware, ToolRetryMiddleware
from src.agents.schemas import CaseSummaryResult
from src.agents.tool_loader import get_summary_tools, load_case_summary_prompt


class SummaryAgent:
    """Specialist agent that synthesizes evidence and policy clauses into a decision brief.
    
    Enforces least privilege: permitted tools are case-mcp (get_case, save_summary),
    documents-mcp (list_documents), and policy-mcp (search_policy_wording).
    Loads prompt template dynamically from FastMCP (`case_summary`).
    """

    def __init__(
        self,
        rate_limiter: Optional[ToolCallLimitMiddleware] = None,
        retry_middleware: Optional[ToolRetryMiddleware] = None,
    ):
        self.rate_limiter = rate_limiter or ToolCallLimitMiddleware(max_tool_calls=8)
        self.retry_middleware = retry_middleware or ToolRetryMiddleware()
        self.llm = get_llm(model_size="mid-size")
        self.tools = get_summary_tools(self.rate_limiter, self.retry_middleware)
        self.tools_by_name = {t.name: t for t in self.tools}
        self.structured_synthesizer = self.llm.with_structured_output(CaseSummaryResult)

    def generate_summary(self, case_id: str) -> CaseSummaryResult:
        """Synthesize clinical facts, document evidence, and policy citations into a structured summary."""
        # 1. Fetch case details
        get_case_tool = self.tools_by_name["get_case"]
        case_info = get_case_tool.invoke({"case_id": case_id})

        # 2. Fetch documents
        list_docs_tool = self.tools_by_name["list_documents"]
        doc_list = list_docs_tool.invoke({"case_id": case_id})

        # 3. Query policy clauses via pgvector search
        search_policy_tool = self.tools_by_name["search_policy_wording"]
        policy_clauses = search_policy_tool.invoke({
            "query": f"inpatient hospitalization coverage exclusions prior authorization {case_info.get('claimant_name', '')}",
            "limit": 3,
            "min_similarity": 0.20,
        })

        # 4. Load prompt from FastMCP
        mcp_prompt_template = load_case_summary_prompt(case_id)

        # 5. Build context payload and scrub PII
        context_payload = (
            f"Case Context:\n"
            f"ID: {case_id}\n"
            f"Claimant: {case_info.get('claimant_name')}\n"
            f"Total Amount: ${case_info.get('total_amount', 0.0):,.2f}\n"
            f"Documents Count: {len(doc_list)}\n"
            f"Retrieved Policy Clauses:\n"
            + "\n".join([f"- [{c.get('clause_id')}] {c.get('clause_text', '')[:200]}" for c in policy_clauses])
        )
        scrubbed_context = PIIMiddleware.sanitize_text(context_payload)

        # 6. Structured Synthesis with LLM
        summary: CaseSummaryResult = self.structured_synthesizer.invoke([
            SystemMessage(content=mcp_prompt_template),
            HumanMessage(content=scrubbed_context),
        ])

        # 7. Persist summary to PostgreSQL via case-mcp: save_summary (adapting types for JSONB / arrays)
        save_tool = self.tools_by_name["save_summary"]
        missing_list = [summary.missing_info] if summary.missing_info and summary.missing_info.lower() != "none" else []
        risks_dict_list = [{"description": r} if isinstance(r, str) else r for r in summary.risks]
        citations_dict_list = [{"citation": c} if isinstance(c, str) else c for c in summary.policy_citations]

        save_tool.invoke({
            "case_id": case_id,
            "facts": {"narrative": summary.facts},
            "evidence": {"sources": summary.evidence},
            "missing_info": missing_list,
            "risks": risks_dict_list,
            "policy_citations": citations_dict_list,
            "next_action": summary.next_action,
        })

        return summary
