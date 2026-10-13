# Runbook

## Deploy (Render free, Docker)

1. Supabase: use the **Session Pooler** string (`aws-0-<region>.pooler.supabase.com:5432`, user `postgres.<project-ref>`). Apply the schema once: `node scripts/db_apply.js` (reads `secrets/db.env`).
2. Render → New → Blueprint from this repo (`render.yaml`), or create a Docker web service (region Frankfurt, plan Free, health check `/healthz`).
3. Set the environment variables marked `sync: false` in `render.yaml` (see [`.env.example`](../.env.example)): `N8N_ENCRYPTION_KEY`, `N8N_OWNER_PASSWORD`, `DB_POSTGRESDB_HOST/USER/PASSWORD`, `WEBHOOK_URL`/`N8N_EDITOR_BASE_URL`/`N8N_HOST` (the service URL), optional `LLM_API_KEY`, `HUB_NOTIFY_URL`.
4. First boot: migrations + import take a few minutes on the free CPU. Logs show `[start] ready: owner claimed, public port … open`.
5. GitHub: repo variable `N8N_BASE_URL` = service URL (keepalive), Pages from `/docs`, and set `window.HUB_API` in `docs/config.js` to the service URL.

Generate secrets locally, never in the repo: `openssl rand -hex 32` (encryption key); owner password ≥ 8 chars with a number and a capital. Keep them in `secrets/` (gitignored) and your password manager.

## Open the editor

The deployed default is headless. Set `N8N_DISABLE_UI=false` and redeploy, sign in as the owner (`N8N_OWNER_EMAIL` / `N8N_OWNER_PASSWORD`). Expect ~90 MB more RAM; switch it back off afterwards.

## Rotate keys

| Secret | Procedure |
|---|---|
| `LLM_API_KEY` | Update the env var, redeploy (credentials are re-imported at every boot). |
| DB password | Reset in Supabase, update `DB_POSTGRESDB_PASSWORD`, redeploy. |
| `HUB_NOTIFY_URL` | Update env var; no redeploy of code needed beyond restart. |
| `N8N_OWNER_PASSWORD` | Change inside n8n (Settings → Personal) and update the env var so bootstrap verification stays green. |
| `N8N_ENCRYPTION_KEY` | **Do not rotate casually**: stored credentials are encrypted with it. Changing it means re-importing credentials (they are re-created from env at boot, so a redeploy with the new key restores them) and invalidates any credential created by hand in the UI. |

## Import / export workflows

Source of truth is `scripts/wf/*.py` → `workflows/*.json` (`python3 scripts/build_workflows.py`). To pull a change made in the UI back into git: `n8n export:workflow --all --separate --output=tmp/` and port the change into the generator (CI rejects drift). Import is automatic at every boot (`scripts/provision.sh`); manual: `scripts/run_local.sh provision`.

## Restore

- **Workflows/credentials lost** (empty n8n schema): redeploy. Boot re-imports everything from the image + env.
- **Data tables** (`hub.*`): Supabase point-in-time/daily backups on paid plans; on free, `pg_dump` the `hub` schema periodically: `pg_dump --schema=hub "$DATABASE_URL" > hub.sql`. The demo data is synthetic and disposable.
- **Dead letters**: nothing to restore; `hub-ops-dead-letter-replay` retries every 15 min. Inspect: `select * from hub.dead_letters where status <> 'replayed' order by id desc`.

## Health & triage

- Is it up? `GET /healthz`. Is it warm? Check the keepalive runs in GitHub Actions.
- Something failed? `select * from hub.error_log order by id desc limit 20`, or the daily health report in the chat channel.
- LLM misbehaving? The health report's *LLM fallback* counter rises; tickets are still routed.
- Out of memory (Render restarts the service)? Keep `N8N_DISABLE_UI=true`, lower `SCRAPE_PAGES`, lower `EXECUTIONS_DATA_MAX_AGE`.

## Upgrade n8n

Change the version in `Dockerfile`, `.github/workflows/ci.yml` (`N8N_VERSION`) and `n8n-runtime` together; run the full test suite locally; read the n8n release notes (this repo relies on CLI `import:workflow`, `execute --id`, `activeVersionId`).
