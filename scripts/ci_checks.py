#!/usr/bin/env python3
"""Static guard-rails for the workflow JSON and the repo. Exit code != 0 on any violation.

 1. lint      every workflow parses, ids/names unique, connections point at real nodes, sticky-note docs present, tags set
 2. leaks     no credentials / secrets / instance ids / real project refs anywhere in tracked files; credential refs are placeholders only
 3. allowlist only vetted node types; dangerous ones (shell, ssh, file system, ftp, email) are forbidden
 4. hygiene   timeouts on HTTP nodes, retries on DB nodes, CORS + respond-node on webhooks, error workflow wired
"""
import glob, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED_NODE_TYPES = {
    "n8n-nodes-base.webhook", "n8n-nodes-base.respondToWebhook", "n8n-nodes-base.code", "n8n-nodes-base.if", "n8n-nodes-base.switch",
    "n8n-nodes-base.httpRequest", "n8n-nodes-base.postgres", "n8n-nodes-base.scheduleTrigger", "n8n-nodes-base.manualTrigger",
    "n8n-nodes-base.wait", "n8n-nodes-base.splitInBatches", "n8n-nodes-base.executeWorkflow", "n8n-nodes-base.executeWorkflowTrigger",
    "n8n-nodes-base.errorTrigger", "n8n-nodes-base.htmlExtract", "n8n-nodes-base.stickyNote", "n8n-nodes-base.noOp", "n8n-nodes-base.set",
}
FORBIDDEN = {"n8n-nodes-base.executeCommand", "n8n-nodes-base.ssh", "n8n-nodes-base.readWriteFile", "n8n-nodes-base.ftp", "n8n-nodes-base.sftp",
             "n8n-nodes-base.emailSend", "n8n-nodes-base.localFileTrigger", "n8n-nodes-base.readBinaryFile", "n8n-nodes-base.writeBinaryFile"}
CRED_PLACEHOLDERS = {("postgres", "hubPostgres01"), ("httpHeaderAuth", "hubGroqAuth01")}
SECRET_PATTERNS = {
    "postgres url with password": r"postgres(?:ql)?://[^\s:@/]+:[^\s@/]{3,}@",
    "groq/openai-style key": r"\b(?:gsk_|sk-)[A-Za-z0-9_\-]{20,}",
    "github token": r"\bgh[pousr]_[A-Za-z0-9]{30,}",
    "render api key": r"\brnd_[A-Za-z0-9]{20,}",
    "jwt": r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",
    "private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "64-hex secret (encryption key)": r"(?<![0-9a-fA-F])[0-9a-f]{64}(?![0-9a-fA-F])",
    "discord/slack webhook url": r"https://(?:discord(?:app)?\.com/api/webhooks|hooks\.slack\.com/services)/\S+",
    "supabase project host": r"\bdb\.[a-z0-9]{20}\.supabase\.co\b",
    "n8n instance/api key": r"\bn8n_api_[A-Za-z0-9]{20,}",
}
SKIP_DIRS = {".git", "n8n-runtime", "secrets", "node_modules", "__pycache__", ".pytest_cache", "artifacts", "tmp"}
TEXT_EXT = {".json", ".js", ".py", ".sh", ".md", ".yml", ".yaml", ".html", ".css", ".txt", ".sql", ".env", ".example", ".toml", ""}


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
        files = [f for f in out if f]
        if files:
            return [os.path.join(ROOT, f) for f in files if os.path.exists(os.path.join(ROOT, f))]
    except Exception:
        pass
    res = []
    for d, dirs, fs in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        res += [os.path.join(d, f) for f in fs]
    return res


def load_workflows():
    wfs = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "workflows", "*.json"))):
        wfs[os.path.basename(p)] = json.load(open(p, encoding="utf-8"))
    return wfs


