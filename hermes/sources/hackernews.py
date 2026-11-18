from __future__ import annotations

from typing import List
from urllib.parse import quote_plus

import httpx

from hermes.sources.base import RawSignal, SourceConnector


class HackerNewsSource(SourceConnector):
    """Public Algolia HN API — hiring / Who is hiring / Ask HN signals."""

    name = "hackernews"

    def fetch(self, query: str = "", limit: int = 25) -> List[RawSignal]:
        q = query or "hiring data OR AI OR LLM OR MLOps OR \"machine learning\""
        url = (
            "https://hn.algolia.com/api/v1/search_by_date"
            f"?query={quote_plus(q)}&tags=story&hitsPerPage={min(limit, 30)}"
        )
        signals: List[RawSignal] = []
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                hits = resp.json().get("hits", [])
        except Exception:
            return []

        for hit in hits:
            title = hit.get("title") or ""
            if not title:
                continue
            text = (hit.get("story_text") or hit.get("comment_text") or "")[:1200]
            story_url = hit.get("url") or ""
            hn_url = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            author = hit.get("author") or ""
            signals.append(
                RawSignal(
                    platform="hackernews",
                    title=title,
                    snippet=text or title,
                    url=story_url or hn_url,
                    company_name=author or "HN poster",
                    contact_name=author,
                    contact_title="HN author",
                    requirement=text or title,
                    tags=["hackernews", "public"],
                    acquisition_source="hackernews:algolia",
                    meta={"points": hit.get("points"), "num_comments": hit.get("num_comments")},
                )
            )
            if len(signals) >= limit:
                break
        return signals
