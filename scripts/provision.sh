#!/bin/sh
# Import credentials + workflows into the n8n instance defined by the current environment, then flag the workflows whose
# JSON says "active": true. Idempotent. Must run while n8n is NOT serving: the CLI shares the database.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
N8N="${N8N_BIN:-n8n}"
WF_DIR="${WF_DIR:-$ROOT/workflows}"
TMP="$(mktemp -d)"; chmod 700 "$TMP"; trap 'rm -rf "$TMP"' EXIT
node "$ROOT/scripts/provision_credentials.js" "$TMP"
"$N8N" import:credentials --input="$TMP/credentials.json" >/dev/null
"$N8N" import:workflow --separate --input="$WF_DIR" >/dev/null
echo "imported $(ls "$WF_DIR"/*.json | wc -l | tr -d ' ') workflows"
node "$ROOT/scripts/activate_workflows.js" "$WF_DIR"
