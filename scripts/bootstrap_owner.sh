#!/bin/sh
# Claim the owner account of a fresh n8n instance (POST /rest/owner/setup) so nobody else can. Idempotent.
# Usage: scripts/bootstrap_owner.sh [BASE_URL] [--generate]
#   locally:      scripts/bootstrap_owner.sh http://localhost:5678 --generate   (password -> secrets/owner.env, gitignored)
#   in the image: N8N_OWNER_PASSWORD comes from the platform's secret env vars
exec node "$(dirname "$0")/bootstrap_owner.js" "$@"
