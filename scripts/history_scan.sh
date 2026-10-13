#!/usr/bin/env bash
# Scan the ENTIRE git history (all branches) for secret patterns and for the literal values held in secrets/*.env.
# Usage: scripts/history_scan.sh   -> exit 1 if anything is found. Prints only file/commit, never the value.
set -uo pipefail
cd "$(dirname "$0")/.."
PAT='postgres(ql)?://[^[:space:]:@/]+:[^[:space:]@/]{3,}@|gsk_[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|rnd_[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|BEGIN [A-Z ]*PRIVATE KEY|(^|[^0-9a-f])[0-9a-f]{64}([^0-9a-f]|$)|hooks\.slack\.com/services/|discord(app)?\.com/api/webhooks/|db\.[a-z0-9]{20}\.supabase\.co'
LIT="$(mktemp)"; trap 'rm -f "$LIT"' EXIT
for f in secrets/*.env .env.render; do [ -f "$f" ] && grep -E '^[A-Z_]*(PASSWORD|KEY|SECRET|TOKEN)[A-Z_]*=' "$f" | cut -d= -f2- | awk 'length($0)>=8' >> "$LIT"; done
bad=0
for c in $(git rev-list --all); do
  if git show --format= -p "$c" -- . ':!tests/test_static.py' ':!scripts/ci_checks.py' ':!scripts/history_scan.sh' | grep -qE "$PAT"; then echo "pattern hit in commit $c: $(git show -s --format=%s "$c")"; bad=1; fi
  if [ -s "$LIT" ] && git show --format= -p "$c" -- . ':!tests/test_static.py' ':!scripts/ci_checks.py' ':!scripts/history_scan.sh' | grep -qF -f "$LIT"; then echo "LITERAL secret value found in commit $c"; bad=1; fi
done
git ls-files | grep -E '(^|/)(\.env($|\.)|secrets/)' | grep -v '\.env\.example$' && bad=1
[ "$bad" = 0 ] && echo "history scan clean ($(git rev-list --all | wc -l | tr -d ' ') commits)" || exit 1
