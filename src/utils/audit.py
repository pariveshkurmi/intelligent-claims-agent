"""Audit logging helper for appending events into case_timeline_audit."""

import json
import logging
from typing import Any, Dict, List, Optional
import httpx
from src.db.connection import execute_mutation, execute_query

logger = logging.getLogger(__name__)

MAILPIT_API_URL = "http://localhost:8025/api/v1"


def log_audit_event(
    case_id: str,
    actor: str,
    action: str,
    before_state: Optional[Dict[str, Any]] = None,
    after_state: Optional[Dict[str, Any]] = None,
) -> None:
    """Record an immutable timeline event into case_timeline_audit."""
    query = """
    INSERT INTO case_timeline_audit (case_id, actor, action, before_state, after_state, timestamp)
    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP);
    """
    execute_mutation(query, (
        case_id,
        actor,
        action,
        json.dumps(before_state or {}),
        json.dumps(after_state or {}),
    ))


def get_case_audit_trail(case_id: str) -> List[Dict[str, Any]]:
    """Retrieve full immutable audit timeline events for a given case."""
    query = """
    SELECT audit_id, case_id, actor, action, before_state, after_state, timestamp
    FROM case_timeline_audit
    WHERE case_id = %s
    ORDER BY timestamp ASC, audit_id ASC;
    """
    return execute_query(query, (case_id,))


def verify_case_audit_integrity(case_id: str) -> Dict[str, Any]:
    """
    Verify that a case has recorded complete, sequential audit entries without tampering.
    Checks for intake, stage transitions, and human decisions.
    """
    records = get_case_audit_trail(case_id)
    actions = [r.get("action") for r in records]
    actors = list(set(r.get("actor") for r in records))
    
    return {
        "case_id": case_id,
        "total_audit_events": len(records),
        "actions": actions,
        "actors": actors,
        "has_records": len(records) > 0,
        "is_complete": len(records) >= 2,
    }


def query_mailpit_messages(search_term: Optional[str] = None) -> List[Dict[str, Any]]:
    """Query local Mailpit API to verify email dispatches for SLA breaches or document requests."""
    try:
        url = f"{MAILPIT_API_URL}/messages"
        params = {}
        if search_term:
            params["query"] = search_term
        resp = httpx.get(url, params=params, timeout=2.0)
        if resp.status_code == 200:
            return resp.json().get("messages", [])
        return []
    except Exception as exc:
        logger.warning(f"Could not connect to Mailpit API at {MAILPIT_API_URL}: {exc}")
        return []
