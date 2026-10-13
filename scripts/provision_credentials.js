// Emits n8n credential import files (plaintext data; n8n encrypts on import) from environment variables.
// Usage: node scripts/provision_credentials.js <outdir>   -- the caller deletes <outdir> afterwards.
const fs = require('fs'), path = require('path');
const out = process.argv[2];
const e = process.env;
const need = ['DB_POSTGRESDB_HOST', 'DB_POSTGRESDB_USER', 'DB_POSTGRESDB_PASSWORD'];
for (const k of need) if (!e[k]) { console.error(`missing env ${k}`); process.exit(1); }
const creds = [
  { id: 'hubPostgres01', name: 'Hub Postgres', type: 'postgres', data: {
    host: e.DB_POSTGRESDB_HOST, port: Number(e.DB_POSTGRESDB_PORT || 5432), database: e.DB_POSTGRESDB_DATABASE || 'postgres',
    user: e.DB_POSTGRESDB_USER, password: e.DB_POSTGRESDB_PASSWORD, schema: 'hub', ssl: 'require', allowUnauthorizedCerts: true,
    maxConnections: 3, sshTunnel: false } },
  { id: 'hubGroqAuth01', name: 'Groq API (LLM_API_KEY)', type: 'httpHeaderAuth', data: {
    name: 'Authorization', value: `Bearer ${e.LLM_API_KEY || 'not-configured'}` } },
];
fs.writeFileSync(path.join(out, 'credentials.json'), JSON.stringify(creds), { mode: 0o600 });
console.log(`credentials prepared: ${creds.map(c => c.name).join(', ')}${e.LLM_API_KEY ? '' : ' (LLM key NOT set -> triage will use the keyword fallback)'}`);
