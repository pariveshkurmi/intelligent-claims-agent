"""Audit logging helper for appending events into case_timeline_audit."""

import json
from typing import Any, Dict, Optional
from src.db.connection import execute_mutation


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
