from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional

from hermes.agents.pipeline import run_scan
from hermes.config import DATA_DIR, get_settings
from hermes.db import Lead, init_db, session_scope
from hermes.runtime import BUS


def count_strong_leads(min_score: float = 70.0) -> int:
    init_db()
    with session_scope() as session:
        return (
            session.query(Lead)
            .filter(Lead.suppressed.is_(False), Lead.fit_score >= min_score)
            .count()
        )


def icp_query_rotation() -> List[str]:
    settings = get_settings()
    base = list(settings.keywords)
    # Expand into hunting phrases for public sources
    phrases = []
    for kw in base:
        phrases.append(kw)
        phrases.append(f"hiring {kw}")
        phrases.append(f"looking for {kw}")
        phrases.append(f"{kw} freelance OR consultant OR contractor")
    # de-dupe preserve order
    seen = set()
    out = []
    for p in phrases:
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out or ["data engineering", "LLM RAG", "MLOps"]


def run_continuous(
    *,
    interval_sec: Optional[int] = None,
    limit_per_source: int = 25,
    use_demo: bool = False,
    use_llm: bool = False,
    strong_target: Optional[int] = None,
    stop_when_target: bool = False,
) -> None:
    """Hunt forever (or until target) — Ctrl+C to stop. Saves every cycle."""
    settings = get_settings()
    interval = interval_sec if interval_sec is not None else settings.scan_interval_sec
    target = strong_target if strong_target is not None else settings.strong_lead_target
    queries = icp_query_rotation()
    imports = list((DATA_DIR / "imports").glob("*.csv"))

    BUS.set_continuous_start(target=target)
    cycle = 0
    try:
        while True:
            cycle += 1
            query = queries[(cycle - 1) % len(queries)]
            strong = count_strong_leads(settings.strong_lead_min_score)
            BUS.tick(
                cycle=cycle,
                query=query,
                signals=0,
                new_leads=0,
                message=f"Cycle {cycle}: hunting “{query}” · strong leads {strong}/{target}",
            )
            try:
                stats = run_scan(
                    query=query,
                    use_demo=use_demo,
                    use_reddit=True,
                    use_web=bool(settings.serper_api_key),
                    use_hn=True,
                    use_remotive=True,
                    use_arbeitnow=True,
                    import_paths=imports,
                    limit_per_source=limit_per_source,
                    use_llm=use_llm,
                )
                strong = count_strong_leads(settings.strong_lead_min_score)
                BUS.tick(
                    cycle=cycle,
                    query=query,
                    signals=stats.signals_found,
                    new_leads=stats.leads_created,
                    message=(
                        f"Cycle {cycle} done · +{stats.leads_created} new "
                        f"({stats.leads_skipped} dupes) · strong {strong}/{target}"
                    ),
                )
                if stop_when_target and strong >= target:
                    BUS.set_idle(f"Target reached: {strong} strong leads. Stopped.")
                    return
            except Exception as exc:  # noqa: BLE001
                BUS.push_error(f"cycle {cycle}: {exc}")
                BUS.tick(
                    cycle=cycle,
                    query=query,
                    signals=0,
                    new_leads=0,
                    message=f"Cycle {cycle} error (will retry): {exc}",
                )

            # Sleep in small chunks so Ctrl+C is responsive
            slept = 0
            while slept < interval:
                time.sleep(min(5, interval - slept))
                slept += 5
    except KeyboardInterrupt:
        BUS.set_idle("Stopped by user (Ctrl+C). Data is saved in SQLite.")
        raise
