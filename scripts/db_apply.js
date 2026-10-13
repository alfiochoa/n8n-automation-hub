// Apply sql/*.sql to the database described by secrets/db.env (or env vars). Usage: node scripts/db_apply.js [file]
const fs = require('fs'), path = require('path');
const { Client } = require(path.join(__dirname, '..', 'n8n-runtime', 'node_modules', 'pg'));
const envFile = path.join(__dirname, '..', 'secrets', 'db.env');
const e = { ...process.env };
if (fs.existsSync(envFile)) for (const l of fs.readFileSync(envFile, 'utf8').split('\n')) { const i = l.indexOf('='); if (i > 0) e[l.slice(0, i)] = l.slice(i + 1); }
(async () => {
  const c = new Client({ host: e.DB_POSTGRESDB_HOST, port: +e.DB_POSTGRESDB_PORT, user: e.DB_POSTGRESDB_USER, password: e.DB_POSTGRESDB_PASSWORD, database: e.DB_POSTGRESDB_DATABASE, ssl: { rejectUnauthorized: false } });
  await c.connect();
  const files = process.argv[2] ? [process.argv[2]] : fs.readdirSync(path.join(__dirname, '..', 'sql')).filter(f => f.endsWith('.sql')).sort().map(f => path.join(__dirname, '..', 'sql', f));
  for (const f of files) { await c.query(fs.readFileSync(f, 'utf8')); console.log('applied', path.basename(f)); }
  await c.end();
})().catch(err => { console.error('ERR', err.message); process.exit(1); });
