#!/usr/bin/env node
// Claim the n8n owner account (POST /rest/owner/setup) so nobody else can. Idempotent. Node-only so it runs in the n8n image.
//   node scripts/bootstrap_owner.js [BASE_URL] [--generate]
// Password: N8N_OWNER_PASSWORD env, else secrets/owner.env, else (only with --generate) a fresh random one saved to secrets/owner.env (chmod 600).
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const base = (process.argv[2] && !process.argv[2].startsWith('--') ? process.argv[2] : 'http://localhost:5678').replace(/\/$/, '');
const gen = process.argv.includes('--generate');
const file = path.join(__dirname, '..', 'secrets', 'owner.env');
if (fs.existsSync(file)) for (const l of fs.readFileSync(file, 'utf8').split('\n')) { const i = l.indexOf('='); if (i > 0 && !process.env[l.slice(0, i)]) process.env[l.slice(0, i)] = l.slice(i + 1).trim(); }
const email = process.env.N8N_OWNER_EMAIL || 'owner@n8n-hub.local';
let pw = process.env.N8N_OWNER_PASSWORD;
if (!pw) {
  if (!gen) { console.error('N8N_OWNER_PASSWORD is not set (use --generate to create one locally)'); process.exit(2); }
  pw = crypto.randomBytes(18).toString('base64url') + 'Aa1';
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `N8N_OWNER_EMAIL=${email}\nN8N_OWNER_PASSWORD=${pw}\n`, { mode: 0o600 });
  console.log('generated a strong owner password -> secrets/owner.env');
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  for (let i = 0; ; i++) {
    try { if ((await fetch(base + '/healthz')).ok) break; } catch (e) { /* not up yet */ }
    if (i > 120) { console.error('n8n did not become healthy'); process.exit(1); }
    await sleep(1000);
  }
  // POST directly: /rest/settings is not served when the UI is disabled, and the endpoint answers 400 once an owner exists.
  let res, text;                     // /healthz answers a moment before the REST router is mounted (HTML 404): retry until it is
  for (let i = 0; ; i++) {
    try {
      res = await fetch(base + '/rest/owner/setup', { method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ email, firstName: 'Hub', lastName: 'Owner', password: pw }) });
      text = await res.text();
      if (!(res.status === 404 && text.startsWith('<!DOCTYPE'))) break;
    } catch (e) { /* connection refused while booting */ }
    if (i > 90) { console.error('n8n REST API did not come up'); process.exit(1); }
    await sleep(1000);
  }
  if (res.ok) console.log('owner account claimed (HTTP 200)');
  else if (res.status === 400 && /already setup/i.test(text)) console.log(`owner already set up on ${base} - nothing to do`);
  else { console.error(`owner setup failed: HTTP ${res.status} ${text.slice(0, 120)}`); process.exit(1); }
  const login = await fetch(base + '/rest/login', { method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ emailOrLdapLoginId: email, password: pw }) });
  console.log(login.ok ? 'owner login verified' : `WARNING: owner login with the configured password failed (HTTP ${login.status}) - was the instance claimed with another password?`);
})().catch(e => { console.error(e.message); process.exit(1); });
