from __future__ import annotations

import csv
from pathlib import Path
from typing import List, Optional

from hermes.sources.base import RawSignal, SourceConnector


COLUMN_MAP = {
    "platform": ["platform", "source", "channel"],
    "title": ["title", "job_title", "post_title", "subject"],
    "snippet": ["snippet", "description", "body", "summary", "post"],
    "url": ["url", "link", "source_url"],
    "company_name": ["company", "company_name", "organization"],
    "company_domain": ["domain", "company_domain", "website"],
    "industry": ["industry", "sector"],
    "employee_count": ["employees", "employee_count", "headcount", "company_size"],
    "revenue_usd": ["revenue", "revenue_usd", "annual_revenue"],
    "location": ["location", "city", "region"],
    "contact_name": ["contact", "contact_name", "name", "full_name"],
    "contact_title": ["contact_title", "title_role", "role", "job_role"],
    "contact_email": ["email", "contact_email"],
    "requirement": ["requirement", "needs", "project", "brief"],
}


def _pick(row: dict, keys: list[str]) -> str:
    lower = {k.lower().strip(): v for k, v in row.items() if k}
    for key in keys:
        if key in lower and lower[key] not in (None, ""):
            return str(lower[key]).strip()
    return ""


def _to_int(value: str) -> Optional[int]:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    return int(digits) if digits else None


class CsvImportSource(SourceConnector):
    """Import LinkedIn/Upwork/Fiverr/Wellfound/Clutch/Toptal/Indeed exports."""

    name = "csv_import"

    def __init__(self, path: Path, default_platform: str = "manual"):
        self.path = Path(path)
        self.default_platform = default_platform

    def fetch(self, query: str = "", limit: int = 500) -> List[RawSignal]:
        if not self.path.exists():
            return []
        signals: List[RawSignal] = []
        with self.path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                platform = _pick(row, COLUMN_MAP["platform"]) or self.default_platform
                title = _pick(row, COLUMN_MAP["title"]) or "Imported opportunity"
                snippet = _pick(row, COLUMN_MAP["snippet"]) or _pick(row, COLUMN_MAP["requirement"])
                signals.append(
                    RawSignal(
                        platform=platform.lower(),
                        title=title,
                        snippet=snippet,
                        url=_pick(row, COLUMN_MAP["url"]),
                        company_name=_pick(row, COLUMN_MAP["company_name"]) or "Unknown company",
                        company_domain=_pick(row, COLUMN_MAP["company_domain"]),
                        industry=_pick(row, COLUMN_MAP["industry"]) or "technology",
                        employee_count=_to_int(_pick(row, COLUMN_MAP["employee_count"])),
                        revenue_usd=_to_int(_pick(row, COLUMN_MAP["revenue_usd"])),
                        location=_pick(row, COLUMN_MAP["location"]),
                        contact_name=_pick(row, COLUMN_MAP["contact_name"]),
                        contact_title=_pick(row, COLUMN_MAP["contact_title"]),
                        contact_email=_pick(row, COLUMN_MAP["contact_email"]),
                        requirement=_pick(row, COLUMN_MAP["requirement"]) or snippet,
                        tags=["import", platform.lower()],
                        acquisition_source=f"import:{self.path.name}",
                    )
                )
                if len(signals) >= limit:
                    break
        from hermes.sources.match import filter_by_query

        return filter_by_query(signals, query)[:limit]