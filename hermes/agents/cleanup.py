from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from hermes.config import get_settings
from hermes.db import (
    Activity,
    Company,
    Contact,
    Deal,
    Lead,
    OutreachMessage,
    ScanRun,
    Suppression,
    init_db,
    session_scope,
    utcnow,
)


def expire_stale_listings(session: Session) -> int:
    """Mark calendar-expired listings and prune low-value old noise."""
    settings = get_settings()
    now = utcnow()
    expired_n = 0

    due = (
        session.query(Lead)
        .filter(
            Lead.expired.is_(False),
            Lead.suppressed.is_(False),
            Lead.record_kind == "listing",
            Lead.expires_at.isnot(None),
            Lead.expires_at < now,
        )
        .all()
    )
    for row in due:
        row.expired = True
        row.stage = "expired"
        session.add(
            Activity(
                lead_id=row.id,
                kind="expired",
                message=f"Listing expired on {row.expires_at.isoformat() if row.expires_at else 'n/a'}",
            )
        )
        expired_n += 1

    # Soft TTL for listings missing expires_at
    cutoff = now - timedelta(days=settings.listing_ttl_days)
    undated = (
        session.query(Lead)
        .filter(
            Lead.expired.is_(False),
            Lead.suppressed.is_(False),
            Lead.record_kind == "listing",
            Lead.expires_at.is_(None),
            Lead.created_at < cutoff,
        )
        .all()
    )
    for row in undated:
        row.expired = True
        row.stage = "expired"
        row.expires_at = now
        expired_n += 1
        session.add(
            Activity(lead_id=row.id, kind="expired", message="Auto-expired by listing TTL")
        )

    # Keep dashboard meaningful: archive weak old listings beyond keep window
    keep_cutoff = now - timedelta(days=settings.keep_expired_days)
    weak = (
        session.query(Lead)
        .filter(
            Lead.expired.is_(True),
            Lead.record_kind == "listing",
            Lead.fit_score < settings.strong_lead_min_score,
            Lead.updated_at < keep_cutoff,
        )
        .limit(500)
        .all()
    )
    for row in weak:
        # hard-delete weak expired listings (not engaged leads)
        lids = [row.id]
        session.query(Activity).filter(Activity.lead_id.in_(lids)).delete(synchronize_session=False)
        session.query(OutreachMessage).filter(OutreachMessage.lead_id.in_(lids)).delete(
            synchronize_session=False
        )
        session.query(Deal).filter(Deal.lead_id.in_(lids)).delete(synchronize_session=False)
        session.query(Lead).filter(Lead.id.in_(lids)).delete(synchronize_session=False)

    return expired_n


def run_expiry_pass() -> dict:
    init_db()
    with session_scope() as session:
        n = expire_stale_listings(session)
        active = (
            session.query(Lead)
            .filter(Lead.expired.is_(False), Lead.suppressed.is_(False))
            .count()
        )
        leads = session.query(Lead).filter(Lead.record_kind == "lead", Lead.expired.is_(False)).count()
        listings = (
            session.query(Lead)
            .filter(Lead.record_kind == "listing", Lead.expired.is_(False), Lead.suppressed.is_(False))
            .count()
        )
        return {
            "expired_marked": n,
            "active_records": active,
            "active_listings": listings,
            "active_leads": leads,
        }


def cleanup_leads(*, mode: str = "all") -> dict:
    """Wipe CRM rows so continuous hunting starts clean.

    mode:
      - all: wipe leads/deals/outreach/companies/contacts/scans
      - demo: remove *.example seed rows
      - expired: run expiry + prune weak expired listings
    """
    init_db()
    if mode == "expired":
        return {"mode": "expired", "result": run_expiry_pass()}

    deleted = {
        "leads": 0,
        "deals": 0,
        "outreach": 0,
        "activities": 0,
        "companies": 0,
        "contacts": 0,
        "scans": 0,
    }
    with session_scope() as session:
        if mode == "demo":
            leads = session.query(Lead).all()
            demo_ids = []
            for lead in leads:
                domain = (lead.company.domain if lead.company else "") or ""
                if domain.endswith(".example"):
                    demo_ids.append(lead.id)
            demo_ids = list(set(demo_ids))
            if demo_ids:
                deleted["activities"] = (
                    session.query(Activity)
                    .filter(Activity.lead_id.in_(demo_ids))
                    .delete(synchronize_session=False)
                )
                deleted["outreach"] = (
                    session.query(OutreachMessage)
                    .filter(OutreachMessage.lead_id.in_(demo_ids))
                    .delete(synchronize_session=False)
                )
                deleted["deals"] = (
                    session.query(Deal).filter(Deal.lead_id.in_(demo_ids)).delete(synchronize_session=False)
                )
                deleted["leads"] = (
                    session.query(Lead).filter(Lead.id.in_(demo_ids)).delete(synchronize_session=False)
                )
            deleted["contacts"] = (
                session.query(Contact)
                .filter(Contact.email.ilike("%.example"))
                .delete(synchronize_session=False)
            )
            deleted["companies"] = (
                session.query(Company)
                .filter(Company.domain.ilike("%.example"))
                .delete(synchronize_session=False)
            )
            return {"mode": mode, "deleted": deleted}

        deleted["activities"] = session.query(Activity).delete()
        deleted["outreach"] = session.query(OutreachMessage).delete()
        deleted["deals"] = session.query(Deal).delete()
        deleted["leads"] = session.query(Lead).delete()
        deleted["contacts"] = session.query(Contact).delete()
        deleted["companies"] = session.query(Company).delete()
        deleted["scans"] = session.query(ScanRun).delete()
        session.query(Suppression).delete()
        return {"mode": "all", "deleted": deleted}
