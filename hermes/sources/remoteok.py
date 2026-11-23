from __future__ import annotations

from datetime import datetime, timezone
from typing import List

import httpx

from hermes.sources.base import RawSignal, SourceConnector
from hermes.sources.match import query_matches


class RemoteOKSource(SourceConnector):
    name = "remoteok"

    def fetch(self, query: str = "", limit: int = 25) -> List[RawSignal]:
        signals: List[RawSignal] = []
        try:
            with httpx.Client(timeout=25.0, headers={"User-Agent": "HermesLeadMachine/0.3"}) as client:
                resp = client.get("https://remoteok.com/api")
                resp.raise_for_status()
                jobs = resp.json()
        except Exception:
            return []

        for job in jobs:
            if not isinstance(job, dict) or not job.get("position"):
                continue
            title = job.get("position") or ""
            company = job.get("company") or "Unknown"
            tags = [str(t) for t in (job.get("tags") or [])]
            desc = (job.get("description") or "")[:1500]
            blob = f"{title} {company} {desc} {' '.join(tags)}"
            if not query_matches(blob, query or "data AI ML LLM analytics engineer"):
                continue
            posted = None
            if job.get("date"):
                try:
                    posted = datetime.fromisoformat(str(job["date"]).replace("Z", "+00:00"))
                except Exception:
                    posted = datetime.now(timezone.utc)
            signals.append(
                RawSignal(
                    platform="remoteok",
                    title=title,
                    snippet=desc or title,
                    url=job.get("url") or f"https://remoteok.com/remote-jobs/{job.get('id','')}",
                    company_name=company,
                    location=job.get("location") or "Remote",
                    industry="technology",
                    requirement=desc or title,
                    tags=["remoteok"] + tags[:6],
                    acquisition_source="remoteok:api",
                    posted_at=posted,
                )
            )
            if len(signals) >= limit:
                break
        return signals
