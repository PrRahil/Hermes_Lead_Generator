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
    "manager",
    "lead",
    "engineer",
    "hiring",
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
    base = 10_000
    if revenue_usd and revenue_usd >= 25_000_000:
        base = 45_000
    elif revenue_usd and revenue_usd >= 5_000_000:
        base = 25_000
    elif revenue_usd and revenue_usd >= 1_000_000:
        base = 15_000

    if employee_count and employee_count >= 500:
        base = int(base * 1.3)
    elif employee_count and employee_count >= 50:
        base = int(base * 1.1)

    if any(k in ("llm", "rag", "ai agent", "mlops", "snowflake", "databricks") for k in [h.lower() for h in keyword_hits]):
        base = int(base * 1.2)
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
    """Lighter ICP — public posts rarely have revenue; don't punish unknowns."""
    settings = settings or get_settings()
    reasons: List[str] = []
    # Everyone starts with a base so Data/AI posts can clear soft thresholds.
    score = 25.0
    reasons.append("Base listing score (lightweight ICP)")

    blob = " ".join(
        filter(
            None,
            [company_name, industry or "", contact_title or "", source_text, description],
        )
    )

    industry_hits = _contains_any(industry or blob, settings.industries)
    if industry_hits:
        score += 15
        reasons.append(f"Industry match: {', '.join(industry_hits[:3])}")
    else:
        score += 5
        reasons.append("Industry inferred from Data/AI context")

    revenue_fit = False
    if revenue_usd is not None:
        if revenue_usd >= settings.icp_min_revenue_usd:
            revenue_fit = True
            score += 15
            reasons.append(f"Revenue fit: ${revenue_usd:,}")
        elif revenue_usd == 0:
            score -= 5
            reasons.append("Zero/unknown commercial signal")
        else:
            # Soft penalty only — still allow consulting SMBs
            score -= 3
            reasons.append(f"Below preferred revenue floor (${revenue_usd:,})")
    else:
        revenue_fit = True  # unknown ≠ fail on light ICP
        score += 10
        reasons.append("Revenue unknown — not penalized under light ICP")

    if employee_count is not None:
        if employee_count >= settings.icp_min_employees:
            score += 10
            reasons.append(f"Team size OK: {employee_count}")
        elif employee_count >= 5:
            score += 5
            reasons.append(f"Small team ({employee_count}) — still workable")
        else:
            reasons.append(f"Very small team ({employee_count})")
    else:
        score += 5
        reasons.append("Headcount unknown — neutral")

    title_fit = False
    if contact_title:
        title_hits = _contains_any(contact_title, settings.target_titles)
        dm_hits = _contains_any(contact_title, DECISION_TITLE_HINTS)
        if title_hits or dm_hits:
            title_fit = True
            score += 15
            reasons.append(f"Relevant title/role: {contact_title}")
        else:
            score += 5
            reasons.append(f"Title present: {contact_title}")
    else:
        score += 3
        reasons.append("No title yet — enrichment later")

    keyword_hits = _contains_any(blob, settings.keywords)
    keyword_fit = bool(keyword_hits)
    if keyword_hits:
        score += min(25, 6 * len(keyword_hits))
        reasons.append(f"Keywords: {', '.join(keyword_hits[:5])}")
    else:
        broad = _contains_any(
            blob,
            ["data", "ai", "ml", "analytics", "etl", "warehouse", "llm", "model", "cloud", "dashboard"],
        )
        if broad:
            keyword_fit = True
            score += 12
            reasons.append(f"Adjacent signals: {', '.join(broad[:4])}")
        else:
            reasons.append("Weak Data/AI keyword signal")

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
            "who is hiring",
            "seeking",
            "consultant",
        ],
    )
    if intent:
        score += 12
        reasons.append(f"Buying intent: {', '.join(intent[:3])}")

    score = max(0.0, min(100.0, score))

    # Soft thresholds so public posts can become actionable listings
    if score >= 65:
        confidence = "high"
        review_required = False
    elif score >= 45:
        confidence = "medium"
        review_required = False
    else:
        confidence = "low"
        review_required = True

    deal_value = estimate_deal_value(revenue_usd, employee_count, keyword_hits)
    summary = _project_summary(company_name, keyword_hits, intent, source_text)

    return ScoreResult(
        fit_score=round(score, 1),
        revenue_fit=revenue_fit,
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
    focus = ", ".join(keywords[:3]) if keywords else "Data/AI engagement"
    intent_bit = f" Intent: {', '.join(intent[:2])}." if intent else ""
    snippet = re.sub(r"\s+", " ", source_text or "").strip()
    if len(snippet) > 160:
        snippet = snippet[:157] + "..."
    base = (
        f"Intellytics angle for {company}: scoped {focus} — pipelines, analytics, "
        f"or AI systems with a short discovery → pilot path."
    )
    if snippet:
        return f"{base} Source: {snippet}{intent_bit}"
    return f"{base}{intent_bit}"
