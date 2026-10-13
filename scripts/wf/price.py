from lib import *
from subs import NOTIFY_ID

PRICE_ID = "hubPriceScrape1"
ERR_ID = "hubErrorHandle1"
UA = "n8n-automation-hub/1.0 (+https://github.com/alfiochoa/n8n-automation-hub; portfolio demo, polite crawler)"


def price_scraper():
    wf = WF(PRICE_ID, "hub-price-scraper-alerts", [tag("scraper"), tag("schedule")], error_wf=ERR_ID, active=True)
    X, Y = 250, 300
    sch = wf.add("Schedule: every 6 hours", "n8n-nodes-base.scheduleTrigger",
                 {"rule": {"interval": [{"field": "hours", "hoursInterval": 6}]}}, (0, Y - 120), 1.2)
    man = wf.add("Manual / headless trigger", "n8n-nodes-base.manualTrigger", {}, (0, Y + 60), 1)
    cfg = code(wf, "Config + pages to crawl", r"""
const env = (k, d) => ($env[k] !== undefined && $env[k] !== '' ? $env[k] : d);
const pages = Number(env('SCRAPE_PAGES', 3)), base = env('SCRAPE_BASE_URL', 'https://books.toscrape.com').replace(/\/$/, '');
const items = [];
for (let p = 1; p <= pages; p++) items.push({ json: { page: p, url: `${base}/catalogue/page-${p}.html`, robots_url: `${base}/robots.txt`,
  drop_pct: Number(env('SCRAPE_DROP_PCT', 5)), delay_s: Number(env('SCRAPE_DELAY_S', 1)) } });
return items;
""", (X, Y))
    rob = http(wf, "robots.txt check", "={{ $json.robots_url }}", (2 * X, Y), headers={"User-Agent": UA},
               timeout=8000, text=True, onError="continueRegularOutput", retryOnFail=False, alwaysOutputData=True, executeOnce=True)
    allow = code(wf, "Respect robots.txt", r"""
// Parse Disallow rules for '*'. 404 (the sandbox has none) means everything is allowed.
const raw = $input.first().json;
const txt = typeof raw.data === 'string' && !raw.error ? raw.data : '';
let applies = false; const dis = [];
for (const line of txt.split('\n')) { const l = line.trim();
  if (/^user-agent:\s*\*/i.test(l)) applies = true; else if (/^user-agent:/i.test(l)) applies = false;
  else if (applies && /^disallow:/i.test(l)) { const p = l.split(':')[1].trim(); if (p) dis.push(p); } }
const pages = $('Config + pages to crawl').all().map(i => i.json);
const ok = pages.filter(p => !dis.some(d => new URL(p.url).pathname.startsWith(d)));
if (!ok.length) throw new Error('robots.txt disallows every configured page');
return ok.map(p => ({ json: { ...p, robots_rules: dis.length } }));
""", (3 * X, Y))
    loop = wf.add("Loop pages (Split In Batches)", "n8n-nodes-base.splitInBatches", {"batchSize": 1, "options": {}}, (4 * X, Y), 3)
    get = http(wf, "GET catalogue page", "={{ $json.url }}", (5 * X, Y + 120), headers={"User-Agent": UA}, timeout=15000, text=True,
               maxTries=3, waitBetweenTries=3000)
    ext = wf.add("HTML Extract: books", "n8n-nodes-base.htmlExtract",
                 {"sourceData": "json", "dataPropertyName": "data",
                  "extractionValues": {"values": [
                      {"key": "titles", "cssSelector": "article.product_pod h3 a", "returnValue": "attribute", "attribute": "title", "returnArray": True},
                      {"key": "hrefs", "cssSelector": "article.product_pod h3 a", "returnValue": "attribute", "attribute": "href", "returnArray": True},
                      {"key": "prices", "cssSelector": "article.product_pod .price_color", "returnArray": True},
                      {"key": "stock", "cssSelector": "article.product_pod .availability", "returnArray": True}]},
                  "options": {"trimValues": True, "cleanUpText": True}}, (6 * X, Y + 120), 1)
    norm = code(wf, "Normalise + breakage detector", r"""
// Zip the parallel arrays into book records. If selectors stop matching, flag it instead of silently returning nothing.
const j = $input.first().json, page = $('Loop pages (Split In Batches)').first().json.page;
const n = (j.titles || []).length;
const consistent = n > 0 && [j.hrefs, j.prices, j.stock].every(a => (a || []).length === n);
const delay_s = Number($('Loop pages (Split In Batches)').first().json.delay_s);
if (!consistent) return [{ json: { broken: true, page, delay_s, books: [], counts: { titles: n, hrefs: (j.hrefs || []).length, prices: (j.prices || []).length, stock: (j.stock || []).length } } }];
return [{ json: { broken: false, page, delay_s, books: j.titles.map((title, i) => ({ page, title,
  book_id: j.hrefs[i].split('/')[0], price_gbp: Number(j.prices[i].replace(/[^0-9.]/g, '')), in_stock: /in stock/i.test(j.stock[i]) })) } }];
""", (7 * X, Y + 120))
    wait = wf.add("Rate limit (Wait)", "n8n-nodes-base.wait",
                  {"amount": "={{ $json.delay_s }}", "unit": "seconds"}, (8 * X, Y + 120), 1.1,
                  webhookId=str(uuid.uuid5(NS, PRICE_ID + "wait")))
    coll = code(wf, "Collect scraped books", r"""
const all = $input.all().map(i => i.json);
const broken = all.filter(x => x.broken), books = all.filter(x => !x.broken).flatMap(x => x.books);
const dedup = Object.values(Object.fromEntries(books.map(b => [b.book_id, b])));
return [{ json: { books: dedup, broken, pages_failed: broken.length, count: dedup.length } }];
""", (5 * X, Y - 160))
    stored = pg(wf, "Load stored prices", "select book_id, price_gbp::float8 as price_gbp, in_stock from hub.prices", None, (6 * X, Y - 160), alwaysOutputData=True)
    diff = code(wf, "Diff vs stored prices", r"""
const s = $('Collect scraped books').first().json;
const rows = $input.all().map(i => i.json).filter(r => r.book_id);
const old = Object.fromEntries(rows.map(r => [r.book_id, r]));
const baseline = rows.length === 0;           // first run seeds the table, no alert storm
const dropPct = Number($('Config + pages to crawl').first().json.drop_pct);
const events = [];
for (const b of s.books) { const o = old[b.book_id];
  if (!o) { if (!baseline) events.push({ book_id: b.book_id, title: b.title, event: 'new', old_price: null, new_price: b.price_gbp }); continue; }
  const chg = (b.price_gbp - o.price_gbp) / o.price_gbp * 100;
  if (b.price_gbp < o.price_gbp) events.push({ book_id: b.book_id, title: b.title, event: 'drop', old_price: o.price_gbp, new_price: b.price_gbp, pct: +chg.toFixed(1), alert: Math.abs(chg) >= dropPct });
  else if (b.price_gbp > o.price_gbp) events.push({ book_id: b.book_id, title: b.title, event: 'rise', old_price: o.price_gbp, new_price: b.price_gbp, pct: +chg.toFixed(1) });
  if (!o.in_stock && b.in_stock) events.push({ book_id: b.book_id, title: b.title, event: 'back_in_stock', old_price: o.price_gbp, new_price: b.price_gbp, alert: true });
  if (o.in_stock && !b.in_stock) events.push({ book_id: b.book_id, title: b.title, event: 'out_of_stock', old_price: o.price_gbp, new_price: b.price_gbp }); }
const alerts = events.filter(e => e.alert || e.event === 'new');
return [{ json: { books: s.books, events, alerts, baseline, broken: s.broken, scraped: s.count } }];
""", (7 * X, Y - 160))
    upsert = pg(wf, "Upsert prices + log events",
                "with up as (insert into hub.prices (book_id,title,price_gbp,in_stock,updated_at) "
                "select b->>'book_id', b->>'title', (b->>'price_gbp')::numeric, (b->>'in_stock')::boolean, now() from jsonb_array_elements($1::jsonb) b "
                "on conflict (book_id) do update set title=excluded.title, price_gbp=excluded.price_gbp, in_stock=excluded.in_stock, updated_at=now() returning 1), "
                "ev as (insert into hub.price_events (book_id,title,event,old_price,new_price) "
                "select e->>'book_id', e->>'title', e->>'event', (e->>'old_price')::numeric, (e->>'new_price')::numeric from jsonb_array_elements($2::jsonb) e returning 1) "
                "select (select count(*) from up) as upserted, (select count(*) from ev) as events_logged",
                "={{ [JSON.stringify($json.books), JSON.stringify($json.events)] }}", (8 * X, Y - 160))
    msg = code(wf, "Compose alert", r"""
const d = $('Diff vs stored prices').first().json;
const lines = d.alerts.slice(0, 12).map(a => a.event === 'drop' ? `▼ ${a.title}: £${a.old_price} -> £${a.new_price} (${a.pct}%)`
  : a.event === 'new' ? `＋ NEW ${a.title} £${a.new_price}` : `↺ ${a.event.replace(/_/g, ' ')}: ${a.title} £${a.new_price}`);
const broken = d.broken.length > 0;
const send = d.alerts.length > 0 || broken;
return [{ json: { send, level: broken ? 'critical' : 'info',
  title: broken ? 'Scraper selectors returned nothing - site layout changed?' : `${d.alerts.length} price alert(s)`,
  text: broken ? `Pages with 0/inconsistent results: ${d.broken.map(b => b.page).join(', ')}` : lines.join('\n'),
  summary: { scraped: d.scraped, events: d.events.length, alerts: d.alerts.length, baseline: d.baseline, broken_pages: d.broken.length } } }];
""", (9 * X, Y - 160))
    has = if_(wf, "Anything to alert?", "={{ $json.send }}", (10 * X, Y - 160))
    ntf = exec_wf(wf, "Notify (sub-workflow)", NOTIFY_ID, "hub-sub-notify", (11 * X, Y - 260), onError="continueRegularOutput")
    done = code(wf, "Run summary", r"""
const m = $('Compose alert').first().json;
return [{ json: { ...m.summary, alerted: m.send, title: m.title } }];
""", (12 * X, Y - 160))
    wf.link(sch, cfg); wf.link(man, cfg)
    wf.chain(cfg, rob, allow, loop)
    wf.link(loop, coll, 0); wf.link(loop, get, 1)
    wf.chain(get, ext, norm, wait)
    wf.link(wait, loop)
    wf.chain(coll, stored, diff, upsert, msg, has)
    wf.link(has, ntf, 0); wf.link(has, done, 1); wf.link(ntf, done)
    wf.note("hub-price-scraper-alerts", "## Polite price monitor (books.toscrape.com sandbox)\nSchedule every 6 h or headless.\n\n"
            "- Respects `robots.txt`, identifies itself with a User-Agent, **rate-limits** with Split In Batches + Wait\n"
            "- HTML Extract -> normalise -> **diff against stored prices** (Postgres)\n- Alerts on drops >= 5 %, new titles, back-in-stock\n"
            "- First run only seeds a baseline (no alert storm)\n- **Breakage detector**: if selectors return nothing / mismatched arrays it alerts instead of silently passing\n\n"
            "Sandbox site built for scraping practice; nothing here targets a real shop.", (-20, Y - 560), (600, 300))
    return wf
