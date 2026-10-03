"""API behaviour: model info, sent-money scoring, received-money rules, validation errors."""

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def post(path, body):
    return client.post(path, json=body)


def test_model_info():
    r = client.get("/api/model-info")
    assert r.status_code == 200
    info = r.json()
    assert {"dataset", "split", "thresholds", "metrics_test", "samples"} <= info.keys()
    assert len(info["samples"]["legit"]) == 5 and len(info["samples"]["fraud"]) == 5


@pytest.mark.parametrize("kind,expected", [("legit", "low"), ("fraud", "high")])
def test_sample_transactions_score_as_labelled(kind, expected):
    for s in client.get("/api/model-info").json()["samples"][kind]:
        r = post("/api/predict", {
            "type": s["type"], "amount": s["amount"], "hour": s["step"] % 24,
            "sender_balance_before": s["oldbalanceOrg"], "sender_balance_after": s["newbalanceOrig"],
            "receiver_balance_before": s["oldbalanceDest"], "receiver_balance_after": s["newbalanceDest"],
        })
        assert r.status_code == 200
        body = r.json()
        assert body["risk"] == expected
        assert body["method"] == "model" and body["used_receiver_balances"] is True
        assert 1 <= len(body["reasons"]) <= 4


def test_emptying_account_at_night_is_high_risk():
    r = post("/api/predict", {"type": "TRANSFER", "amount": 181000, "hour": 3, "sender_balance_before": 181000})
    body = r.json()
    assert body["risk"] == "high" and body["probability"] > 0.9
    assert body["used_receiver_balances"] is False
    assert any("entire balance" in x["text"] for x in body["reasons"])


def test_amount_above_balance_is_rejected():
    r = post("/api/predict", {"type": "TRANSFER", "amount": 5000, "hour": 10, "sender_balance_before": 100})
    assert r.status_code == 400
    assert "balance" in r.json()["detail"]


def test_invalid_type_message():
    r = post("/api/predict", {"type": "PAYMENT", "amount": 10, "hour": 10, "sender_balance_before": 100})
    assert r.status_code == 400
    assert r.json()["detail"] == "Payment type must be a transfer or a cash withdrawal."


RECEIVED = {"amount": 300, "hour": 14, "knows_sender": "yes", "in_bank": "yes", "asked_to_pay": "no"}


@pytest.mark.parametrize("changes,expected", [
    ({}, "low"),
    ({"knows_sender": "no"}, "medium"),
    ({"knows_sender": "unsure"}, "medium"),
    ({"in_bank": "unsure"}, "medium"),
    ({"knows_sender": "no", "amount": 75000}, "high"),
    ({"asked_to_pay": "yes"}, "high"),
    ({"in_bank": "no"}, "high"),
])
def test_received_rules(changes, expected):
    r = post("/api/check-received", {**RECEIVED, **changes})
    assert r.status_code == 200
    body = r.json()
    assert body["risk"] == expected
    assert body["probability"] is None and body["method"] == "rules"


def test_received_rejects_unknown_answer():
    r = post("/api/check-received", {**RECEIVED, "knows_sender": "maybe"})
    assert r.status_code == 400
    assert r.json()["detail"].startswith("Do you know the sender")


def test_vercel_entrypoint_exposes_the_app():
    """api/index.py is what Vercel runs; it must import the same FastAPI app."""
    path = Path(__file__).resolve().parents[2] / "api" / "index.py"
    spec = importlib.util.spec_from_file_location("vercel_index", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    routes = {r.path for r in module.app.routes}
    assert {"/api/predict", "/api/check-received", "/api/model-info"} <= routes
