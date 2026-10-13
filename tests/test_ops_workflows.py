"""fx-digest-alert, price-scraper-alerts and the ops workflows (health, dead-letter replay, global error handler), run headless via the n8n CLI."""
import json, time
import requests
from conftest import BASE, NOTIFY, db, node_json, post, run_cli


def last_notification():
    return requests.get(f"{NOTIFY}/recorded", timeout=5).json()[-1]["content"]


# ---------------- fx-digest-alert -------------------------------------------------------------------
def test_fx_01_digest_runs_against_real_frankfurter_api():
    ex, out = run_cli("hubFxDigest0001")
    r = node_json(ex, "Digest result")
    assert ex["status"] == "success" and r["pairs"] == 5 and r["notified"] is True
    assert "EUR/USD" in r["digest"] and "z=" in r["digest"]


def test_fx_02_digest_is_delivered_to_the_notifier():
    run_cli("hubFxDigest0001")
    assert "FX digest" in last_notification()


def test_fx_03_zscore_flags_unusual_moves_with_tight_thresholds():
    ex, _ = run_cli("hubFxDigest0001", {"FX_PCT_THRESHOLD": "0.0001", "FX_Z_THRESHOLD": "0.0001"})
    r = node_json(ex, "Digest result")
    assert len(r["unusual"]) >= 1 and "UNUSUAL" in r["digest"] and "Unusual moves" in last_notification()


def test_fx_04_quiet_day_with_loose_thresholds():
    ex, _ = run_cli("hubFxDigest0001", {"FX_PCT_THRESHOLD": "50", "FX_Z_THRESHOLD": "50"})
    assert node_json(ex, "Digest result")["unusual"] == []


def test_fx_05_symbols_are_configurable():
    ex, _ = run_cli("hubFxDigest0001", {"FX_SYMBOLS": "USD,GBP"})
    assert node_json(ex, "Digest result")["pairs"] == 2


def test_fx_06_analysis_has_30_day_stats():
    ex, _ = run_cli("hubFxDigest0001")
    pair = node_json(ex, "Analyse: % move + z-score")["pairs"][0]
    assert pair["points"] >= 15 and pair["min30"] <= pair["rate"] * 1.2 and "pct30" in pair and "z" in pair


# ---------------- price-scraper-alerts --------------------------------------------------------------
ENV1 = {"SCRAPE_PAGES": "1", "SCRAPE_DELAY_S": "1"}


def test_price_01_first_run_seeds_baseline_without_alert_storm():
    db("delete from hub.prices; delete from hub.price_events")
    ex, _ = run_cli("hubPriceScrape1", ENV1)
    r = node_json(ex, "Run summary")
    assert r["scraped"] == 20 and r["baseline"] is True and r["alerts"] == 0 and r["broken_pages"] == 0
    assert db("select count(*)::int c from hub.prices")[0]["c"] == 20


def test_price_02_unchanged_second_run_has_no_events():
    r = node_json(run_cli("hubPriceScrape1", ENV1)[0], "Run summary")
    assert r["baseline"] is False and r["events"] == 0 and r["alerted"] is False


def test_price_03_price_drop_alert():
    db("update hub.prices set price_gbp = price_gbp * 1.5 where book_id in ('a-light-in-the-attic_1000','tipping-the-velvet_999')")
    ex, _ = run_cli("hubPriceScrape1", ENV1)
    r = node_json(ex, "Run summary")
    assert r["alerts"] == 2 and r["events"] == 2
    n = last_notification()
    assert "price alert" in n.lower() and "▼" in n and "A Light in the Attic" in n
    assert db("select count(*)::int c from hub.price_events where event='drop'")[0]["c"] == 2


def test_price_04_small_move_logged_but_not_alerted():
    db("update hub.prices set price_gbp = price_gbp * 1.02 where book_id = 'soumission_998'")
    r = node_json(run_cli("hubPriceScrape1", ENV1)[0], "Run summary")
    assert r["events"] == 1 and r["alerts"] == 0


def test_price_05_back_in_stock_alert():
    db("update hub.prices set in_stock = false where book_id = 'sharp-objects_997'")
    r = node_json(run_cli("hubPriceScrape1", ENV1)[0], "Run summary")
    assert r["alerts"] == 1 and "back in stock" in last_notification()


def test_price_06_new_title_alert():
    db("delete from hub.prices where book_id = 'sapiens-a-brief-history-of-humankind_996'")
    r = node_json(run_cli("hubPriceScrape1", ENV1)[0], "Run summary")
    assert r["alerts"] == 1 and "NEW" in last_notification()


