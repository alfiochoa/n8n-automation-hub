"""The repo guard-rails themselves are tested: good workflows pass, planted violations are caught."""
import copy, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import ci_checks as c


def run(fn, wfs=None):
    errs = []
    fn(*( [wfs] if wfs is not None else []), errs)
    return errs


def good():
    return c.load_workflows()


def test_repo_workflows_pass_every_check():
    assert c.main() == 0


def test_secret_in_workflow_credentials_is_caught():
    w = good(); n = next(n for n in w["hub-lead-intake.json"]["nodes"] if n.get("credentials"))
    n["credentials"]["postgres"]["id"] = "REAL-CRED-ID-123"
    assert any("not an approved placeholder" in e for e in run(c.check_workflow_leaks, w))


def test_pindata_is_caught():
    w = good(); w["hub-lead-intake.json"]["pinData"] = {"Webhook: lead": [{"json": {"email": "real@person.com"}}]}
    assert any("pinData" in e for e in run(c.check_workflow_leaks, w))


def test_forbidden_node_type_is_caught():
    w = good(); w["hub-lead-intake.json"]["nodes"].append({"name": "x", "id": "z", "type": "n8n-nodes-base.executeCommand", "parameters": {}})
    assert any("forbidden" in e for e in run(c.check_allowlist, w))


def test_unknown_node_type_is_caught():
    w = good(); w["hub-lead-intake.json"]["nodes"].append({"name": "x", "id": "z", "type": "n8n-nodes-base.mysteryNode", "parameters": {}})
    assert any("not in the allowlist" in e for e in run(c.check_allowlist, w))


def test_http_node_without_timeout_is_caught():
    w = good(); n = next(n for n in w["hub-fx-digest-alert.json"]["nodes"] if n["type"] == "n8n-nodes-base.httpRequest"); n["parameters"]["options"] = {}
    assert any("no timeout" in e for e in run(c.check_hygiene, w))


def test_wildcard_cors_is_caught():
    w = good(); n = next(n for n in w["hub-lead-intake.json"]["nodes"] if n["type"] == "n8n-nodes-base.webhook"); n["parameters"]["options"]["allowedOrigins"] = "*"
    assert any("CORS" in e for e in run(c.check_hygiene, w))


def test_broken_connection_is_caught():
    w = good(); w["hub-lead-intake.json"]["connections"]["Validate payload"]["main"][0].append({"node": "ghost", "type": "main", "index": 0})
    assert any("unknown node 'ghost'" in e for e in run(c.check_lint, w))


def test_secret_patterns_detect_planted_values():
    import re
    samples = {"postgres url with password": "postgresql://postgres.abc:hunter2pw@host:5432/db", "groq/openai-style key": "gsk_" + "a" * 40,
               "render api key": "rnd_" + "b" * 30, "github token": "ghp_" + "c" * 36, "discord/slack webhook url": "https://discord.com/api/webhooks/1/abc"}
    for label, s in samples.items():
        assert re.search(c.SECRET_PATTERNS[label], s), label