def check_lint(wfs, errs):
    if not wfs:
        errs.append("lint: no workflows found")
    ids, names = {}, {}
    for f, w in wfs.items():
        for k in ("id", "name", "nodes", "connections", "settings"):
            if k not in w:
                errs.append(f"lint: {f} missing '{k}'")
        if w.get("id") in ids:
            errs.append(f"lint: duplicate workflow id {w['id']} ({f} and {ids[w['id']]})")
        ids[w.get("id")] = f
        names[w.get("name")] = f
        if not str(w.get("name", "")).startswith("hub-") or f != f"{w.get('name')}.json":
            errs.append(f"lint: {f}: name must be 'hub-<slug>' and match the file name")
        nn = [n["name"] for n in w["nodes"]]
        if len(nn) != len(set(nn)):
            errs.append(f"lint: {f}: duplicate node names")
        nids = [n["id"] for n in w["nodes"]]
        if len(nids) != len(set(nids)):
            errs.append(f"lint: {f}: duplicate node ids")
        for src, c in w["connections"].items():
            if src not in nn:
                errs.append(f"lint: {f}: connection from unknown node '{src}'")
            for outs in c.get("main", []):
                for t in outs:
                    if t["node"] not in nn:
                        errs.append(f"lint: {f}: connection '{src}' -> unknown node '{t['node']}'")
        if not any(n["type"] == "n8n-nodes-base.stickyNote" for n in w["nodes"]):
            errs.append(f"lint: {f}: no Sticky Note documentation on the canvas")
        if not w.get("tags"):
            errs.append(f"lint: {f}: no tags")
        triggers = [n for n in w["nodes"] if re.search(r"(Trigger|webhook)$", n["type"], re.I)]
        if not triggers:
            errs.append(f"lint: {f}: no trigger node")
    for f, w in wfs.items():
        ew = w["settings"].get("errorWorkflow")
        if ew and ew not in ids:
            errs.append(f"lint: {f}: errorWorkflow '{ew}' is not in this repo")
        for n in w["nodes"]:
            if n["type"] == "n8n-nodes-base.executeWorkflow":
                tid = n["parameters"].get("workflowId", {}).get("value")
                if tid not in ids:
                    errs.append(f"lint: {f}: node '{n['name']}' executes unknown workflow '{tid}'")


def check_allowlist(wfs, errs):
    for f, w in wfs.items():
        for n in w["nodes"]:
            if n["type"] in FORBIDDEN:
                errs.append(f"allowlist: {f}: forbidden node type {n['type']} ('{n['name']}')")
            elif n["type"] not in ALLOWED_NODE_TYPES:
                errs.append(f"allowlist: {f}: node type {n['type']} ('{n['name']}') is not in the allowlist")


def check_workflow_leaks(wfs, errs):
    for f, w in wfs.items():
        if w.get("pinData"):
            errs.append(f"leaks: {f}: pinData must be empty in committed workflows")
        for k in ("instanceId", "staticData", "versionId", "triggerCount", "shared", "homeProject"):
            if k in w and w[k]:
                errs.append(f"leaks: {f}: instance-specific key '{k}' present")
        for n in w["nodes"]:
            for ctype, ref in (n.get("credentials") or {}).items():
                if (ctype, ref.get("id")) not in CRED_PLACEHOLDERS or set(ref) - {"id", "name"}:
                    errs.append(f"leaks: {f}: node '{n['name']}' credential reference {ctype}/{ref} is not an approved placeholder")
            blob = json.dumps(n.get("parameters", {}))
            if re.search(r"authorization\W+bearer\s+[A-Za-z0-9]", blob, re.I):
                errs.append(f"leaks: {f}: node '{n['name']}' hard-codes a bearer token")
            if re.search(r"https?://[^\"'\s]*(?:localhost|127\.0\.0\.1)", blob) and "$env" not in blob and n["type"] not in ("n8n-nodes-base.stickyNote", "n8n-nodes-base.webhook"):
                errs.append(f"leaks: {f}: node '{n['name']}' hard-codes a localhost URL")


