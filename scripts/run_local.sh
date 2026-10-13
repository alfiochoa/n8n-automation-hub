#!/usr/bin/env bash
# Run the pinned n8n from ./n8n-runtime with the same config shape as production.
# Secrets come from gitignored files in ./secrets (db.env, n8n.env, owner.env, optional llm.env).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
set -a
for f in db.env n8n.env owner.env llm.env; do [ -f "$ROOT/secrets/$f" ] && . "$ROOT/secrets/$f"; done
set +a
export N8N_USER_FOLDER="$ROOT/n8n-runtime/data"
mkdir -p "$N8N_USER_FOLDER"
export N8N_PORT="${N8N_PORT:-5678}" N8N_HOST=localhost N8N_PROTOCOL=http
export WEBHOOK_URL="${WEBHOOK_URL:-http://localhost:$N8N_PORT/}"
export DB_TYPE=postgresdb DB_POSTGRESDB_SCHEMA=n8n DB_POSTGRESDB_SSL_ENABLED=true DB_POSTGRESDB_SSL_REJECT_UNAUTHORIZED=false
export DB_POSTGRESDB_POOL_SIZE=3 DB_POSTGRESDB_CONNECTION_TIMEOUT=30000
export N8N_DIAGNOSTICS_ENABLED=false N8N_PERSONALIZATION_ENABLED=false N8N_VERSION_NOTIFICATIONS_ENABLED=false N8N_TEMPLATES_ENABLED=false
export N8N_SECURE_COOKIE=false            # local http only; production keeps this true
export EXECUTIONS_DATA_PRUNE=true EXECUTIONS_DATA_MAX_AGE=72 EXECUTIONS_DATA_SAVE_ON_SUCCESS=all
export N8N_RUNNERS_ENABLED=false N8N_BLOCK_ENV_ACCESS_IN_NODE=false
export NODE_OPTIONS="--max-old-space-size=384"
export GENERIC_TIMEZONE=Europe/Madrid TZ=Europe/Madrid
export N8N_PUBLIC_API_DISABLED=false NODE_FUNCTION_ALLOW_BUILTIN=crypto N8N_PAYLOAD_SIZE_MAX=1
export HUB_ALLOWED_ORIGIN="${HUB_ALLOWED_ORIGIN:-*}"
export HUB_NOTIFY_URL="${HUB_NOTIFY_URL:-http://localhost:${MOCK_PORT:-5699}/notify}"
export HUB_SELF_URL="${HUB_SELF_URL:-http://localhost:$N8N_PORT}"
export N8N_BIN="$ROOT/n8n-runtime/node_modules/.bin/n8n"
case "${1:-start}" in
  provision) exec "$ROOT/scripts/provision.sh" ;;
  *) exec "$N8N_BIN" "${@:-start}" ;;
esac
