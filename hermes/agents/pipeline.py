from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

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
    init_db,
    session_scope,
)
from hermes.email_ops import add_suppression, apply_merge_tags, is_suppressed, validate_address
from hermes.llm import chat_text
from hermes.scoring import revenue_band, score_lead
from hermes.sources import RawSignal, gather_signals


@dataclass
class PipelineStats:
    signals_found: int = 0
    leads_created: int = 0
    leads_skipped: int = 0
    qualified: int = 0
    outreach_drafted: int = 0
    suppressed: int = 0
    deals_opened: int = 0
    notes: List[str] = field(default_factory=list)


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
    if not signal.contact_name and not signal.contact_email:
        return None
    email_check = validate_address(signal.contact_email)
    email = email_check.normalized or (signal.contact_email or None)
    if email:
        existing = session.query(Contact).filter(Contact.email == email).one_or_none()
        if existing:
            return existing
    contact = Contact(
        company_id=company.id,
        full_name=signal.contact_name or "Unknown contact",
        title=signal.contact_title or None,
        email=email,
        email_status=email_check.status if signal.contact_email else "missing",
        is_decision_maker=bool(signal.contact_title),
    )
    session.add(contact)
    session.flush()
    return contact


def _lead_exists(session: Session, signal: RawSignal) -> bool:
    if signal.url:
        return (
            session.query(Lead)
            .filter(Lead.source_url == signal.url)
            .first()
            is not None
        )
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
    project = lead.project_summary or lead.raw_requirement or lead.source_snippet or "your Data/AI initiative"
    subject_a = f"Quick idea for {company_name}'s { (lead.tags or ['AI'])[0] } roadmap"
    subject_b = f"{contact_name}, converting your post into a scoped delivery plan"
    template = (
        "Hi {{first_name}},\n\n"
        "I came across your note on {{platform}} about {{project}}.\n\n"
        "We help Tech/Data/AI teams turn public requirements into a clear project brief, "
        "delivery plan, and measurable rollout — usually starting with a short paid discovery.\n\n"
        "Based on what you shared, a sensible first milestone would be:\n"
        "1) clarify success metrics,\n"
        "2) map current stack + gaps,\n"
        "3) propose a fixed-scope pilot (~2–4 weeks).\n\n"
        "Open to a 20-minute working session this week?\n\n"
        "Best,\nHermes Lead Machine\n"
        "Estimated engagement band: ${{deal_value}}\n"
    )
    body = apply_merge_tags(
        template,
        {
            "first_name": contact_name,
            "platform": lead.source_platform,
            "project": project[:220],
            "deal_value": f"{lead.estimated_deal_value or 10000:,}",
        },
    )
    if not use_llm:
        return subject_a, subject_b, body
    llm_body = chat_text(
        "You write concise B2B outreach for Data/AI consulting. Return only the email body.",
        f"Rewrite this outreach to be sharper and personalized:\n{body}",
        fallback=body,
    )
    return subject_a, subject_b, llm_body


def ingest_signal(
    session: Session,
    signal: RawSignal,
    stats: PipelineStats,
    *,
    use_llm: bool = False,
) -> Optional[Lead]:
    if _lead_exists(session, signal):
        stats.leads_skipped += 1
        return None

    company = _find_company(session, signal)
    contact = _find_contact(session, company, signal)

    # Suppression / deliverability gate
    if contact and contact.email:
        check = validate_address(contact.email)
        if not check.ok:
            if check.status == "disposable":
                add_suppression(session, contact.email, "disposable mailbox", layer="global")
            stats.suppressed += 1
            lead = Lead(
                company_id=company.id,
                contact_id=contact.id if contact else None,
                source_platform=signal.platform,
                source_url=signal.url or None,
                source_title=signal.title,
                source_snippet=signal.snippet,
                raw_requirement=signal.requirement or signal.snippet,
                stage="suppressed",
                fit_score=0,
                suppressed=True,
                suppress_reason=check.reason or check.status,
                tags=signal.tags,
                acquisition_source=signal.acquisition_source or signal.platform,
                review_required=False,
            )
            session.add(lead)
            session.flush()
            session.add(
                Activity(
                    lead_id=lead.id,
                    kind="suppressed",
                    message=f"Blocked by email checks: {check.status} — {check.reason}",
                )
            )
            stats.leads_created += 1
            return lead

        suppressed = is_suppressed(session, contact.email)
        if suppressed:
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
                suppressed=True,
                suppress_reason=suppressed.reason,
                tags=signal.tags,
                acquisition_source=signal.acquisition_source or signal.platform,
            )
            session.add(lead)
            session.flush()
            stats.leads_created += 1
            return lead

    scored = score_lead(
        company_name=company.name,
        industry=company.industry,
        employee_count=company.employee_count,
        revenue_usd=company.revenue_usd,
        contact_title=contact.title if contact else signal.contact_title,
        source_text=signal.text_blob(),
        description=company.description or "",
    )

    stage = "lead"
    if scored.fit_score >= 55 and scored.keyword_fit and (
        scored.revenue_fit or company.revenue_usd is None
    ):
        stage = "qualified"

    # Hard reject clearly non-commercial / below revenue when known
    settings = get_settings()
    if company.revenue_usd is not None and company.revenue_usd < settings.icp_min_revenue_usd:
        stage = "lead"
        scored.review_required = True

    lead = Lead(
        company_id=company.id,
        contact_id=contact.id if contact else None,
        source_platform=signal.platform,
        source_url=signal.url or None,
        source_title=signal.title,
        source_snippet=signal.snippet,
        raw_requirement=signal.requirement or signal.snippet,
        stage=stage,
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
    )
    session.add(lead)
    session.flush()
    session.add(
        Activity(
            lead_id=lead.id,
            kind="ingested",
            message=f"Signal from {signal.platform} scored {scored.fit_score} ({scored.confidence})",
            meta={"reasons": scored.reasons},
        )
    )
    stats.leads_created += 1
    if stage == "qualified":
        stats.qualified += 1
        _maybe_draft_and_deal(session, lead, company, contact, stats, use_llm=use_llm)
    return lead


