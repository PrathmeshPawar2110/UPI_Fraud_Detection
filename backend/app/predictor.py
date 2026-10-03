"""Pure-Python inference for the exported LightGBM model (no lightgbm / numpy / scipy at runtime).

LightGBM is used for training only. `train_model.py` exports the trees to `model/trees.json`, and this
module reproduces LightGBM's prediction and its `pred_contrib=True` SHAP values exactly:
- `NumericalDecision` from LightGBM's tree.h (missing-value handling included), and
- `TreeSHAP` / `ExtendPath` / `UnwindPath` / `UnwoundPathSum` from LightGBM's tree.cpp
  (Lundberg et al. 2018, "Consistent Individualized Feature Attribution for Tree Ensembles").
tests/test_predictor.py checks both against LightGBM itself.

Keeping the deployed function free of lightgbm, numpy and scipy keeps it a few MB instead of ~190 MB,
and avoids LightGBM's dependency on the system OpenMP library (libgomp) on serverless hosts.
"""

import json
import math
from pathlib import Path

MISSING_NONE, MISSING_ZERO, MISSING_NAN = 0, 1, 2
K_ZERO_THRESHOLD = 1e-35  # LightGBM's kZeroThreshold


class Model:
    def __init__(self, path: Path):
        data = json.loads(Path(path).read_text())
        self.features = data["features"]
        self.trees = data["trees"]
        self.expected = sum(_expected_value(t) for t in self.trees)

    # ---------- prediction ----------

    def raw(self, x: list[float]) -> float:
        total = 0.0
        for node in self.trees:
            while "v" not in node:
                node = node["l"] if _goes_left(node, x[node["f"]]) else node["r"]
            total += node["v"]
        return total

    def predict(self, x: list[float]) -> float:
        """Fraud probability (LightGBM objective `binary sigmoid:1`)."""
        return 1.0 / (1.0 + math.exp(-self.raw(x)))

    # ---------- SHAP contributions ----------

    def contributions(self, x: list[float]) -> list[float]:
        """Per-feature contributions in log-odds, plus the expected value last (like pred_contrib=True)."""
        phi = [0.0] * (len(self.features) + 1)
        for tree in self.trees:
            if "v" not in tree:
                _tree_shap(tree, x, phi, [], 1.0, 1.0, -1)
        phi[-1] = self.expected
        return phi


def _goes_left(node: dict, fval: float) -> bool:
    missing = node["m"]
    if math.isnan(fval) and missing != MISSING_NAN:
        fval = 0.0
    if (missing == MISSING_ZERO and abs(fval) <= K_ZERO_THRESHOLD) or (missing == MISSING_NAN and math.isnan(fval)):
        return node["d"]
    return fval <= node["t"]


def _expected_value(tree: dict) -> float:
    if "v" in tree:
        return tree["v"]
    total = tree["c"]
    acc = 0.0
    stack = [tree]
    while stack:
        n = stack.pop()
        if "v" in n:
            acc += n["c"] / total * n["v"]
        else:
            stack += [n["l"], n["r"]]
    return acc


# A path element is [feature_index, zero_fraction, one_fraction, pweight].

def _extend(path, zero_fraction, one_fraction, feature_index):
    depth = len(path)
    path.append([feature_index, zero_fraction, one_fraction, 1.0 if depth == 0 else 0.0])
    for i in range(depth - 1, -1, -1):
        path[i + 1][3] += one_fraction * path[i][3] * (i + 1) / (depth + 1)
        path[i][3] = zero_fraction * path[i][3] * (depth - i) / (depth + 1)


def _unwind(path, index):
    depth = len(path) - 1
    one_fraction, zero_fraction = path[index][2], path[index][1]
    next_one = path[depth][3]
    for i in range(depth - 1, -1, -1):
        if one_fraction != 0:
            tmp = path[i][3]
            path[i][3] = next_one * (depth + 1) / ((i + 1) * one_fraction)
            next_one = tmp - path[i][3] * zero_fraction * (depth - i) / (depth + 1)
        else:
            path[i][3] = path[i][3] * (depth + 1) / (zero_fraction * (depth - i))
    for i in range(index, depth):
        path[i][0], path[i][1], path[i][2] = path[i + 1][0], path[i + 1][1], path[i + 1][2]
    path.pop()


def _unwound_sum(path, index):
    depth = len(path) - 1
    one_fraction, zero_fraction = path[index][2], path[index][1]
    next_one = path[depth][3]
    total = 0.0
    for i in range(depth - 1, -1, -1):
        if one_fraction != 0:
            tmp = next_one * (depth + 1) / ((i + 1) * one_fraction)
            total += tmp
            next_one = path[i][3] - tmp * zero_fraction * ((depth - i) / (depth + 1))
        elif zero_fraction != 0:
            total += (path[i][3] / zero_fraction) / ((depth - i) / (depth + 1))
    return total


def _tree_shap(node, x, phi, parent_path, zero_fraction, one_fraction, feature_index):
    path = [el[:] for el in parent_path]
    _extend(path, zero_fraction, one_fraction, feature_index)

    if "v" in node:
        for i in range(1, len(path)):
            w = _unwound_sum(path, i)
            phi[path[i][0]] += w * (path[i][2] - path[i][1]) * node["v"]
        return

    hot, cold = (node["l"], node["r"]) if _goes_left(node, x[node["f"]]) else (node["r"], node["l"])
    hot_zero = hot["c"] / node["c"]
    cold_zero = cold["c"] / node["c"]
    incoming_zero = incoming_one = 1.0
    # if this feature was already split on above, undo that split's entry first
    for k in range(len(path)):
        if path[k][0] == node["f"]:
            incoming_zero, incoming_one = path[k][1], path[k][2]
            _unwind(path, k)
            break
    _tree_shap(hot, x, phi, path, hot_zero * incoming_zero, incoming_one, node["f"])
    _tree_shap(cold, x, phi, path, cold_zero * incoming_zero, 0.0, node["f"])
