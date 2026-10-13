#!/usr/bin/env node
// n8n's CLI cannot activate workflows from JSON outside queue mode, and one `update:workflow` process per id is slow on a
// 0.1-CPU free tier. So: workflows whose JSON has "active": true are flagged active directly in the n8n schema; the server
// activates them on boot. Run AFTER import:workflow (which imports everything inactive) and BEFORE `n8n start`.
const fs = require('fs'), path = require('path');
const dir = process.argv[2] || path.join(__dirname, '..', 'workflows');
const ids = fs.readdirSync(dir).filter(f => f.endsWith('.json')).map(f => JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'))).filter(w => w.active).map(w => w.id);
const roots = [path.join(__dirname, '..', 'n8n-runtime', 'node_modules', 'n8n'), '/usr/local/lib/node_modules/n8n', '/usr/lib/node_modules/n8n',
  ...(process.env.NODE_PATH || '').split(':').filter(Boolean).map(p => path.join(p, 'n8n'))];
let pg;
for (const r of roots) { try { pg = require(require.resolve('pg', { paths: [r] })); break; } catch (e) { /* next */ } }
if (!pg) { console.error('cannot locate the pg module shipped with n8n'); process.exit(1); }
const schema = process.env.DB_POSTGRESDB_SCHEMA || 'public';
(async () => {
  const c = new pg.Client({ host: process.env.DB_POSTGRESDB_HOST, port: +(process.env.DB_POSTGRESDB_PORT || 5432), user: process.env.DB_POSTGRESDB_USER,
    password: process.env.DB_POSTGRESDB_PASSWORD, database: process.env.DB_POSTGRESDB_DATABASE || 'postgres', ssl: { rejectUnauthorized: false } });
  await c.connect();
  const t = `"${schema.replace(/"/g, '')}".workflow_entity`;
  // 1.12x tracks the published version: a workflow only goes live when activeVersionId points at its current versionId.
  const r = await c.query(`update ${t} set active = (id = any($1)), "activeVersionId" = case when id = any($1) then "versionId" else null end returning id, active`, [ids]);
  await c.end();
  console.log(`active workflows: ${r.rows.filter(x => x.active).map(x => x.id).join(' ')}`);
})().catch(e => { console.error('activation failed:', e.message); process.exit(1); });
