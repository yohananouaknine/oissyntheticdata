# -*- coding: utf-8 -*-
"""oissyntheticdata._tree — a small CART (Classification And Regression Tree)
grown from scratch, using only the Python standard library (no numpy/sklearn).

Why a tree, and how it is used for synthesis
--------------------------------------------
To synthesize a column ``Y`` from the columns already synthesized, we grow a tree
that recursively partitions the real rows into groups ("leaves") that are as
homogeneous as possible in ``Y``. Each leaf keeps the *list of real ``Y`` values
that reached it* — its "donors". Synthesis then routes a synthetic row to the
matching leaf and draws one donor at random (see :func:`sample_leaf`). Drawing a
donor — rather than predicting a single point value — is what reproduces the
*conditional distribution* of ``Y`` given the predictors (Reiter, 2005).

Two confidentiality properties fall directly out of the construction:
  * ``min_leaf`` (k): a node is never split in a way that leaves fewer than k real
    records on either side, so every donor pool blends at least k individuals and
    no synthetic value can be traced to one person. It also bounds how deep, and
    therefore how specific, the tree can get.

The implementation is deliberately small and explicit so that a data owner can
read it in full before letting it touch confidential records. There is no hidden
state: every function takes its inputs as arguments and returns its result.

Data representation
-------------------
Rows are referred to by integer index. ``y`` is the full target list; ``idx`` is
the list of row indices currently under consideration. Predictor columns are
passed in ``pred`` as ``{feature_name: [value_per_row]}`` aligned to ``y``.
Numeric predictors hold floats (missing -> ``None``); categorical predictors hold
strings. ``num_cols[name]`` is True for numeric predictors, False for categorical.
"""

import math
import random

# Cap how many candidate split points we try on a numeric predictor. Trees are
# insensitive to the exact threshold between two observed values, so evaluating
# every distinct value is wasteful on high-cardinality columns; ~40 quantile
# points give effectively the same splits far more cheaply.
MAX_THRESHOLDS = 40


def _gini(counts, n):
    """Gini impurity of a categorical target from a {value: count} dict.

    Gini = 1 - sum(p_i^2). It is 0 when all rows share one value (pure) and grows
    as the values become more mixed. Used to score candidate splits for
    categorical targets.
    """
    if n == 0:
        return 0.0
    sum_sq = 0.0
    for c in counts.values():
        p = c / n
        sum_sq += p * p
    return 1.0 - sum_sq


def _sse(values):
    """Sum of squared errors of a numeric target around its mean.

    SSE = sum((v - mean)^2). It is the regression analogue of Gini: 0 when all
    values are identical, larger when they are more spread out.
    """
    n = len(values)
    if n == 0:
        return 0.0
    mean = sum(values) / n
    return sum((v - mean) ** 2 for v in values)


def _impurity(idx, y, target_kind):
    """Total (not average) impurity of the rows ``idx`` for target ``y``.

    Returning the total — Gini weighted by group size, or raw SSE — lets us
    compare a parent's impurity directly against the sum of its two children's,
    so the "impurity reduction" of a split is just parent - (left + right).
    """
    if target_kind == "cat":
        counts = {}
        for i in idx:
            counts[y[i]] = counts.get(y[i], 0) + 1
        return _gini(counts, len(idx)) * len(idx)
    else:
        return _sse([y[i] for i in idx])


def _candidate_thresholds(values):
    """Midpoints between sorted distinct numeric values, capped at MAX_THRESHOLDS.

    A numeric split "x <= t" only ever needs t to sit between two observed
    values, so we test midpoints of adjacent distinct values. On high-cardinality
    columns we sub-sample those distinct values to at most MAX_THRESHOLDS first.
    """
    distinct = sorted(set(values))
    if len(distinct) <= 1:
        return []
    if len(distinct) > MAX_THRESHOLDS:
        step = len(distinct) / float(MAX_THRESHOLDS)
        distinct = [distinct[int(i * step)] for i in range(1, MAX_THRESHOLDS)]
    return [(distinct[i - 1] + distinct[i]) / 2.0 for i in range(1, len(distinct))]


class _Node(object):
    """A single tree node.

    A *leaf* carries ``donors`` (the real target values that reached it). An
    *internal* node carries a split: ``feature`` is the predictor name, ``kind``
    is 'num' or 'cat', and the test is "value <= ``threshold``" (numeric) or
    "value == ``category``" (categorical). ``left`` holds rows passing the test.
    """

    __slots__ = ("leaf", "donors", "feature", "kind", "threshold", "category",
                 "left", "right")

    def __init__(self):
        self.leaf = False
        self.donors = None
        self.feature = None
        self.kind = None          # 'num' or 'cat'
        self.threshold = None     # numeric split point
        self.category = None      # categorical split value
        self.left = None
        self.right = None


