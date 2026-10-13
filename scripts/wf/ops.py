from lib import *
from subs import NOTIFY_ID

ERR_ID = "hubErrorHandle1"
HEALTH_ID = "hubHealthReport1"
DLQ_ID = "hubDlqReplay001"


def error_handler():
    wf = WF(ERR_ID, "hub-ops-error-handler", [tag("ops")])
    X, Y = 250, 220
    t = wf.add("Error Trigger", "n8n-nodes-base.errorTrigger", {}, (0, Y), 1)
    rec = code(wf, "Structured error record", r"""
// One normalised record per failure: queryable in Postgres, readable in chat.
const e = $input.first().json, x = e.execution || {}, w = e.workflow || {};
const msg = String(x.error?.message || 'unknown error').replace(/(key|token|secret|password)[=:]\s*\S+/gi, '$1=[redacted]').slice(0, 500);
return [{ json: { workflow_id: w.id || null, workflow_name: w.name || null, execution_id: x.id || null,
  failed_node: x.lastNodeExecuted || null, message: msg, mode: x.mode || null,
  level: 'critical', title: `Workflow failed: ${w.name}`,
  text: `Node: ${x.lastNodeExecuted}\nError: ${msg}\nExecution: ${x.id} (${x.mode})` } }];
""", (X, Y))
    store = pg(wf, "Store in error_log",
               "insert into hub.error_log (workflow_id, workflow_name, execution_id, failed_node, message, mode) values ($1,$2,$3,$4,$5,$6) returning id",
               "={{ [$json.workflow_id,$json.workflow_name,$json.execution_id,$json.failed_node,$json.message,$json.mode] }}", (2 * X, Y),
               onError="continueRegularOutput")
    back = code(wf, "Restore record", "return [{ json: $('Structured error record').first().json }];", (3 * X, Y))
    ntf = exec_wf(wf, "Notify (sub-workflow)", NOTIFY_ID, "hub-sub-notify", (4 * X, Y), onError="continueRegularOutput")
    wf.chain(t, rec, store, back, ntf)
    wf.note("hub-ops-error-handler", "## Global error workflow\nSet as `errorWorkflow` in the settings of every other workflow.\n\n"
            "1. Error Trigger -> structured record (secrets scrubbed)\n2. Persist to `hub.error_log`\n3. Notify (level `critical`)\n\n"
            "Storing the record is itself fail-soft so the notification always goes out.", (-20, Y - 300), (520, 200))
    return wf


def health():
    wf = WF(HEALTH_ID, "hub-ops-daily-health-report", [tag("ops"), tag("schedule")], error_wf=ERR_ID)
    X, Y = 250, 220
    sch = wf.add("Schedule: daily 07:00", "n8n-nodes-base.scheduleTrigger",
                 {"rule": {"interval": [{"field": "cronExpression", "expression": "0 7 * * *"}]}}, (0, Y - 100), 1.2)
    man = wf.add("Manual / headless trigger", "n8n-nodes-base.manualTrigger", {}, (0, Y + 60), 1)
    ex = pg(wf, "Executions last 24h (n8n DB)",
            "select w.name as workflow, e.status, count(*)::int as n from n8n.execution_entity e "
            "join n8n.workflow_entity w on w.id = e.\"workflowId\" where e.\"startedAt\" > now() - interval '24 hours' group by 1,2 order by 1,2",
            None, (X, Y), alwaysOutputData=True)
    biz = pg(wf, "Business counters (hub DB)",
             "select (select count(*)::int from hub.leads where created_at > now() - interval '24 hours') as leads_24h, "
             "(select count(*)::int from hub.tickets where created_at > now() - interval '24 hours') as tickets_24h, "
             "(select count(*)::int from hub.tickets where created_at > now() - interval '24 hours' and classifier='fallback') as fallback_24h, "
             "(select count(*)::int from hub.dead_letters where status='pending') as dlq_pending, "
             "(select count(*)::int from hub.error_log where created_at > now() - interval '24 hours') as errors_24h", None, (2 * X, Y))
    rep = code(wf, "Build report", r"""
const rows = $('Executions last 24h (n8n DB)').all().map(i => i.json).filter(r => r.workflow);
const b = $input.first().json;
const by = {}; let ok = 0, bad = 0;
for (const r of rows) { by[r.workflow] = by[r.workflow] || { success: 0, error: 0, other: 0 };
  const k = r.status === 'success' ? 'success' : (r.status === 'error' || r.status === 'crashed') ? 'error' : 'other';
  by[r.workflow][k] += r.n; if (k === 'success') ok += r.n; if (k === 'error') bad += r.n; }
const total = ok + bad, rate = total ? Math.round(ok / total * 1000) / 10 : 100;
const lines = Object.entries(by).map(([w, c]) => `${w.padEnd(28)} ok ${String(c.success).padStart(3)}  fail ${String(c.error).padStart(3)}`);
const level = bad > 0 || b.dlq_pending > 0 ? 'warn' : 'info';
const text = `Success rate ${rate}% (${ok}/${total})  ·  leads ${b.leads_24h}  tickets ${b.tickets_24h} (LLM fallback ${b.fallback_24h})  ·  DLQ pending ${b.dlq_pending}\n\`\`\`\n${lines.join('\n') || 'no executions in the last 24h'}\n\`\`\``;
return [{ json: { date: new Date().toISOString().slice(0, 10), success: ok, failed: bad, by_workflow: by, rate, ...b, level, title: 'n8n daily health report', text } }];
""", (3 * X, Y))
    save = pg(wf, "Save report (upsert by day)",
              "insert into hub.health_reports (report_date, success, failed, by_workflow) values ($1,$2,$3,$4::jsonb) "
              "on conflict (report_date) do update set success=excluded.success, failed=excluded.failed, by_workflow=excluded.by_workflow, created_at=now() returning report_date",
              "={{ [$json.date,$json.success,$json.failed,JSON.stringify($json.by_workflow)] }}", (4 * X, Y))
    back = code(wf, "Restore report payload", "return [{ json: $('Build report').first().json }];", (5 * X, Y))
    ntf = exec_wf(wf, "Notify (sub-workflow)", NOTIFY_ID, "hub-sub-notify", (6 * X, Y), onError="continueRegularOutput")
    out = code(wf, "Report result", "const r = $('Build report').first().json; return [{ json: { date: r.date, success: r.success, failed: r.failed, rate: r.rate, dlq_pending: r.dlq_pending } }];", (7 * X, Y))
    wf.link(sch, ex); wf.link(man, ex)
    wf.chain(ex, biz, rep, save, back, ntf, out)
    wf.note("hub-ops-daily-health-report", "## Daily health report\nReads n8n's own execution table (schema `n8n`) plus business counters (schema `hub`).\n\n"
            "- success / failed per workflow, last 24 h\n- leads, tickets, **LLM-fallback ratio**, dead-letter backlog, error_log count\n"
            "- upserts one row per day in `hub.health_reports`, then notifies\n\nNo API key needed: it queries the database directly.", (-20, Y - 360), (560, 220))
    return wf


