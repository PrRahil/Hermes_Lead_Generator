# Hermes Lead Machine

Local-only **Tech / Data / AI lead generation agent** inspired by how business owners use [Hermes for cold outreach & prospecting](https://www.reddit.com/r/hermesagent/comments/1w3z7r5/what_i_actually_use_hermes_for_as_a_business_owner/).

It turns public postings into a scored pipeline:

**signal (post) → lead → qualified → outreach draft → deal desk → won/lost**

No VPS required. Everything runs when **you** start it from your terminal.

## What it does

| Capability | Detail |
|---|---|
| Multi-source intake | Demo corpus + live Reddit search + CSV imports for LinkedIn / Upwork / Fiverr / Wellfound / Clutch / Toptal / Indeed + optional Serper web search |
| ICP revenue gate | Filters toward companies meeting your income floor (default **$1M+** revenue) and team size band |
| Staff + requirement capture | Company, buyer title, email status, raw posting requirement |
| Fit scoring | Industry, revenue, title, keyword, and buying-intent reasons (not a black-box score) |
| Post → project conversion | Project summary + estimated deal value for each strong lead |
| Outreach drafts | A/B subject lines + personalized body (LLM if key present, templates otherwise) |
| Deliverability basics | Email validation, disposable/typo blocks, suppression layers, bounce classification helpers |
| Interactive dashboard | KPIs, funnel, platform mix, revenue bands, lead desk, stage moves |

This is **not** a full Beehiiv clone. The long newsletter checklist you shared informed the *ops discipline* (validation, suppression, acquisition source, A/B subjects, merge tags, engagement-ready drafts) without trying to rebuild an ESP, website builder, podcast host, and ad network.

## Quick start (after venv is ready)

```powershell
cd c:\Hermes_Agent
.\.venv\Scripts\Activate.ps1

# optional: copy env and add keys
copy .env.example .env

# create DB
python -m hermes init-db

# wipe demo/seed leads before a real hunt
python -m hermes cleanup --mode all -y

# MAIN COMMAND — continuous hunt + dashboard (leave this open 24–36h)
python -m hermes run
```

Open **http://127.0.0.1:8787** (auto-refreshes every 60s).

Stop anytime with `Ctrl+C`. Leads stay saved in `data/hermes_leads.db`.

ICP keywords in `.env` are the hunt topics — you do **not** need `-q`.

## Manual steps on your side

1. **Activate the venv** whenever you work:
   ```powershell
   cd c:\Hermes_Agent
   .\.venv\Scripts\Activate.ps1
   ```
2. **Optional API keys** in `.env` (copy from `.env.example`):
   - `OPENROUTER_API_KEY` — OpenRouter key (`sk-or-v1-...`); routes OpenAI models cheaply
   - Default model: `openai/gpt-4.1-nano` (cheapest solid OpenAI option for scoring + outreach)
   - `SERPER_API_KEY` — enable `--web` / dashboard “Web (Serper)” search
   - Tune `ICP_MIN_REVENUE_USD`, titles, keywords for your niche
3. **Platform exports**: LinkedIn/Upwork/etc. do not offer free full scrapers here (ToS + reliability). Export or paste rows into CSV using the headers in `data/imports/sample_platform_export.csv`, drop files into `data/imports/`, then run `python -m hermes scan`.
4. **Sending email**: drafts stay local for human review. Connect your own ESP later (Postmark/SES/etc.) if you want automated send — not included by default on purpose.
5. **Reddit live fetch** needs outbound HTTPS from your machine; if it fails, demo + CSV still work.

## CLI reference

```text
python -m hermes init-db
python -m hermes seed
python -m hermes scan [--query TEXT] [--demo/--no-demo] [--reddit/--no-reddit] [--web] [--import path.csv]
python -m hermes dashboard [--host 127.0.0.1] [--port 8787]
python -m hermes version
```

## Pipeline design (Hermes-style)

1. **Prospector** — gather RawSignals from sources  
2. **Enrich / CRM write** — company + contact records  
3. **Deliverability gate** — validate / suppress bad emails  
4. **Qualifier** — ICP + revenue + keyword scoring with reasons  
5. **Outreach agent** — draft A/B email for qualified leads  
6. **Deal desk** — open weighted pipeline opportunities  
7. **Human** — move stages in the dashboard (replied → negotiation → won)

## Project layout

```text
hermes/
  agents/pipeline.py   # orchestration
  sources/             # reddit, demo, csv, web
  scoring/icp.py       # revenue + fit scoring
  email_ops.py         # validation / suppression / merge tags
  analytics.py         # dashboard KPIs
  api.py               # FastAPI
  static/              # interactive UI
data/imports/          # drop CSV exports here
```

## Notes

- Default DB: `data/hermes_leads.db`
- Designed for **local terminal execution only**
- Respect each platform’s terms when collecting leads; prefer official exports / public APIs
