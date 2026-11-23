from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from hermes.config import get_settings
from hermes.db import Company, Deal, Lead, OutreachMessage, ScanRun


def dashboard_kpis(session: Session) -> Dict[str, Any]:
    settings = get_settings()
    rows: List[Lead] = (
        session.query(Lead)
        .options(joinedload(Lead.company), joinedload(Lead.contact), joinedload(Lead.deal))
        .all()
    )
    active = [l for l in rows if not l.suppressed and not l.expired and l.stage != "lost"]
    listings = [l for l in active if (l.record_kind or "listing") == "listing"]
    leads = [l for l in active if l.record_kind == "lead"]
    deals: List[Deal] = session.query(Deal).all()
    outreach: List[OutreachMessage] = session.query(OutreachMessage).all()

    stage_counts = Counter(l.stage for l in active)
    platform_counts = Counter(l.source_platform for l in active)
    revenue_bands = Counter(
        (l.company.revenue_band if l.company and l.company.revenue_band else "unknown")
        for l in active
    )

    pipeline_value = sum((l.estimated_deal_value or 0) for l in active)
    weighted_pipeline = sum(
        int((d.value_usd or 0) * (d.probability or 0)) for d in deals if d.status == "open"
    )
    won_value = sum(d.value_usd for d in deals if d.status == "won")
    strong = sum(1 for l in active if l.fit_score >= settings.strong_lead_min_score)
    with_draft = len({o.lead_id for o in outreach})
    missing_draft = sum(
        1
        for l in active
        if not any(o.lead_id == l.id for o in outreach)
    )
    hot = sum(1 for l in active if l.fit_score >= 65)
    avg_deal = int(pipeline_value / len(active)) if active else 0

    conversion = {
        "listing_to_lead": _pct(len(leads), max(1, len(listings) + len(leads))),
        "lead_to_reply": _pct(
            sum(1 for l in leads if l.stage in {"replied", "negotiation", "won"}),
            max(1, len(leads)),
        ),
        "reply_to_won": _pct(
            sum(1 for l in leads if l.stage == "won"),
            max(1, sum(1 for l in leads if l.stage in {"replied", "negotiation", "won"})),
        ),
        "outreach_to_reply": _pct(
            sum(1 for l in leads if l.stage in {"replied", "negotiation", "won"}),
            max(1, sum(1 for l in leads if l.stage in {"contacted", "outreach", "replied", "negotiation", "won"})),
        ),
        "reply_to_won_legacy": 0.0,
    }

    funnel = [
        {"stage": "Active listings", "count": len(listings)},
        {"stage": "Strong fit", "count": strong},
        {"stage": "Drafts ready", "count": with_draft},
        {"stage": "Engaged leads", "count": len(leads)},
        {"stage": "Won", "count": stage_counts.get("won", 0)},
    ]

    recent_scans = session.query(ScanRun).order_by(ScanRun.started_at.desc()).limit(8).all()
    action_queue = sorted(
        [l for l in active if l.stage not in {"won", "lost", "expired", "suppressed"}],
        key=lambda x: (
            0 if x.record_kind == "lead" and x.stage in {"replied", "negotiation"} else 1,
            0 if x.fit_score >= settings.strong_lead_min_score else 1,
            -(x.fit_score or 0),
            -(x.created_at.timestamp() if x.created_at else 0),
        ),
    )[:10]

    by_platform_value = defaultdict(int)
    for l in active:
        by_platform_value[l.source_platform] += l.estimated_deal_value or 0

    return {
        "totals": {
            "listings": len(listings),
            "leads": len(leads),
            "active_records": len(active),
            "active_leads": len(active),  # legacy alias for UI
            "companies": session.query(func.count(Company.id)).scalar() or 0,
            "strong_leads": strong,
            "strong_listings": strong,
            "strong_lead_target": settings.strong_lead_target,
            "strong_lead_min_score": settings.strong_lead_min_score,
            "hot_leads": hot,
            "drafts_ready": with_draft,
            "missing_drafts": missing_draft,
            "expired": sum(1 for l in rows if l.expired),
            "revenue_fit": sum(1 for l in active if l.revenue_fit),
            "icp_pass_rate": _pct(strong, max(1, len(active))),
            "outreach_drafts": len(outreach),
            "ready_to_send": with_draft,
            "in_negotiation": sum(1 for l in leads if l.stage in {"replied", "negotiation"}),
            "awaiting_reply": sum(1 for l in leads if l.stage in {"contacted", "outreach"}),
            "open_deals": sum(1 for d in deals if d.status == "open"),
            "won_deals": sum(1 for d in deals if d.status == "won"),
            "pipeline_value": pipeline_value,
            "weighted_pipeline": weighted_pipeline,
            "won_value": won_value,
            "avg_deal_value": avg_deal,
            "avg_fit_score": round(
                (sum(l.fit_score for l in active) / len(active)) if active else 0,
                1,
            ),
            "listing_ttl_days": settings.listing_ttl_days,
        },
        "stages": dict(stage_counts),
        "platforms": dict(platform_counts),
        "platform_pipeline_value": dict(by_platform_value),
        "revenue_bands": dict(revenue_bands),
        "confidence": dict(Counter(l.confidence for l in active)),
        "conversion": conversion,
        "funnel": funnel,
        "action_queue": [_serialize_lead(l) for l in action_queue],
        "top_leads": [_serialize_lead(l) for l in action_queue[:12]],
        "recent_scans": [
            {
                "id": s.id,
                "status": s.status,
                "signals_found": s.signals_found,
                "leads_created": s.leads_created,
                "qualified": s.qualified,
                "outreach_drafted": s.outreach_drafted,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
            }
            for s in recent_scans
        ],
        "empty": len(active) == 0,
        "naming": {
            "listing": "Crawled opportunity (not a lead yet)",
            "lead": "Engaged — we sent or they replied",
        },
    }


