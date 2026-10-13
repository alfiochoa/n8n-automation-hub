#!/bin/sh
# Container entrypoint (also usable locally): provision -> start n8n privately -> claim owner -> open the public port.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
for v in N8N_ENCRYPTION_KEY DB_POSTGRESDB_HOST DB_POSTGRESDB_USER DB_POSTGRESDB_PASSWORD N8N_OWNER_PASSWORD; do
  eval "val=\${$v:-}"; [ -n "$val" ] || { echo "FATAL: required env $v is not set" >&2; exit 1; }
done
if [ "${HUB_LEAN:-true}" = "true" ] && [ -f "$ROOT/config/lean.env" ]; then set -a; . "$ROOT/config/lean.env"; set +a; fi
PUBLIC_PORT="${PORT:-5678}"
INTERNAL_PORT=5679
export N8N_PORT="$INTERNAL_PORT" N8N_LISTEN_ADDRESS=127.0.0.1
export WF_DIR="${WF_DIR:-$ROOT/workflows}"
export N8N_BIN="${N8N_BIN:-n8n}"

echo "[start] provisioning credentials + workflows"
sh "$HERE/provision.sh"

echo "[start] starting n8n on 127.0.0.1:$INTERNAL_PORT (private)"
"$N8N_BIN" start &
N8N_PID=$!
trap 'kill $N8N_PID 2>/dev/null; kill ${GATE_PID:-0} 2>/dev/null' TERM INT

node "$HERE/bootstrap_owner.js" "http://127.0.0.1:$INTERNAL_PORT"

node --max-old-space-size=16 "$HERE/gate.js" "$PUBLIC_PORT" "$INTERNAL_PORT" &
GATE_PID=$!
echo "[start] ready: owner claimed, public port $PUBLIC_PORT open"
wait $N8N_PID
