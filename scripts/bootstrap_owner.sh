#!/usr/bin/env bash
# Claim the owner account of a fresh n8n instance so nobody else can. Idempotent.
# Usage: scripts/bootstrap_owner.sh [BASE_URL]   (default http://localhost:5678)
# Reads N8N_OWNER_EMAIL / N8N_OWNER_PASSWORD from the environment or secrets/owner.env.
# On first run it generates a strong password into secrets/owner.env (gitignored, chmod 600).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${1:-http://localhost:5678}"
OWNER_FILE="$ROOT/secrets/owner.env"
mkdir -p "$ROOT/secrets"
if [ -f "$OWNER_FILE" ]; then set -a; . "$OWNER_FILE"; set +a; fi
EMAIL="${N8N_OWNER_EMAIL:-owner@n8n-hub.local}"
if [ -z "${N8N_OWNER_PASSWORD:-}" ]; then
  N8N_OWNER_PASSWORD="$(python3 -c 'import secrets;print(secrets.token_urlsafe(18)+"Aa1")')"
  umask 077
  printf 'N8N_OWNER_EMAIL=%s\nN8N_OWNER_PASSWORD=%s\n' "$EMAIL" "$N8N_OWNER_PASSWORD" > "$OWNER_FILE"
fi
for i in $(seq 1 60); do
  curl -fsS "$BASE/healthz" >/dev/null 2>&1 && break
  sleep 5
done
SHOW=$(curl -fsS "$BASE/rest/settings" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["userManagement"].get("showSetupOnFirstLoad",False))')
if [ "$SHOW" != "True" ]; then echo "owner already set up on $BASE - nothing to do"; exit 0; fi
CODE=$(PW="$N8N_OWNER_PASSWORD" python3 - "$EMAIL" "$BASE" <<'PY'
import json,os,sys,urllib.request
email,base=sys.argv[1:3]
req=urllib.request.Request(base+"/rest/owner/setup",data=json.dumps({"email":email,"firstName":"Hub","lastName":"Owner","password":os.environ["PW"]}).encode(),headers={"Content-Type":"application/json"},method="POST")
try:
    print(urllib.request.urlopen(req,timeout=60).status)
except urllib.error.HTTPError as e:
    print(e.code, e.read().decode()[:200], file=sys.stderr); print(e.code)
PY
)
echo "owner setup HTTP $CODE (credentials in secrets/owner.env)"
[ "$CODE" = "200" ]
