from __future__ import annotations

from typing import List

from hermes.llm import serper_search
from hermes.sources.base import RawSignal, SourceConnector

SITE_QUERIES = [
    'site:linkedin.com/jobs "{q}" (data OR AI OR LLM OR MLOps)',
    'site:wellfound.com "{q}" (hiring OR engineer OR AI)',
    'site:indeed.com "{q}" (data engineer OR ML OR AI)',
    'site:upwork.com/jobs "{q}" (data OR LLM OR machine learning)',
    'site:reddit.com "{q}" (hiring OR "looking for" OR freelance) (AI OR data)',
    'site:clutch.co "{q}" (AI OR data OR analytics)',
    '"{q}" (RFP OR "looking for agency" OR consultant) (AI OR "data engineering" OR MLOps)',
]


class WebSearchSource(SourceConnector):
    name = "web"

    def fetch(self, query: str = "", limit: int = 15) -> List[RawSignal]:
        focus = (query or "data engineering LLM RAG MLOps").strip()
        signals: List[RawSignal] = []
        seen_links = set()

        # Rotate a couple of site templates per call for breadth
        templates = SITE_QUERIES[:4] if len(focus) > 40 else SITE_QUERIES
        per = max(3, limit // max(1, len(templates)))
        for tmpl in templates:
            q = tmpl.replace("{q}", focus)
            for item in serper_search(q, num=per):
                title = item.get("title") or "Web opportunity"
                link = item.get("link") or ""
                if not link or link in seen_links:
                    continue
                seen_links.add(link)
                snippet = item.get("snippet") or ""
                platform = "web"
                lower = link.lower()
                for name in (
                    "linkedin",
                    "upwork",
                    "fiverr",
                    "wellfound",
                    "angel.co",
                    "clutch",
                    "toptal",
                    "indeed",
                    "reddit",
                    "ycombinator",
                ):
                    if name in lower:
                        platform = "wellfound" if name in {"angel.co", "ycombinator"} else name
                        break
                signals.append(
                    RawSignal(
                        platform=platform,
                        title=title,
                        snippet=snippet,
                        url=link,
                        company_name=title.split(" - ")[0][:120],
                        requirement=snippet,
                        tags=["web_search", focus[:40]],
                        acquisition_source="serper:web",
                    )
                )
                if len(signals) >= limit:
                    return signals
        return signals
