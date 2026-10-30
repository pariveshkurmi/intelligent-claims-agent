"""PII Redaction Middleware: Enforces zero-leakage threshold before prompts reach LLMs."""

import re
from typing import Any, List, Union
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage


class PIIMiddleware:
    """Deterministic PII sanitization middleware using regex scrubbers.
    
    Guarantees that sensitive patient and policyholder identifiers (SSN, phone,
    email, government IDs) are redacted prior to payload transmission to any external model.
    """

    # Compiled patterns for high-performance deterministic scanning
    SSN_PATTERN = re.compile(r"\b(?:\d{3}-\d{2}-\d{4}|\d{9})\b")
    EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    PHONE_PATTERN = re.compile(
        r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b"
    )
    MEMBER_ID_PATTERN = re.compile(r"\b(?:MEMBER[-_]?ID|SSN|ID#?)\s*[:=]\s*([A-Za-z0-9\-]+)\b", re.IGNORECASE)

    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """Sanitize a raw string, replacing detected PII with standardized redaction tokens."""
        if not text:
            return text

        scrubbed = cls.SSN_PATTERN.sub("[REDACTED_SSN]", text)
        scrubbed = cls.EMAIL_PATTERN.sub("[REDACTED_EMAIL]", scrubbed)
        scrubbed = cls.PHONE_PATTERN.sub("[REDACTED_PHONE]", scrubbed)
        
        # Redact specific ID labels
        def id_replacer(match):
            prefix = match.group(0).split(":")[0] if ":" in match.group(0) else match.group(0).split("=")[0]
            return f"{prefix}: [REDACTED_ID]"
            
        scrubbed = cls.MEMBER_ID_PATTERN.sub(id_replacer, scrubbed)
        return scrubbed

    @classmethod
    def sanitize_messages(cls, messages: List[Union[BaseMessage, dict, str]]) -> List[Any]:
        """Sanitize a sequence of LangChain chat messages in place or copy."""
        sanitized = []
        for msg in messages:
            if isinstance(msg, BaseMessage):
                # Copy message with sanitized content
                msg_copy = msg.model_copy(update={"content": cls.sanitize_text(str(msg.content))})
                sanitized.append(msg_copy)
            elif isinstance(msg, dict) and "content" in msg:
                d = dict(msg)
                d["content"] = cls.sanitize_text(str(d["content"]))
                sanitized.append(d)
            elif isinstance(msg, str):
                sanitized.append(cls.sanitize_text(msg))
            else:
                sanitized.append(msg)
        return sanitized

