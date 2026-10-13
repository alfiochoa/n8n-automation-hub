#!/bin/sh
# Sample total RSS (MB) of all n8n/gate node processes every second into a file. Usage: rss_sampler.sh OUT SECONDS
OUT="$1"; N="${2:-60}"; : > "$OUT"
i=0; while [ "$i" -lt "$N" ]; do
  ps -eo rss,args | grep -E "[n]8n start|[g]ate.js" | grep -v "rss_sampler" | awk '{s+=$1} END {printf "%.1f\n", s/1024}' >> "$OUT"
  sleep 1; i=$((i+1)); done
