"""Pattern detectors and the unified risk engine."""

from datetime import datetime, timedelta

import pytest

from app.engine import patterns as P
from app.engine.risk import HIGH, MEDIUM, assess, calibrate_model, level_of, noisy_or
from app.engine.simulator import SimTx
from app.fraud import T_HIGH, T_MED, score as model_score
from app.schemas import Transaction as ModelInput

T0 = datetime(2026, 9, 1, 12, 0)


def tx(i, minutes, amount, vpa="shop@ybl", direction="sent", before=None, device=None, answers=None):
    return SimTx(i, T0 + timedelta(minutes=minutes), direction, float(amount), vpa.split("@")[0], vpa,
                 balance_before=before, balance_after=None if before is None else max(before - amount, 0),
                 device_id=device, received_answers=answers)


def history(n=12, amount=500, hour_step=60 * 24):
    """n ordinary daytime payments, one per day, to a few known payees."""
    return [tx(i + 1, i * hour_step, amount + 10 * (i % 4), f"known{i % 3}@ybl", device="home") for i in range(n)]


def codes(found):
    return {p.code for p in found}


# ---------- patterns ----------

def test_rapid_transfer_needs_three_outgoing_within_five_minutes():
    h = history()
    base = h[-1].occurred_at + timedelta(days=1)
    burst = [SimTx(100 + k, base + timedelta(minutes=k), "sent", 30_000.0, "x", "mule@axl") for k in range(3)]
    assert "RAPID_TRANSFER" in codes(P.detect(burst[2], h + burst))
    assert "RAPID_TRANSFER" not in codes(P.detect(burst[1], h + burst))  # only 2 so far
    spread = [SimTx(200 + k, base + timedelta(minutes=10 * k), "sent", 300.0, "x", "a@ybl") for k in range(3)]
    assert "RAPID_TRANSFER" not in codes(P.detect(spread[2], h + spread))


def test_rapid_transfer_severity_grows_with_total():
    h = history()
    base = h[-1].occurred_at + timedelta(days=1)
    burst = [SimTx(100 + k, base + timedelta(minutes=k), "sent", 30_000.0, "x", "mule@axl") for k in range(3)]
    p = next(p for p in P.detect(burst[2], h + burst) if p.code == "RAPID_TRANSFER")
    assert p.severity == "high" and p.evidence["total"] == 90_000


def test_burst_of_six_in_an_hour_without_rapid_transfer():
    h = history()
    base = h[-1].occurred_at + timedelta(days=1)
    six = [SimTx(300 + k, base + timedelta(minutes=11 * k), "sent", 100.0, "x", f"p{k}@ybl") for k in range(6)]
    found = codes(P.detect(six[-1], h + six))
    assert "TRANSACTION_BURST" in found and "RAPID_TRANSFER" not in found


def test_balance_depletion_at_90_percent():
    t = tx(50, 99999, 92_000, before=100_000)
    assert "BALANCE_DEPLETION" in codes(P.detect(t, []))
    assert "BALANCE_DEPLETION" not in codes(P.detect(tx(51, 99999, 50_000, before=100_000), []))


def test_new_recipient_requires_history():
    t = tx(60, 99999, 500, "brandnew@ybl")
    assert "NEW_RECIPIENT" not in codes(P.detect(t, history(3)))  # too little history to know
    assert "NEW_RECIPIENT" in codes(P.detect(t, history(6)))
    assert "NEW_RECIPIENT" not in codes(P.detect(tx(61, 99999, 500, "known1@ybl"), history(6)))


def test_unusual_amount_against_own_baseline():
    big = tx(70, 99999, 82_000, "known1@ybl")
    p = next(p for p in P.detect(big, history(12)) if p.code == "UNUSUAL_AMOUNT")
    assert p.evidence["median"] < 600 and "your median" in p.detail
    assert "UNUSUAL_AMOUNT" not in codes(P.detect(tx(71, 99999, 560, "known1@ybl"), history(12)))
    assert "UNUSUAL_AMOUNT" not in codes(P.detect(big, history(5)))  # not enough baseline


def test_unusual_hour_only_late_night_and_rare():
    h = history(12)  # all at 12:00
    night = SimTx(80, h[-1].occurred_at.replace(hour=2) + timedelta(days=1), "sent", 500.0, "k", "known1@ybl")
    assert "UNUSUAL_HOUR" in codes(P.detect(night, h))
    noon = SimTx(81, h[-1].occurred_at + timedelta(days=1), "sent", 500.0, "k", "known1@ybl")
    assert "UNUSUAL_HOUR" not in codes(P.detect(noon, h))


def test_recipient_concentration_three_payments_to_new_payee_in_a_day():
    h = history(8)
    base = h[-1].occurred_at + timedelta(days=1)
    pays = [SimTx(90 + k, base + timedelta(hours=3 * k), "sent", 10_000.0, "Desk", "desk@ibl") for k in range(3)]
    assert "RECIPIENT_CONCENTRATION" in codes(P.detect(pays[2], h + pays))
    # a long-known payee doesn't count
    known = [SimTx(95 + k, base + timedelta(hours=k), "sent", 500.0, "k", "known0@ybl") for k in range(3)]
    assert "RECIPIENT_CONCENTRATION" not in codes(P.detect(known[2], h + known))


