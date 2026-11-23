from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from hermes import brand
from hermes.config import get_settings
from hermes.db import (
    Activity,
    Company,
    Contact,
    Deal,
    Lead,
    OutreachMessage,
    ScanRun,
    init_db,
    session_scope,
    utcnow,
)
from hermes.email_ops import add_suppression, apply_merge_tags, is_suppressed, validate_address
from hermes.llm import chat_text
from hermes.scoring import revenue_band, score_lead
from hermes.sources import RawSignal, gather_signals


@dataclass
class PipelineStats:
    signals_found: int = 0
    leads_created: int = 0  # listings ingested (legacy field name)
    listings_created: int = 0
    leads_skipped: int = 0
    qualified: int = 0
    outreach_drafted: int = 0
    suppressed: int = 0
    deals_opened: int = 0
    expired: int = 0
    notes: List[str] = field(default_factory=list)


def _default_expiry(posted_at: Optional[datetime] = None) -> datetime:
    settings = get_settings()
    base = posted_at or utcnow()
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base + timedelta(days=settings.listing_ttl_days)


def _find_company(session: Session, signal: RawSignal) -> Company:
    q = session.query(Company)
    if signal.company_domain:
        existing = q.filter(Company.domain == signal.company_domain.lower()).one_or_none()
        if existing:
            return existing
    existing = q.filter(Company.name == signal.company_name).one_or_none()
    if existing:
        return existing
    company = Company(
        name=signal.company_name or "Unknown company",
        domain=(signal.company_domain or "").lower() or None,
        industry=signal.industry or None,
        employee_count=signal.employee_count,
        revenue_usd=signal.revenue_usd,
        revenue_band=revenue_band(signal.revenue_usd),
        location=signal.location or None,
        website=f"https://{signal.company_domain}" if signal.company_domain else None,
        description=signal.snippet[:2000] if signal.snippet else None,
        tech_stack=signal.tags or [],
    )
    session.add(company)
    session.flush()
    return company


def _find_contact(session: Session, company: Company, signal: RawSignal) -> Optional[Contact]:
    if not signal.contact_name and not signal.contact_email and not signal.contact_phone:
        return None
    email_check = validate_address(signal.contact_email)
    email = email_check.normalized or (signal.contact_email or None)
    if email:
        existing = session.query(Contact).filter(Contact.email == email).one_or_none()
        if existing:
            if signal.contact_phone and not existing.phone:
                existing.phone = signal.contact_phone
            return existing
    contact = Contact(
        company_id=company.id,
        full_name=signal.contact_name or "Unknown contact",
        title=signal.contact_title or None,
        email=email,
        email_status=email_check.status if signal.contact_email else "missing",
        phone=signal.contact_phone or None,
        is_decision_maker=bool(signal.contact_title),
    )
    session.add(contact)
    session.flush()
    return contact


def _listing_exists(session: Session, signal: RawSignal) -> bool:
    if signal.url:
        return session.query(Lead).filter(Lead.source_url == signal.url).first() is not None
    return (
        session.query(Lead)
        .filter(
            Lead.source_platform == signal.platform,
            Lead.source_title == signal.title,
        )
        .first()
        is not None
    )


