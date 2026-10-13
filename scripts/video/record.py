#!/usr/bin/env python3
"""Record the screen scenes for the demo video with Playwright (1280x600 viewport, visible cursor, eased scrolling/panning).
Needs: local n8n with UI (scripts/dev.sh restart), mocks (scripts/mocks.sh start), docs served on :8080 (python3 -m http.server 8080 -d docs)."""
import json, os, sys, time, math
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "tmp", "video")
BASE, DEMO = "http://localhost:5678", "http://localhost:8080/?compact=1&api=http://localhost:5678"
env = dict(l.strip().split("=", 1) for l in open(os.path.join(ROOT, "secrets", "owner.env")) if "=" in l)
W, H = 1280, 600

CURSOR = """
(() => { const setup = () => { if (window.__cur) return;
  const c = document.createElement('div'); c.id='__cur'; window.__cur = c;
  c.style.cssText='position:fixed;left:0;top:0;width:26px;height:26px;z-index:2147483647;pointer-events:none;transform:translate(-100px,-100px);filter:drop-shadow(0 2px 3px rgba(0,0,0,.45))';
  c.innerHTML='<svg width="26" height="26" viewBox="0 0 24 24"><path d="M4 2l14 9-6 1.5L9 19z" fill="#fff" stroke="#111" stroke-width="1.5" stroke-linejoin="round"/></svg>';
  const ring = document.createElement('div'); ring.style.cssText='position:fixed;left:0;top:0;width:34px;height:34px;margin:-17px 0 0 -17px;border:3px solid #2a78d6;border-radius:50%;opacity:0;z-index:2147483646;pointer-events:none';
  ring.id='__ring'; document.documentElement.appendChild(ring); document.documentElement.appendChild(c);
  addEventListener('mousemove', e => { c.style.transform=`translate(${e.clientX-4}px,${e.clientY-2}px)`; ring.style.left=e.clientX+'px'; ring.style.top=e.clientY+'px'; }, true);
  addEventListener('mousedown', () => { ring.animate([{opacity:.9,transform:'scale(.4)'},{opacity:0,transform:'scale(1.4)'}],{duration:450}); }, true);
  }; if (document.body) setup(); else addEventListener('DOMContentLoaded', setup); })();
"""
ease = lambda t: t * t * (3 - 2 * t)


class Rec:
    def __init__(self, p, name, wide=False):
        vw, vh = (1360, 638) if wide else (W, H)
        self.name = name
        self.b = p.chromium.launch()
        self.ctx = self.b.new_context(viewport={"width": vw, "height": vh}, record_video_dir=os.path.join(OUT, "raw_" + name),
                                      record_video_size={"width": W, "height": H}, color_scheme="light")
        self.ctx.add_init_script(CURSOR)
        self.page = self.ctx.new_page(); self.x, self.y = vw // 2, vh // 2
        self.t0 = time.time()

    def login(self):
        r = self.ctx.request.post(f"{BASE}/rest/login", data={"emailOrLdapLoginId": env["N8N_OWNER_EMAIL"], "password": env["N8N_OWNER_PASSWORD"]})
        assert r.ok

    def wait(self, s): self.page.wait_for_timeout(int(s * 1000))

    def move(self, x, y, dur=0.7):
        n = max(8, int(dur * 40)); x0, y0 = self.x, self.y
        for i in range(1, n + 1):
            t = ease(i / n); self.page.mouse.move(x0 + (x - x0) * t, y0 + (y - y0) * t); self.page.wait_for_timeout(int(dur * 1000 / n))
        self.x, self.y = x, y

    def click(self, sel, dur=0.8, **kw):
        loc = self.page.locator(sel).first; loc.scroll_into_view_if_needed(); b = loc.bounding_box()
        self.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, dur); self.wait(0.15); self.page.mouse.down(); self.page.mouse.up(); self.wait(0.2)

    def scroll(self, dy, dur=1.2):
        self.page.evaluate("""([dy, dur]) => new Promise(res => { const y0 = scrollY, t0 = performance.now();
          const f = t => { const k = Math.min(1, (t - t0) / (dur * 1000)); const e = k * k * (3 - 2 * k); scrollTo(0, y0 + dy * e); k < 1 ? requestAnimationFrame(f) : res(); }; requestAnimationFrame(f); })""", [dy, dur])

    def send(self):
        self.click("#send", 0.8); self.wait(0.4); self.page.wait_for_function("!document.querySelector('#send').disabled", timeout=90000); self.wait(0.5)

    def wheel(self, dx, dy, dur=1.2, ctrl=False):
        n = int(dur * 30); prev = 0
        if ctrl: self.page.keyboard.down("Control")
        for i in range(1, n + 1):
            e = ease(i / n); self.page.mouse.wheel(dx * (e - prev), dy * (e - prev)); prev = e; self.page.wait_for_timeout(int(dur * 1000 / n))
        if ctrl: self.page.keyboard.up("Control")

    def close(self):
        v = self.page.video; self.ctx.close(); path = v.path(); self.b.close()
        dst = os.path.join(OUT, f"{self.name}.webm"); os.replace(path, dst); print("scene", self.name, round(time.time() - self.t0, 1), "s"); return dst


