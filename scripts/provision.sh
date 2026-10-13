#!/usr/bin/env bash
# Import credentials + workflows into the n8n instance defined by the current environment and activate the live ones.
# Idempotent. Must run while n8n is NOT serving (the CLI shares the database); the start script does this before `n8n start`.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
N8N="${N8N_BIN:-n8n}"
WF_DIR="${WF_DIR:-$ROOT/workflows}"
ACTIVATE="${ACTIVATE:-hubLeadIntake01 hubSupportTri01 hubFxDigest0001 hubPriceScrape1 hubHealthReport1 hubDlqReplay001}"
TMP="$(mktemp -d)"; chmod 700 "$TMP"; trap 'rm -rf "$TMP"' EXIT
node "$ROOT/scripts/provision_credentials.js" "$TMP"
"$N8N" import:credentials --input="$TMP/credentials.json" >/dev/null
for f in "$WF_DIR"/*.json; do "$N8N" import:workflow --input="$f" >/dev/null; done
echo "imported $(ls "$WF_DIR"/*.json | wc -l) workflows"
for id in $ACTIVATE; do "$N8N" update:workflow --id="$id" --active=true >/dev/null 2>&1 || echo "WARN could not activate $id"; done
echo "activated: $ACTIVATE"