def test_refund_loop_paying_back_a_recent_sender():
    rx = SimTx(100, T0, "received", 5000.0, "Unknown", "stranger@okaxis")
    back = SimTx(101, T0 + timedelta(hours=2), "sent", 5000.0, "Unknown", "stranger@okaxis")
    assert "REFUND_LOOP" in codes(P.detect(back, [rx]))
    later = SimTx(102, T0 + timedelta(days=5), "sent", 5000.0, "Unknown", "stranger@okaxis")
    assert "REFUND_LOOP" not in codes(P.detect(later, [rx]))


def test_new_device_and_large_amount():
    h = history(5)
    t = tx(110, 99999, 150_000, "known1@ybl", device="iphone-x91")
    found = codes(P.detect(t, h))
    assert {"NEW_DEVICE", "LARGE_AMOUNT"} <= found


def test_future_transactions_are_ignored():
    """Detectors look only backwards in time."""
    t = tx(1, 0, 500, "first@ybl")
    later = [tx(i, 10 + i, 500, f"x{i}@ybl") for i in range(2, 12)]
    assert P.prior_of(t, later) == []


# ---------- unified risk ----------

def test_noisy_or_properties():
    assert noisy_or([]) == 0
    assert noisy_or([0.7]) == pytest.approx(0.7)
    assert noisy_or([0.5, 0.5]) == pytest.approx(0.75)
    s = [0.3, 0.2, 0.6]
    assert noisy_or(s) >= max(s)


def test_model_calibration_keeps_its_thresholds():
    assert calibrate_model(T_MED) == pytest.approx(MEDIUM)
    assert calibrate_model(T_HIGH) == pytest.approx(HIGH)
    assert calibrate_model(0) == 0 and calibrate_model(1) == pytest.approx(1)
    for p in (0.0, 0.01, T_MED - 1e-6, T_MED, 0.2, T_HIGH, 0.9, 1.0):
        band = "high" if p >= T_HIGH else "medium" if p >= T_MED else "low"
        assert level_of(calibrate_model(p)) == band


@pytest.mark.parametrize("amount,before,hour", [(181_000, 181_000, 3), (5_000, 40_000, 14), (9_000, 10_000, 1)])
def test_model_only_level_matches_original_predict(amount, before, hour):
    """Backward compatibility: with no history, the unified level equals /api/predict's level."""
    t = SimTx(1, T0.replace(hour=hour), "sent", float(amount), "x", "x@ybl", before, max(before - amount, 0))
    r = assess(t, [])
    original = model_score(ModelInput(type="TRANSFER", amount=amount, hour=hour, sender_balance_before=before))
    assert r["level"] == original["risk"]
    assert r["components"]["model"]["probability"] == pytest.approx(original["probability"])


def test_breakdown_sums_to_score_and_never_below_strongest_component():
    h = history(12)
    base = h[-1].occurred_at.replace(hour=0, minute=48) + timedelta(days=1)
    burst = [SimTx(200 + k, base + timedelta(minutes=k), "sent", 30_000.0, "Mule", "mule@axl",
                   balance_before=100_000 - 30_000 * k, balance_after=70_000 - 30_000 * k, device_id="new")
             for k in range(3)]
    r = assess(burst[2], h + burst)
    assert sum(b["points"] for b in r["breakdown"]) == pytest.approx(r["score"] * 100, abs=0.5)
    comps = [r["components"]["model"]["score"], r["components"]["patterns"]["score"]]
    assert r["score"] >= max(comps) - 1e-9
    assert r["level"] == "high"


def test_balance_depletion_not_double_counted_with_model():
    t = SimTx(1, T0, "sent", 95_000.0, "x", "x@ybl", 100_000.0, 5_000.0)
    r = assess(t, [])
    dep = next(p for p in r["components"]["patterns"]["items"] if p["code"] == "BALANCE_DEPLETION")
    assert dep["informational"] is True
    assert all(b["label"] != "Possible balance depletion" for b in r["breakdown"])


def test_received_money_uses_rules_when_answered():
    t = SimTx(1, T0, "received", 5000.0, "x", "x@ybl", received_answers={"knows_sender": "no", "in_bank": "no", "asked_to_pay": "no"})
    r = assess(t, [])
    assert r["components"]["rules"]["available"] and r["level"] == "high"
    t2 = SimTx(2, T0, "received", 5000.0, "x", "x@ybl")
    r2 = assess(t2, [])
    assert not r2["components"]["rules"]["available"] and r2["level"] == "low"
    assert any("three received-money questions" in n for n in r2["notes"])


def test_reputation_alone_never_reaches_high():
    t = SimTx(1, T0, "sent", 100.0, "x", "x@ybl")
    assert assess(t, [], distinct_reporters=10)["level"] == "medium"
    assert assess(t, [], distinct_reporters=1)["level"] == "low"


def test_history_cannot_suppress_a_serious_signal():
    """Many legitimate payments to the same payee don't lower a high model score."""
    h = [SimTx(i, T0 - timedelta(days=i), "sent", 500.0, "x", "x@ybl", 50_000.0, 49_500.0) for i in range(1, 30)]
    t = SimTx(100, T0.replace(hour=3), "sent", 181_000.0, "x", "x@ybl", 181_000.0, 0.0)
    assert assess(t, h)["level"] == "high"
