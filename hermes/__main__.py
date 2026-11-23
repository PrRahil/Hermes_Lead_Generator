from __future__ import annotations

import threading
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from hermes import __app_name__, __version__
from hermes.agents.cleanup import cleanup_leads, run_expiry_pass
from hermes.agents.continuous import count_strong_leads, run_continuous
from hermes.agents.pipeline import backfill_missing_drafts, run_scan
from hermes.config import DATA_DIR, get_settings
from hermes.db import init_db

app = typer.Typer(add_completion=False, no_args_is_help=True, help=__app_name__)
console = Console()


@app.command("version")
def version() -> None:
    console.print(f"{__app_name__} v{__version__}")


@app.command("init-db")
def init_database() -> None:
    """Create local SQLite tables."""
    init_db()
    console.print(f"[green]Database ready:[/green] {get_settings().db_path}")


@app.command("cleanup")
def cleanup(
    mode: str = typer.Option("all", "--mode", help="all | demo | expired"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete demo/all rows, or run expiry prune (mode=expired)."""
    if mode != "expired" and not yes:
        confirm = typer.confirm(f"Delete with mode={mode}? This cannot be undone.")
        if not confirm:
            console.print("Cancelled.")
            raise typer.Exit()
    result = cleanup_leads(mode=mode)
    console.print(f"[green]Cleanup done[/green]: {result}")


@app.command("expire")
def expire() -> None:
    """Mark calendar-expired listings and prune weak stale rows."""
    result = run_expiry_pass()
    console.print(f"[green]Expiry pass[/green]: {result}")


@app.command("backfill-drafts")
def backfill_drafts() -> None:
    """Ensure every active listing has an Intellytics cold draft."""
    n = backfill_missing_drafts(use_llm=False)
    console.print(f"[green]Drafts created:[/green] {n}")


@app.command("scan")
def scan(
    query: str = typer.Option(
        "",
        "--query",
        "-q",
        help="Optional override. Empty = use ICP keywords from .env",
    ),
    demo: bool = typer.Option(False, "--demo/--no-demo", help="Include demo corpus (off by default)"),
    reddit: bool = typer.Option(True, "--reddit/--no-reddit"),
    web: bool = typer.Option(True, "--web/--no-web", help="Serper web search if key set"),
    limit: int = typer.Option(25, "--limit", "-n"),
    llm: bool = typer.Option(False, "--llm/--no-llm", help="Use LLM to rewrite outreach (costs tokens)"),
    import_csv: Optional[List[Path]] = typer.Option(None, "--import"),
) -> None:
    """One-shot scan (usually prefer `hermes run` for continuous hunting)."""
    settings = get_settings()
    imports = list(import_csv or [])
    imports.extend((DATA_DIR / "imports").glob("*.csv"))
    console.print(f"[bold]{__app_name__}[/bold] one-shot scan…")
    stats = run_scan(
        query=query,
        use_demo=demo,
        use_reddit=reddit,
        use_web=web and bool(settings.serper_api_key),
        import_paths=imports,
        limit_per_source=limit,
        use_llm=llm or settings.hermes_use_llm,
    )
    table = Table(title="Scan results")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Signals found", str(stats.signals_found))
    table.add_row("Leads created", str(stats.leads_created))
    table.add_row("Already in DB (skipped)", str(stats.leads_skipped))
    table.add_row("Qualified", str(stats.qualified))
    table.add_row("Outreach drafted", str(stats.outreach_drafted))
    table.add_row("Strong leads now", str(count_strong_leads(settings.strong_lead_min_score)))
    console.print(table)


def _startup_maintenance(*, use_llm: bool = False) -> None:
    """Backfill drafts then expire/prune stale listings before hunting."""
    console.print("[bold]Startup maintenance[/bold]")
    init_db()
    console.print("1/2 Backfilling Intellytics cold drafts…")
    drafted = backfill_missing_drafts(use_llm=use_llm)
    console.print(f"   [green]Drafts created/ensured:[/green] {drafted}")
    console.print("2/2 Expiring stale listings + pruning weak noise…")
    expired = run_expiry_pass()
    console.print(f"   [green]Expiry pass:[/green] {expired}")


@app.command("run")
def run(
    host: Optional[str] = typer.Option(None, "--host"),
    port: Optional[int] = typer.Option(None, "--port"),
    interval: Optional[int] = typer.Option(
        None, "--interval", help="Seconds between hunt cycles (default from .env)"
    ),
    demo: bool = typer.Option(False, "--demo/--no-demo"),
    llm: bool = typer.Option(False, "--llm/--no-llm"),
    target: Optional[int] = typer.Option(None, "--target", help="Strong-lead target (default 50)"),
    stop_at_target: bool = typer.Option(
        False, "--stop-at-target", help="Exit when strong-lead target is reached"
    ),
    skip_startup: bool = typer.Option(
        False, "--skip-startup", help="Skip backfill+expiry bootstrap (not recommended)"
    ),
) -> None:
    """Start dashboard + continuous lead hunting until you press Ctrl+C.

    On every start: backfill missing drafts → expire/prune stale listings → hunt.
    """
    import uvicorn

    settings = get_settings()
    init_db()
    h = host or settings.hermes_host
    p = port or settings.hermes_port
    tgt = target or settings.strong_lead_target
    use_llm = llm or settings.hermes_use_llm

    if not skip_startup:
        _startup_maintenance(use_llm=use_llm)
    else:
        console.print("[yellow]Skipped startup backfill/expiry[/yellow]")

    def _hunt() -> None:
        try:
            run_continuous(
                interval_sec=interval,
                use_demo=demo,
                use_llm=use_llm,
                strong_target=tgt,
                stop_when_target=stop_at_target,
            )
        except KeyboardInterrupt:
            pass

    hunter = threading.Thread(target=_hunt, name="hermes-hunter", daemon=True)
    hunter.start()

    console.print(f"[bold green]{__app_name__} continuous mode[/bold green]")
    console.print(f"Dashboard: http://{h}:{p}")
    console.print(
        f"Hunting Data/AI leads from ICP keywords · target {tgt} strong "
        f"(score ≥ {settings.strong_lead_min_score}) · interval "
        f"{interval or settings.scan_interval_sec}s"
    )
    console.print("[dim]LLM outreach rewrite: OFF (templates only) unless --llm[/dim]")
    console.print("[dim]Press Ctrl+C to stop. All leads stay saved in the DB.[/dim]")
    try:
        uvicorn.run("hermes.api:app", host=h, port=p, reload=False, log_level="info")
    finally:
        from hermes.runtime import BUS

        BUS.set_idle("Dashboard stopped")


@app.command("dashboard")
def dashboard(
    host: Optional[str] = typer.Option(None, "--host"),
    port: Optional[int] = typer.Option(None, "--port"),
) -> None:
    """Dashboard only (no continuous hunting). Prefer `hermes run` for lead gen."""
    import uvicorn

    settings = get_settings()
    init_db()
    h = host or settings.hermes_host
    p = port or settings.hermes_port
    console.print(f"[green]Dashboard:[/green] http://{h}:{p}")
    console.print("[yellow]Note:[/yellow] this does not hunt leads. Use: python -m hermes run")
    uvicorn.run("hermes.api:app", host=h, port=p, reload=False)


@app.command("seed")
def seed() -> None:
    """Load demo leads (optional). Prefer real hunting via `hermes run`."""
    stats = run_scan(query="", use_demo=True, use_reddit=False, use_web=False, use_hn=False, use_remotive=False, use_arbeitnow=False, limit_per_source=50)
    console.print(
        f"[green]Seeded[/green] signals={stats.signals_found} leads={stats.leads_created}"
    )


if __name__ == "__main__":
    app()