def _best_split(idx, y, predictors, pred, num_cols, target_kind, min_leaf):
    """Find the split that most reduces impurity, or None if no valid split.

    A split is valid only if BOTH sides keep at least ``min_leaf`` real records;
    that single rule is what enforces the k-record confidentiality floor. We scan
    every predictor: numeric predictors are tried at each candidate threshold,
    categorical predictors at each "== value" partition, and we keep the split
    with the largest impurity reduction.

    Returns ``(reduction, feature, kind, value, left_idx, right_idx)`` or None.
    """
    base = _impurity(idx, y, target_kind)
    best = None
    for f in predictors:
        if num_cols[f]:
            present = [pred[f][i] for i in idx if pred[f][i] is not None]
            for thr in _candidate_thresholds(present):
                left = [i for i in idx if pred[f][i] is not None and pred[f][i] <= thr]
                right = [i for i in idx if not (pred[f][i] is not None and pred[f][i] <= thr)]
                if len(left) < min_leaf or len(right) < min_leaf:
                    continue
                reduction = base - _impurity(left, y, target_kind) - _impurity(right, y, target_kind)
                if best is None or reduction > best[0]:
                    best = (reduction, f, "num", thr, left, right)
        else:
            for c in set(pred[f][i] for i in idx):
                left = [i for i in idx if pred[f][i] == c]
                right = [i for i in idx if pred[f][i] != c]
                if len(left) < min_leaf or len(right) < min_leaf:
                    continue
                reduction = base - _impurity(left, y, target_kind) - _impurity(right, y, target_kind)
                if best is None or reduction > best[0]:
                    best = (reduction, f, "cat", c, left, right)
    return best


def build_tree(idx, y, predictors, pred, num_cols, target_kind,
               min_leaf=5, max_depth=12, depth=0):
    """Recursively grow a CART and return its root :class:`_Node`.

    Parameters
    ----------
    idx         : row indices currently under consideration
    y           : full target list (indexed by the values in ``idx``)
    predictors  : predictor feature names available for splitting
    pred        : {feature: [value_per_row]} predictor columns aligned to ``y``
    num_cols    : {feature: bool} True for numeric predictors
    target_kind : 'cat' (classification/Gini) or 'num' (regression/SSE)
    min_leaf    : minimum real records per leaf (the confidentiality floor, k)
    max_depth   : hard cap on tree depth

    A node becomes a leaf when it is too small to split (< 2*min_leaf rows),
    has reached ``max_depth``, is already pure (one distinct target value), has
    no predictors, or when no split both reduces impurity and respects the
    ``min_leaf`` floor on each side. A leaf stores its rows' real target values
    as donors for sampling.
    """
    node = _Node()

    # --- stopping rules: make this a leaf and keep its donors ---
    too_small = len(idx) < 2 * min_leaf
    pure = len(set(y[i] for i in idx)) <= 1
    if too_small or depth >= max_depth or pure or not predictors:
        node.leaf = True
        node.donors = [y[i] for i in idx]
        return node

    # --- otherwise, pick the best valid split ---
    best = _best_split(idx, y, predictors, pred, num_cols, target_kind, min_leaf)
    if best is None or best[0] <= 1e-12:        # no split helps -> leaf
        node.leaf = True
        node.donors = [y[i] for i in idx]
        return node

    _, feature, kind, value, left_idx, right_idx = best
    node.feature, node.kind = feature, kind
    if kind == "num":
        node.threshold = value
    else:
        node.category = value

    # --- recurse into both sides ---
    node.left = build_tree(left_idx, y, predictors, pred, num_cols, target_kind,
                           min_leaf, max_depth, depth + 1)
    node.right = build_tree(right_idx, y, predictors, pred, num_cols, target_kind,
                            min_leaf, max_depth, depth + 1)
    return node


def sample_leaf(node, row, num_cols, rng, smoothing=0.0):
    """Route a synthetic ``row`` ({feature: value}) to its leaf and draw a donor.

    We walk from the root, applying each node's test to the row's already-
    synthesized predictor values, until we reach a leaf, then sample one of its
    real donor values uniformly at random.

    If ``smoothing`` > 0 and the drawn value is a float, we add bounded Gaussian
    noise (scaled by the leaf's own spread and clipped to the leaf's range) so the
    output is not an exact copy of a real value, while staying within the observed
    support. Categorical donors are never altered.
    """
    while not node.leaf:
        if node.kind == "num":
            v = row.get(node.feature)
            go_left = (v is not None and v <= node.threshold)
        else:
            go_left = (row.get(node.feature) == node.category)
        node = node.left if go_left else node.right

    donors = node.donors
    value = rng.choice(donors)

    if smoothing and value is not None and isinstance(value, float):
        numeric_donors = [d for d in donors if isinstance(d, float)]
        if len(numeric_donors) > 2:
            mean = sum(numeric_donors) / len(numeric_donors)
            sd = math.sqrt(sum((x - mean) ** 2 for x in numeric_donors) / len(numeric_donors))
            if sd > 0:
                low, high = min(numeric_donors), max(numeric_donors)
                value = min(high, max(low, value + rng.gauss(0.0, smoothing * sd)))
    return value
