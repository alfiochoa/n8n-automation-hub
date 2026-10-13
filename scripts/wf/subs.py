from lib import *

NOTIFY_ID = "hubNotify00001"
NORMALIZE_ID = "hubNormalize001"


def notify():
    wf = WF(NOTIFY_ID, "hub-sub-notify", [tag("sub-workflow")])
    t = wf.add("Execute Workflow Trigger", "n8n-nodes-base.executeWorkflowTrigger",
               {"inputSource": "passthrough"}, (0, 200), 1.1)
    f = code(wf, "Format message", r"""
// Input: { title, text, level: info|warn|critical }. Output is Discord/Slack-compatible.
const i = $input.first().json;
const icon = { info: 'ℹ️', warn: '⚠️', critical: '🚨' }[i.level] || 'ℹ️';
const content = `${icon} **${String(i.title || 'n8n-automation-hub').slice(0, 120)}**\n${String(i.text || '')}`.slice(0, 1900);
const url = $env.HUB_NOTIFY_URL || '';
return [{ json: { url, has_url: !!url, payload: { username: 'n8n-automation-hub', content, text: content } } }];
""", (260, 200))
    gate = if_(wf, "Notify URL configured?", "={{ $json.has_url }}", (500, 200))
    post = http(wf, "POST to webhook", "={{ $json.url }}", (760, 120), method="POST",
                body="={{ $json.payload }}", timeout=8000, onError="continueRegularOutput",
                headers={"Content-Type": "application/json"})
    ok = code(wf, "Result: sent", """
const failed = !!$input.first().json.error;
return [{ json: { sent: !failed, reason: failed ? 'delivery_failed' : 'ok' } }];
""", (1020, 120))
    skip = code(wf, "Result: skipped", "return [{ json: { sent: false, reason: 'no_notify_url_configured' } }];", (760, 300))
    wf.chain(t, f, gate)
    wf.link(gate, post, 0); wf.link(gate, skip, 1); wf.link(post, ok)
    wf.note("What this does", "## Shared notifier\nSub-workflow used by every other workflow (Execute Workflow node).\n\n"
            "- Input: `title`, `text`, `level`\n- Posts a Discord/Slack-compatible JSON body to env `HUB_NOTIFY_URL`\n"
            "- No URL configured -> skips quietly (demo mode)\n- 8 s timeout, 2 tries, never fails the caller", (-20, -60), (420, 200))
    return wf


def normalize():
    wf = WF(NORMALIZE_ID, "hub-sub-normalise-contact", [tag("sub-workflow")])
    t = wf.add("Execute Workflow Trigger", "n8n-nodes-base.executeWorkflowTrigger", {"inputSource": "passthrough"}, (0, 200), 1.1)
    c = code(wf, "Normalise name, country, phone", r"""
// Input: { name, country, phone }  ->  { name, country_iso, country_name, phone_e164, phone_valid }
const i = $input.first().json;
const C = { // alias -> [ISO2, calling code, name]
  'es':['ES','34','Spain'],'spain':['ES','34','Spain'],'españa':['ES','34','Spain'],'espana':['ES','34','Spain'],
  'gb':['GB','44','United Kingdom'],'uk':['GB','44','United Kingdom'],'united kingdom':['GB','44','United Kingdom'],'england':['GB','44','United Kingdom'],
  'us':['US','1','United States'],'usa':['US','1','United States'],'united states':['US','1','United States'],'united states of america':['US','1','United States'],
  'de':['DE','49','Germany'],'germany':['DE','49','Germany'],'deutschland':['DE','49','Germany'],
  'fr':['FR','33','France'],'france':['FR','33','France'],
  'it':['IT','39','Italy'],'italy':['IT','39','Italy'],'italia':['IT','39','Italy'],
  'pt':['PT','351','Portugal'],'portugal':['PT','351','Portugal'],
  'nl':['NL','31','Netherlands'],'netherlands':['NL','31','Netherlands'],'holland':['NL','31','Netherlands'],
  'ie':['IE','353','Ireland'],'ireland':['IE','353','Ireland'],
  'ch':['CH','41','Switzerland'],'switzerland':['CH','41','Switzerland'],
  'be':['BE','32','Belgium'],'belgium':['BE','32','Belgium'],
  'se':['SE','46','Sweden'],'sweden':['SE','46','Sweden'],
  'mx':['MX','52','Mexico'],'mexico':['MX','52','Mexico'],'méxico':['MX','52','Mexico'],
  'ar':['AR','54','Argentina'],'argentina':['AR','54','Argentina'],
  'co':['CO','57','Colombia'],'colombia':['CO','57','Colombia'],
  'cl':['CL','56','Chile'],'chile':['CL','56','Chile'],
  'br':['BR','55','Brazil'],'brazil':['BR','55','Brazil'],'brasil':['BR','55','Brazil'],
  'ca':['CA','1','Canada'],'canada':['CA','1','Canada'],
  'au':['AU','61','Australia'],'australia':['AU','61','Australia'],
  'in':['IN','91','India'],'india':['IN','91','India'],
  'ae':['AE','971','United Arab Emirates'],'uae':['AE','971','United Arab Emirates'],
  'pl':['PL','48','Poland'],'poland':['PL','48','Poland'],
  'ro':['RO','40','Romania'],'romania':['RO','40','Romania'],
};
const small = new Set(['de','van','von','da','di','del','la','el','y','e']);
const titleCase = s => s.trim().replace(/\s+/g, ' ').split(' ')
  .map((w, k) => (k > 0 && small.has(w.toLowerCase())) ? w.toLowerCase()
    : w.split('-').map(p => p ? p[0].toUpperCase() + p.slice(1).toLowerCase() : p).join('-')).join(' ');
const name = i.name ? titleCase(String(i.name)) : '';
const hit = C[String(i.country || '').trim().toLowerCase()];
const iso = hit ? hit[0] : '';
let digits = String(i.phone || '').replace(/[^\d+]/g, '');
if (digits.startsWith('00')) digits = '+' + digits.slice(2);
let e164 = '';
if (digits.startsWith('+')) e164 = '+' + digits.slice(1).replace(/\D/g, '');
else if (digits && hit) e164 = '+' + hit[1] + digits.replace(/\D/g, '').replace(/^0+/, '');
const len = e164.replace(/\D/g, '').length;
const phone_valid = !!e164 && len >= 8 && len <= 15;
return [{ json: { name, country_iso: iso, country_name: hit ? hit[2] : '', country_recognised: !!hit || !i.country,
  phone_e164: phone_valid ? e164 : '', phone_valid } }];
""", (260, 200))
    wf.chain(t, c)
    wf.note("What this does", "## Contact normaliser\nSub-workflow called by `hub-lead-intake`.\n\n- Name -> Title Case (keeps *de/van/von*)\n"
            "- Country alias/name -> ISO-2 (40+ aliases)\n- Phone -> E.164 using the country calling code; validated 8-15 digits\n"
            "- Pure function: no network, no DB", (-20, -60), (420, 200))
    return wf
