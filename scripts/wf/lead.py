from lib import *
from subs import NOTIFY_ID, NORMALIZE_ID

LEAD_ID = "hubLeadIntake01"
ERR_ID = "hubErrorHandle1"


def lead_intake():
    wf = WF(LEAD_ID, "hub-lead-intake", [tag("lead-intake"), tag("webhook")], error_wf=ERR_ID)
    X, Y = 240, 300
    hook = webhook(wf, "Webhook: lead", "demo-lead-intake", (0, Y))
    val = code(wf, "Validate payload", r"""
// Shape, size and e-mail validation. Never trusts the caller.
const item = $input.first().json;
const body = item.body, headers = item.headers || {};
const MAX = 8000, errors = [];
const isObj = body && typeof body === 'object' && !Array.isArray(body);
if (!isObj) errors.push({ field: 'body', code: 'not_an_object' });
const b = isObj ? body : {};
const size = JSON.stringify(b).length;
if (size > MAX) errors.push({ field: 'body', code: 'payload_too_large', detail: `${size} > ${MAX} bytes` });
const allowed = ['email', 'name', 'company', 'country', 'phone', 'message', 'source', 'idempotency_key'];
const unknown = Object.keys(b).filter(k => !allowed.includes(k));
if (unknown.length) errors.push({ field: unknown.join(','), code: 'unknown_fields' });
const str = (k, max) => {
  const v = b[k];
  if (v === undefined || v === null || v === '') return '';
  if (typeof v !== 'string') { errors.push({ field: k, code: 'must_be_string' }); return ''; }
  if (v.length > max) { errors.push({ field: k, code: 'too_long', detail: `max ${max}` }); return ''; }
  return v.replace(/[\u0000-\u001f]/g, ' ').trim();
};
const email = str('email', 254).toLowerCase();
if (!email) { if (!errors.some(e => e.field === 'email')) errors.push({ field: 'email', code: 'required' }); }
else if (!/^[a-z0-9._%+\-]+@[a-z0-9\-]+(\.[a-z0-9\-]+)*\.[a-z]{2,}$/i.test(email)) errors.push({ field: 'email', code: 'invalid_format' });
const lead = { email, name: str('name', 100), company: str('company', 120), country: str('country', 60),
  phone: str('phone', 40), message: str('message', 2000), source: str('source', 40) || 'webhook' };
const crypto = require('crypto');
const key = String(headers['idempotency-key'] || b.idempotency_key || '').slice(0, 120)
  || 'lead:' + crypto.createHash('sha256').update(email).digest('hex').slice(0, 32);
const domain = email.includes('@') ? email.split('@')[1] : '';
const out = { valid: errors.length === 0, domain, key, ...lead, lead,
  chaos: String(headers['x-hub-chaos'] || '') };
if (!out.valid) {
  out.status = errors.some(e => e.code === 'payload_too_large') ? 413 : 422;
  out.response = { ok: false, error: 'validation_failed', errors, trace: ['webhook', 'validate:rejected'] };
}
return [{ json: out }];
""", (X, Y))
    ok = if_(wf, "Payload valid?", "={{ $json.valid }}", (2 * X, Y))
    rej = respond(wf, "Respond: rejected", (3 * X, Y + 220))
    norm = exec_wf(wf, "Normalise contact (sub-workflow)", NORMALIZE_ID, "hub-sub-normalise-contact", (3 * X, Y - 40))
    app = code(wf, "Apply normalised", r"""
const v = $('Validate payload').first().json, n = $input.first().json;
const lead = { ...v.lead, name: n.name || v.lead.name, country_iso: n.country_iso, country_name: n.country_name,
  phone_e164: n.phone_e164, phone_valid: n.phone_valid };
return [{ json: { key: v.key, domain: v.domain, chaos: v.chaos, lead } }];
""", (4 * X, Y - 40))
    dd = pg(wf, "Dedupe lookup", "select idempotency_key, email, score, tier, reasons, created_at from hub.leads where idempotency_key = $1",
            "={{ [$json.key] }}", (5 * X, Y - 40), alwaysOutputData=True)
    ddr = code(wf, "Dedupe result", r"""
// Carry the lead forward (parameters downstream only read $json) and flag duplicates.
const a = $('Apply normalised').first().json, r = $input.first().json;
return [{ json: { ...a, duplicate: !!r.idempotency_key, existing: r } }];
""", (6 * X, Y - 40))
    seen = if_(wf, "Already seen?", "={{ $json.duplicate }}", (7 * X, Y - 40))
    dup = code(wf, "Build duplicate response", r"""
const a = $input.first().json, r = a.existing;
return [{ json: { status: 200, response: { ok: true, duplicate: true,
  decision: { tier: r.tier, score: r.score, route: 'already_processed' }, reasons: r.reasons || [],
  idempotency_key: a.key, first_seen_at: r.created_at,
  trace: ['webhook', 'validate', 'normalise', 'dedupe:duplicate', 'respond'] } } }];
""", (8 * X, Y - 220))
    mx = http(wf, "Enrich: MX lookup (DoH)", "https://cloudflare-dns.com/dns-query", (8 * X, Y - 40),
              headers={"accept": "application/dns-json"},
              qs={"name": "={{ $json.domain }}", "type": "MX"},
              timeout=6000, onError="continueRegularOutput")
    mxm = code(wf, "Merge MX result", r"""
// DoH answers with content-type application/dns-json, which n8n hands over as text: parse it (fail-soft).
const r = $input.first().json; let mx = { error: true };
try { if (!r.error) mx = typeof r.data === 'string' ? JSON.parse(r.data) : r; } catch (e) { /* keep unknown */ }
return [{ json: { ...$('Dedupe result').first().json, mx_raw: mx } }];
""", (9 * X, Y - 40))
    hasc = if_(wf, "Has country?", "={{ $json.lead.country_iso }}", (10 * X, Y - 40), op="notEmpty")
    cty = http(wf, "Enrich: country (World Bank)",
               "=https://api.worldbank.org/v2/country/{{ $json.lead.country_iso }}",
               (11 * X, Y - 160), qs={"format": "json"}, timeout=6000, onError="continueRegularOutput")
    ctym = code(wf, "Merge country result", r"""
// The World Bank returns [meta, [record]]; n8n splits that array into two items. Find the record.
const items = $input.all().map(i => i.json);
const flat = items.flatMap(x => (x && typeof x === 'object') ? [x, ...Object.values(x)] : []).flatMap(x => Array.isArray(x) ? x : [x]);
const rec = flat.find(x => x && x.iso2Code) || null;
return [{ json: { ...$('Merge MX result').first().json, wb: rec } }];
""", (12 * X, Y - 160))
    score = code(wf, "Score lead", r"""
const a = $input.first().json, lead = a.lead;
const mxRes = a.mx_raw || { error: true };
const rec = a.wb || null;
const R = []; let s = 30;
const add = (pts, rule) => { s += pts; R.push({ rule, points: pts }); };
// 1) deliverability: does the e-mail domain accept mail?
if (mxRes.error) R.push({ rule: 'mx_check_unavailable', points: 0 });
else if (mxRes.Status === 3) add(-40, 'domain_does_not_exist');
else if (Array.isArray(mxRes.Answer) && mxRes.Answer.some(x => x.type === 15)) add(20, 'domain_accepts_mail');
else add(-25, 'domain_has_no_mx');
// 2) business vs free / disposable mailbox
const free = ['gmail.com','hotmail.com','outlook.com','yahoo.com','icloud.com','proton.me','protonmail.com','live.com','gmx.com','aol.com'];
const disposable = ['mailinator.com','guerrillamail.com','10minutemail.com','tempmail.com','yopmail.com','trashmail.com','sharklasers.com'];
if (disposable.includes(a.domain)) add(-50, 'disposable_domain');
else if (free.includes(a.domain)) add(0, 'free_mailbox');
else add(20, 'business_domain');
// 3) completeness
if (lead.company) add(10, 'company_given');
if (lead.phone_valid) add(10, 'phone_valid'); else if (lead.phone) add(-5, 'phone_unparseable');
if (lead.name && lead.name.includes(' ')) add(5, 'full_name');
// 4) intent signals in the free-text message
const m = (lead.message || '').toLowerCase();
if (/(budget|quote|pricing|proposal|contract|invoice|per month|€|\$)/.test(m)) add(15, 'intent_budget_or_pricing');
if (/(urgent|asap|this week|deadline|immediately|next week)/.test(m)) add(10, 'intent_urgency');
if (/(sales\s*pitch|seo|backlinks?|crypto|casino|viagra|guest post)/.test(m)) add(-30, 'spam_keywords');
// 5) market fit from the World Bank country record
let region = '', income = '';
if (rec) { region = rec.region?.value || ''; income = rec.incomeLevel?.value || '';
  if (/Europe|North America/.test(region)) add(5, 'target_region'); if (/High income/.test(income)) add(5, 'high_income_market'); }
s = Math.max(0, Math.min(100, s));
const tier = s >= 70 ? 'hot' : s >= 45 ? 'warm' : 'cold';
return [{ json: { key: a.key, chaos: a.chaos, lead, score: s, tier, reasons: R, region, income,
  mx: mxRes.error ? 'unknown' : (mxRes.Status === 3 ? 'nxdomain' : (mxRes.Answer || []).some(x => x.type === 15) ? 'ok' : 'none') } }];
""", (13 * X, Y - 40))
    prep = code(wf, "Prepare persist (fault-injection hook)", r"""
// Fault injection for tests only: header x-hub-chaos=persist-fail while HUB_CHAOS=true. Disabled in production.
const j = $input.first().json;
if ($env.HUB_CHAOS === 'true' && j.chaos === 'persist-fail') throw new Error('chaos: simulated persistence failure');
return [{ json: j }];
""", (14 * X, Y - 40), onError="continueErrorOutput")
    persist = pg(wf, "Persist lead (idempotent upsert)",
                 "insert into hub.leads (idempotency_key,email,name,company,country,phone,score,tier,reasons,source) "
                 "values ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10) on conflict (idempotency_key) do nothing returning idempotency_key",
                 "={{ [$json.key,$json.lead.email,$json.lead.name,$json.lead.company,$json.lead.country_iso,$json.lead.phone_e164,"
                 "$json.score,$json.tier,JSON.stringify($json.reasons),$json.lead.source] }}",
                 (15 * X, Y - 40), alwaysOutputData=True, onError="continueErrorOutput")
    pres = code(wf, "Persist result", "return [{ json: { ...$('Prepare persist (fault-injection hook)').first().json, persisted: !!$input.first().json.idempotency_key } }];", (16 * X, Y - 40))
    route = switch(wf, "Route by tier", "={{ $json.tier }}", ["hot", "warm", "cold"], (17 * X, Y - 40))
    comp = code(wf, "Compose notification", r"""
const s = $input.first().json, l = s.lead;
const hot = s.tier === 'hot';
return [{ json: { level: hot ? 'critical' : 'info',
  title: `${hot ? '🔥 HOT' : 'WARM'} lead (${s.score}/100)`,
  text: `${l.name || '(no name)'} <${l.email}> ${l.company ? '· ' + l.company : ''} ${l.country_name ? '· ' + l.country_name : ''}\nWhy: ${s.reasons.map(r => r.rule + (r.points ? ` ${r.points > 0 ? '+' : ''}${r.points}` : '')).join(', ')}` } }];
""", (18 * X, Y - 160))
    ntf = exec_wf(wf, "Notify (sub-workflow)", NOTIFY_ID, "hub-sub-notify", (19 * X, Y - 160), onError="continueRegularOutput")
    build = code(wf, "Build decision response", r"""
const s = $('Persist result').first().json, l = s.lead;
let sent = null; try { sent = $('Notify (sub-workflow)').first().json.sent; } catch (e) { /* cold lead: no notification */ }
const raced = !s.persisted;
const route = { hot: 'notify_sales_now', warm: 'notify_and_nurture', cold: 'log_only' }[s.tier];
const trace = ['webhook', 'validate', 'normalise', 'dedupe:new', 'enrich:mx', ...(l.country_iso ? ['enrich:country'] : []),
  'score', 'persist', 'route:' + s.tier, ...(s.tier !== 'cold' ? ['notify'] : []), 'respond'];
return [{ json: { status: 200, response: { ok: true, duplicate: raced,
  decision: { tier: s.tier, score: s.score, route },
  reasons: s.reasons, enrichment: { mx: s.mx, region: s.region || null, income_level: s.income || null },
  normalized: { name: l.name, email: l.email, country: l.country_iso || null, phone: l.phone_e164 || null },
  notified: sent, idempotency_key: s.key, trace } } }];
""", (20 * X, Y - 40))
    pdl = code(wf, "Prepare dead letter", r"""
// Error-output items carry the failure; rebuild the original request from the validated lead.
const v = $('Validate payload').first().json, e = $input.first().json.error;
return [{ json: { payload: JSON.stringify({ ...v.lead, idempotency_key: v.key }),
  error: String((e && (e.message || e)) || 'persist failed').slice(0, 500) } }];
""", (16 * X, Y + 260))
    dlq = pg(wf, "Dead-letter: store for replay",
             "insert into hub.dead_letters (source, payload, error) values ('lead-intake', $1::jsonb, $2) returning id",
             "={{ [$json.payload, $json.error] }}", (17 * X, Y + 260))
    acc = code(wf, "Build accepted response", r"""
const v = $('Validate payload').first().json;
return [{ json: { status: 202, response: { ok: true, accepted: true,
  decision: { tier: null, score: null, route: 'queued_for_replay' },
  message: 'Persistence failed; the lead was stored in the dead-letter queue and will be replayed.',
  idempotency_key: v.key, trace: ['webhook', 'validate', 'normalise', 'dedupe:new', 'score', 'persist:failed', 'dead-letter', 'respond'] } } }];
""", (18 * X, Y + 260))
    resp = respond(wf, "Respond: decision", (21 * X, Y - 40))

    wf.chain(hook, val, ok)
    wf.link(ok, norm, 0); wf.link(ok, rej, 1)
    wf.chain(norm, app, dd, ddr, seen)
    wf.link(seen, dup, 0); wf.link(seen, mx, 1)
    wf.link(dup, resp)
    wf.chain(mx, mxm, hasc)
    wf.link(hasc, cty, 0); wf.link(hasc, score, 1); wf.chain(cty, ctym, score)
    wf.chain(score, prep)
    wf.link(prep, persist, 0); wf.link(prep, pdl, 1)
    wf.link(persist, pres, 0); wf.link(persist, pdl, 1)
    wf.link(pres, route)
    wf.link(route, comp, 0); wf.link(route, comp, 1); wf.link(route, build, 2)
    wf.chain(comp, ntf, build, resp)
    wf.chain(pdl, dlq, acc, resp)

    wf.note("hub-lead-intake", "## Lead intake\n`POST /webhook/demo-lead-intake`\n\n1. **Validate** shape, size (<8 KB) and e-mail -> 422/413\n"
            "2. **Normalise** name/country/phone (sub-workflow)\n3. **Dedupe** on idempotency key (header or hash of e-mail)\n"
            "4. **Enrich**: MX via DNS-over-HTTPS, country via World Bank (fail-soft)\n5. **Score** 0-100 with explainable reasons\n"
            "6. **Route** hot / warm / cold, persist, notify\n7. **Respond** with the decision JSON\n\n"
            "Persistence errors go to a dead-letter table (replayed by `hub-ops-dead-letter-replay`). Synthetic demo data only.",
            (-20, Y - 420), (560, 300))
    wf.note("Resilience", "Retry-on-fail + timeouts on every network/DB node.\nEnrichment is fail-soft (`continueRegularOutput`) so a slow DNS/API never blocks a lead.\n"
            "`Prepare persist` has a test-only fault-injection hook (`HUB_CHAOS`).", (14 * X - 40, Y - 330), (600, 140), color=3)
    return wf
