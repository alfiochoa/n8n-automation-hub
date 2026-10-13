"""hub-lead-intake: 24 cases against the live webhook (valid, invalid, duplicate, oversized, normalisation, enrichment, dead-letter, CORS)."""
import json, time
import pytest, requests
from conftest import BASE, db, post

GOOD = {"email": "jane.doe@stripe.com", "name": "jane doe", "company": "Stripe", "country": "USA", "phone": "+1 415 555 0100",
        "message": "We need pricing for 50 seats, budget approved, this week."}


def err_codes(r):
    return {e["code"] for e in r.json()["errors"]}


def test_01_valid_business_lead_is_hot(lead, key):
    r = lead(GOOD, key)
    j = r.json()
    assert r.status_code == 200 and j["ok"] and not j["duplicate"]
    assert j["decision"]["tier"] == "hot" and j["decision"]["route"] == "notify_sales_now" and j["decision"]["score"] >= 70
    assert any(x["rule"] == "business_domain" for x in j["reasons"])
    assert j["trace"][0] == "webhook" and "route:hot" in j["trace"]


def test_02_hot_lead_sends_notification(lead, key, notifications):
    before = len(notifications())
    lead({**GOOD, "email": "cto@stripe.com"}, key)
    after = notifications()
    assert len(after) == before + 1 and "HOT" in after[-1]["content"]


def test_03_warm_lead_free_mailbox(lead, key):
    j = lead({"email": "john.smith@gmail.com", "name": "John Smith"}, key).json()
    assert j["decision"]["tier"] == "warm" and j["decision"]["route"] == "notify_and_nurture"
    assert any(x["rule"] == "free_mailbox" for x in j["reasons"])


def test_04_cold_lead_disposable_domain(lead, key, notifications):
    before = len(notifications())
    j = lead({"email": "x@mailinator.com"}, key).json()
    assert j["decision"]["tier"] == "cold" and j["decision"]["route"] == "log_only"
    assert any(x["rule"] == "disposable_domain" for x in j["reasons"])
    assert len(notifications()) == before          # cold leads never page anyone


def test_05_spam_keywords_penalised(lead, key):
    j = lead({"email": "seo@gmail.com", "message": "Cheap SEO backlinks and guest post offers"}, key).json()
    assert any(x["rule"] == "spam_keywords" for x in j["reasons"]) and j["decision"]["tier"] == "cold"


def test_06_nonexistent_domain_flagged(lead, key):
    j = lead({"email": "a@this-domain-should-not-exist-8f3k2.com", "name": "A B"}, key).json()
    assert j["enrichment"]["mx"] == "nxdomain" and any(x["rule"] == "domain_does_not_exist" for x in j["reasons"])


def test_07_country_alias_normalised(lead, key):
    j = lead({"email": "a.b@bbc.co.uk", "name": "A B", "country": "UK", "phone": "020 7946 0000"}, key).json()
    assert j["normalized"]["country"] == "GB" and j["normalized"]["phone"] == "+442079460000"
    assert j["enrichment"]["region"] == "Europe & Central Asia"


def test_08_phone_to_e164_with_spanish_alias(lead, key):
    j = lead({"email": "maria@telefonica.com", "name": "maría de la cruz", "country": "España", "phone": "600 11 22 33"}, key).json()
    assert j["normalized"]["phone"] == "+34600112233" and j["normalized"]["country"] == "ES"


def test_09_name_title_case_keeps_particles(lead, key):
    j = lead({"email": "ana@telefonica.com", "name": "ANA-maría DE LA cruz"}, key).json()
    assert j["normalized"]["name"] == "Ana-María de la Cruz"


def test_10_unparseable_phone_penalised_not_rejected(lead, key):
    j = lead({"email": "p@stripe.com", "name": "P Q", "phone": "12"}, key)
    assert j.status_code == 200 and any(x["rule"] == "phone_unparseable" for x in j.json()["reasons"])


def test_11_duplicate_same_idempotency_key(lead, key):
    first = lead(GOOD, key).json()
    second = lead(GOOD, key)
    j = second.json()
    assert second.status_code == 200 and j["duplicate"] is True and j["decision"]["route"] == "already_processed"
    assert j["decision"]["tier"] == first["decision"]["tier"] and j["trace"][-2] == "dedupe:duplicate"
    assert db(f"select count(*)::int c from hub.leads where idempotency_key='{key}'")[0]["c"] == 1


