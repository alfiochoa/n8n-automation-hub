#!/usr/bin/env bash
# Local dev helper: dev.sh restart | stop | logs
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
stop() { pkill -f "[s]cripts/gate.js" 2>/dev/null; pkill -f "[n]8n-runtime/node_modules/.bin/n8n" 2>/dev/null; pkill -f "[n]8n-runtime/node_modules/n8n/bin/n8n" 2>/dev/null; sleep 3; }
case "${1:-restart}" in
  stop) stop ;;
  logs) tail -f "$ROOT/n8n-runtime/n8n.log" ;;
  restart) stop; "$ROOT/scripts/run_local.sh" provision | tail -3
    nohup "$ROOT/scripts/run_local.sh" start > "$ROOT/n8n-runtime/n8n.log" 2>&1 &
    for i in $(seq 1 60); do curl -fsS localhost:5678/healthz >/dev/null 2>&1 && { echo "n8n up"; exit 0; }; sleep 2; done; echo "n8n did not come up"; exit 1 ;;
esac
