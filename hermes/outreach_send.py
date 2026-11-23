"""Send / open drafts via mailto, tel, or optional SMTP."""

from __future__ import annotations

import smtplib
import urllib.parse
from email.message import EmailMessage
from typing import Any, Dict, Optional

from hermes.config import get_settings
from hermes.db import Lead, OutreachMessage, session_scope
from hermes.agents.pipeline import mark_as_lead


def build_mailto(lead: Lead, message: OutreachMessage, subject_variant: str = "a") -> Optional[str]:
    email = lead.contact.email if lead.contact else None
    if not email:
        return None
    subject = message.subject_a if subject_variant != "b" else message.subject_b
    subject = subject or "Quick idea from Intellytics"
    query = urllib.parse.urlencode({"subject": subject, "body": message.body})
    return f"mailto:{email}?{query}"


def build_tel(lead: Lead) -> Optional[str]:
    phone = lead.phone_captured or (lead.contact.phone if lead.contact else None)
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
    return f"tel:{digits}" if digits else None


def send_via_smtp(to_email: str, subject: str, body: str) -> Dict[str, Any]:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_user:
        return {"ok": False, "error": "SMTP not configured (SMTP_HOST / SMTP_USER)"}
    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            smtp.starttls()
            if settings.smtp_password:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        return {"ok": True, "channel": "smtp"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def prepare_send(
    listing_id: int,
    *,
    subject_variant: str = "a",
    mark_sent: bool = True,
    use_smtp: bool = False,
) -> Dict[str, Any]:
    with session_scope() as session:
        lead = session.get(Lead, listing_id)
        if not lead:
            return {"ok": False, "error": "Listing not found"}
        message = (
            session.query(OutreachMessage)
            .filter(OutreachMessage.lead_id == listing_id)
            .order_by(OutreachMessage.id.desc())
            .first()
        )
        if not message:
            return {"ok": False, "error": "No outreach draft — run backfill"}

        mailto = build_mailto(lead, message, subject_variant)
        tel = build_tel(lead)
        subject = message.subject_a if subject_variant != "b" else message.subject_b
        result: Dict[str, Any] = {
            "ok": True,
            "listing_id": listing_id,
            "mailto": mailto,
            "tel": tel,
            "subject": subject,
            "body": message.body,
            "email": lead.contact.email if lead.contact else None,
            "phone": lead.phone_captured or (lead.contact.phone if lead.contact else None),
            "source_url": lead.source_url,
        }

        if use_smtp and lead.contact and lead.contact.email:
            smtp_result = send_via_smtp(lead.contact.email, subject or "Hello", message.body)
            result["smtp"] = smtp_result
            if smtp_result.get("ok") and mark_sent:
                mark_as_lead(session, listing_id, note="Sent via SMTP")
                result["record_kind"] = "lead"
                result["stage"] = "contacted"
            return result

        if mark_sent and (mailto or tel):
            # User will send via client; we still convert listing → lead when they click Send
            mark_as_lead(session, listing_id, note="Send action opened (mailto/tel)")
            result["record_kind"] = "lead"
            result["stage"] = "contacted"
        return result
