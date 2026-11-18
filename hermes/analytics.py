from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from hermes.db import Company, Deal, Lead, OutreachMessage, ScanRun


def dashboard_kpis(session: Session) -> Dict[str, Any]:
    leads: List[Lead] = (
        session.query(Lead)
        .options(joinedload(Lead.company), joinedload(Lead.contact), joinedload(Lead.deal))
        .all()
    )
    deals: List[Deal] = session.query(Deal).all()
    outreach: List[OutreachMessage] = session.query(OutreachMessage).all()

    active = [l for l in leads if not l.suppressed and l.stage != "lost"]
    stage_counts = Counter(l.stage for l in leads)
    platform_counts = Counter(l.source_platform for l in leads)
    revenue_bands = Counter(
        (l.company.revenue_band if l.company and l.company.revenue_band else "unknown")
        for l in leads
    )
    confidence = Counter(l.confidence for l in leads)

    pipeline_value = sum((l.estimated_deal_value or 0) for l in active)
    weighted_pipeline = sum(
        int((d.value_usd or 0) * (d.probability or 0)) for d in deals if d.status == "open"
    )
    won_value = sum(d.value_usd for d in deals if d.status == "won")
    qualified = sum(1 for l in leads if l.fit_score >= 55 and not l.suppressed)
    revenue_fit = sum(1 for l in leads if l.revenue_fit)
    high_conf = sum(1 for l in leads if l.confidence == "high" and not l.suppressed)
    from hermes.config import get_settings

    settings = get_settings()
    hot = sum(1 for l in active if l.fit_score >= 75)
    strong = sum(1 for l in active if l.fit_score >= settings.strong_lead_min_score)
    needs_review = sum(1 for l in active if l.review_required)
    ready_to_send = sum(
        1 for l in active if l.stage == "outreach" and any(o.status == "draft" for o in l.outreach)
    )
    awaiting_reply = sum(1 for l in active if l.stage == "outreach")
    in_negotiation = sum(1 for l in active if l.stage in {"replied", "negotiation"})
    avg_deal = int(pipeline_value / len(active)) if active else 0
    icp_pass_rate = _pct(revenue_fit, max(1, len([l for l in leads if not l.suppressed])))

    conversion = {
        "signal_to_lead": 100.0 if leads else 0.0,
        "lead_to_qualified": _pct(
            sum(1 for l in leads if l.stage in {"qualified", "outreach", "replied", "negotiation", "won"}),
            max(1, len([l for l in leads if not l.suppressed])),
        ),
        "qualified_to_outreach": _pct(
            sum(1 for l in leads if l.stage in {"outreach", "replied", "negotiation", "won"}),
            max(
                1,
                sum(
                    1
                    for l in leads
                    if l.stage in {"qualified", "outreach", "replied", "negotiation", "won"}
                ),
            ),
        ),
        "outreach_to_reply": _pct(
            sum(1 for l in leads if l.stage in {"replied", "negotiation", "won"}),
            max(1, sum(1 for l in leads if l.stage in {"outreach", "replied", "negotiation", "won"})),
        ),
        "reply_to_won": _pct(
            sum(1 for l in leads if l.stage == "won"),
            max(1, sum(1 for l in leads if l.stage in {"replied", "negotiation", "won"})),
        ),
    }

    funnel = [
        {"stage": "All leads", "count": len([l for l in leads if not l.suppressed])},
        {
            "stage": "Qualified+",
            "count": sum(
                1
                for l in leads
                if l.stage in {"qualified", "outreach", "replied", "negotiation", "won"}
            ),
        },
        {
            "stage": "Outreach+",
            "count": sum(
                1 for l in leads if l.stage in {"outreach", "replied", "negotiation", "won"}
            ),
        },
        {
            "stage": "Replied+",
            "count": sum(1 for l in leads if l.stage in {"replied", "negotiation", "won"}),
        },
        {"stage": "Won", "count": stage_counts.get("won", 0)},
    ]

    recent_scans = (
        session.query(ScanRun).order_by(ScanRun.started_at.desc()).limit(8).all()
    )

    top_leads = sorted(
        active,
        key=lambda x: (x.fit_score, x.estimated_deal_value or 0),
        reverse=True,
    )[:12]

    action_queue = sorted(
        [l for l in active if l.stage in {"lead", "qualified", "outreach", "replied", "negotiation"}],
        key=lambda x: (
            0 if x.stage == "negotiation" else 1 if x.stage == "replied" else 2 if x.fit_score >= 75 else 3,
            -(x.fit_score or 0),
        ),
    )[:8]

    by_platform_value = defaultdict(int)
    for l in leads:
        if l.suppressed:
            continue
        by_platform_value[l.source_platform] += l.estimated_deal_value or 0

    return {
        "totals": {
            "leads": len(leads),
            "active_leads": len(active),
            "companies": session.query(func.count(Company.id)).scalar() or 0,
            "qualified": qualified,
            "revenue_fit": revenue_fit,
            "high_confidence": high_conf,
            "hot_leads": hot,
            "strong_leads": strong,
            "strong_lead_target": settings.strong_lead_target,
            "strong_lead_min_score": settings.strong_lead_min_score,
            "needs_review": needs_review,
            "ready_to_send": ready_to_send,
            "awaiting_reply": awaiting_reply,
            "in_negotiation": in_negotiation,
            "outreach_drafts": len(outreach),
            "open_deals": sum(1 for d in deals if d.status == "open"),
            "won_deals": sum(1 for d in deals if d.status == "won"),
            "pipeline_value": pipeline_value,
            "weighted_pipeline": weighted_pipeline,
            "won_value": won_value,
            "avg_deal_value": avg_deal,
            "icp_pass_rate": icp_pass_rate,
            "avg_fit_score": round(
                (sum(l.fit_score for l in leads) / len(leads)) if leads else 0,
                1,
            ),
        },
        "stages": dict(stage_counts),
        "platforms": dict(platform_counts),
        "platform_pipeline_value": dict(by_platform_value),
        "revenue_bands": dict(revenue_bands),
        "confidence": dict(confidence),
        "conversion": conversion,
        "funnel": funnel,
        "action_queue": [_serialize_lead(l) for l in action_queue],
        "top_leads": [_serialize_lead(l) for l in top_leads],
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
        "empty": len(leads) == 0,
    }


def _pct(num: int, den: int) -> float:
    if den <= 0:
        return 0.0
    return round(100.0 * num / den, 1)


def _serialize_lead(lead: Lead) -> Dict[str, Any]:
    return {
        "id": lead.id,
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
) -> List[Dict[str, Any]]:
    q = session.query(Lead).options(
        joinedload(Lead.company), joinedload(Lead.contact), joinedload(Lead.deal)
    )
    if stage:
        q = q.filter(Lead.stage == stage)
    if platform:
        q = q.filter(Lead.source_platform == platform)
    if min_score:
        q = q.filter(Lead.fit_score >= min_score)
    if revenue_fit_only:
        q = q.filter(Lead.revenue_fit.is_(True))
    rows = q.order_by(Lead.fit_score.desc(), Lead.created_at.desc()).all()
    return [_serialize_lead(r) for r in rows]
