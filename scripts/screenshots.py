#!/usr/bin/env python3
"""Real canvas screenshots of every workflow (headless Chromium against the local n8n editor) + execution history.
Usage: python3 scripts/screenshots.py [workflow-id ...]   (needs scripts/dev.sh restart running, UI enabled)"""
import json, os, sys
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("BASE", "http://localhost:5678")
OUT = os.path.join(ROOT, "docs", "img")
env = dict(l.strip().split("=", 1) for l in open(os.path.join(ROOT, "secrets", "owner.env")) if "=" in l)
WFS = {"hubLeadIntake01": "lead-intake", "hubSupportTri01": "support-triage-ai", "hubFxDigest0001": "fx-digest-alert",
       "hubPriceScrape1": "price-scraper-alerts", "hubErrorHandle1": "ops-error-handler", "hubHealthReport1": "ops-daily-health-report",
       "hubDlqReplay001": "ops-dead-letter-replay", "hubNotify00001": "sub-notify", "hubNormalize001": "sub-normalise-contact"}


def login(ctx):
    r = ctx.request.post(f"{BASE}/rest/login", data={"emailOrLdapLoginId": env["N8N_OWNER_EMAIL"], "password": env["N8N_OWNER_PASSWORD"]})
    assert r.ok, r.status


def tidy(page):
    page.add_style_tag(content="[class*='notification'], [class*='Toast'], .el-notification {display:none !important}")
    for txt in ("Got it", "Skip", "Close", "Dismiss"):
        try: page.get_by_role("button", name=txt).first.click(timeout=800)
        except Exception: pass


def canvas(page, wid, name, w=3400, h=1200):
    page.set_viewport_size({"width": w, "height": h})
    page.goto(f"{BASE}/workflow/{wid}", wait_until="domcontentloaded")
    page.wait_for_selector(".vue-flow__node", timeout=60000)
    page.wait_for_timeout(2500); tidy(page)
    page.keyboard.press("Shift+1")                       # zoom to fit
    page.wait_for_timeout(1500)
    page.screenshot(path=os.path.join(OUT, f"{name}.png"), clip={"x": 64, "y": 100, "width": w - 64 - 90, "height": h - 100 - 120})
    print("wrote", name)


def main():
    only = set(sys.argv[1:])
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(device_scale_factor=1, viewport={"width": 3400, "height": 1200}, color_scheme="light")
        login(ctx)
        page = ctx.new_page()
        for wid, name in WFS.items():
            if only and wid not in only and name not in only: continue
            canvas(page, wid, name)
        if not only or "executions" in only:
            page.set_viewport_size({"width": 1700, "height": 950})
            page.goto(f"{BASE}/home/executions", wait_until="domcontentloaded"); page.wait_for_timeout(4000); tidy(page)
            page.screenshot(path=os.path.join(OUT, "execution-history.png")); print("wrote execution-history")
        b.close()


if __name__ == "__main__":
    main()
