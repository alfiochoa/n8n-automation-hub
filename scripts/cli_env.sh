# source me: environment for running the n8n CLI against the local instance (same DB, no server needed)
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -a; for f in db.env n8n.env llm.env; do [ -f "$ROOT/secrets/$f" ] && . "$ROOT/secrets/$f"; done; set +a
export N8N_USER_FOLDER="$ROOT/n8n-runtime/data" DB_TYPE=postgresdb DB_POSTGRESDB_SCHEMA=n8n DB_POSTGRESDB_SSL_ENABLED=true DB_POSTGRESDB_SSL_REJECT_UNAUTHORIZED=false
export N8N_RUNNERS_ENABLED=false N8N_DIAGNOSTICS_ENABLED=false N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=false NODE_FUNCTION_ALLOW_BUILTIN=crypto
export HUB_NOTIFY_URL="${HUB_NOTIFY_URL:-http://127.0.0.1:5699/notify}" HUB_SELF_URL="${HUB_SELF_URL:-http://localhost:5678}"
export N8N_BIN="$ROOT/n8n-runtime/node_modules/.bin/n8n"
