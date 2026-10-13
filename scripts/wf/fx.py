from lib import *
from subs import NOTIFY_ID

FX_ID = "hubFxDigest0001"
ERR_ID = "hubErrorHandle1"


def fx_digest():
    wf = WF(FX_ID, "hub-fx-digest-alert", [tag("fx"), tag("schedule")], error_wf=ERR_ID)
    X, Y = 250, 260
    sch = wf.add("Schedule: weekdays 08:00", "n8n-nodes-base.scheduleTrigger",
                 {"rule": {"interval": [{"field": "cronExpression", "expression": "0 8 * * 1-5"}]}}, (0, Y - 120), 1.2)
    man = wf.add("Manual / headless trigger", "n8n-nodes-base.manualTrigger", {}, (0, Y + 60), 1)
    cfg = code(wf, "Config (thresholds)", r"""
// Tunable in one place. Env overrides let CI/ops change them without editing the workflow.
const env = (k, d) => ($env[k] !== undefined && $env[k] !== '' ? $env[k] : d);
const symbols = String(env('FX_SYMBOLS', 'USD,GBP,CHF,JPY,CNY')).split(',');
const days = Number(env('FX_HISTORY_DAYS', 30));
const end = new Date(); const start = new Date(end.getTime() - days * 86400000);
const iso = d => d.toISOString().slice(0, 10);
return [{ json: { base: env('FX_BASE', 'EUR'), symbols: symbols.join(','), start: iso(start), end: iso(end),
  pct_threshold: Number(env('FX_PCT_THRESHOLD', 0.7)), z_threshold: Number(env('FX_Z_THRESHOLD', 2)) } }];
""", (X, Y))
    latest = http(wf, "Frankfurter: latest", "https://api.frankfurter.dev/v1/latest", (2 * X, Y - 90),
                  qs={"base": "={{ $json.base }}", "symbols": "={{ $json.symbols }}"}, timeout=15000)
    lm = code(wf, "Merge latest", "return [{ json: { ...$('Config (thresholds)').first().json, latest: $input.first().json } }];", (3 * X, Y - 90))
    hist = http(wf, "Frankfurter: 30-day history",
                "=https://api.frankfurter.dev/v1/{{ $json.start }}..{{ $json.end }}",
                (4 * X, Y - 90), qs={"base": "={{ $json.base }}", "symbols": "={{ $json.symbols }}"}, timeout=15000)
    an = code(wf, "Analyse: % move + z-score", r"""
const cfg = $('Config (thresholds)').first().json;
const latest = $('Merge latest').first().json.latest;
const hist = $input.first().json;
const dates = Object.keys(hist.rates).sort();
const out = [];
for (const cur of cfg.symbols.split(',')) {
  const s = dates.map(d => hist.rates[d][cur]).filter(x => typeof x === 'number');
  if (s.length < 8) { out.push({ cur, error: 'insufficient_history', points: s.length }); continue; }
  const rets = s.slice(1).map((p, i) => Math.log(p / s[i]));
  const last = rets[rets.length - 1], base = rets.slice(0, -1);
  const mean = base.reduce((a, b) => a + b, 0) / base.length;
  const sd = Math.sqrt(base.reduce((a, b) => a + (b - mean) ** 2, 0) / (base.length - 1));
  const z = sd > 0 ? (last - mean) / sd : 0;
  const pct1d = (Math.exp(last) - 1) * 100, pct30 = (s[s.length - 1] / s[0] - 1) * 100;
  const price = latest.rates[cur] ?? s[s.length - 1];
  const reasons = [];
  if (Math.abs(pct1d) >= cfg.pct_threshold) reasons.push(`1d move ${pct1d.toFixed(2)}% >= ${cfg.pct_threshold}%`);
  if (Math.abs(z) >= cfg.z_threshold) reasons.push(`z-score ${z.toFixed(2)} >= ${cfg.z_threshold}`);
  out.push({ cur, rate: price, pct1d: +pct1d.toFixed(3), pct30: +pct30.toFixed(2), z: +z.toFixed(2),
    min30: Math.min(...s), max30: Math.max(...s), points: s.length, unusual: reasons.length > 0, reasons });
}
return [{ json: { as_of: latest.date, base: cfg.base, pairs: out, unusual: out.filter(p => p.unusual).map(p => p.cur) } }];
""", (5 * X, Y - 90))
    fmt = code(wf, "Format digest", r"""
const d = $input.first().json;
const pad = (s, n) => String(s).padEnd(n), arrow = v => (v > 0 ? '▲' : v < 0 ? '▼' : '■');
const rows = d.pairs.filter(p => !p.error).map(p =>
  `${pad(d.base + '/' + p.cur, 8)} ${pad(p.rate, 9)} ${arrow(p.pct1d)}${pad(Math.abs(p.pct1d).toFixed(2) + '%', 7)} 30d ${pad((p.pct30 > 0 ? '+' : '') + p.pct30 + '%', 8)} z=${p.z}${p.unusual ? '  ⚠ UNUSUAL' : ''}`);
const head = d.unusual.length ? `Unusual moves: ${d.unusual.join(', ')}` : 'No unusual moves today';
const text = `${head} (as of ${d.as_of})\n\`\`\`\n${rows.join('\n')}\n\`\`\``;
return [{ json: { ...d, level: d.unusual.length ? 'warn' : 'info', title: `FX digest ${d.as_of}`, text } }];
""", (6 * X, Y - 90))
    ntf = exec_wf(wf, "Notify (sub-workflow)", NOTIFY_ID, "hub-sub-notify", (7 * X, Y - 90), onError="continueRegularOutput")
    done = code(wf, "Digest result", r"""
const d = $('Format digest').first().json;
return [{ json: { as_of: d.as_of, unusual: d.unusual, pairs: d.pairs.length, notified: ($input.first().json || {}).sent ?? false, digest: d.text } }];
""", (8 * X, Y - 90))
    wf.link(sch, cfg); wf.link(man, cfg)
    wf.chain(cfg, latest, lm, hist, an, fmt, ntf, done)
    wf.note("hub-fx-digest-alert", "## FX digest + unusual-move alert\nSchedule (weekdays 08:00 Madrid) or headless: `n8n execute --id hubFxDigest0001`.\n\n"
            "1. Frankfurter (ECB reference rates): latest + 30-day history\n2. Per pair: 1-day move, 30-day move, **z-score** of the last daily log-return vs the previous 29\n"
            "3. Flag if `|1d| >= 0.7%` **or** `|z| >= 2` (env-tunable)\n4. Digest -> shared notifier (Discord/Slack compatible)\n\n"
            "Free, no key. ECB publishes ~16:00 CET on working days, so weekend/holiday gaps are expected.", (-20, Y - 420), (560, 260))
    return wf