def dlq():
    wf = WF(DLQ_ID, "hub-ops-dead-letter-replay", [tag("ops"), tag("schedule")], error_wf=ERR_ID)
    X, Y = 250, 220
    sch = wf.add("Schedule: every 15 min", "n8n-nodes-base.scheduleTrigger",
                 {"rule": {"interval": [{"field": "minutes", "minutesInterval": 15}]}}, (0, Y - 100), 1.2)
    man = wf.add("Manual / headless trigger", "n8n-nodes-base.manualTrigger", {}, (0, Y + 60), 1)
    claim = pg(wf, "Claim pending dead letters (SKIP LOCKED)",
               "update hub.dead_letters set attempts = attempts + 1 where id in (select id from hub.dead_letters where status = 'pending' and attempts < 5 "
               "order by id limit 20 for update skip locked) returning id, source, payload, attempts", None, (X, Y))
    req = code(wf, "Build replay request", r"""
const base = ($env.HUB_SELF_URL || `http://localhost:${$env.N8N_PORT || 5678}`).replace(/\/$/, '');
const path = { 'lead-intake': '/webhook/demo-lead-intake', 'support-triage-ai': '/webhook/demo-support-triage' };
return $input.all().map(i => { const r = i.json, p = r.payload || {};
  return { json: { id: r.id, attempts: r.attempts, url: base + (path[r.source] || '/webhook/unknown'), key: p.idempotency_key, body: p } }; });
""", (2 * X, Y))
    post = http(wf, "Replay through the original webhook", "={{ $json.url }}", (3 * X, Y), method="POST",
                headers={"Content-Type": "application/json", "Idempotency-Key": "={{ $json.key }}"},
                body="={{ $json.body }}", timeout=30000, onError="continueRegularOutput", retryOnFail=False)
    res = code(wf, "Classify outcome", r"""
const src = $('Build replay request').all();
return $input.all().map((i, k) => { const r = src[k].json, ok = !i.json.error && i.json.ok === true;
  return { json: { id: r.id, status: ok ? 'replayed' : (r.attempts >= 5 ? 'dropped' : 'pending'), error: ok ? null : String(i.json.error?.message || i.json.message || 'replay failed').slice(0, 300) } }; });
""", (4 * X, Y))
    upd = pg(wf, "Mark outcome",
             "update hub.dead_letters set status = $2, error = coalesce($3, error), replayed_at = case when $2 = 'replayed' then now() end where id = $1 returning id, status",
             "={{ [$json.id, $json.status, $json.error] }}", (5 * X, Y))
    sm = code(wf, "Summary", r"""
const a = $input.all().map(i => i.json).filter(x => x.id);
return [{ json: { processed: a.length, replayed: a.filter(x => x.status === 'replayed').length, still_pending: a.filter(x => x.status === 'pending').length, dropped: a.filter(x => x.status === 'dropped').length } }];
""", (6 * X, Y), alwaysOutputData=True)
    wf.link(sch, claim); wf.link(man, claim)
    wf.chain(claim, req, post, res, upd, sm)
    wf.note("hub-ops-dead-letter-replay", "## Dead-letter replay\nLead and triage workflows park a request in `hub.dead_letters` when persistence fails (they still answer `202`).\n\n"
            "1. Claim up to 20 rows atomically (`FOR UPDATE SKIP LOCKED`, attempts + 1)\n2. Replay through the **original webhook** with the original `Idempotency-Key`\n"
            "3. 2xx -> `replayed`; else back to `pending`; after 5 attempts -> `dropped`\n\nIdempotency makes replays safe: a lead that was in fact stored is not duplicated.", (-20, Y - 380), (560, 240))
    return wf
