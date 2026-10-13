"""Tiny DSL to generate sanitized n8n workflow JSON (credentials by reference only)."""
import json, uuid

NS = uuid.UUID("6e386e38-0000-4000-8000-000000000001")
PG = {"postgres": {"id": "hubPostgres01", "name": "Hub Postgres"}}
GROQ = {"httpHeaderAuth": {"id": "hubGroqAuth01", "name": "Groq API (LLM_API_KEY)"}}
ORIGINS = "https://alfiochoa.github.io,http://localhost:8080,http://127.0.0.1:8080"
TAG = {"id": "hubtag000000001", "name": "n8n-automation-hub"}


class WF:
    def __init__(self, wid, name, tags=(), error_wf=None, desc="", active=False):
        self.id, self.name, self.nodes, self.conns = wid, name, [], {}
        self.tags, self.error_wf, self.desc, self.active = list(tags), error_wf, desc, active

    def add(self, name, type_, params=None, pos=(0, 0), ver=1, creds=None, **extra):
        n = {"parameters": params or {}, "id": str(uuid.uuid5(NS, self.id + name)), "name": name,
             "type": type_, "typeVersion": ver, "position": list(pos)}
        if creds:
            n["credentials"] = creds
        n.update(extra)
        self.nodes.append(n)
        return name

    def link(self, a, b, out=0, inp=0):
        self.conns.setdefault(a, {"main": []})
        m = self.conns[a]["main"]
        while len(m) <= out:
            m.append([])
        m[out].append({"node": b, "type": "main", "index": inp})

    def chain(self, *names):
        for a, b in zip(names, names[1:]):
            self.link(a, b)

    def note(self, title, text, pos, size=(360, 220), color=4):
        return self.add(f"Note: {title}", "n8n-nodes-base.stickyNote",
                        {"content": text, "height": size[1], "width": size[0], "color": color}, pos, 1)

    def layout(self, dx=230, dy=150):
        """Left-to-right auto layout: x = longest-path depth, y = lanes (first child keeps the row, siblings fan out)."""
        names = [n["name"] for n in self.nodes if n["type"] != "n8n-nodes-base.stickyNote"]
        kids = {n: [t["node"] for outs in self.conns.get(n, {"main": []})["main"] for t in outs] for n in names}
        indeg = {n: 0 for n in names}
        for n in names:
            for k in kids[n]:
                indeg[k] += 1
        roots = [n for n in names if indeg[n] == 0]
        depth, order = {}, []
        def visit(n, d, seen):
            if n in seen:
                return                                   # loop-back edge (Split In Batches): ignore for layout
            if depth.get(n, -1) >= d:
                return
            depth[n] = d
            for k in kids[n]:
                visit(k, d + 1, seen | {n})
        for r in roots:
            visit(r, 0, frozenset())
        pos, taken = {}, set()
        def place(n, y):
            while (depth[n], y) in taken:
                y += 1
            taken.add((depth[n], y)); pos[n] = (depth[n], y)
            first = True
            for k in kids[n]:
                if k in pos or k not in depth or depth[k] <= depth[n]:
                    continue
                place(k, y if first else y + 1); first = False
        for i, r in enumerate(roots):
            place(r, i * 2 + 1)
        for nd in self.nodes:
            if nd["name"] in pos:
                x, y = pos[nd["name"]]; nd["position"] = [x * dx, y * dy]
        ys = [p[1] for p in pos.values()] or [0]; xs = [p[0] for p in pos.values()] or [0]
        notes = [n for n in self.nodes if n["type"] == "n8n-nodes-base.stickyNote"]
        for i, nd in enumerate(notes):
            nd["position"] = [0 if i == 0 else max(xs) * dx // 2, (min(ys) * dy - 60 - nd["parameters"]["height"]) if i == 0 else (max(ys) * dy + 230)]

    def json(self):
        self.layout()
        return {"id": self.id, "name": self.name, "active": self.active, "nodes": self.nodes,
                "connections": self.conns,
                "settings": {"executionOrder": "v1", "saveDataErrorExecution": "all",
                             "saveDataSuccessExecution": "all", "saveManualExecutions": True,
                             "executionTimeout": 300, "timezone": "Europe/Madrid",
                             **({"errorWorkflow": self.error_wf} if self.error_wf else {})},
                "tags": [TAG] + [{"id": t[0], "name": t[1]} for t in self.tags],
                "meta": {"templateCredsSetupCompleted": True}, "pinData": {}}


def tag(name):
    return ("hubtag_" + name.replace("-", "_"), name)


# ---- node helpers -------------------------------------------------------------------
def code(wf, name, js, pos, **kw):
    return wf.add(name, "n8n-nodes-base.code", {"jsCode": js.strip()}, pos, 2, **kw)


def webhook(wf, name, path, pos):
    return wf.add(name, "n8n-nodes-base.webhook",
                  {"httpMethod": "POST", "path": path, "responseMode": "responseNode",
                   "options": {"allowedOrigins": ORIGINS}},
                  pos, 2.1, webhookId=str(uuid.uuid5(NS, wf.id + path)))


def respond(wf, name, pos):
    return wf.add(name, "n8n-nodes-base.respondToWebhook",
                  {"respondWith": "json", "responseBody": "={{ $json.response }}",
                   "options": {"responseCode": "={{ $json.status }}"}}, pos, 1.4)


def if_(wf, name, left, pos, op="true"):
    """Boolean IF on an expression. op: true|false|notEmpty|empty."""
    if op in ("true", "false"):
        cond = {"leftValue": left, "rightValue": "", "operator": {"type": "boolean", "operation": op, "singleValue": True}}
    else:
        cond = {"leftValue": left, "rightValue": "", "operator": {"type": "string", "operation": op, "singleValue": True}}
    return wf.add(name, "n8n-nodes-base.if",
                  {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                                  "conditions": [{"id": str(uuid.uuid5(NS, wf.id + name)), **cond}], "combinator": "and"},
                   "options": {}}, pos, 2.2)


