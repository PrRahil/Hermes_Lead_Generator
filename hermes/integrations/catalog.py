"""Market tools that Hermes can learn from / plug into later.

These are connectors and enrichment patterns — not built-in scrapers that risk
LinkedIn bans. Prefer official APIs + user-owned sessions (Camoufox profile).
"""

from __future__ import annotations

from typing import Any, Dict, List


INTEGRATIONS: List[Dict[str, Any]] = [
    {
        "name": "Apollo.io",
        "type": "closed",
        "role": "B2B contact + company enrichment, sequences",
        "status": "planned",
        "notes": "Best paid enrichment. Use for emails/titles after listing capture.",
        "env_keys": ["APOLLO_API_KEY"],
    },
    {
        "name": "Hunter.io",
        "type": "closed",
        "role": "Email finder / verifier",
        "status": "partial",
        "notes": "HUNTER_API_KEY already in config for future enrichment calls.",
        "env_keys": ["HUNTER_API_KEY"],
    },
    {
        "name": "Scout",
        "type": "freemium",
        "role": "Lightweight prospecting alternative to Apollo",
        "status": "planned",
        "notes": "Good for early enrichment without heavy LinkedIn scraping.",
        "env_keys": [],
    },
    {
        "name": "GetProspect / SignalHire / Lusha / ContactOut",
        "type": "closed/chrome",
        "role": "Email/phone finders (often LinkedIn-adjacent)",
        "status": "manual",
        "notes": "High ban risk if automated against LinkedIn. Prefer human-assisted export → CSV import.",
        "env_keys": [],
    },
    {
        "name": "BehindTheMail",
        "type": "closed",
        "role": "Email pattern discovery",
        "status": "planned",
        "notes": "Use after domain capture on a listing.",
        "env_keys": [],
    },
    {
        "name": "Camoufox + OS cookies",
        "type": "open",
        "role": "Authenticated browsing for job pages without cold-bot fingerprints",
        "status": "implemented",
        "notes": "Persistent profile in data/browser_profiles. Rate-limit strictly.",
        "env_keys": ["CAMOUFOX_ENABLED", "CAMOUFOX_HEADLESS", "CAMOUFOX_MIN_DELAY_SEC"],
    },
    {
        "name": "Serper / web search",
        "type": "closed-api",
        "role": "Discover listings across LinkedIn, Indeed, Wellfound, Dice, Greenhouse, etc.",
        "status": "implemented",
        "notes": "Primary discovery engine — safer than headless LinkedIn crawl.",
        "env_keys": ["SERPER_API_KEY"],
    },
    {
        "name": "HubSpot / Salesforce CRM",
        "type": "closed",
        "role": "Push engaged leads (not raw listings) into CRM",
        "status": "planned",
        "notes": "Only sync record_kind=lead after outreach/reply.",
        "env_keys": ["HUBSPOT_TOKEN", "SALESFORCE_TOKEN"],
    },
    {
        "name": "Tinyfish-style GPT plugins / Claude sales MCPs",
        "type": "inspiration",
        "role": "Agentic sales workflows — research, draft, CRM update",
        "status": "inspiration",
        "notes": "Mirror: listing capture → qualify → draft → human send → CRM.",
        "env_keys": [],
    },
]


def list_integrations() -> List[Dict[str, Any]]:
    return INTEGRATIONS
