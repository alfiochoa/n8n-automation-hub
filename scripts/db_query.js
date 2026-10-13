// Run one SQL statement against the hub database; prints rows as JSON.  Usage: echo "select 1" | node scripts/db_query.js
const fs = require('fs'), path = require('path');
const { Client } = require(path.join(__dirname, '..', 'n8n-runtime', 'node_modules', 'pg'));
const e = { ...process.env }, envFile = path.join(__dirname, '..', 'secrets', 'db.env');
if (fs.existsSync(envFile)) for (const l of fs.readFileSync(envFile, 'utf8').split('\n')) { const i = l.indexOf('='); if (i > 0 && !e[l.slice(0, i)]) e[l.slice(0, i)] = l.slice(i + 1); }
(async () => {
  const sql = fs.readFileSync(0, 'utf8');
  const c = new Client({ host: e.DB_POSTGRESDB_HOST, port: +e.DB_POSTGRESDB_PORT, user: e.DB_POSTGRESDB_USER, password: e.DB_POSTGRESDB_PASSWORD, database: e.DB_POSTGRESDB_DATABASE, ssl: { rejectUnauthorized: false } });
  await c.connect(); const r = await c.query(sql); await c.end();
  console.log(JSON.stringify(Array.isArray(r) ? r.map(x => x.rows) : r.rows));
})().catch(err => { console.error('ERR', err.message); process.exit(1); });
