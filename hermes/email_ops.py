"""Lightweight deliverability helpers inspired by newsletter ops checklists.

Not a full ESP — validates addresses, classifies bounce risk, and manages
suppression layers before outreach drafts leave the machine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from email_validator import EmailNotValidError, validate_email
from sqlalchemy.orm import Session

from hermes.db import Suppression, utcnow

DISPOSABLE_DOMAINS = {
    "mailinator.com",
    "guerrillamail.com",
    "tempmail.com",
    "10minutemail.com",
    "trashmail.com",
    "yopmail.com",
    "sharklasers.com",
}

TYPO_DOMAINS = {
    "gmal.com": "gmail.com",
    "gmial.com": "gmail.com",
    "yahooo.com": "yahoo.com",
    "hotnail.com": "hotmail.com",
    "outlok.com": "outlook.com",
}


@dataclass
class EmailCheck:
    email: str
    ok: bool
    status: str
    reason: str = ""
    normalized: str = ""


def classify_bounce(message: str) -> str:
    text = (message or "").lower()
    if any(x in text for x in ["user unknown", "does not exist", "mailbox unavailable", "550"]):
        return "hard"
    if any(x in text for x in ["mailbox full", "quota", "over quota"]):
        return "mailbox_full"
    if any(x in text for x in ["dns", "nxdomain", "host not found"]):
        return "dns_failure"
    if any(x in text for x in ["try again", "temporarily deferred", "421", "450", "451"]):
        return "soft"
    return "unknown"


def validate_address(raw: Optional[str]) -> EmailCheck:
    if not raw or not str(raw).strip():
        return EmailCheck(email="", ok=False, status="missing", reason="No email provided")

    candidate = str(raw).strip().lower()
    if re.search(r"\s", candidate) or candidate.count("@") != 1:
        return EmailCheck(email=candidate, ok=False, status="invalid", reason="Malformed address")

    local, domain = candidate.split("@", 1)
    if domain in DISPOSABLE_DOMAINS:
        return EmailCheck(
            email=candidate,
            ok=False,
            status="disposable",
            reason="Disposable mailbox blocked",
        )
    if domain in TYPO_DOMAINS:
        return EmailCheck(
            email=candidate,
            ok=False,
            status="typo",
            reason=f"Likely typo — did you mean {TYPO_DOMAINS[domain]}?",
        )
    if local in {"admin", "postmaster", "abuse"} and domain in {"example.com", "test.com"}:
        return EmailCheck(email=candidate, ok=False, status="invalid", reason="Placeholder address")

    try:
        result = validate_email(candidate, check_deliverability=False)
        normalized = result.normalized
        return EmailCheck(email=normalized, ok=True, status="valid", normalized=normalized)
    except EmailNotValidError as exc:
        return EmailCheck(email=candidate, ok=False, status="invalid", reason=str(exc))


def is_suppressed(session: Session, email: str) -> Optional[Suppression]:
    if not email:
        return None
    row = session.query(Suppression).filter(Suppression.email == email.lower()).one_or_none()
    if not row:
        return None
    if not row.permanent and row.expires_at and row.expires_at < utcnow():
        session.delete(row)
        return None
    return row


def add_suppression(
    session: Session,
    email: str,
    reason: str,
    *,
    layer: str = "global",
    permanent: bool = True,
    expires_at: Optional[datetime] = None,
) -> Suppression:
    existing = session.query(Suppression).filter(Suppression.email == email.lower()).one_or_none()
    if existing:
        existing.reason = reason
        existing.layer = layer
        existing.permanent = permanent
        existing.expires_at = expires_at
        return existing
    row = Suppression(
        email=email.lower(),
        reason=reason,
        layer=layer,
        permanent=permanent,
        expires_at=expires_at,
    )
    session.add(row)
    return row


MERGE_TAG_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def apply_merge_tags(template: str, values: dict) -> str:
    def repl(match: re.Match) -> str:
        key = match.group(1)
        return str(values.get(key, match.group(0)))

    return MERGE_TAG_PATTERN.sub(repl, template)