#!/usr/bin/env bash
# Start/stop the notify + LLM mocks used by tests and CI. Usage: scripts/mocks.sh start|stop
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; PID="$ROOT/tests/.mocks.pid"
case "${1:-start}" in
  start) [ -f "$PID" ] && kill "$(cat "$PID")" 2>/dev/null; python3 "$ROOT/tests/mock_services.py" > "$ROOT/tests/.mocks.log" 2>&1 & echo $! > "$PID"; sleep 1; echo "mocks pid $(cat "$PID")" ;;
  stop) [ -f "$PID" ] && kill "$(cat "$PID")" 2>/dev/null; rm -f "$PID" ;;
esac
