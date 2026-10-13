#!/usr/bin/env python3
"""Record the workflow's real responses for every demo preset (local n8n + mocks) into docs/samples.json.
The demo page shows them as clearly-labelled 'recorded sample' when no live server is configured."""
import json, os, sys, uuid, requests
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("N8N_BASE_URL", "http://localhost:5678")
presets = json.load(open(os.path.join(ROOT, "docs", "presets.json")))
out, run = {}, uuid.uuid4().hex[:6]
for p in presets:
    path = "demo-lead-intake" if p["flow"] == "lead" else "demo-support-triage"
    key = f"sample-{run}-{p['id']}"
    for i in range(2 if p.get("repeat") else 1):
        r = requests.post(f"{BASE}/webhook/{path}", json=p["body"], headers={"Idempotency-Key": key}, timeout=90)
    out[p["id"]] = {"status": r.status_code, "response": r.json()}
    print(p["id"], r.status_code)
json.dump(out, open(os.path.join(ROOT, "docs", "samples.json"), "w"), indent=1, ensure_ascii=False)
