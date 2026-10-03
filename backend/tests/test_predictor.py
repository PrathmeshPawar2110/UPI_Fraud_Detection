"""The pure-Python predictor must match LightGBM exactly: probabilities and SHAP contributions."""

import json
import math
import random
from pathlib import Path

import pytest

lgb = pytest.importorskip("lightgbm")
np = pytest.importorskip("numpy")

from app.predictor import Model  # noqa: E402

MODEL_DIR = Path(__file__).resolve().parents[1] / "app" / "model"
NAN = float("nan")


@pytest.fixture(scope="module")
def models():
    return Model(MODEL_DIR / "trees.json"), lgb.Booster(model_file=str(MODEL_DIR / "fraud_model.txt"))


def feature_row(amount, before, after, dest_before=NAN, dest_after=NAN, hour=12, transfer=1):
    """Same feature definitions as train_model.build_features / fraud.build_row."""
    return [transfer, amount, hour, before, after, amount / (before + 1.0),
            int(after == 0 and before > 0), dest_before, dest_after, dest_before + amount - dest_after]


def rows():
    meta = json.loads((MODEL_DIR / "meta.json").read_text(encoding="utf-8"))
    out = []
    for s in meta["samples"]["legit"] + meta["samples"]["fraud"]:
        args = (s["amount"], s["oldbalanceOrg"], s["newbalanceOrig"])
        common = dict(hour=s["step"] % 24, transfer=int(s["type"] == "TRANSFER"))
        out.append(feature_row(*args, s["oldbalanceDest"], s["newbalanceDest"], **common))
        out.append(feature_row(*args, **common))  # receiver balances unknown
    rng = random.Random(0)
    for _ in range(300):
        before = rng.choice([0.0, rng.uniform(1, 5e5), rng.uniform(1, 1e7)])
        amount = rng.uniform(0.01, before) if before and rng.random() < 0.8 else before
        after = max(before - amount, 0.0)
        if rng.random() < 0.5:
            db = rng.choice([0.0, rng.uniform(0, 1e6)])
            da = rng.choice([db, db + amount, 0.0, rng.uniform(0, 2e6)])
        else:
            db = da = NAN
        out.append(feature_row(amount, before, after, db, da, rng.randrange(24), rng.randrange(2)))
    return out


def test_probability_matches_lightgbm(models):
    ours, ref = models
    X = rows()
    expected = ref.predict(np.array(X, dtype=float))
    for x, e in zip(X, expected):
        assert ours.predict(x) == pytest.approx(e, abs=1e-12)


def test_shap_contributions_match_lightgbm(models):
    ours, ref = models
    X = rows()
    expected = ref.predict(np.array(X, dtype=float), pred_contrib=True)
    for x, e in zip(X, expected):
        assert ours.contributions(x) == pytest.approx(list(e), abs=1e-9)


def test_contributions_sum_to_raw_score(models):
    ours, _ = models
    for x in rows()[:50]:
        assert sum(ours.contributions(x)) == pytest.approx(ours.raw(x), abs=1e-9)
        assert ours.predict(x) == pytest.approx(1 / (1 + math.exp(-ours.raw(x))))
