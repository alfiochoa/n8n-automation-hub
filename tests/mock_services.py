#!/usr/bin/env python3
"""Local stand-ins used by the test suite and CI (stdlib only).

 * notify mock  :5699  POST /notify  -> records the body;  GET /recorded -> list;  DELETE /recorded -> clear
 * LLM mock     :5698  POST /v1/chat/completions (OpenAI/Groq-compatible). Behaviour is driven by markers in the user message:
      [mock:invalid-json] [mock:bad-enum] [mock:upstream-fail] [mock:slow] [mock:empty] ; otherwise a plausible classification.
"""
import json, re, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RECORDED = []


def classify(text):
    t = text.lower()
    cat = next((c for c, rx in [("billing", r"invoice|refund|charge|payment|bill"), ("technical", r"error|bug|crash|down|outage|broken"),
                                ("account", r"password|login|log in|account"), ("shipping", r"delivery|parcel|shipping|order"),
                                ("sales", r"pricing|quote|demo|enterprise")] if re.search(rx, t)), "other")
    urg = "critical" if re.search(r"outage|data loss|breach", t) else "high" if re.search(r"broken|error|twice|locked", t) else "medium"
    return {"category": cat, "urgency": urg, "summary": text[:100], "draft_reply": f"Thanks for contacting us about your {cat} request. We are on it and will reply shortly."}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path == "/recorded": return self._send(200, RECORDED)
        if self.path.startswith("/broken/catalogue/"):   # a "redesigned" shop page: selectors match nothing
            b = b"<html><body><h1>We are redesigning our shop</h1></body></html>"
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(b))); self.end_headers(); return self.wfile.write(b)
        self._send(404, {})

    def do_DELETE(self):
        RECORDED.clear(); self._send(200, {"cleared": True})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); raw = self.rfile.read(n).decode() if n else ""
        if self.path == "/notify":
            RECORDED.append(json.loads(raw or "{}")); return self._send(204 if False else 200, {"ok": True})
        if self.path.endswith("/chat/completions"):
            body = json.loads(raw); user = body["messages"][-1]["content"]
            if "[mock:upstream-fail]" in user: return self._send(500, {"error": {"message": "mock upstream failure"}})
            if "[mock:slow]" in user: time.sleep(8)
            content = classify(user)
            if "[mock:invalid-json]" in user: content = "Sorry, I cannot produce JSON for this."
            elif "[mock:bad-enum]" in user: content = json.dumps({**content, "category": "weather"})
            elif "[mock:empty]" in user: content = ""
            else: content = json.dumps(content)
            return self._send(200, {"choices": [{"message": {"role": "assistant", "content": content}}]})
        self._send(404, {})


if __name__ == "__main__":
    for port in (5699, 5698):
        threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever, daemon=True).start()
    print("mocks up on 5699 (notify) and 5698 (llm)", flush=True)
    while True: time.sleep(3600)
