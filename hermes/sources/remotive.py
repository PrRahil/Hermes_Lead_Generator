from __future__ import annotations

from typing import List

import httpx

from hermes.sources.base import RawSignal, SourceConnector
from hermes.sources.match import query_matches


class RemotiveSource(SourceConnector):
    """Public Remotive jobs API — remote Data/AI roles."""

    name = "remotive"

    def fetch(self, query: str = "", limit: int = 25) -> List[RawSignal]:
        url = "https://remotive.com/api/remote-jobs?category=data"
        signals: List[RawSignal] = []
        try:
            with httpx.Client(timeout=25.0, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                jobs = resp.json().get("jobs", [])
        except Exception:
            # fallback broader category fetch
            try:
                with httpx.Client(timeout=25.0, follow_redirects=True) as client:
                    resp = client.get("https://remotive.com/api/remote-jobs")
                    resp.raise_for_status()
                    jobs = resp.json().get("jobs", [])
            except Exception:
                return []

        for job in jobs:
            title = job.get("title") or ""
            company = job.get("company_name") or "Unknown"
            desc = (job.get("description") or "")[:1500]
            blob = f"{title} {company} {desc} {job.get('category','')}"
            if query and not query_matches(blob, query):
                # keep AI/data-ish jobs even if query is narrow
                if not query_matches(blob, "data AI ML LLM machine learning analytics"):
                    continue
            signals.append(
                RawSignal(
                    platform="remotive",
                    title=title,
                    snippet=desc or title,
                    url=job.get("url") or "",
                    company_name=company,
                    company_domain="",
                    industry="technology",
                    location=job.get("candidate_required_location") or "Remote",
                    contact_title="Hiring manager",
                    requirement=desc or title,
                    tags=["remotive", "jobs", (job.get("category") or "").lower()],
                    acquisition_source="remotive:api",
                )
            )
            if len(signals) >= limit:
                break
        return signals