def _draft_outreach(
    lead: Lead,
    company: Company,
    contact: Optional[Contact],
    *,
    use_llm: bool = False,
) -> tuple[str, str, str]:
    contact_name = contact.full_name.split()[0] if contact and contact.full_name else "there"
    company_name = company.name
    project = (
        lead.project_summary
        or lead.raw_requirement
        or lead.source_snippet
        or "your data / AI initiative"
    )
    subject_a = f"{company_name}: a practical next step on { (lead.tags or ['data'])[0] }"
    subject_b = f"{contact_name}, Intellytics can scope this into a 2–4 week pilot"
    template = (
        "Hi {{first_name}},\n\n"
        "I saw your post on {{platform}} about {{project}}.\n\n"
        f"{brand.ONE_LINER}\n\n"
        "For teams in a similar spot we usually start with a short paid discovery, then a "
        "fixed-scope pilot — pipelines, analytics/BI, or AI/LLM systems — without a giant "
        "upfront commitment.\n\n"
        "Suggested first milestone:\n"
        "1) clarify success metrics,\n"
        "2) map current stack + gaps,\n"
        "3) propose a 2–4 week delivery slice.\n\n"
        "Open to a 20-minute working call this week?\n\n"
        f"{brand.outreach_signature()}\n"
        "Est. engagement band: ${{deal_value}}\n"
    )
    body = apply_merge_tags(
        template,
        {
            "first_name": contact_name,
            "platform": lead.source_platform,
            "project": project[:240],
            "deal_value": f"{lead.estimated_deal_value or 10000:,}",
        },
    )
    if not use_llm:
        return subject_a, subject_b, body
    llm_body = chat_text(
        "You write concise B2B outreach for Intellytics (data/AI consultancy). "
        "Keep proof points subtle. Return only the email body.",
        f"Rewrite sharper and personalized:\n{body}",
        fallback=body,
    )
    return subject_a, subject_b, llm_body


def ensure_outreach_draft(
    session: Session,
    lead: Lead,
    company: Company,
    contact: Optional[Contact],
    stats: Optional[PipelineStats] = None,
    *,
    use_llm: bool = False,
) -> None:
    """Every non-expired listing should have a cold draft."""
    if lead.suppressed or lead.expired or lead.stage in {"suppressed", "expired", "lost"}:
        return
    existing = session.query(OutreachMessage).filter(OutreachMessage.lead_id == lead.id).first()
    if existing:
        return
    subject_a, subject_b, body = _draft_outreach(lead, company, contact, use_llm=use_llm)
    session.add(
        OutreachMessage(
            lead_id=lead.id,
            channel="email",
            subject_a=subject_a,
            subject_b=subject_b,
            body=body,
            status="draft",
        )
    )
    session.add(
        Activity(
            lead_id=lead.id,
            kind="outreach_drafted",
            message="Cold outreach draft ready (listing — not yet a lead until sent)",
        )
    )
    if stats:
        stats.outreach_drafted += 1


def ensure_opportunity_deal(
    session: Session,
    lead: Lead,
    company: Company,
    stats: Optional[PipelineStats] = None,
) -> None:
    if lead.deal or lead.suppressed or lead.expired:
        return
    if lead.fit_score < get_settings().listing_deal_min_score:
        return
    deal = Deal(
        lead_id=lead.id,
        title=f"{company.name}: {lead.project_summary[:80] if lead.project_summary else 'Data/AI engagement'}",
        value_usd=lead.estimated_deal_value or 10000,
        probability=0.2 if lead.confidence == "high" else 0.12,
        status="open",
        next_step="Review draft → send → convert listing to lead",
    )
    session.add(deal)
    if stats:
        stats.deals_opened += 1