def test_price_07_breakage_detector_alerts_when_selectors_match_nothing():
    before = db("select count(*)::int c from hub.prices")[0]["c"]
    ex, _ = run_cli("hubPriceScrape1", {**ENV1, "SCRAPE_BASE_URL": f"{NOTIFY}/broken"})
    r = node_json(ex, "Run summary")
    assert r["broken_pages"] == 1 and r["scraped"] == 0 and r["alerted"] is True
    assert "selectors" in last_notification().lower()
    assert db("select count(*)::int c from hub.prices")[0]["c"] == before          # stored prices are not wiped by a broken run


def test_price_08_rate_limit_is_applied_between_pages():
    t = time.time()
    run_cli("hubPriceScrape1", {"SCRAPE_PAGES": "3", "SCRAPE_DELAY_S": "2"})
    assert time.time() - t >= 6                                                      # 3 pages x 2 s wait


# ---------------- dead-letter replay ----------------------------------------------------------------
def test_dlq_01_replay_recovers_a_lead(key):
    payload = json.dumps({"email": "replayed@stripe.com", "name": "Re Played", "idempotency_key": key})
    db(f"insert into hub.dead_letters (source,payload,error) values ('lead-intake','{payload}'::jsonb,'simulated')")
    ex, _ = run_cli("hubDlqReplay001")
    assert node_json(ex, "Summary")["replayed"] >= 1
    assert db(f"select count(*)::int c from hub.leads where idempotency_key='{key}'")[0]["c"] == 1
    assert db(f"select status from hub.dead_letters where payload->>'idempotency_key'='{key}'")[0]["status"] == "replayed"


def test_dlq_02_replay_recovers_a_ticket(key):
    payload = json.dumps({"message": "Replay me please, billing issue", "subject": "Dead letter", "idempotency_key": key})
    db(f"insert into hub.dead_letters (source,payload,error) values ('support-triage-ai','{payload}'::jsonb,'simulated')")
    run_cli("hubDlqReplay001")
    assert db(f"select count(*)::int c from hub.tickets where idempotency_key='{key}'")[0]["c"] == 1


def test_dlq_03_replay_is_idempotent(key):
    lead = {"email": "already.there@stripe.com", "name": "Al Ready"}
    post("demo-lead-intake", lead, {"Idempotency-Key": key})
    db(f"insert into hub.dead_letters (source,payload,error) values ('lead-intake','{json.dumps({**lead, 'idempotency_key': key})}'::jsonb,'x')")
    run_cli("hubDlqReplay001")
    assert db(f"select count(*)::int c from hub.leads where idempotency_key='{key}'")[0]["c"] == 1


def test_dlq_04_poison_message_is_retried_then_dropped(key):
    payload = json.dumps({"email": "not-valid", "idempotency_key": key})
    db(f"insert into hub.dead_letters (source,payload,error,attempts) values ('lead-intake','{payload}'::jsonb,'poison',3)")
    run_cli("hubDlqReplay001")
    row = db(f"select status,attempts from hub.dead_letters where payload->>'idempotency_key'='{key}'")[0]
    assert row["status"] == "pending" and row["attempts"] == 4
    run_cli("hubDlqReplay001")
    row = db(f"select status,attempts from hub.dead_letters where payload->>'idempotency_key'='{key}'")[0]
    assert row["status"] == "dropped" and row["attempts"] == 5


# ---------------- observability ---------------------------------------------------------------------
def test_obs_01_daily_health_report():
    ex, _ = run_cli("hubHealthReport1")
    r = node_json(ex, "Report result")
    assert ex["status"] == "success" and r["success"] > 0 and 0 <= r["rate"] <= 100
    assert db("select count(*)::int c from hub.health_reports where report_date = current_date")[0]["c"] == 1
    assert "Success rate" in last_notification()


def test_obs_02_health_report_is_idempotent_per_day():
    run_cli("hubHealthReport1")
    assert db("select count(*)::int c from hub.health_reports where report_date = current_date")[0]["c"] == 1


def test_obs_03_unhandled_failure_reaches_the_global_error_workflow():
    n_before = db("select count(*)::int c from hub.error_log")[0]["c"]
    r = post("demo-lead-intake", {"email": "boom@stripe.com", "idempotency_key": "nul\u0000byte"})      # Postgres rejects NUL in text -> unhandled node error
    assert r.status_code >= 400 or r.text == ""
    for _ in range(30):
        if db("select count(*)::int c from hub.error_log")[0]["c"] > n_before:
            break
        time.sleep(1)
    rows = db("select workflow_name, failed_node, message from hub.error_log order by id desc limit 1")
    assert rows[0]["workflow_name"] == "hub-lead-intake" and rows[0]["failed_node"] == "Dedupe lookup"
    assert "Workflow failed: hub-lead-intake" in last_notification()
