"""LLM Factory: Provides transparent switching between deterministic Mock LLM and Live Gemini/OpenAI."""

import os
import re
from typing import Any, Dict, List, Optional, Sequence, Type, Union
from dotenv import load_dotenv
from pydantic import BaseModel
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda

from src.agents.schemas import (
    DocumentExtractionResult,
    CaseSummaryResult,
    RoutingResult,
    IntakeResult,
    SLACommsResult,
)

load_dotenv()


class MockStructuredRunnable(Runnable):
    """Runnable simulating structured LLM outputs with deterministic domain heuristics."""

    def __init__(self, schema: Type[BaseModel], model_size: str = "small"):
        self.schema = schema
        self.model_size = model_size

    def invoke(self, input: Any, config: Optional[Dict[str, Any]] = None) -> Any:
        # Extract combined text content from input
        text = ""
        if isinstance(input, list):
            text = " ".join(str(m.content) if hasattr(m, "content") else str(m) for m in input)
        elif hasattr(input, "content"):
            text = str(input.content)
        else:
            text = str(input)

        text_lower = text.lower()

        # 1. Document Extraction Schema
        if self.schema == DocumentExtractionResult:
            # Isolate raw document text if wrapped in delimiter
            doc_body = text
            if "--- BEGIN DOCUMENT TEXT ---" in text:
                doc_body = text.split("--- BEGIN DOCUMENT TEXT ---")[1].split("--- END DOCUMENT TEXT ---")[0]
            elif "Raw Document Text:" in text:
                doc_body = text.split("Raw Document Text:")[-1]
            doc_lower = doc_body.lower()

            # Injection detection
            injection_patterns = [
                r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
                r"system\s+override",
                r"you\s+must\s+(approve|set\s+case\s+status)",
                r"disregard\s+(all\s+)?rules",
                r"admin(istrator)?\s+mode",
                r"pretend\s+you\s+are",
                r"jailbreak",
            ]
            is_injection = any(re.search(pat, doc_lower) for pat in injection_patterns)
            
            # Low OCR confidence detection
            is_low_conf = "unreadable" in doc_lower or "[unreadable" in doc_lower or "blur" in doc_lower or "???" in doc_lower
            
            # Extract basic fields
            amount_match = re.search(r"\$\s*([0-9,]+(?:\.[0-9]{2})?)", doc_body)
            total_amt = float(amount_match.group(1).replace(",", "")) if amount_match else None
            
            name_match = re.search(r"(?:claimant|patient|name)\s*[:=]\s*([A-Za-z\s]+)", doc_body, re.IGNORECASE)
            name = name_match.group(1).strip().split("\n")[0] if name_match else None
            
            pol_match = re.search(r"\b(POL-[A-Z0-9-]+)\b", doc_body)
            pol = pol_match.group(1) if pol_match else None
            
            doc_type = "claim_form"
            if "itemized" in doc_lower or "hospital - itemized bill" in doc_lower:
                doc_type = "itemized_bill"
            elif "clinical" in doc_lower or "medical record" in doc_lower:
                doc_type = "medical_record"
                
            confidence = 0.42 if is_low_conf else (0.95 if not is_injection else 0.88)
            status = "SUSPECTED_INJECTION" if is_injection else ("LOW_CONFIDENCE" if is_low_conf else "VALID")

            return DocumentExtractionResult(
                doc_type=doc_type,
                confidence=confidence,
                claimant_name=name,
                policy_number=pol,
                date_of_service="2026-10-15",
                total_amount=total_amt,
                diagnosis="Acute Condition" if not is_low_conf else None,
                procedure="Medical Treatment" if not is_low_conf else None,
                extracted_fields={
                    "claimant_name": name,
                    "policy_number": pol,
                    "total_amount": total_amt,
                    "doc_type": doc_type,
                },
                is_injection_flagged=is_injection,
                injection_rationale="Adversarial instruction detected: attempted bypass of policy review." if is_injection else None,
                validation_status=status,
            )

        # 2. Case Summary Schema
        elif self.schema == CaseSummaryResult:
            is_exclusion = "cosmetic" in text_lower or "experimental" in text_lower or "exclusion" in text_lower or "out of policy" in text_lower
            is_missing = "missing" in text_lower or "pending" in text_lower
            is_injection = "injection" in text_lower or "adversarial" in text_lower
            
            case_id_match = re.search(r"\b(CASE-[A-Z0-9-]+)\b", text)
            cid = case_id_match.group(1) if case_id_match else "CASE-UNKNOWN"
            
            risks = []
            citations = []
            next_action = "APPROVE"
            
            if is_exclusion:
                risks.append("Procedure classified under elective/cosmetic exclusions without prior medical necessity approval.")
                citations.append("Clause 3.1: Exclusions & Non-Covered Elective Services")
                next_action = "REJECT"
            elif is_missing:
                risks.append("Required itemized facility bill or primary diagnosis physician notes absent.")
                next_action = "REQUEST_DOCUMENTS"
            elif is_injection:
                risks.append("Document text contained prohibited prompt-override attempt.")
                next_action = "MANUAL_REVIEW"
            else:
                citations.append("Clause 2.1: Inpatient & Emergency Hospitalization Coverage")
                citations.append("Clause 4.3: Prior Authorization Guidelines")

            return CaseSummaryResult(
                case_id=cid,
                facts="Claimant incurred eligible inpatient hospital services on 2026-10-15.",
                evidence="Verified against itemized billing breakdown and attending physician statement.",
                missing_info="None" if not is_missing else "Itemized hospital bill required.",
                risks=risks,
                policy_citations=citations,
                next_action=next_action,
            )

        # 3. Routing Schema
        elif self.schema == RoutingResult:
            case_id_match = re.search(r"\b(CASE-[A-Z0-9-]+)\b", text)
            cid = case_id_match.group(1) if case_id_match else "CASE-UNKNOWN"
            
            amt_match = re.search(r"\$\s*([0-9,]+(?:\.[0-9]{2})?)", text)
            claim_amt = float(amt_match.group(1).replace(",", "")) if amt_match else 2000.00
            
            # Tiering rules: <= 2500 -> APP-201, <= 10000 -> APP-202, > 10000 -> APP-203
            if claim_amt <= 2500.0:
                approver_id = "APP-201"
                limit = 2500.0
            elif claim_amt <= 10000.0:
                approver_id = "APP-202"
                limit = 10000.0
            else:
                approver_id = "APP-203"
                limit = 100000.0
                
            return RoutingResult(
                case_id=cid,
                assigned_adjuster_id="ADJ-103", # Elena Rostova has lowest workload (1)
                assigned_approver_id=approver_id,
                approver_limit=limit,
                claim_amount=claim_amt,
                rationale=f"Routed to adjuster ADJ-103 (lowest active load) and {approver_id} whose ${limit:,.2f} limit covers claim amount.",
                status="ROUTED_FOR_APPROVAL",
            )

        # 4. Fallback for any other BaseModel
        return self.schema.model_validate({})