def _maybe_draft_and_deal(
    session: Session,
    lead: Lead,
    company: Company,
    contact: Optional[Contact],
    stats: PipelineStats,
    *,
    use_llm: bool = False,
) -> None:
    subject_a, subject_b, body = _draft_outreach(lead, company, contact, use_llm=use_llm)
    msg = OutreachMessage(
        lead_id=lead.id,
        channel="email",
        subject_a=subject_a,
        subject_b=subject_b,
        body=body,
        status="draft",
    )
    session.add(msg)
    lead.stage = "outreach"
    session.add(
        Activity(
            lead_id=lead.id,
            kind="outreach_drafted",
            message="Personalized outreach draft ready for human send review",
        )
    )
    stats.outreach_drafted += 1

    if not lead.deal:
        deal = Deal(
            lead_id=lead.id,
            title=f"{company.name}: {lead.project_summary[:80] if lead.project_summary else 'Data/AI engagement'}",
            value_usd=lead.estimated_deal_value or 10000,
            probability=0.25 if lead.confidence == "high" else 0.15,
            status="open",
            next_step="Review outreach draft and send / book discovery call",
        )
        session.add(deal)
        stats.deals_opened += 1
        session.add(
            Activity(
                lead_id=lead.id,
                kind="deal_opened",
                message=f"Deal desk opened at ${deal.value_usd:,}",
            )
        )


def advance_lead(session: Session, lead_id: int, stage: str, note: str = "") -> Lead:
    lead = session.get(Lead, lead_id)
    if not lead:
        raise ValueError(f"Lead {lead_id} not found")
    lead.stage = stage
    session.add(Activity(lead_id=lead.id, kind="stage_change", message=note or f"Moved to {stage}"))
    if stage == "won" and lead.deal:
        lead.deal.status = "won"
        lead.deal.probability = 1.0
        lead.deal.close_date = datetime.now(timezone.utc)
    if stage == "lost" and lead.deal:
        lead.deal.status = "lost"
        lead.deal.probability = 0.0
        lead.deal.close_date = datetime.now(timezone.utc)
    if stage == "replied" and lead.deal:
        lead.deal.probability = max(lead.deal.probability, 0.45)
        lead.deal.next_step = "Qualify scope and propose SOW"
    if stage == "negotiation" and lead.deal:
        lead.deal.probability = max(lead.deal.probability, 0.65)
        lead.deal.next_step = "Finalize commercial terms"
    return lead


def run_scan(
    *,
    query: str = "",
    use_demo: bool = False,
    use_reddit: bool = True,
    use_web: bool = True,
    use_hn: bool = True,
    use_remotive: bool = True,
    use_arbeitnow: bool = True,
    import_paths: Optional[Iterable[Path]] = None,
    limit_per_source: int = 25,
    use_llm: bool = False,
) -> PipelineStats:
    init_db()
    settings = get_settings()
    if not query.strip():
        # Fall back to rotating ICP keywords so -q is never required.
        kws = settings.keywords or ["data engineering", "LLM", "RAG"]
        query = kws[0]

    stats = PipelineStats()
    with session_scope() as session:
        run = ScanRun(
            status="running",
            platforms=["reddit", "hackernews", "remotive", "arbeitnow", "web", "csv", "demo"],
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
            import_paths=import_paths,
        )
        stats.signals_found = len(signals)
        for signal in signals:
            ingest_signal(session, signal, stats, use_llm=use_llm)

        run.status = "completed"
        run.signals_found = stats.signals_found
        run.leads_created = stats.leads_created
        run.qualified = stats.qualified
        run.outreach_drafted = stats.outreach_drafted
        run.finished_at = datetime.now(timezone.utc)
        run.notes = (
            f"query={query!r}; suppressed={stats.suppressed}; "
            f"deals_opened={stats.deals_opened}; skipped={stats.leads_skipped}; "
            + "; ".join(stats.notes)
        )
        stats.notes.append(f"scan_run_id={run.id}")
        stats.notes.append(f"query={query}")
    return stats