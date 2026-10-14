#!/usr/bin/env python3
"""Set the Render service's env vars from gitignored secrets/*.env (never printed) and trigger a deploy.
Usage: python3 scripts/render_deploy.py <service-id> <public-url>   (RENDER_API_KEY from .env.render)"""
import json, os, sys, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def load(p):
    return dict(l.rstrip("\n").split("=", 1) for l in open(os.path.join(ROOT, p)) if "=" in l and not l.startswith("#"))
mode = sys.argv[1]  # "create <ownerId>" | "update <serviceId> <url>"
key = load(".env.render")["RENDER_API_KEY"]
url = (sys.argv[3] if mode == "update" else "https://placeholder.invalid").rstrip("/")
db, n8n, owner, llm = (load(f"secrets/{f}") for f in ("db.env", "n8n.env", "owner.env", "llm.real.env"))
env = {**{k: db[k] for k in ("DB_POSTGRESDB_HOST", "DB_POSTGRESDB_USER", "DB_POSTGRESDB_PASSWORD")},
       "N8N_ENCRYPTION_KEY": n8n["N8N_ENCRYPTION_KEY"], "N8N_OWNER_EMAIL": owner["N8N_OWNER_EMAIL"], "N8N_OWNER_PASSWORD": owner["N8N_OWNER_PASSWORD"],
       "LLM_API_KEY": llm["LLM_API_KEY"], "LLM_BASE_URL": llm["LLM_BASE_URL"], "LLM_MODEL": llm["LLM_MODEL"], "HUB_LLM_TIMEOUT_MS": "15000",
       "WEBHOOK_URL": url + "/", "N8N_EDITOR_BASE_URL": url + "/", "N8N_HOST": url.split("//")[1],
       "HUB_SELF_URL": "http://localhost:5679", "N8N_DISABLE_UI": "true", "HUB_CHAOS": "false"}
def call(method, path, body=None):
    r = urllib.request.Request("https://api.render.com/v1" + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                               headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=60))
if mode == "create":
    r = call("POST", "/services", {"type": "web_service", "name": "n8n-automation-hub", "ownerId": sys.argv[2], "repo": "https://github.com/alfiochoa/n8n-automation-hub",
        "branch": "main", "autoDeploy": "yes", "serviceDetails": {"runtime": "docker", "plan": "free", "region": "frankfurt", "healthCheckPath": "/healthz",
        "envSpecificDetails": {"dockerfilePath": "./Dockerfile", "dockerContext": "."}},
        "envVars": [{"key": k, "value": v} for k, v in env.items()]})
    print("created", r["service"]["id"], r["service"]["serviceDetails"]["url"])
else:
    sid = sys.argv[2]
    call("PUT", f"/services/{sid}/env-vars", [{"key": k, "value": v} for k, v in env.items()])
    print("env vars set:", ", ".join(sorted(env)))
    d = call("POST", f"/services/{sid}/deploys", {"clearCache": "do_not_clear"}); print("deploy", d.get("id"), d.get("status"))