def ingest_signal(
    session: Session,
    signal: RawSignal,
    stats: PipelineStats,
    *,
    use_llm: bool = False,
) -> Optional[Lead]:
    if _listing_exists(session, signal):
        stats.leads_skipped += 1
        return None

    # Expire-at-crawl: skip already-stale signals when source provides dates
    now = utcnow()
    expires_at = signal.expires_at or _default_expiry(signal.posted_at)
    if signal.posted_at:
        posted = signal.posted_at
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        if (now - posted).days > get_settings().listing_ttl_days:
            stats.expired += 1
            stats.notes.append(f"skipped_stale:{signal.platform}:{signal.title[:40]}")
            return None

    company = _find_company(session, signal)
    contact = _find_contact(session, company, signal)

    if contact and contact.email:
        check = validate_address(contact.email)
        if not check.ok:
            if check.status == "disposable":
                add_suppression(session, contact.email, "disposable mailbox", layer="global")
            stats.suppressed += 1
            lead = Lead(
                company_id=company.id,
                contact_id=contact.id,
                source_platform=signal.platform,
                source_url=signal.url or None,
                source_title=signal.title,
                source_snippet=signal.snippet,
                raw_requirement=signal.requirement or signal.snippet,
                stage="suppressed",
                record_kind="listing",
                fit_score=0,
                suppressed=True,
                suppress_reason=check.reason or check.status,
                tags=signal.tags,
                acquisition_source=signal.acquisition_source or signal.platform,
                posted_at=signal.posted_at or now,
                expires_at=expires_at,
                phone_captured=signal.contact_phone or None,
            )
            session.add(lead)
            session.flush()
            stats.leads_created += 1
            stats.listings_created += 1
            return lead

        if is_suppressed(session, contact.email):
            stats.suppressed += 1
            return None

    scored = score_lead(
        company_name=company.name,
        industry=company.industry,
        employee_count=company.employee_count,
        revenue_usd=company.revenue_usd,
        contact_title=contact.title if contact else signal.contact_title,
        source_text=signal.text_blob(),
        description=company.description or "",
    )

    settings = get_settings()
    # Listings stay listings until human sends / gets a reply
    stage = "listing"
    if scored.fit_score >= settings.qualify_min_score and scored.keyword_fit:
        stage = "listing"  # still a listing; "qualified" is a tag via score/confidence
        stats.qualified += 1

    lead = Lead(
        company_id=company.id,
        contact_id=contact.id if contact else None,
        source_platform=signal.platform,
        source_url=signal.url or None,
        source_title=signal.title,
        source_snippet=signal.snippet,
        raw_requirement=signal.requirement or signal.snippet,
        stage=stage,
        record_kind="listing",
        fit_score=scored.fit_score,
        revenue_fit=scored.revenue_fit,
        title_fit=scored.title_fit,
        keyword_fit=scored.keyword_fit,
        confidence=scored.confidence,
        score_reasons=scored.reasons,
        project_summary=scored.project_summary,
        estimated_deal_value=scored.estimated_deal_value,
        tags=signal.tags,
        acquisition_source=signal.acquisition_source or signal.platform,
        review_required=scored.review_required,
        posted_at=signal.posted_at or now,
        expires_at=expires_at,
        phone_captured=signal.contact_phone or (contact.phone if contact else None),
    )
    session.add(lead)
    session.flush()
    session.add(
        Activity(
            lead_id=lead.id,
            kind="listing_ingested",
            message=f"Listing from {signal.platform} scored {scored.fit_score} ({scored.confidence})",
            meta={"reasons": scored.reasons},
        )
    )
    stats.leads_created += 1
    stats.listings_created += 1

    # Cold draft for EVERY listing
    ensure_outreach_draft(session, lead, company, contact, stats, use_llm=use_llm)
    ensure_opportunity_deal(session, lead, company, stats)
    return lead


def mark_as_lead(session: Session, listing_id: int, *, note: str = "Outreach sent") -> Lead:
    """Promote listing → lead when we actually interact."""
    row = session.get(Lead, listing_id)
    if not row:
        raise ValueError(f"Listing {listing_id} not found")
    row.record_kind = "lead"
    if row.stage in {"listing", "signal", "lead", "qualified"}:
        row.stage = "contacted"
    session.add(Activity(lead_id=row.id, kind="converted_to_lead", message=note))
    if row.deal:
        row.deal.probability = max(row.deal.probability or 0, 0.3)
        row.deal.next_step = "Await reply / book discovery"
    for msg in row.outreach:
        if msg.status == "draft":
            msg.status = "sent"
            msg.sent_at = utcnow()
    return row


