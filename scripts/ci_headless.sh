#!/usr/bin/env bash
# Headless proof that the repo works end to end with NO database server and NO secrets:
#   fresh SQLite n8n -> import every workflow -> execute hub-fx-digest-alert through the CLI against the REAL Frankfurter API,
#   with the notifier mocked by a local HTTP server -> assert the digest and the notification payload -> keep the logs.
# Usage: scripts/ci_headless.sh [N8N_BIN]   (artifacts land in ./artifacts)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
N8N="${1:-$ROOT/n8n-runtime/node_modules/.bin/n8n}"
OUT="$ROOT/artifacts"; mkdir -p "$OUT"; rm -f "$OUT"/*
export N8N_USER_FOLDER="$(mktemp -d)"
unset DB_TYPE DB_POSTGRESDB_HOST DB_POSTGRESDB_SCHEMA DB_POSTGRESDB_USER DB_POSTGRESDB_PASSWORD
export N8N_DIAGNOSTICS_ENABLED=false N8N_RUNNERS_ENABLED=false N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=false NODE_FUNCTION_ALLOW_BUILTIN=crypto
export N8N_ENCRYPTION_KEY="ci-only-$(date +%s)-not-a-secret" N8N_BLOCK_ENV_ACCESS_IN_NODE=false
export HUB_NOTIFY_URL="http://127.0.0.1:5699/notify"

python3 "$ROOT/tests/mock_services.py" > "$OUT/mock.log" 2>&1 & MOCK=$!
trap 'kill $MOCK 2>/dev/null || true; rm -rf "$N8N_USER_FOLDER"' EXIT
for _ in $(seq 1 20); do curl -fsS http://127.0.0.1:5699/recorded >/dev/null 2>&1 && break; sleep 0.5; done

echo "== import workflows"
"$N8N" import:workflow --separate --input="$ROOT/workflows" 2>&1 | tee "$OUT/import.log" | tail -3

echo "== execute hub-fx-digest-alert (real Frankfurter API, mocked notifier)"
ok=0
for attempt in 1 2 3; do                                   # the public API is free: tolerate one transient hiccup
  if "$N8N" execute --id=hubFxDigest0001 > "$OUT/fx-execution.log" 2>&1 && grep -q '"status": "success"' "$OUT/fx-execution.log"; then ok=1; break; fi
  echo "attempt $attempt failed, retrying"; sleep 5
done
[ "$ok" = 1 ] || { echo "execution failed"; tail -40 "$OUT/fx-execution.log"; exit 1; }
curl -fsS http://127.0.0.1:5699/recorded > "$OUT/notification-recorded.json"
python3 "$ROOT/scripts/ci_assert_fx.py" "$OUT/fx-execution.log" "$OUT/notification-recorded.json"