def switch(wf, name, expr, values, pos):
    rules = []
    for i, v in enumerate(values):
        rules.append({"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                                     "conditions": [{"id": str(uuid.uuid5(NS, wf.id + name + v)), "leftValue": expr, "rightValue": v,
                                                     "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"},
                      "renameOutput": True, "outputKey": v})
    return wf.add(name, "n8n-nodes-base.switch", {"rules": {"values": rules}, "options": {}}, pos, 3.2)


def pg(wf, name, query, replacement, pos, **kw):
    opts = {}
    if replacement:
        opts["queryReplacement"] = replacement
    return wf.add(name, "n8n-nodes-base.postgres",
                  {"operation": "executeQuery", "query": query, "options": opts}, pos, 2.5, creds=PG,
                  retryOnFail=True, maxTries=3, waitBetweenTries=1000, **kw)


def http(wf, name, url, pos, method="GET", headers=None, qs=None, body=None, timeout=10000, text=False, extra=None, **kw):
    p = {"method": method, "url": url, "options": {"timeout": timeout}}
    if headers:
        p["sendHeaders"] = True
        p["headerParameters"] = {"parameters": [{"name": k, "value": v} for k, v in headers.items()]}
    if qs:
        p["sendQuery"] = True
        p["queryParameters"] = {"parameters": [{"name": k, "value": v} for k, v in qs.items()]}
    if body is not None:
        p["sendBody"] = True
        p["specifyBody"] = "json"
        p["jsonBody"] = body
    if text:
        p["options"]["response"] = {"response": {"responseFormat": "text", "outputPropertyName": "data"}}
    if extra:
        p.update(extra)
    kw.setdefault("retryOnFail", True)
    kw.setdefault("maxTries", 2)
    kw.setdefault("waitBetweenTries", 1500)
    return wf.add(name, "n8n-nodes-base.httpRequest", p, pos, 4.3, **kw)


def exec_wf(wf, name, wid, label, pos, **kw):
    return wf.add(name, "n8n-nodes-base.executeWorkflow",
                  {"workflowId": {"__rl": True, "value": wid, "mode": "list", "cachedResultName": label},
                   "options": {"waitForSubWorkflow": True}}, pos, 1.2, **kw)


def write(wf, outdir):
    import os
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, wf.name + ".json"), "w") as f:
        json.dump(wf.json(), f, indent=2, ensure_ascii=False)
        f.write("\n")
