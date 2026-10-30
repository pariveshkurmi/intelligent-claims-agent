"""FastMCP Server for Workflow, Assignments, SLAs, and Mailpit Notifications."""

import json
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP
from src.db.connection import execute_mutation, execute_query
from src.utils.audit import log_audit_event

mcp = FastMCP("workflow-mcp")

SMTP_HOST = os.getenv("MAILPIT_SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("MAILPIT_SMTP_PORT", "1025"))


def _send_email_via_mailpit(recipient: str, subject: str, body: str) -> bool:
    """Send an email to Mailpit local SMTP server."""
    try:
        msg = MIMEMultipart()
        msg["From"] = "claims-automation@uhg.example.com"
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.sendmail(msg["From"], [recipient], msg.as_string())
        return True
    except Exception as e:
        print(f"Warning: Failed to dispatch email via Mailpit ({e})")
        return False


@mcp.tool()
def get_workload(role: Optional[str] = "adjuster") -> List[Dict[str, Any]]:
    """Query staff directory ordered by lowest active cases for balanced assignment."""
    if role:
        sql = """
            SELECT staff_id, name, role, email, active_cases, approval_limit
            FROM staff WHERE role = %s ORDER BY active_cases ASC, approval_limit ASC;
        """
        rows = execute_query(sql, (role,))
    else:
        sql = """
            SELECT staff_id, name, role, email, active_cases, approval_limit
            FROM staff ORDER BY active_cases ASC;
        """
        rows = execute_query(sql)

    for r in rows:
        r["approval_limit"] = float(r["approval_limit"])
    return rows


@mcp.tool()
def assign_case(
    case_id: str,
    staff_id: str,
    role: str,
    actor: str = "routing_agent",
) -> Dict[str, Any]:
    """Assign an adjuster or approver to a case and increment their active workload."""
    staff_rows = execute_query("SELECT staff_id, name, role FROM staff WHERE staff_id = %s;", (staff_id,))
    if not staff_rows:
        return {"error": f"Staff member '{staff_id}' not found."}

    staff_info = staff_rows[0]

    if role == "adjuster":
        col_to_update = "assigned_adjuster_id"
    elif role == "approver":
        col_to_update = "assigned_approver_id"
    else:
        return {"error": f"Invalid assignment role: '{role}'"}

    # Update case assignment
    execute_mutation(
        f"UPDATE cases SET {col_to_update} = %s, updated_at = CURRENT_TIMESTAMP WHERE case_id = %s;",
        (staff_id, case_id)
    )

    # Increment staff active workload
    execute_mutation(
        "UPDATE staff SET active_cases = active_cases + 1 WHERE staff_id = %s;",
        (staff_id,)
    )

    log_audit_event(
        case_id=case_id,
        actor=actor,
        action="CASE_ASSIGNED",
        before_state={},
        after_state={"assigned_staff_id": staff_id, "staff_name": staff_info["name"], "role": role},
    )

    return {
        "status": "success",
        "case_id": case_id,
        "assigned_to": staff_info["name"],
        "staff_id": staff_id,
        "role": role,
    }


@mcp.tool()
def request_approval(
    case_id: str,
    approver_id: str,
    claim_amount: float,
    actor: str = "routing_agent",
) -> Dict[str, Any]:
    """Route case to a qualified approver whose dollar authorization tier covers the claim amount.
    
    NOTE: In adherence to the Golden Rule, this tool requests approval and queues the case;
    it CANNOT approve, reject, or settle the claim.
    """
    approver_rows = execute_query(
        "SELECT staff_id, name, approval_limit FROM staff WHERE staff_id = %s AND role = 'approver';",
        (approver_id,)
    )
    if not approver_rows:
        return {"error": f"Approver '{approver_id}' not found in directory."}

    approver = approver_rows[0]
    limit = float(approver["approval_limit"])

    if claim_amount > limit:
        return {
            "error": "INSUFFICIENT_LIMIT",
            "message": f"Claim amount ${claim_amount:,.2f} exceeds approver limit of ${limit:,.2f} for {approver['name']}. Escalate to higher tier.",
            "approver_limit": limit,
            "claim_amount": claim_amount,
        }

    # Transition case status to READY_FOR_APPROVAL
    execute_mutation(
        """
        UPDATE cases
        SET assigned_approver_id = %s,
            status = 'READY_FOR_APPROVAL',
            updated_at = CURRENT_TIMESTAMP
        WHERE case_id = %s;
        """,
        (approver_id, case_id)
    )

    log_audit_event(
        case_id=case_id,
        actor=actor,
        action="APPROVAL_REQUESTED",
        before_state={"status": "ROUTING"},
        after_state={
            "status": "READY_FOR_APPROVAL",
            "approver_id": approver_id,
            "approver_name": approver["name"],
            "claim_amount": claim_amount,
        },
    )

    return {
        "status": "success",
        "case_id": case_id,
        "assigned_approver": approver["name"],
        "case_status": "READY_FOR_APPROVAL",
    }


@mcp.tool()
def schedule_sla(
    case_id: str,
    tier_name: str = "Standard Claim",
    actor: str = "sla_agent",
) -> Dict[str, Any]:
    """Calculate SLA target turnaround and escalation deadlines based on active rules."""
    rules = execute_query("SELECT * FROM sla_rules WHERE LOWER(tier_name) LIKE LOWER(%s);", (f"%{tier_name}%",))
    if not rules:
        rule = {
            "rule_id": "SLA-STANDARD",
            "tier_name": "Standard Claim",
            "max_turnaround_hours": 48,
            "escalation_threshold_hours": 36,
        }
    else:
        rule = rules[0]

    now = datetime.now(timezone.utc)
    target_deadline = now + timedelta(hours=rule["max_turnaround_hours"])
    escalation_deadline = now + timedelta(hours=rule["escalation_threshold_hours"])

    log_audit_event(
        case_id=case_id,
        actor=actor,
        action="SLA_SCHEDULED",
        before_state={},
        after_state={
            "rule_id": rule["rule_id"],
            "target_deadline": target_deadline.isoformat(),
            "escalation_deadline": escalation_deadline.isoformat(),
        },
    )

    return {
        "case_id": case_id,
        "rule_id": rule["rule_id"],
        "target_deadline": target_deadline.isoformat(),
        "escalation_deadline": escalation_deadline.isoformat(),
        "turnaround_hours": rule["max_turnaround_hours"],
    }


@mcp.tool()
def send_notification(
    case_id: str,
    recipient_email: str,
    subject: str,
    message: str,
    notification_type: str = "status_update",
    actor: str = "sla_agent",
) -> Dict[str, Any]:
    """Send an email notification via Mailpit and record event in timeline audit."""
    delivered = _send_email_via_mailpit(recipient_email, subject, message)

    log_audit_event(
        case_id=case_id,
        actor=actor,
        action="NOTIFICATION_SENT",
        before_state={},
        after_state={
            "recipient": recipient_email,
            "subject": subject,
            "type": notification_type,
            "delivered": delivered,
        },
    )

    return {
        "status": "success" if delivered else "warning",
        "case_id": case_id,
        "recipient": recipient_email,
        "delivered": delivered,
        "mailpit_ui": "http://localhost:8025",
    }


@mcp.tool()
def request_documents(
    case_id: str,
    claimant_email: str,
    missing_docs: List[str],
    actor: str = "sla_agent",
) -> Dict[str, Any]:
    """Transition case to DOCS_PENDING, email claimant via Mailpit, and pause for submission."""
    # Update case status to DOCS_PENDING
    execute_mutation(
        "UPDATE cases SET status = 'DOCS_PENDING', updated_at = CURRENT_TIMESTAMP WHERE case_id = %s;",
        (case_id,)
    )

    docs_list_str = "\n".join([f"- {d.replace('_', ' ').title()}" for d in missing_docs])
    subject = f"Action Required: Missing Documentation for Claim {case_id}"
    body = (
        f"Dear Claimant,\n\n"
        f"We have begun reviewing your claim ({case_id}). To complete our coverage evaluation, "
        f"please provide the following missing documentation within 7 business days:\n\n"
        f"{docs_list_str}\n\n"
        f"You can upload these files through your secure claims portal.\n\n"
        f"Sincerely,\nUHG Claims Operations Team"
    )

    delivered = _send_email_via_mailpit(claimant_email, subject, body)

    log_audit_event(
        case_id=case_id,
        actor=actor,
        action="DOCUMENTS_REQUESTED",
        before_state={"status": "DOCUMENT_REVIEW"},
        after_state={
            "status": "DOCS_PENDING",
            "missing_docs": missing_docs,
            "email_sent": delivered,
        },
    )

    return {
        "status": "success",
        "case_id": case_id,
        "new_case_status": "DOCS_PENDING",
        "missing_docs": missing_docs,
        "email_delivered": delivered,
    }


# --- FastMCP Resources ---

@mcp.resource("staff://directory")
def get_staff_directory_resource() -> str:
    """Read-only resource returning active directory of staff and authorization limits."""
    rows = execute_query("SELECT staff_id, name, role, email, active_cases, approval_limit FROM staff;")
    for r in rows:
        r["approval_limit"] = float(r["approval_limit"])
    return json.dumps(rows, indent=2)


@mcp.resource("sla://rules")
def get_sla_rules_resource() -> str:
    """Read-only resource returning SLA thresholds and turnaround matrices."""
    rows = execute_query("SELECT * FROM sla_rules;")
    return json.dumps(rows, indent=2)


# --- FastMCP Prompts ---

@mcp.prompt()
def claimant_letter(case_id: str, claimant_name: str, missing_docs: str) -> str:
    """Reusable template for drafting a professional missing document letter to claimant."""
    return f"""Draft a professional, clear, and compassionate email to {claimant_name} regarding claim {case_id}.
Inform them that their claim is currently in progress, but we need the following documentation:
{missing_docs}

Highlight the 7-day submission window and provide instructions on where to upload files. Maintain UHG brand voice."""


@mcp.prompt()
def approver_brief(case_id: str, claim_amount: float, risks: str) -> str:
    """Reusable template for preparing a concise approver brief for human sign-off."""
    return f"""Prepare a concise 1-page decision brief for the Senior Approver for Case {case_id}.
Total Claimed: ${claim_amount:,.2f}
Identified Policy & Clinical Risks:
{risks}

Include:
1. Executive Recommendation (Approve / Reject / Request Info)
2. Relevant Policy Clause Citations
3. Suggested Rationale for the official decision log."""


if __name__ == "__main__":
    mcp.run()
