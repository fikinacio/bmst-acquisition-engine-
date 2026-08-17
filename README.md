# BMST Acquisition Engine

Automated B2B client acquisition system for BMST / Bisca Mais Sistemas e Tecnologias (Angola).

Multi-agent pipeline: landing page → WhatsApp qualification bot → prospecting crew → content engine → nurture sequence.

## Architecture

```
Landing Page (Vercel)
    │ POST lead
    ▼
n8n Workflow 01 — Inbound Webhook
    │ creates/updates Airtable record
    ▼
n8n Workflow 03 — WhatsApp Router (Evolution API)
    │ routes inbound messages
    ▼
FastAPI /qualify ──► LangGraph Qualification Bot
    │                      │ Google Calendar
    │                      ▼
    │               Airtable (companies + interactions)
    ▼
FastAPI /run-prospecting ──► crewAI Prospecting Crew
    │                              │ Angolan job boards + Apify/LinkedIn
    │                              ▼
    │                        n8n Prospecting Webhook
    ▼
FastAPI /generate-content ──► LangChain Content Engine
    │                                    │
    │                                    ▼
    │                         LinkedIn + Instagram posts
    ▼
n8n Workflow 06 — Nurture Sequence (scheduled Mon–Fri 09:30 WAT)
    │ D14/D30/D60/D75 touches → Evolution API
    ▼
n8n Workflow 05 — Error Handler
    │ centralised error log → Airtable errors table + Slack
    ▼
                          All workflow errors
```

## Phase Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Repository skeleton | ✅ Complete |
| 2 | Airtable schema | ✅ Complete |
| 3 | Landing page | ✅ Complete |
| 4 | n8n Workflow 01 (Inbound) | ✅ Complete |
| 5 | Qualification bot (LangGraph) | ✅ Complete |
| 6 | n8n Workflow 03 (WhatsApp router) | ✅ Complete |
| 7 | Prospecting agent (crewAI) | ✅ Complete |
| 8 | Content engine (LangChain) | ✅ Complete |
| 9 | Nurture sequence | ✅ Complete |
| 10 | Error handler & finalisation | ✅ Complete |

## Quick Start

```bash
cp .env.example .env
# Fill in all values in .env

pip install -r requirements.txt

# Sync Airtable schema (run once)
python airtable/create_schema.py

# Run FastAPI service
uvicorn api.main:app --host $API_HOST --port $API_PORT

# Import n8n workflows (activate in this order)
# 1. 05_error_handler.json  — must be active first
# 2. 01_inbound_webhook.json
# 3. 03_whatsapp_router.json
# 4. 06_nurture_sequence.json
```

See `docs/setup_guide.md` for the full phase-by-phase setup with test commands.

## Repository Layout

```
agents/
  qualification_bot/   LangGraph WhatsApp qualification bot
    nodes.py           10 Q-nodes + 4 nurture nodes + requalify
    graph.py           StateGraph with conditional edges
    prompts.py         All 15 prompt templates (PT-PT)
    state.py           ConversationState dataclass
    tools/             Airtable CRUD + Google Calendar
  prospecting/         crewAI job-board prospecting crew
    agents.py          scraper, classifier, decision_finder agents
    tasks.py           scrape → classify → resolve task chain
    crew.py            Crew assembly + n8n webhook dispatch
    tools/             scraper, classifier, decision_finder tools
  content_engine/      LangChain LinkedIn/Instagram content pipeline
    chain.py           run_content_chain() with 2-pass validation
    prompts.py         LINKEDIN_POST_PROMPT + INSTAGRAM_POST_PROMPT
    templates.py       Validators + FORBIDDEN_PHRASES
api/
  main.py              FastAPI: /health /qualify /run-prospecting /generate-content
airtable/
  create_schema.py     Idempotent schema creator (companies + interactions + errors)
  views.md             Airtable view definitions
landing_page/
  index.html           Static HTML lead-capture form (Vercel deploy)
n8n_workflows/
  01_inbound_webhook.json   Lead intake → Airtable upsert
  03_whatsapp_router.json   Evolution API → qualification bot
  05_error_handler.json     Centralised error log + Slack alert + retry
  06_nurture_sequence.json  Scheduled nurture touches (D14/D30/D60/D75)
docs/
  setup_guide.md            Full setup walkthrough + curl tests + common errors
  prompt_changelog.md       Versioned prompt change log
  evolution_api_config.md   Evolution API webhook configuration
credentials/                Service account keys (git-ignored)
```

## n8n Workflow Overview

| File | Trigger | Purpose |
|------|---------|---------|
| `01_inbound_webhook.json` | POST `/webhook/inbound` | Landing page lead → Airtable upsert |
| `03_whatsapp_router.json` | Evolution API webhook | Route WA messages → qualification bot |
| `05_error_handler.json` | POST `/webhook/error-handler` | Log errors + Slack alert + Evolution retry |
| `06_nurture_sequence.json` | Cron `30 8 * * 1-5` (09:30 WAT) | Automated nurture touches |

## Environment Variables

See `.env.example` for all required variables. All 18 variables are documented with their purpose.

Key variables by component:

| Component | Variables |
|-----------|-----------|
| Airtable | `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID` |
| LLM | `ANTHROPIC_API_KEY` |
| WhatsApp | `EVOLUTION_API_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE` |
| n8n | `N8N_WEBHOOK_BASE_URL`, `N8N_PROSPECTING_WEBHOOK_PATH`, `FASTAPI_BASE_URL` |
| Google Calendar | `GOOGLE_CALENDAR_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON` |
| Apify | `APIFY_API_TOKEN` |
| Notifications | `SLACK_WEBHOOK_URL`, `NOTIFICATION_EMAIL` |
| Vercel | `NEXT_PUBLIC_N8N_WEBHOOK_URL`, `BMST_WHATSAPP_NUMBER` |
| FastAPI | `API_HOST`, `API_PORT` |

---

*BMST · Bisca Mais Sistemas e Tecnologias · contact@biscaplus.com*