def check_repo_leaks(errs):
    extra = []
    for sf in ("db.env", "n8n.env", "owner.env", "llm.env"):          # local-only: also scan for the literal secret values
        p = os.path.join(ROOT, "secrets", sf)
        if os.path.exists(p):
            for line in open(p):
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    if len(v) >= 8 and k.endswith(("PASSWORD", "KEY", "SECRET")):
                        extra.append((f"literal value of {k}", re.escape(v)))
    for p in tracked_files():
        rel = os.path.relpath(p, ROOT)
        if rel.startswith(("secrets/", "n8n-runtime/")) or os.path.splitext(p)[1].lower() in (".png", ".jpg", ".mp4", ".mp3", ".woff2", ".ico", ".pdf"):
            continue
        if os.path.basename(rel) in ("ci_checks.py", "test_static.py", "history_scan.sh"):
            continue                                                  # contains the patterns themselves
        try:
            text = open(p, encoding="utf-8").read()
        except Exception:
            continue
        for label, rx in list(SECRET_PATTERNS.items()) + extra:
            m = re.search(rx, text)
            if m:
                errs.append(f"leaks: {rel}: looks like a {label}")
        if re.search(r"^\s*(N8N_ENCRYPTION_KEY|N8N_OWNER_PASSWORD|DB_POSTGRESDB_PASSWORD|LLM_API_KEY|RENDER_API_KEY)\s*=\s*\S+", text, re.M) \
                and not rel.endswith((".md", ".example")):
            errs.append(f"leaks: {rel}: assigns a real-looking value to a secret variable")
    for forbidden in (".env", ".env.render", "secrets"):
        if any(os.path.relpath(p, ROOT).split(os.sep)[0] == forbidden for p in tracked_files()):
            errs.append(f"leaks: '{forbidden}' is tracked by git")


def check_hygiene(wfs, errs):
    for f, w in wfs.items():
        for n in w["nodes"]:
            t, p, nm = n["type"], n["parameters"], n["name"]
            if t == "n8n-nodes-base.httpRequest" and "timeout" not in p.get("options", {}):
                errs.append(f"hygiene: {f}: HTTP node '{nm}' has no timeout")
            if t == "n8n-nodes-base.postgres" and not n.get("retryOnFail"):
                errs.append(f"hygiene: {f}: Postgres node '{nm}' has no retry-on-fail")
            if t == "n8n-nodes-base.webhook":
                if p.get("responseMode") != "responseNode":
                    errs.append(f"hygiene: {f}: webhook '{nm}' must respond via a Respond node")
                if not p.get("options", {}).get("allowedOrigins") or "*" in p["options"]["allowedOrigins"]:
                    errs.append(f"hygiene: {f}: webhook '{nm}' needs an explicit CORS allow-list (no '*')")
                if not p.get("path", "").startswith("demo-"):
                    errs.append(f"hygiene: {f}: webhook path '{p.get('path')}' must be demo-only (prefix 'demo-')")
            if re.search(r"\$\('", json.dumps(p)) and t != "n8n-nodes-base.code":
                errs.append(f"hygiene: {f}: node '{nm}' uses $('Node') in a parameter expression (unreliable in this n8n version; use $json)")
        if f not in ("hub-ops-error-handler.json", "hub-sub-notify.json", "hub-sub-normalise-contact.json") and not w["settings"].get("errorWorkflow"):
            errs.append(f"hygiene: {f}: no errorWorkflow configured")


def main(argv=None):
    errs = []
    wfs = load_workflows()
    check_lint(wfs, errs); check_allowlist(wfs, errs); check_workflow_leaks(wfs, errs); check_repo_leaks(errs); check_hygiene(wfs, errs)
    if errs:
        print("\n".join(sorted(set(errs))))
        print(f"\nFAILED: {len(set(errs))} problem(s)")
        return 1
    n = sum(len(w["nodes"]) for w in wfs.values())
    print(f"OK: {len(wfs)} workflows, {n} nodes - lint, allowlist, leak scan and hygiene all clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
