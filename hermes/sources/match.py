from __future__ import annotations

import re
from typing import Iterable


def query_matches(text: str, query: str) -> bool:
    """Token OR-match so 'Data Engineering' hits 'data engineer' posts."""
    q = (query or "").strip().lower()
    if not q:
        return True
    blob = (text or "").lower()
    if q in blob:
        return True
    tokens = [t for t in re.split(r"[^a-z0-9+]+", q) if len(t) >= 3]
    if not tokens:
        return True
    # Match if at least half the meaningful tokens appear (min 1).
    hits = sum(1 for t in tokens if t in blob)
    need = max(1, (len(tokens) + 1) // 2)
    return hits >= need


def filter_by_query(items: Iterable, query: str):
    if not (query or "").strip():
        return list(items)
    return [item for item in items if query_matches(item.text_blob(), query)]