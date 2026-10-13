"""Shared fixtures. The suite talks to a REAL local n8n (see README: scripts/run_local.sh) plus the mocks in mock_services.py."""
import collections, json, os, subprocess, time, uuid
import pytest, requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("N8N_BASE_URL", "http://localhost:5678")
NOTIFY = os.environ.get("NOTIFY_MOCK_URL", "http://127.0.0.1:5699")
RUN = uuid.uuid4().hex[:8]
RESULTS = collections.OrderedDict()


def pytest_runtest_logreport(report):
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        mod = report.nodeid.split("::")[0].replace("tests/", "").replace("test_", "").replace(".py", "")
        r = RESULTS.setdefault(mod, {"passed": 0, "failed": 0, "skipped": 0, "seconds": 0.0})
        r["passed" if report.outcome == "passed" else "failed" if report.outcome == "failed" else "skipped"] += 1
        r["seconds"] = round(r["seconds"] + report.duration, 1)


def pytest_sessionfinish(session, exitstatus):
    with open(os.path.join(ROOT, "tests", "results.json"), "w") as f:
        json.dump({"run": RUN, "exit": int(exitstatus), "modules": RESULTS}, f, indent=2)


def db(sql):
    out = subprocess.run(["node", os.path.join(ROOT, "scripts", "db_query.js")], input=sql, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.fixture(scope="session")
def run_id():
    return RUN


@pytest.fixture(scope="session", autouse=True)
def _cleanup(run_id):
    yield
    db(f"delete from hub.leads where idempotency_key like 'pytest-{run_id}%'; delete from hub.tickets where idempotency_key like 'pytest-{run_id}%'; "
       f"delete from hub.dead_letters where payload->>'idempotency_key' like 'pytest-{run_id}%'")


@pytest.fixture()
def key(run_id):
    return f"pytest-{run_id}-{uuid.uuid4().hex[:10]}"


@pytest.fixture(scope="session", autouse=True)
def _services():
    for url in (f"{BASE}/healthz", f"{NOTIFY}/recorded"):
        for _ in range(20):
            try:
                if requests.get(url, timeout=3).ok:
                    break
            except requests.RequestException:
                time.sleep(1)
        else:
            pytest.exit(f"required service not reachable: {url} (start n8n + tests/mock_services.py first)", 2)


def post(path, body=None, headers=None, raw=None, timeout=90):
    h = {"Content-Type": "application/json", **(headers or {})}
    data = raw if raw is not None else json.dumps(body)
    return requests.post(f"{BASE}/webhook/{path}", data=data.encode() if isinstance(data, str) else data, headers=h, timeout=timeout)


@pytest.fixture()
def lead():
    def _lead(body=None, key=None, headers=None, **kw):
        h = dict(headers or {})
        if key:
            h["Idempotency-Key"] = key
        return post("demo-lead-intake", body, h, **kw)
    return _lead


@pytest.fixture()
def triage():
    def _t(body=None, key=None, headers=None, **kw):
        h = dict(headers or {})
        if key:
            h["Idempotency-Key"] = key
        return post("demo-support-triage", body, h, **kw)
    return _t


@pytest.fixture()
def notifications():
    def _get():
        return requests.get(f"{NOTIFY}/recorded", timeout=5).json()
    return _get


def run_cli(workflow_id, extra_env=None, timeout=240):
    """Execute a workflow headless through the n8n CLI (same path CI uses). Returns (execution_json, raw_output)."""
    env = {**os.environ, **(extra_env or {})}
    cmd = f'. {ROOT}/scripts/cli_env.sh; exec "$N8N_BIN" execute --id={workflow_id}'
    p = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout, env=env)
    out = p.stdout + p.stderr
    start = out.find("\n{")
    ex = json.loads(out[start:]) if start >= 0 else {}
    return ex, out


def node_json(ex, node):
    runs = ex["data"]["resultData"]["runData"].get(node)
    return runs[0]["data"]["main"][0][0]["json"] if runs else None