def test_12_duplicate_by_email_hash_without_key(lead, run_id):
    email = f"dup.{run_id}@stripe.com"
    a = lead({"email": email, "name": "Dup Lic"}).json()
    b = lead({"email": email.upper(), "name": "Dup Lic"}).json()      # case-insensitive
    assert not a["duplicate"] and b["duplicate"]
    db(f"delete from hub.leads where idempotency_key='{a['idempotency_key']}'")


def test_13_concurrent_duplicates_store_once(lead, key):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(lambda _: lead(GOOD, key).json(), range(4)))
    assert all(r["ok"] for r in res)
    assert db(f"select count(*)::int c from hub.leads where idempotency_key='{key}'")[0]["c"] == 1


def test_14_invalid_email_format_422(lead):
    r = lead({"email": "not-an-email"})
    assert r.status_code == 422 and err_codes(r) == {"invalid_format"} and r.json()["trace"] == ["webhook", "validate:rejected"]


def test_15_missing_email_422(lead):
    r = lead({"name": "No Email"})
    assert r.status_code == 422 and "required" in err_codes(r)


def test_16_empty_object_422(lead):
    assert lead({}).status_code == 422


def test_17_body_not_an_object_422(lead):
    r = lead(["email", "x@y.com"])
    assert r.status_code == 422 and "not_an_object" in err_codes(r)


def test_18_unknown_fields_rejected(lead):
    r = lead({"email": "a@stripe.com", "isAdmin": True})
    assert r.status_code == 422 and "unknown_fields" in err_codes(r)


def test_19_field_too_long_422(lead):
    r = lead({"email": "a@stripe.com", "name": "x" * 101})
    assert r.status_code == 422 and "too_long" in err_codes(r)


def test_20_wrong_type_422(lead):
    r = lead({"email": "a@stripe.com", "name": 12345})
    assert r.status_code == 422 and "must_be_string" in err_codes(r)


def test_21_oversized_payload_validator_413(lead):
    r = lead({"email": "a@stripe.com", "message": "m" * 1999, "name": "n" * 99, "company": "c" * 119, "country": "x" * 59, "phone": "1" * 39, "source": "s" * 39,
              "idempotency_key": "k" * 119, "extra": "y" * 9000})
    assert r.status_code == 413 and "payload_too_large" in err_codes(r)


def test_22_oversized_body_rejected_at_the_edge():
    r = post("demo-lead-intake", raw=json.dumps({"email": "a@stripe.com", "message": "z" * 2_000_000}))
    # N8N_PAYLOAD_SIZE_MAX=1 (MB): the body parser rejects it before any workflow runs (n8n answers with its generic 5xx envelope, never 2xx)
    assert r.status_code in (413, 500) and not r.text.startswith('{"ok"')


def test_23_malformed_json_is_a_client_error():
    r = post("demo-lead-intake", raw="{not json")
    assert 400 <= r.status_code < 500


def test_24_get_not_allowed():
    assert requests.get(f"{BASE}/webhook/demo-lead-intake", timeout=15).status_code == 404


def test_25_cors_preflight_for_allowed_origin():
    r = requests.options(f"{BASE}/webhook/demo-lead-intake", headers={"Origin": "http://localhost:8080", "Access-Control-Request-Method": "POST",
                                                                      "Access-Control-Request-Headers": "content-type,idempotency-key"}, timeout=15)
    assert r.status_code in (200, 204) and r.headers.get("Access-Control-Allow-Origin") == "http://localhost:8080"


def test_26_cors_disallowed_origin_gets_no_header(lead, key):
    r = requests.post(f"{BASE}/webhook/demo-lead-intake", json=GOOD, headers={"Origin": "https://evil.example", "Idempotency-Key": key}, timeout=60)
    assert r.headers.get("Access-Control-Allow-Origin") != "https://evil.example"


def test_27_persistence_failure_goes_to_dead_letter(lead, key):
    r = lead({**GOOD, "email": "dlq.lead@stripe.com"}, key, headers={"x-hub-chaos": "persist-fail"})
    j = r.json()
    assert r.status_code == 202 and j["accepted"] and j["decision"]["route"] == "queued_for_replay"
    row = db(f"select source,status,payload from hub.dead_letters where payload->>'idempotency_key'='{key}'")
    assert row and row[0]["source"] == "lead-intake" and row[0]["status"] == "pending" and row[0]["payload"]["email"] == "dlq.lead@stripe.com"
    assert db(f"select count(*)::int c from hub.leads where idempotency_key='{key}'")[0]["c"] == 0