def _pct(num: int, den: int) -> float:
    if den <= 0:
        return 0.0
    return round(100.0 * num / den, 1)


def _serialize_lead(lead: Lead) -> Dict[str, Any]:
    return {
        "id": lead.id,
        "record_kind": lead.record_kind or "listing",
        "stage": lead.stage,
        "fit_score": lead.fit_score,
        "confidence": lead.confidence,
        "source_platform": lead.source_platform,
        "source_title": lead.source_title,
        "source_url": lead.source_url,
        "project_summary": lead.project_summary,
        "estimated_deal_value": lead.estimated_deal_value,
        "revenue_fit": lead.revenue_fit,
        "title_fit": lead.title_fit,
        "keyword_fit": lead.keyword_fit,
        "score_reasons": lead.score_reasons or [],
        "tags": lead.tags or [],
        "review_required": lead.review_required,
        "expired": bool(lead.expired),
        "expires_at": lead.expires_at.isoformat() if lead.expires_at else None,
        "posted_at": lead.posted_at.isoformat() if lead.posted_at else None,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "phone_captured": lead.phone_captured,
        "company": {
            "id": lead.company.id if lead.company else None,
            "name": lead.company.name if lead.company else None,
            "industry": lead.company.industry if lead.company else None,
            "employee_count": lead.company.employee_count if lead.company else None,
            "revenue_usd": lead.company.revenue_usd if lead.company else None,
            "revenue_band": lead.company.revenue_band if lead.company else None,
            "location": lead.company.location if lead.company else None,
        },
        "contact": {
            "id": lead.contact.id if lead.contact else None,
            "full_name": lead.contact.full_name if lead.contact else None,
            "title": lead.contact.title if lead.contact else None,
            "email": lead.contact.email if lead.contact else None,
            "email_status": lead.contact.email_status if lead.contact else None,
            "phone": lead.contact.phone if lead.contact else None,
        },
        "deal": {
            "id": lead.deal.id if lead.deal else None,
            "value_usd": lead.deal.value_usd if lead.deal else None,
            "probability": lead.deal.probability if lead.deal else None,
            "status": lead.deal.status if lead.deal else None,
            "next_step": lead.deal.next_step if lead.deal else None,
        }
        if lead.deal
        else None,
    }


def list_leads(
    session: Session,
    *,
    stage: str | None = None,
    platform: str | None = None,
    min_score: float = 0,
    revenue_fit_only: bool = False,
    record_kind: str | None = None,
    include_expired: bool = False,
) -> List[Dict[str, Any]]:
    q = session.query(Lead).options(
        joinedload(Lead.company), joinedload(Lead.contact), joinedload(Lead.deal)
    )
    if not include_expired:
        q = q.filter(Lead.expired.is_(False))
    if stage:
        q = q.filter(Lead.stage == stage)
    if platform:
        q = q.filter(Lead.source_platform == platform)
    if min_score:
        q = q.filter(Lead.fit_score >= min_score)
    if revenue_fit_only:
        q = q.filter(Lead.revenue_fit.is_(True))
    if record_kind:
        q = q.filter(Lead.record_kind == record_kind)
    rows = q.order_by(Lead.created_at.desc(), Lead.fit_score.desc()).all()
    return [_serialize_lead(r) for r in rows]