class MockChatModel(BaseChatModel):
    """Deterministic, zero-cost Mock Chat Model for offline testing and verification."""

    model_size: str = "small"
    model_name: str = "mock-insurance-agent-llm"

    @property
    def _llm_type(self) -> str:
        return "mock-chat-model"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        full_text = " ".join(str(m.content) for m in messages)
        response_content = (
            f"[Mock LLM Response ({self.model_size})] Processed {len(messages)} messages. "
            f"Evaluated input with 0 token cost and deterministic policy adherence."
        )
        generation = ChatGeneration(message=AIMessage(content=response_content))
        return ChatResult(generations=[generation])

    def with_structured_output(self, schema: Union[Dict[str, Any], Type[BaseModel]], **kwargs) -> Runnable:
        """Return deterministic structured output runnable conforming to target schema."""
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            return MockStructuredRunnable(schema=schema, model_size=self.model_size)
        return super().with_structured_output(schema, **kwargs)

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Any:
        return self


def get_llm(model_size: str = "small") -> BaseChatModel:
    """Return configured LLM instance:
    - If MOCK_LLM=true or GEMINI_API_KEY is not set: returns MockChatModel
    - If MOCK_LLM=false and GEMINI_API_KEY is set: returns ChatGoogleGenerativeAI
    """
    mock_env = os.getenv("MOCK_LLM", "true").lower() in ("true", "1", "yes")
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    if mock_env or not gemini_key:
        return MockChatModel(model_size=model_size)

    # Live Gemini Provider
    from langchain_google_genai import ChatGoogleGenerativeAI
    model_name = "gemini-2.5-flash" if model_size == "small" else "gemini-2.5-pro"
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=gemini_key,
        temperature=0.0,
    )
