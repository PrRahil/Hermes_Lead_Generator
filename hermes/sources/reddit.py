from __future__ import annotations

from typing import List
from urllib.parse import quote_plus

import httpx

from hermes.sources.base import RawSignal, SourceConnector

DEFAULT_SUBREDDITS = [
    "MachineLearning",
    "datascience",
    "LocalLLaMA",
    "LanguageTechnology",
    "cscareerquestions",
    "forhire",
    "hiring",
    "startups",
    "Entrepreneur",
    "artificial",
    "MLQuestions",
    "dataengineering",
    "analytics",
    "BusinessIntelligence",
    "OpenAI",
    "ClaudeAI",
    "Rag",
    "LLMDevs",
    "mlops",
    "devopsjobs",
]


class RedditSource(SourceConnector):
    name = "reddit"

    def __init__(self, subreddits: List[str] | None = None):
        self.subreddits = subreddits or DEFAULT_SUBREDDITS

    def fetch(self, query: str = "", limit: int = 25) -> List[RawSignal]:
        signals: List[RawSignal] = []
        q = query or 'hiring OR "looking for" (data OR LLM OR "machine learning" OR MLOps OR RAG)'
        headers = {"User-Agent": "HermesLeadMachine/0.2 (local research bot; lead discovery)"}

        # Rotate through a slice of subs each call for breadth without hammering.
        offset = abs(hash(q)) % max(1, len(self.subreddits) - 8)
        subs = self.subreddits[offset : offset + 10] or self.subreddits[:10]

        for sub in subs:
            if len(signals) >= limit:
                break
            url = (
                f"https://www.reddit.com/r/{sub}/search.json"
                f"?q={quote_plus(q)}&restrict_sr=1&sort=new&t=month&limit=15"
            )
            try:
                with httpx.Client(timeout=15.0, headers=headers, follow_redirects=True) as client:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        continue
                    children = resp.json().get("data", {}).get("children", [])
            except Exception:
                continue

            for child in children:
                post = child.get("data", {})
                title = post.get("title") or ""
                selftext = (post.get("selftext") or "")[:1200]
                author = post.get("author") or ""
                permalink = post.get("permalink") or ""
                full_url = f"https://www.reddit.com{permalink}" if permalink else ""
                if not title:
                    continue
                signals.append(
                    RawSignal(
                        platform="reddit",
                        title=title,
                        snippet=selftext or title,
                        url=full_url,
                        company_name=f"r/{sub} poster",
                        contact_name=author if author and author != "[deleted]" else "",
                        contact_title="Reddit OP",
                        requirement=selftext or title,
                        tags=["reddit", sub.lower()],
                        acquisition_source=f"reddit:{sub}",
                        meta={"score": post.get("score"), "num_comments": post.get("num_comments")},
                    )
                )
                if len(signals) >= limit:
                    break
        return signals[:limit]