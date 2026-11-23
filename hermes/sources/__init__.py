from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional

from hermes.sources.arbeitnow import ArbeitnowSource
from hermes.sources.base import RawSignal, SourceConnector
from hermes.sources.demo import DemoSource
from hermes.sources.hackernews import HackerNewsSource
from hermes.sources.import_csv import CsvImportSource
from hermes.sources.reddit import RedditSource
from hermes.sources.remoteok import RemoteOKSource
from hermes.sources.remotive import RemotiveSource
from hermes.sources.web_search import WebSearchSource


def gather_signals(
    *,
    query: str = "",
    limit_per_source: int = 20,
    use_demo: bool = False,
    use_reddit: bool = True,
    use_web: bool = True,
    use_hn: bool = True,
    use_remotive: bool = True,
    use_arbeitnow: bool = True,
    use_remoteok: bool = True,
    import_paths: Optional[Iterable[Path]] = None,
) -> List[RawSignal]:
    connectors: List[SourceConnector] = []
    if use_demo:
        connectors.append(DemoSource())
    if use_reddit:
        connectors.append(RedditSource())
    if use_hn:
        connectors.append(HackerNewsSource())
    if use_remotive:
        connectors.append(RemotiveSource())
    if use_arbeitnow:
        connectors.append(ArbeitnowSource())
    if use_remoteok:
        connectors.append(RemoteOKSource())
    if use_web:
        connectors.append(WebSearchSource())
    for path in import_paths or []:
        connectors.append(CsvImportSource(Path(path)))

    all_signals: List[RawSignal] = []
    seen = set()
    for connector in connectors:
        try:
            batch = connector.fetch(query=query, limit=limit_per_source)
        except Exception:
            continue
        for signal in batch:
            key = (signal.platform, signal.url or signal.title, signal.company_name)
            if key in seen:
                continue
            seen.add(key)
            all_signals.append(signal)
    return all_signals


__all__ = [
    "RawSignal",
    "gather_signals",
    "DemoSource",
    "RedditSource",
    "CsvImportSource",
    "HackerNewsSource",
    "RemotiveSource",
    "ArbeitnowSource",
    "RemoteOKSource",
]
