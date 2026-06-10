# -*- coding: utf-8 -*-
"""oissyntheticdata._tree — a small CART grown from scratch (no numpy/sklearn).

Each leaf keeps the list of REAL target values that reached it ("donors").
Synthesis samples from a leaf's donors rather than predicting a point value,
which reproduces the conditional distribution (Reiter, 2005). A minimum leaf
size (`min_leaf`) guarantees every donor pool blends >= k real records, so a
synthetic value is never traceable to one individual.
"""

import math
import random

MAX_THRESHOLDS = 40   # cap numeric split candidates for speed


def _gini(counts, n):
    if n == 0:
        return 0.0
    s = 0.0
    for c in counts.values():
        p = c / n
        s += p * p
    return 1.0 - s


def _sse(values):
    n = len(values)
    if n == 0:
        return 0.0
    m = sum(values) / n
    return sum((v - m) ** 2 for v in values)


def _candidate_thresholds(vals):
    uniq = sorted(set(vals))
    if len(uniq) <= 1:
        return []
    if len(uniq) <= MAX_THRESHOLDS:
        cuts = uniq
    else:
        step = len(uniq) / float(MAX_THRESHOLDS)
        cuts = [uniq[int(i * step)] for i in range(1, MAX_THRESHOLDS)]
    mids = []
    for i in range(1, len(cuts)):
        mids.append((cuts[i - 1] + cuts[i]) / 2.0)
    return mids


class _Node(object):
    __slots__ = ("leaf", "donors", "feature", "kind", "threshold", "category",
                 "left", "right")

    def __init__(self):
        self.leaf = False
        self.donors = None
        self.feature = None
        self.kind = None          # 'num' or 'cat'
        self.threshold = None
        self.category = None
        self.left = None
        self.right = None


def _impurity(idx, y, target_kind):
    if target_kind == "cat":
        counts = {}
        for i in idx:
            counts[y[i]] = counts.get(y[i], 0) + 1
        return _gini(counts, len(idx)) * len(idx)
    else:
        return _sse([y[i] for i in idx])


def build_tree(idx, y, predictors, num_cols, target_kind,
               min_leaf=5, max_depth=12, depth=0):
    """idx: row indices; y: target list; predictors: list of feature names;
    num_cols: dict name->bool (True if numeric predictor)."""
    node = _Node()
    distinct_y = set(y[i] for i in idx)
    if (len(idx) < 2 * min_leaf or depth >= max_depth or len(distinct_y) <= 1
            or not predictors):
        node.leaf = True
        node.donors = [y[i] for i in idx]
        return node

    base = _impurity(idx, y, target_kind)
    best = None  # (reduction, feature, kind, thr/cat, left_idx, right_idx)

    for f in predictors:
        is_num = num_cols[f]
        if is_num:
            colvals = [PRED[f][i] for i in idx]
            present = [v for v in colvals if v is not None]
            for thr in _candidate_thresholds(present):
                left = [i for i in idx if PRED[f][i] is not None and PRED[f][i] <= thr]
                right = [i for i in idx if not (PRED[f][i] is not None and PRED[f][i] <= thr)]
                if len(left) < min_leaf or len(right) < min_leaf:
                    continue
                red = base - _impurity(left, y, target_kind) - _impurity(right, y, target_kind)
                if best is None or red > best[0]:
                    best = (red, f, "num", thr, left, right)
        else:
            cats = set(PRED[f][i] for i in idx)
            if len(cats) <= 1:
                continue
            for c in cats:
                left = [i for i in idx if PRED[f][i] == c]
                right = [i for i in idx if PRED[f][i] != c]
                if len(left) < min_leaf or len(right) < min_leaf:
                    continue
                red = base - _impurity(left, y, target_kind) - _impurity(right, y, target_kind)
                if best is None or red > best[0]:
                    best = (red, f, "cat", c, left, right)

    if best is None or best[0] <= 1e-12:
        node.leaf = True
        node.donors = [y[i] for i in idx]
        return node

    _, f, kind, val, left_idx, right_idx = best
    node.feature, node.kind = f, kind
    if kind == "num":
        node.threshold = val
    else:
        node.category = val
    node.left = build_tree(left_idx, y, predictors, num_cols, target_kind,
                           min_leaf, max_depth, depth + 1)
    node.right = build_tree(right_idx, y, predictors, num_cols, target_kind,
                            min_leaf, max_depth, depth + 1)
    return node


# PRED is module-level so the recursive builder can read predictor columns by
# row index without copying. set_predictors() installs it for one fit.
PRED = {}


def set_predictors(pred_cols):
    global PRED
    PRED = pred_cols


def sample_leaf(node, row, num_cols, rng, smoothing=0.0):
    """Route a synthetic row (dict feature->value) to a leaf and draw a donor."""
    while not node.leaf:
        if node.kind == "num":
            v = row.get(node.feature)
            go_left = (v is not None and v <= node.threshold)
        else:
            go_left = (row.get(node.feature) == node.category)
        node = node.left if go_left else node.right
    donors = node.donors
    val = rng.choice(donors)
    if smoothing and val is not None and isinstance(val, float):
        nums = [d for d in donors if isinstance(d, float)]
        if len(nums) > 2:
            m = sum(nums) / len(nums)
            sd = math.sqrt(sum((x - m) ** 2 for x in nums) / len(nums))
            if sd > 0:
                lo, hi = min(nums), max(nums)
                val = min(hi, max(lo, val + rng.gauss(0.0, smoothing * sd)))
    return val
