#!/usr/bin/env python3
"""Ken-Burns style tour over the real (hi-res) canvas screenshots: eased pan/zoom, a visible cursor gliding to each stage.
Output: tmp/video/tour_<name>.mp4 (1280x600, 25 fps). Source images come from: OUT=tmp/video SCALE=2 python3 scripts/screenshots.py ..."""
import os, subprocess, sys
from PIL import Image, ImageDraw, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
V = os.path.join(ROOT, "tmp", "video")
W, H, FPS = 1280, 600, 25
ease = lambda t: t * t * (3 - 2 * t)
lerp = lambda a, b, t: a + (b - a) * t

TOURS = {
    # name: (image, [(t, cx, cy, window_width, cursor_x, cursor_y)])
    "lead": ("lead-intake.png", [
        (0.0, 3246, 980, 6492, 3246, 980), (1.6, 3246, 980, 6492, 700, 915),
        (3.4, 1250, 800, 2000, 620, 915), (6.2, 1650, 930, 1900, 1909, 915),
        (9.0, 2900, 1010, 1900, 2684, 1078), (12.0, 3900, 1040, 1900, 3986, 1078),
        (15.2, 4700, 1040, 1900, 5031, 1097), (18.0, 5400, 1000, 1900, 5557, 1078),
        (20.0, 5650, 960, 1900, 6063, 915)]),
    "triage": ("support-triage-ai.png", [
        (0.0, 3246, 980, 6492, 3246, 980), (1.4, 3246, 980, 6492, 620, 915),
        (3.0, 1250, 850, 2000, 700, 915), (5.4, 2350, 1100, 1900, 2623, 1289),
        (8.0, 3000, 1100, 1900, 3473, 1090), (11.0, 4300, 1060, 1900, 4330, 1090),
        (13.5, 5300, 1020, 1900, 5486, 1090), (15.5, 5500, 1000, 1900, 6057, 915)]),
    "ops1": ("ops-error-handler.png", [(0.0, 3246, 980, 5200, 3246, 980), (1.6, 3300, 1000, 3300, 1900, 1030), (6.0, 3300, 1000, 3300, 4300, 1030)]),
    "ops2": ("ops-dead-letter-replay.png", [(0.0, 3246, 980, 5200, 3246, 980), (1.6, 3300, 1000, 3300, 1950, 1030), (6.0, 3300, 1000, 3300, 4700, 1030)]),
}


def cursor(d, x, y):
    pts = [(x, y), (x, y + 30), (x + 8, y + 23), (x + 14, y + 36), (x + 20, y + 33), (x + 14, y + 21), (x + 25, y + 21)]
    d.polygon([(px + 2, py + 3) for px, py in pts], fill=(0, 0, 0, 90))
    d.polygon(pts, fill=(255, 255, 255), outline=(15, 23, 42), width=2)


def render(name):
    img, keys = TOURS[name]; src0 = Image.open(os.path.join(V, img)).convert("RGB"); PAD = 2400
    src = ImageOps.expand(src0, border=PAD, fill=(250, 250, 250))
    total = keys[-1][0]; n = int(total * FPS)
    out = os.path.join(V, f"tour_{name}.mp4")
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", "-preset", "medium", out], stdin=subprocess.PIPE)
    for f in range(n):
        t = f / FPS
        i = max(j for j, k in enumerate(keys[:-1]) if k[0] <= t) if t < total else len(keys) - 2
        a, b = keys[i], keys[i + 1]; e = ease(min(1, (t - a[0]) / (b[0] - a[0])))
        cx, cy, ww, kx, ky = (lerp(a[j], b[j], e) for j in range(1, 6)); wh = ww * H / W
        x0, y0 = cx - ww / 2 + PAD, cy - wh / 2 + PAD
        fr = src.crop((int(x0), int(y0), int(x0 + ww), int(y0 + wh))).resize((W, H), Image.BILINEAR if ww > 3000 else Image.LANCZOS)
        d = ImageDraw.Draw(fr, "RGBA"); sx, sy = (kx + PAD - x0) * W / ww, (ky + PAD - y0) * H / wh
        if 0 <= sx < W and 0 <= sy < H: cursor(d, sx, sy)
        ff.stdin.write(fr.tobytes())
    ff.stdin.close(); ff.wait(); print("tour", name, f"{total}s")


if __name__ == "__main__":
    for n in (sys.argv[1:] or TOURS): render(n)
