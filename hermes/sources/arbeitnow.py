from __future__ import annotations

from typing import List

import httpx

from hermes.sources.base import RawSignal, SourceConnector
from hermes.sources.match import query_matches


class ArbeitnowSource(SourceConnector):
    """Public Arbeitnow job board API."""

    name = "arbeitnow"

    def fetch(self, query: str = "", limit: int = 25) -> List[RawSignal]:
        url = "https://www.arbeitnow.com/api/job-board-api"
        signals: List[RawSignal] = []
        try:
            with httpx.Client(timeout=25.0, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                jobs = resp.json().get("data", [])
        except Exception:
            return []

        for job in jobs:
            title = job.get("title") or ""
            company = job.get("company_name") or "Unknown"
            desc = (job.get("description") or "")[:1500]
            tags = job.get("tags") or []
            blob = f"{title} {company} {desc} {' '.join(tags)}"
            if not query_matches(blob, query or "data AI ML LLM analytics engineer"):
                continue
            signals.append(
                RawSignal(
                    platform="arbeitnow",
                    title=title,
                    snippet=desc or title,
                    url=job.get("url") or "",
                    company_name=company,
                    location=job.get("location") or "",
                    industry="technology",
                    contact_title="Hiring team",
                    requirement=desc or title,
                    tags=["arbeitnow"] + [str(t).lower() for t in tags[:5]],
                    acquisition_source="arbeitnow:api",
                )
            )
            if len(signals) >= limit:
                break
        return signals
