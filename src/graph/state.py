"""LangGraph State definitions for Claims Processing Workflow."""

import operator
from typing import Annotated, Any, Dict, List, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from src.agents.schemas import Route


class DocumentWorkerInput(TypedDict):
    """Input payload fanned out to DocumentWorker via Send()."""
    case_id: str
    doc: Dict[str, Any]


class ClaimState(TypedDict, total=False):
    """Central TypedDict tracking complete claims state, trajectory, and results."""
    case_id: str
    policy_id: str
    claimant_name: str
    total_amount: float
    date_of_service: str
    claimant_email: Optional[str]
    messages: Annotated[List[BaseMessage], add_messages]
    case_status: str
    next_step: Optional[str]
    agent_hops: Annotated[List[str], operator.add]
    stage_results: Dict[str, Any]
    human_decision: Optional[Dict[str, Any]]
    errors: Annotated[List[str], operator.add]
    token_usage: Dict[str, int]
    documents: List[Dict[str, Any]]
    extracted_documents: Annotated[List[Dict[str, Any]], operator.add]


__all__ = ["ClaimState", "DocumentWorkerInput", "Route"]