def advance_lead(session: Session, lead_id: int, stage: str, note: str = "") -> Lead:
    lead = session.get(Lead, lead_id)
    if not lead:
        raise ValueError(f"Record {lead_id} not found")
    lead.stage = stage
    # Interaction stages promote to lead
    if stage in {"contacted", "outreach", "replied", "negotiation", "won"}:
        lead.record_kind = "lead"
        if stage == "outreach":
            lead.stage = "contacted"
    session.add(Activity(lead_id=lead.id, kind="stage_change", message=note or f"Moved to {stage}"))
    if stage == "won" and lead.deal:
        lead.deal.status = "won"
        lead.deal.probability = 1.0
        lead.deal.close_date = utcnow()
    if stage == "lost" and lead.deal:
        lead.deal.status = "lost"
        lead.deal.probability = 0.0
        lead.deal.close_date = utcnow()
    if stage == "replied" and lead.deal:
        lead.deal.probability = max(lead.deal.probability or 0, 0.45)
        lead.deal.next_step = "Qualify scope and propose SOW"
    if stage == "negotiation" and lead.deal:
        lead.deal.probability = max(lead.deal.probability or 0, 0.65)
        lead.deal.next_step = "Finalize commercial terms"
    return lead


def backfill_missing_drafts(*, use_llm: bool = False) -> int:
    init_db()
    created = 0
    with session_scope() as session:
        # Only rows that do not already have an outreach draft
        existing_ids = {
            row[0]
            for row in session.query(OutreachMessage.lead_id).distinct().all()
        }
        rows = (
            session.query(Lead)
            .filter(
                Lead.suppressed.is_(False),
                Lead.expired.is_(False),
                Lead.stage.notin_(["suppressed", "expired", "lost"]),
            )
            .all()
        )
        for lead in rows:
            if lead.id in existing_ids:
                continue
            ensure_outreach_draft(
                session,
                lead,
                lead.company,
                lead.contact,
                use_llm=use_llm,
            )
            created += 1
            if created and created % 100 == 0:
                session.flush()
    return created


def run_scan(
    *,
    query: str = "",
    use_demo: bool = False,
    use_reddit: bool = True,
    use_web: bool = True,
    use_hn: bool = True,
    use_remotive: bool = True,
    use_arbeitnow: bool = True,
    use_remoteok: bool = True,
    import_paths: Optional[Iterable[Path]] = None,
    limit_per_source: int = 25,
    use_llm: bool = False,
) -> PipelineStats:
    init_db()
    settings = get_settings()
    if not query.strip():
        kws = settings.keywords or ["data engineering", "LLM", "RAG"]
        query = kws[0]

    stats = PipelineStats()
    with session_scope() as session:
        run = ScanRun(
            status="running",
            platforms=[
                "reddit",
                "hackernews",
                "remotive",
                "arbeitnow",
                "remoteok",
                "web",
                "csv",
            ],
        )
        session.add(run)
        session.flush()

        signals = gather_signals(
            query=query,
            limit_per_source=limit_per_source,
            use_demo=use_demo,
            use_reddit=use_reddit,
            use_web=use_web,
            use_hn=use_hn,
            use_remotive=use_remotive,
            use_arbeitnow=use_arbeitnow,
            use_remoteok=use_remoteok,
            import_paths=import_paths,
        )
        stats.signals_found = len(signals)
        for signal in signals:
            ingest_signal(session, signal, stats, use_llm=use_llm)

        # Expire due listings during every scan cycle
        from hermes.agents.cleanup import expire_stale_listings

        expired_n = expire_stale_listings(session)
        stats.expired += expired_n

        run.status = "completed"
        run.signals_found = stats.signals_found
        run.leads_created = stats.listings_created
        run.qualified = stats.qualified
        run.outreach_drafted = stats.outreach_drafted
        run.finished_at = utcnow()
        run.notes = (
            f"query={query!r}; listings={stats.listings_created}; "
            f"drafts={stats.outreach_drafted}; expired={stats.expired}; "
            f"skipped={stats.leads_skipped}"
        )
        stats.notes.append(f"scan_run_id={run.id}")
        stats.notes.append(f"query={query}")
    return stats
