# Architecture

## Runtime topology

```
Internet ──► Render router (TLS) ──► gate.js :$PORT ──► n8n 127.0.0.1:5679 ──► Supabase Postgres (session pooler)
                                     (opens only after            │                schema n8n  = n8n internals
                                      owner is claimed)           │                schema hub  = application tables
                                                                  └─► public APIs / Groq / chat webhook
```

`scripts/start.sh` (container entrypoint): validate required env → `provision.sh` (import credentials + workflows with the n8n CLI, flag live workflows) → start n8n **privately** → `bootstrap_owner.js` (`POST /rest/owner/setup`, then verify login) → start `gate.js` on the public port. A stranger can never reach, let alone claim, an unclaimed editor.

## Data model (`sql/001_hub_schema.sql`, schema `hub`)

| Table | Purpose | Idempotency |
|---|---|---|
| `leads` | scored, routed leads | PK `idempotency_key`, `ON CONFLICT DO NOTHING` |
| `tickets` | triaged tickets incl. `classifier` (`llm`/`fallback`) and `fallback_reason` | PK `idempotency_key` |
| `prices`, `price_events` | latest price per book, history of drops/rises/stock changes | PK `book_id` upsert |
| `dead_letters` | requests whose persistence failed (`pending → replayed/dropped`, `attempts`) | claimed with `FOR UPDATE SKIP LOCKED` |
| `error_log` | structured failures from the global error workflow | append-only |
| `health_reports` | one row per day | unique `report_date` upsert |

RLS is enabled on all tables and the schema is not exposed through Supabase's API (only `public` is).

## Workflow design rules (enforced by `scripts/ci_checks.py`)

1. Webhook → **Respond to Webhook** node, explicit CORS allow-list, `demo-` path prefix.
2. Every HTTP node has a timeout; every Postgres node has retry-on-fail.
3. Parameter expressions read `$json` only; Code nodes assemble context (`$('Node')` in parameters is unreliable on this n8n version).
4. Credentials appear only as references (`hubPostgres01`, `hubGroqAuth01`); no pinned data, no instance ids.
5. Only allow-listed node types; shell/file/SSH/FTP/e-mail nodes are forbidden.
6. Every non-sub workflow sets `errorWorkflow` to `hub-ops-error-handler`.

## Request lifecycle: lead intake

`webhook → validate → [422/413] → normalise (sub-workflow) → dedupe lookup → [duplicate → 200] → MX (DoH) → country (World Bank) → score → persist → [failure → dead-letter → 202] → route(hot|warm|cold) → notify → respond`. The response carries `decision`, `reasons`, `enrichment`, `normalized` and a `trace` array naming each stage that ran; the demo page renders it.

## Request lifecycle: support triage

`webhook → validate → dedupe → (demo switch) → LLM → parse + schema-validate → [invalid → keyword fallback] → assemble ticket (queue, priority) → persist → notify when high/critical/sales → respond`.

## Why the lean profile

n8n 1.123 idles around 440 MB. `config/lean.env` loads only the node types used here, disables unused core modules and caps V8; `N8N_DISABLE_UI=true` removes ~90 MB more. Measured numbers are in the README.
