#!/usr/bin/env python3
"""Print per-node results/errors of the latest (or given) n8n execution via the editor REST API. Local debugging aid."""
import json, sys, urllib.request, http.cookiejar, os
base = os.environ.get("BASE", "http://localhost:5678")
env = dict(l.strip().split("=", 1) for l in open(os.path.join(os.path.dirname(__file__), "..", "secrets", "owner.env")) if "=" in l)
cj = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
def call(path, data=None):
    req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data else None, headers={"Content-Type": "application/json"})
    return json.load(op.open(req, timeout=60))
call("/rest/login", {"emailOrLdapLoginId": env["N8N_OWNER_EMAIL"], "password": env["N8N_OWNER_PASSWORD"]})
wid = sys.argv[1] if len(sys.argv) > 1 else None
q = "/rest/executions?limit=3" + (f"&filter=%7B%22workflowId%22%3A%22{wid}%22%7D" if wid else "")
lst = call(q)["data"]["results"]
ex = call(f"/rest/executions/{lst[0]['id']}?includeData=true")["data"]
print("execution", lst[0]["id"], lst[0]["status"], lst[0].get("workflowName"))
import re
data = ex["data"]
# data is flatted-json string
def unflatten(s):
    arr = json.loads(s)
    memo = {}
    def res(i):
        if i in memo: return memo[i]
        v = arr[i]
        if isinstance(v, dict):
            memo[i] = out = {}
            for k, x in v.items(): out[k] = res(int(x)) if isinstance(x, str) and x.isdigit() else x
        elif isinstance(v, list):
            memo[i] = out = []
            for x in v: out.append(res(int(x)) if isinstance(x, str) and x.isdigit() else x)
        else: memo[i] = out = v
        return out
    return res(0)
d = unflatten(data) if isinstance(data, str) else data
rd = d["resultData"]
for name, runs in rd["runData"].items():
    for r in runs:
        err = r.get("error")
        out = (r.get("data") or {}).get("main")
        summ = ""
        if out:
            summ = " | ".join(f"out{ i}:{len(o or [])}" for i, o in enumerate(out))
            first = next((o[0]["json"] for o in out if o), None)
            if first is not None: summ += " " + json.dumps(first)[:int(os.environ.get("W", 300))]
        print(("ERR " if err else "ok  ") + name, (err or {}).get("message", ""), summ)
if rd.get("error"): print("TOP ERROR", rd["error"].get("message"))
