from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from hermes.config import Settings, get_settings


REVENUE_BANDS = [
    (0, 1_000_000, "under_1m"),
    (1_000_000, 5_000_000, "1m_5m"),
    (5_000_000, 25_000_000, "5m_25m"),
    (25_000_000, 100_000_000, "25m_100m"),
    (100_000_000, 10_000_000_000, "100m_plus"),
]


def revenue_band(revenue_usd: Optional[int]) -> str:
    if revenue_usd is None:
        return "unknown"
    for low, high, label in REVENUE_BANDS:
        if low <= revenue_usd < high:
            return label
    return "unknown"


@dataclass
class ScoreResult:
    fit_score: float
    revenue_fit: bool
    title_fit: bool
    keyword_fit: bool
    confidence: str
    reasons: List[str] = field(default_factory=list)
    review_required: bool = True
    estimated_deal_value: int = 0
    project_summary: str = ""


DECISION_TITLE_HINTS = [
    "cto",
    "ceo",
    "founder",
    "co-founder",
    "vp",
    "vice president",
    "head of",
    "director",
    "chief",
    "owner",
]


def _contains_any(text: str, needles: List[str]) -> List[str]:
    hits = []
    lower = text.lower()
    for n in needles:
        if n.lower() in lower:
            hits.append(n)
    return hits


def estimate_deal_value(
    revenue_usd: Optional[int],
    employee_count: Optional[int],
    keyword_hits: List[str],
) -> int:
    base = 8_000
    if revenue_usd and revenue_usd >= 25_000_000:
        base = 45_000
    elif revenue_usd and revenue_usd >= 5_000_000:
        base = 25_000
    elif revenue_usd and revenue_usd >= 1_000_000:
        base = 15_000

    if employee_count and employee_count >= 500:
        base = int(base * 1.4)
    elif employee_count and employee_count >= 100:
        base = int(base * 1.15)

    if any(k in ("llm", "rag", "ai agent", "mlops") for k in [h.lower() for h in keyword_hits]):
        base = int(base * 1.25)
    return base


def score_lead(
    *,
    company_name: str,
    industry: Optional[str] = None,
    employee_count: Optional[int] = None,
    revenue_usd: Optional[int] = None,
    contact_title: Optional[str] = None,
    source_text: str = "",
    description: str = "",
    settings: Optional[Settings] = None,
) -> ScoreResult:
    settings = settings or get_settings()
    reasons: List[str] = []
    score = 0.0

    blob = " ".join(
        filter(
            None,
            [company_name, industry or "", contact_title or "", source_text, description],
        )
    )

    # Industry fit
    industry_hits = _contains_any(industry or blob, settings.industries)
    if industry_hits:
        score += 20
        reasons.append(f"Industry match: {', '.join(industry_hits[:3])}")
    else:
        reasons.append("Industry unclear — needs review")

    # Revenue / company income filter (core KPI gate)
    revenue_fit = False
    if revenue_usd is not None:
        if revenue_usd >= settings.icp_min_revenue_usd:
            revenue_fit = True
            score += 25
            reasons.append(
                f"Revenue fit: ${revenue_usd:,} >= ${settings.icp_min_revenue_usd:,}"
            )
        else:
            reasons.append(
                f"Below revenue floor: ${revenue_usd:,} < ${settings.icp_min_revenue_usd:,}"
            )
            score -= 15
    else:
        # Soft pass when unknown — still allow but mark review
        score += 5
        reasons.append("Revenue unknown — estimated from signals")

    # Employee band
    if employee_count is not None:
        if settings.icp_min_employees <= employee_count <= settings.icp_max_employees:
            score += 15
            reasons.append(f"Team size fit: {employee_count} employees")
        elif employee_count < settings.icp_min_employees:
            score -= 5
            reasons.append(f"Team may be too small ({employee_count})")
        else:
            score += 5
            reasons.append(f"Enterprise-scale team ({employee_count}) — longer cycle")

    # Title / buyer fit
    title_fit = False
    if contact_title:
        title_hits = _contains_any(contact_title, settings.target_titles)
        dm_hits = _contains_any(contact_title, DECISION_TITLE_HINTS)
        if title_hits or dm_hits:
            title_fit = True
            score += 20
            reasons.append(f"Buyer-relevant title: {contact_title}")
        else:
            reasons.append(f"Title weak for ICP: {contact_title}")
    else:
        reasons.append("No contact title yet")

    # Keyword / requirement fit (post → project conversion signal)
    keyword_hits = _contains_any(blob, settings.keywords)
    keyword_fit = bool(keyword_hits)
    if keyword_hits:
        score += min(20, 5 * len(keyword_hits))
        reasons.append(f"Requirement keywords: {', '.join(keyword_hits[:5])}")
    else:
        # Broader tech/data/ai language
        broad = _contains_any(
            blob,
            ["data", "ai", "ml", "analytics", "etl", "warehouse", "llm", "model"],
        )
        if broad:
            keyword_fit = True
            score += 8
            reasons.append(f"Adjacent tech signals: {', '.join(broad[:4])}")
        else:
            reasons.append("Weak Tech/Data/AI requirement signal")

    # Buying-intent language in posts
    intent = _contains_any(
        blob,
        [
            "looking for",
            "hiring",
            "need help",
            "rfp",
            "budget",
            "freelance",
            "contractor",
            "agency",
            "urgent",
            "asap",
            "proposal",
            "quote",
        ],
    )
    if intent:
        score += 10
        reasons.append(f"Buying intent: {', '.join(intent[:3])}")

    score = max(0.0, min(100.0, score))

    if score >= 75:
        confidence = "high"
        review_required = False
    elif score >= 55:
        confidence = "medium"
        review_required = True
    else:
        confidence = "low"
        review_required = True

    # Strict revenue gate: if explicitly below floor, force low unless overridden later
    if revenue_usd is not None and revenue_usd < settings.icp_min_revenue_usd:
        confidence = "low"
        review_required = True

    deal_value = estimate_deal_value(revenue_usd, employee_count, keyword_hits)
    summary = _project_summary(company_name, keyword_hits, intent, source_text)

    return ScoreResult(
        fit_score=round(score, 1),
        revenue_fit=revenue_fit or (revenue_usd is None and score >= 55),
        title_fit=title_fit,
        keyword_fit=keyword_fit,
        confidence=confidence,
        reasons=reasons,
        review_required=review_required,
        estimated_deal_value=deal_value,
        project_summary=summary,
    )


def _project_summary(
    company: str,
    keywords: List[str],
    intent: List[str],
    source_text: str,
) -> str:
    focus = ", ".join(keywords[:3]) if keywords else "Tech/Data/AI work"
    intent_bit = f" Intent signals: {', '.join(intent[:2])}." if intent else ""
    snippet = re.sub(r"\s+", " ", source_text or "").strip()
    if len(snippet) > 160:
        snippet = snippet[:157] + "..."
    base = f"Convert public signal at {company} into a scoped {focus} engagement."
    if snippet:
        return f"{base} Source: {snippet}{intent_bit}"
    return f"{base}{intent_bit}"