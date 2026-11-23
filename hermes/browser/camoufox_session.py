"""Optional Camoufox session using a persistent profile / cookie jar.

Designed for *your* logged-in browser profile so LinkedIn/job sites see a
normal session instead of a cold bot. Keep volume low to avoid bans.

Install (optional):
  pip install "camoufox[geoip]"
  python -m camoufox fetch
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from hermes.config import ROOT_DIR, get_settings

logger = logging.getLogger(__name__)

PROFILE_DIR = ROOT_DIR / "data" / "browser_profiles" / "default"
COOKIES_FILE = ROOT_DIR / "data" / "browser_profiles" / "cookies.json"


def camoufox_available() -> bool:
    try:
        import camoufox  # noqa: F401

        return True
    except Exception:
        return False


def load_cookie_file(path: Optional[Path] = None) -> list[dict[str, Any]]:
    path = path or COOKIES_FILE
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "cookies" in data:
            return list(data["cookies"])
    except Exception as exc:
        logger.warning("Failed reading cookies: %s", exc)
    return []


def fetch_page_text(url: str, *, wait_ms: int = 2500) -> str:
    """Open a URL with Camoufox persistent profile; return visible text.

    Rate-limit friendly: single page, polite wait. Returns empty string if
    Camoufox is not installed or the navigation fails.
    """
    settings = get_settings()
    if not settings.camoufox_enabled:
        return ""
    if not camoufox_available():
        logger.info("Camoufox not installed — skipping browser fetch for %s", url)
        return ""

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from camoufox.sync_api import Camoufox

        with Camoufox(
            headless=settings.camoufox_headless,
            persistent_context=True,
            user_data_dir=str(PROFILE_DIR),
            os="windows",
        ) as context:
            cookies = load_cookie_file()
            if cookies:
                try:
                    context.add_cookies(cookies)
                except Exception:
                    pass
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(wait_ms)
            # polite pacing
            time.sleep(max(1.0, settings.camoufox_min_delay_sec))
            return page.inner_text("body")[:8000]
    except Exception as exc:
        logger.warning("Camoufox fetch failed for %s: %s", url, exc)
        return ""


def warmup_note() -> str:
    return (
        "To avoid LinkedIn rate limits: 1) pip install 'camoufox[geoip]' && python -m camoufox fetch  "
        "2) set CAMOUFOX_ENABLED=true  3) export cookies to data/browser_profiles/cookies.json "
        "OR log in once with CAMOUFOX_HEADLESS=false into the persistent profile. "
        "Keep requests slow (CAMOUFOX_MIN_DELAY_SEC). Prefer Serper discovery + light enrichment."
    )
