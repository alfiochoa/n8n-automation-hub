#!/usr/bin/env python3
"""Assert the headless fx-digest execution produced a real digest and exactly one mocked notification."""
import json, sys
log, rec = sys.argv[1:3]
txt = open(log, encoding="utf-8").read()
ex = json.loads(txt[txt.index("\n{") + 1:])
assert ex["status"] == "success" and ex["finished"], "execution did not finish successfully"
run = ex["data"]["resultData"]["runData"]
res = run["Digest result"][0]["data"]["main"][0][0]["json"]
pairs = run["Analyse: % move + z-score"][0]["data"]["main"][0][0]["json"]["pairs"]
assert res["pairs"] == 5 and len(pairs) == 5, f"expected 5 currency pairs, got {res['pairs']}"
assert all("z" in p and "pct1d" in p and p["points"] >= 15 for p in pairs), "analysis is missing statistics"
assert "EUR/USD" in res["digest"], "digest text lacks EUR/USD"
sent = json.load(open(rec))
assert len(sent) == 1 and "FX digest" in sent[0]["content"], f"expected one mocked FX notification, got {sent}"
print(f"OK: as_of={res['as_of']} pairs={res['pairs']} unusual={res['unusual']} notified={res['notified']} (mock received {len(sent)} message)")
print(res["digest"])
