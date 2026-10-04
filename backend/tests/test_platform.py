"""UPI Guard platform APIs: auth, transactions, import, investigation, cases, reports, alerts,
simulator, network, account and security."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.engine.simulator import SCENARIOS
from app.main import app

NOW = datetime(2026, 9, 20, 12, 0)


def tx(**kw):
    body = {"occurred_at": NOW.isoformat(), "direction": "sent", "amount": 500,
            "counterparty_name": "Shop", "counterparty_upi": "shop@ybl", "balance_before": 40_000}
    body.update(kw)
    return body


# ---------- auth ----------

def test_signup_login_logout_me(client):
    r = client.post("/api/auth/signup", json={"email": "Alice@Example.com", "password": "a very long password"})
    assert r.status_code == 200 and r.json()["email"] == "alice@example.com"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/auth/me").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "alice@example.com", "password": "a very long password"}).status_code == 200


@pytest.mark.parametrize("body,status", [
    ({"email": "bad", "password": "long enough pw"}, 400),
    ({"email": "x@example.com", "password": "short"}, 400),
])
def test_signup_validation(client, body, status):
    assert client.post("/api/auth/signup", json=body).status_code == status


def test_duplicate_email(client):
    body = {"email": "dup@example.com", "password": "a very long password"}
    assert client.post("/api/auth/signup", json=body).status_code == 200
    assert TestClient(app).post("/api/auth/signup", json=body).status_code == 409


def test_login_throttle(client):
    client.post("/api/auth/signup", json={"email": "throttle@example.com", "password": "a very long password"})
    c = TestClient(app)
    for _ in range(5):
        assert c.post("/api/auth/login", json={"email": "throttle@example.com", "password": "wrong"}).status_code == 401
    assert c.post("/api/auth/login", json={"email": "throttle@example.com", "password": "a very long password"}).status_code == 429


def test_tampered_or_missing_session_is_rejected(user):
    token = user.cookies.get("upig_session")
    body, sig = token.split(".")
    c = TestClient(app)
    c.cookies.set("upig_session", body + "." + sig[:-2] + ("AA" if not sig.endswith("AA") else "BB"))
    assert c.get("/api/transactions").status_code == 401
    assert TestClient(app).get("/api/transactions").status_code == 401


# ---------- transactions ----------

def test_create_scores_and_lists(user):
    r = user.post("/api/transactions", json=tx(amount=181000, balance_before=181000,
                                               occurred_at=NOW.replace(hour=3).isoformat()))
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["risk_level"] == "high" and t["risk"]["components"]["model"]["available"]
    assert t["risk"]["breakdown"] and t["risk"]["version"] == "risk-v1"
    page = user.get("/api/transactions").json()
    assert page["total"] == 1 and page["items"][0]["id"] == t["id"]


@pytest.mark.parametrize("bad", [
    {"amount": 0}, {"amount": -5}, {"amount": "NaN"}, {"direction": "stolen"},
    {"counterparty_upi": "not a vpa"}, {"external_id": "'; DROP TABLE transactions; --"},
    {"balance_before": -1}, {"note": "x" * 300},
])
def test_create_validation(user, bad):
    r = user.post("/api/transactions", json=tx(**bad))
    assert r.status_code == 400, r.text
    assert isinstance(r.json()["detail"], str)


def test_search_filters_and_injection_safe(user):
    for i, (amount, upi) in enumerate([(200, "chai@ybl"), (60_000, "bigshop@okaxis"), (900, "chai@ybl")]):
        user.post("/api/transactions", json=tx(amount=amount, counterparty_upi=upi,
                                               occurred_at=(NOW + timedelta(hours=i)).isoformat(), balance_before=100_000))
    assert user.get("/api/transactions", params={"q": "chai"}).json()["total"] == 2
    assert user.get("/api/transactions", params={"min_amount": 1000}).json()["total"] == 1
    assert user.get("/api/transactions", params={"q": "' OR '1'='1"}).json()["total"] == 0
    assert user.get("/api/transactions", params={"sort": "amount"}).json()["items"][0]["amount"] == 60_000
    assert user.get("/api/transactions", params={"risk": "extreme"}).status_code == 400


def test_other_users_records_are_invisible(user, other_user):
    tid = user.post("/api/transactions", json=tx()).json()["id"]
    cid = user.post("/api/cases", json={"title": "My case", "transaction_ids": [tid]}).json()["id"]
    for method, path, body in [
        ("get", f"/api/transactions/{tid}", None), ("patch", f"/api/transactions/{tid}", {"review_status": "legitimate"}),
        ("delete", f"/api/transactions/{tid}", None), ("get", f"/api/investigations/{tid}", None),
        ("post", f"/api/investigations/{tid}/notes", {"text": "hi"}), ("get", f"/api/cases/{cid}", None),
        ("get", f"/api/cases/{cid}/report", None), ("patch", f"/api/cases/{cid}", {"status": "RESOLVED"}),
        ("get", f"/api/network/transaction/{tid}", None),
    ]:
        r = getattr(other_user, method)(path, **({"json": body} if body else {}))
        assert r.status_code == 404, (path, r.status_code)
    # and can't attach someone else's transaction to their own case
    r = other_user.post("/api/cases", json={"title": "Sneaky", "transaction_ids": [tid]})
    assert r.status_code == 404
    assert other_user.get("/api/transactions").json()["total"] == 0


def test_review_and_delete(user):
    tid = user.post("/api/transactions", json=tx()).json()["id"]
    assert user.patch(f"/api/transactions/{tid}", json={"review_status": "confirmed_fraud"}).json()["review_status"] == "confirmed_fraud"
    assert user.delete(f"/api/transactions/{tid}").json()["ok"]
    assert user.get(f"/api/transactions/{tid}").status_code == 404


# ---------- CSV import ----------

CSV = """Date,Type,Amount,Name,UPI ID,Reference,Balance Before
2026-09-01 10:00,debit,500,Chai,chai@ybl,512345678901,40000
01/09/2026 11:00,DR,700,Store,store@okaxis,,39500
2026-09-01 12:00,credit,62000,Employer,payroll@hdfcbank,,
2026-09-02,sent,abc,Bad,bad@ybl,,
2026-09-03 00:40,sent,38000,Mule,mule@axl,,38800
"""


def test_csv_import_with_errors(user):
    r = user.post("/api/transactions/import", json={"csv": CSV})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 4 and len(body["errors"]) == 1 and body["errors"][0]["line"] == 5
    page = user.get("/api/transactions", params={"sort": "oldest"}).json()
    assert [t["direction"] for t in page["items"]] == ["sent", "sent", "received", "sent"]
    assert all(t["source"] == "csv" for t in page["items"])


def test_csv_missing_columns_and_empty(user):
    r = user.post("/api/transactions/import", json={"csv": "Name,UPI\nA,a@ybl\n"})
    assert r.status_code == 400 and "Missing required column" in r.json()["detail"]
    assert user.post("/api/transactions/import", json={"csv": ""}).status_code == 400


def test_bulk_rows_get_explained_on_investigation(user):
    user.post("/api/transactions/import", json={"csv": CSV})
    big = user.get("/api/transactions", params={"q": "mule"}).json()["items"][0]
    stored = user.get(f"/api/transactions/{big['id']}").json()["risk"]["components"]["model"]
    assert stored["available"] and stored["explained"] is False and stored["reasons"] == []
    inv = user.get(f"/api/investigations/{big['id']}").json()
    model = inv["transaction"]["risk"]["components"]["model"]
    assert model["explained"] is True and model["reasons"]
    assert {"timeline", "related", "counterparty", "notes", "cases"} <= inv.keys()


def test_investigation_notes(user):
    tid = user.post("/api/transactions", json=tx()).json()["id"]
    assert user.post(f"/api/investigations/{tid}/notes", json={"text": "Called bank"}).status_code == 200
    assert user.get(f"/api/investigations/{tid}").json()["notes"][0]["text"] == "Called bank"


# ---------- cases & incident report ----------

def test_case_workflow_and_report(user):
    tid = user.post("/api/transactions", json=tx(amount=181000, balance_before=181000,
                                                 occurred_at=NOW.replace(hour=3).isoformat())).json()["id"]
    c = user.post("/api/cases", json={"title": "Night transfer", "priority": "high", "transaction_ids": [tid]}).json()
    assert c["status"] == "OPEN" and c["transaction_count"] == 1
    c = user.post(f"/api/cases/{c['id']}/evidence", json={"type": "message", "label": "SMS from bank",
                                                           "data": {"text": "Your OTP is 482913", "upi": "mule@axl"}}).json()
    assert "482913" not in str(c["evidence"])  # secrets masked before storage
    c = user.post(f"/api/cases/{c['id']}/notes", json={"text": "PIN 4321 was shared"}).json()
    assert "4321" not in c["notes"][0]["text"]
    c = user.patch(f"/api/cases/{c['id']}", json={"status": "ESCALATED"}).json()
    assert c["status"] == "ESCALATED"
    rep = user.get(f"/api/cases/{c['id']}/report").json()
    for section in ("case", "summary", "risk_assessment", "model_evidence", "timeline", "related_entities",
                    "notes", "next_steps", "resources", "disclaimer"):
        assert section in rep
    assert rep["risk_assessment"]["highest_level"] == "high"
    assert rep["model_evidence"][0]["reasons"]
    assert any("1930" in s for s in rep["next_steps"])
    assert any(e["value"] == "mule@axl" for e in rep["related_entities"])
    assert user.patch(f"/api/cases/{c['id']}", json={"status": "CLOSED"}).status_code == 400


# ---------- community reports ----------

def test_entity_reports_are_aggregate_only_for_others(user, other_user):
    r = user.post("/api/entity-reports", json={"entity_type": "upi", "entity_value": "Scam.Desk@YBL",
                                               "category": "fake_refund", "description": "Called me, my number 9876543210"})
    assert r.status_code == 200 and r.json()["entity_value"] == "scam.desk@ybl"
    seen = other_user.get("/api/upi/scam.desk@ybl").json()
    assert seen["reports"]["total_reporters"] == 1 and seen["reports"]["by_category"] == {"fake_refund": 1}
    assert "9876543210" not in str(seen) and "description" not in str(seen["reports"])
    assert other_user.get("/api/entity-reports").json() == []           # can't list others' reports
    rid = r.json()["id"]
    assert other_user.patch(f"/api/entity-reports/{rid}", json={"status": "REMOVED"}).status_code == 404
    assert user.patch(f"/api/entity-reports/{rid}", json={"status": "REMOVED"}).json()["status"] == "REMOVED"
    assert other_user.get("/api/upi/scam.desk@ybl").json()["reports"]["total_reporters"] == 0


@pytest.mark.parametrize("body", [
    {"entity_type": "upi", "entity_value": "nope", "category": "other"},
    {"entity_type": "phone", "entity_value": "12345", "category": "other"},
    {"entity_type": "url", "entity_value": "not a url", "category": "other"},
    {"entity_type": "upi", "entity_value": "a.b@ybl", "category": "terrorist"},
    {"entity_type": "upi", "entity_value": "a.b@ybl", "category": "other", "incident_date": "2999-01-01"},
])
def test_entity_report_validation(user, body):
    assert user.post("/api/entity-reports", json=body).status_code == 400


def test_reports_feed_unified_risk(user, other_user):
    for c in (user, other_user):
        c.post("/api/entity-reports", json={"entity_type": "upi", "entity_value": "flagged@ybl", "category": "phishing"})
    t = user.post("/api/transactions", json=tx(counterparty_upi="flagged@ybl", amount=100)).json()
    assert t["risk"]["components"]["reputation"]["reports"] == 2


# ---------- alerts ----------

def test_high_risk_creates_alert_and_read(user):
    user.post("/api/transactions", json=tx(amount=181000, balance_before=181000, occurred_at=NOW.replace(hour=3).isoformat()))
    alerts = user.get("/api/alerts").json()
    assert alerts["unread"] >= 1 and alerts["items"][0]["title"] == "High-risk transaction detected"
    aid = alerts["items"][0]["id"]
    assert user.post(f"/api/alerts/{aid}/read").json()["read"] is True
    user.post("/api/alerts/read-all")
    assert user.get("/api/alerts").json()["unread"] == 0


# ---------- simulator, demo data, network ----------

@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_every_scenario_is_detected(client, scenario):
    r = client.post("/api/simulator/run", json={"scenario": scenario}).json()
    assert r["final_level"] in ("medium", "high"), (scenario, r["final_level"])
    assert r["detected"] and r["label"].startswith("SYNTHETIC")


def test_account_takeover_story(client):
    r = client.post("/api/simulator/run", json={"scenario": "account_takeover"}).json()
    codes = {d["code"] for d in r["detected"]}
    assert {"NEW_DEVICE", "RAPID_TRANSFER", "MODEL"} <= codes and r["final_level"] == "high"


def test_unknown_scenario(client):
    assert client.post("/api/simulator/run", json={"scenario": "nope"}).status_code == 400


def test_demo_data_network_and_removal(user):
    loaded = user.post("/api/demo/load").json()
    assert loaded["loaded"] > 50 and loaded["high_risk"] >= 1
    page = user.get("/api/transactions", params={"synthetic": True, "limit": 1}).json()
    assert page["total"] == loaded["loaded"]
    g = user.get("/api/network").json()
    assert g["stats"]["cycles"] >= 1 and g["clusters"]
    mule = next(n for n in g["nodes"] if n["id"] == "party:quickpay.mule01@axl")
    assert mule["suspicious"] and any("circular" in f for f in mule["flags"])
    devices = {n["id"]: n for n in g["nodes"] if n["kind"] == "device"}
    assert devices["device:iphone-x91"]["suspicious"]          # used only for the takeover
    assert not devices["device:android-7f3a"]["suspicious"]    # the user's everyday phone isn't accused
    ego = user.get("/api/network/entity/party:quickpay.mule01@axl").json()
    assert ego["center"] == "party:quickpay.mule01@axl" and len(ego["nodes"]) > 1
    assert user.get("/api/network/entity/party:nobody@ybl").status_code == 404
    assert user.delete("/api/demo").json()["removed"] == loaded["loaded"]


def test_stream_creates_synthetic_transaction(user):
    r = user.post("/api/simulator/stream/next").json()
    assert r["transaction"]["is_synthetic"] and r["transaction"]["source"] == "stream"


# ---------- account ----------

def test_settings_export_delete(user):
    user.post("/api/transactions", json=tx())
    s = user.patch("/api/account/settings", json={"ai_consent": True, "retention_days": 0}).json()
    assert s["settings"]["ai_consent"] is True
    exp = user.get("/api/account/export").json()
    assert len(exp["transactions"]) == 1 and "password_hash" not in str(exp)
    user.delete("/api/account/data")
    assert user.get("/api/transactions").json()["total"] == 0


def test_retention_purges_old_transactions(user):
    user.post("/api/transactions", json=tx(occurred_at="2020-01-01T10:00:00"))
    user.post("/api/transactions", json=tx(occurred_at=datetime.now().isoformat()))
    assert user.patch("/api/account/settings", json={"retention_days": 30}).json()["purged"] == 1
    assert user.get("/api/transactions").json()["total"] == 1


def test_delete_account_needs_password(user):
    assert user.request("DELETE", "/api/account", json={"password": "wrong"}).status_code == 401
    assert user.request("DELETE", "/api/account", json={"password": "correct horse battery"}).json()["ok"]
    assert user.get("/api/auth/me").status_code == 401


def test_model_monitoring(user):
    user.post("/api/transactions", json=tx())
    m = user.get("/api/model/monitoring").json()
    assert m["thresholds"]["high"] > m["thresholds"]["medium"]
    assert m["live"]["scored"] == 1 and sum(b["count"] for b in m["live"]["probability_histogram"]) == 1


# ---------- security ----------

def test_security_headers_and_limits(client):
    r = client.get("/api/model-info")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"
    big = client.post("/api/message/analyze", content=b"x" * 1_100_000, headers={"content-type": "application/json"})
    assert big.status_code == 413
    assert client.get("/api/does-not-exist").status_code == 404


def test_csp_matches_vercel_config():
    """The CSP served by FastAPI and the one in vercel.json must stay identical."""
    import json
    from pathlib import Path
    from app.main import CSP
    cfg = json.loads((Path(__file__).resolve().parents[2] / "vercel.json").read_text())
    headers = {h["key"]: h["value"] for block in cfg["headers"] for h in block["headers"]}
    assert headers["Content-Security-Policy"] == CSP


def test_cors_only_dev_origin(client):
    ok = client.options("/api/model-info", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    bad = client.options("/api/model-info", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in bad.headers


def test_never_asks_for_credentials():
    """No request schema anywhere accepts a PIN, OTP, CVV or bank password field."""
    spec = app.openapi()
    fields = set()
    for schema in spec["components"]["schemas"].values():
        fields |= {f.lower() for f in schema.get("properties", {})}
    assert not fields & {"pin", "upi_pin", "mpin", "otp", "cvv", "bank_password", "card_number"}


# ---------- batch save (multiple scanned screenshots) ----------

def test_batch_save_scores_and_skips_duplicates(user):
    items = [
        tx(external_id="512345678901", amount=500, counterparty_upi="chai@ybl"),
        tx(external_id="512345678902", direction="received", amount=300, balance_before=None,
           counterparty_upi="friend@okaxis"),
        tx(external_id="512345678901", amount=500),                      # repeated in the batch
        tx(amount=181000, balance_before=181000, occurred_at=NOW.replace(hour=3).isoformat()),  # no reference
    ]
    r = user.post("/api/transactions/batch", json={"items": items})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["saved"]) == 3 and [s["index"] for s in body["skipped"]] == [2]
    assert all(t["risk_level"] for t in body["saved"]) and body["high_risk"] == 1
    assert user.get("/api/alerts").json()["unread"] >= 1
    again = user.post("/api/transactions/batch", json={"items": items[:2]}).json()   # same screenshots again
    assert again["saved"] == [] and len(again["skipped"]) == 2
    assert user.get("/api/transactions").json()["total"] == 3


def test_batch_validation_and_auth(user):
    assert user.post("/api/transactions/batch", json={"items": []}).status_code == 400
    assert user.post("/api/transactions/batch", json={"items": [tx()] * 51}).status_code == 400
    assert user.post("/api/transactions/batch", json={"items": [tx(amount=-1)]}).status_code == 400
    assert TestClient(app).post("/api/transactions/batch", json={"items": [tx()]}).status_code == 401  # signed out


def test_adding_balance_rescores_with_the_model(user):
    t = user.post("/api/transactions", json=tx(amount=181000, balance_before=None,
                                               occurred_at=NOW.replace(hour=3).isoformat())).json()
    assert t["risk"]["components"]["model"]["available"] is False
    r = user.patch(f"/api/transactions/{t['id']}", json={"balance_before": 181000})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["balance_before"] == 181000 and body["review_status"] == "unreviewed"
    assert body["risk"]["components"]["model"]["available"] and body["risk_level"] == "high"
    assert user.patch(f"/api/transactions/{t['id']}", json={"balance_before": -5}).status_code == 400