def canvas_open(r, wid):
    r.page.goto(f"{BASE}/workflow/{wid}", wait_until="domcontentloaded"); r.page.wait_for_selector(".vue-flow__node", timeout=60000); r.wait(1.5)
    r.page.add_style_tag(content="[class*='notification'], .el-notification {display:none!important}")
    for t in ("Got it", "Skip"):
        try: r.page.get_by_role("button", name=t).first.click(timeout=600)
        except Exception: pass


def scene_canvas(p):
    r = Rec(p, "s2_canvas"); r.login(); canvas_open(r, "hubLeadIntake01"); r.page.keyboard.press("Shift+1"); r.wait(1.6)
    r.move(300, 330, 0.8); r.wheel(0, -260, 1.6, ctrl=True); r.wait(0.6)          # zoom into the first stages
    r.wheel(-500, 0, 0.1); r.wait(0.2)
    for dx in (700, 700, 700): r.wheel(dx, 0, 1.6); r.wait(0.7)                  # pan across enrich / score / persist
    r.wheel(0, 300, 1.2, ctrl=True); r.wait(0.4); r.page.keyboard.press("Shift+1"); r.wait(1.2)
    canvas_open(r, "hubSupportTri01"); r.page.keyboard.press("Shift+1"); r.wait(1.8)
    r.move(700, 360, 0.8); r.wheel(0, -200, 1.4, ctrl=True); r.wait(0.5); r.wheel(900, 150, 2.0); r.wait(1.5)
    return r.close()


def scene_live_lead(p):
    r = Rec(p, "s3_live", wide=True); r.page.goto(DEMO); r.page.wait_for_selector(".chip"); r.wait(1.4)
    r.click("text=Hot B2B lead", 0.9); r.wait(1.0); r.send()
    r.wait(1.8); r.move(1100, 560, 0.9); r.wait(2.4)
    r.click("text=Same lead twice", 0.9); r.wait(0.6); r.send(); r.wait(0.6); r.send(); r.page.wait_for_selector(".badge.dup"); r.wait(2.2)
    r.click("text=Invalid e-mail", 0.9); r.wait(0.5); r.send(); r.wait(2.0)
    return r.close()


def scene_fallback(p):
    r = Rec(p, "s4_fallback", wide=True); r.page.goto(DEMO); r.page.wait_for_selector(".chip"); r.wait(0.8)
    r.click("#tab-triage", 0.9); r.wait(0.5); r.click("text=Production outage", 0.8); r.wait(0.7); r.send()
    r.wait(2.2)
    r.click("text=LLM is down (simulated)", 1.0); r.wait(1.4); r.send()
    r.move(1150, 560, 0.9); r.wait(3.6)
    return r.close()


def scene_ops(p):
    r = Rec(p, "s5_ops"); r.login(); r.page.goto(f"{BASE}/home/executions", wait_until="domcontentloaded"); r.wait(2.5)
    r.page.add_style_tag(content="[class*='notification'], .el-notification {display:none!important}")
    r.move(700, 320, 0.8); r.scroll(240, 1.6); r.wait(1.0); r.scroll(-240, 1.2); r.wait(0.6)
    return r.close()


if __name__ == "__main__":
    which = sys.argv[1:] or ["canvas", "live", "fallback", "ops"]
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        for w in which: {"canvas": scene_canvas, "live": scene_live_lead, "fallback": scene_fallback, "ops": scene_ops}[w](p)
