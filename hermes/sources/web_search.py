from __future__ import annotations

from typing import List

from hermes.llm import serper_search
from hermes.sources.base import RawSignal, SourceConnector

# Broad marketplace / job / RFP coverage (Serper). LinkedIn is one of many — not sole.
SITE_QUERIES = [
    'site:linkedin.com/jobs "{q}" (data OR AI OR LLM OR MLOps OR Snowflake OR Databricks)',
    'site:wellfound.com OR site:angel.co "{q}" (hiring OR engineer OR AI OR data)',
    'site:indeed.com "{q}" (data engineer OR ML OR "machine learning" OR AI)',
    'site:upwork.com/jobs "{q}" (data OR LLM OR Snowflake OR dbt OR MLOps)',
    'site:reddit.com "{q}" (hiring OR "looking for" OR freelance) (AI OR data OR LLM)',
    'site:clutch.co "{q}" (AI OR data OR analytics OR "machine learning")',
    'site:dice.com "{q}" (data OR ML OR AI OR Databricks)',
    'site:glassdoor.com/job-listing "{q}" (data OR AI OR analytics)',
    'site:otta.com "{q}" (data OR AI OR ML)',
    'site:weworkremotely.com "{q}" (data OR AI OR python)',
    'site:builtin.com/job "{q}" (data OR AI OR MLOps)',
    'site:levels.fyi/jobs "{q}" (data OR ML)',
    'site:ycombinator.com/jobs OR site:news.ycombinator.com "{q}" (hiring data OR AI)',
    'site:greenhouse.io "{q}" (data engineer OR ML engineer OR AI)',
    'site:lever.co "{q}" (data OR ML OR AI)',
    'site:ashbyhq.com "{q}" (data OR AI)',
    'site:toptal.com "{q}" (data OR AI OR ML)',
    'site:fiverr.com "{q}" (data OR AI OR chatbot OR LLM)',
    '"{q}" (RFP OR "looking for agency" OR "seeking consultant") (AI OR "data engineering" OR analytics OR Snowflake)',
]


def _platform_from_url(link: str) -> str:
    lower = (link or "").lower()
    mapping = [
        ("linkedin", "linkedin"),
        ("upwork", "upwork"),
        ("fiverr", "fiverr"),
        ("wellfound", "wellfound"),
        ("angel.co", "wellfound"),
        ("clutch", "clutch"),
        ("toptal", "toptal"),
        ("indeed", "indeed"),
        ("reddit", "reddit"),
        ("dice.com", "dice"),
        ("glassdoor", "glassdoor"),
        ("otta.com", "otta"),
        ("weworkremotely", "weworkremotely"),
        ("builtin.com", "builtin"),
        ("levels.fyi", "levels"),
        ("ycombinator", "ycombinator"),
        ("news.ycombinator", "hackernews"),
        ("greenhouse.io", "greenhouse"),
        ("lever.co", "lever"),
        ("ashbyhq", "ashby"),
        ("remoteok", "remoteok"),
    ]
    for needle, name in mapping:
        if needle in lower:
            return name
    return "web"


class WebSearchSource(SourceConnector):
    name = "web"

    def fetch(self, query: str = "", limit: int = 30) -> List[RawSignal]:
        focus = (query or "data engineering LLM RAG MLOps Snowflake").strip()
        signals: List[RawSignal] = []
        seen_links = set()

        # Rotate templates for breadth each cycle
        start = abs(hash(focus)) % max(1, len(SITE_QUERIES) - 6)
        templates = SITE_QUERIES[start : start + 8] or SITE_QUERIES[:8]
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
                platform = _platform_from_url(link)
                signals.append(
                    RawSignal(
                        platform=platform,
                        title=title,
                        snippet=snippet,
                        url=link,
                        company_name=title.split(" - ")[0][:120],
                        requirement=snippet,
                        tags=["web_search", focus[:40], platform],
                        acquisition_source=f"serper:{platform}",
                    )
                )
                if len(signals) >= limit:
                    return signals
        return signals
