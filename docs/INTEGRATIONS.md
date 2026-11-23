# Hermes integrations & market tools

## Naming

| Term | Meaning |
|------|---------|
| **Listing** | A crawled post/job/RFP. Not a lead yet. |
| **Lead** | We interacted (sent outreach / reply / negotiation). |

## Discovery (safer than LinkedIn mass scrape)

1. **Serper** — multi-site search (LinkedIn, Indeed, Wellfound, Dice, Greenhouse, Lever, Otta, Builtin, Clutch, Upwork, Reddit, …)
2. **Public APIs** — Reddit, HN Algolia, Remotive, Arbeitnow, RemoteOK
3. **CSV import** — export from Apollo / Hunter / Chrome finders → `data/imports/`

## LinkedIn rate limits

Do **not** hammer LinkedIn with headless bots. Prefer:

- Serper `site:linkedin.com/jobs` for discovery
- Optional **Camoufox** persistent profile + your cookies (`CAMOUFOX_ENABLED=true`)
- Manual Chrome tools (ContactOut, Lusha, GetProspect) → CSV import

Camoufox setup:

```bash
pip install "camoufox[geoip]"
python -m camoufox fetch
# set CAMOUFOX_ENABLED=true, keep CAMOUFOX_MIN_DELAY_SEC >= 4
```

Export cookies to `data/browser_profiles/cookies.json` or log in once with `CAMOUFOX_HEADLESS=false`.

## Enrichment / CRM (planned)

| Tool | Use |
|------|-----|
| Apollo.io | Paid B2B enrichment + sequences |
| Hunter.io | Email find/verify (`HUNTER_API_KEY`) |
| Scout | Freemium prospecting |
| HubSpot / Salesforce | Sync **leads only** after engagement |

## Inspiration

- Tinyfish-style GPT plugins — research → draft → CRM
- Claude sales MCPs — same loop, human send gate
- Open-source lead agents — multi-source → score → outreach draft

## Intellytics positioning

Outreach templates use Intellytics proof points (pipelines, Snowflake/Databricks, BI, AI/LLM pilots) from [intellytics.ai](https://intellytics.ai).
