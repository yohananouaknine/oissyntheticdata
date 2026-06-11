# -*- coding: utf-8 -*-
"""oissyntheticdata._synth — sequential CART synthesis (the synthpop paradigm).

Columns are synthesized one at a time in `visit` order. The first column is
drawn from its own (disclosure-controlled) marginal. Each later column is
synthesized by growing a CART that predicts it from the columns ALREADY
synthesized, fitted on the real data, then drawing a donor from the matching
leaf for every synthetic row. Because predictors at draw time are the
synthetic values, the joint distribution is built up sequentially.

Confidentiality:
  * `min_leaf` (k): no leaf / no marginal cell is built from fewer than k real
    records, so a drawn value never isolates one person.
  * `smoothing`: optional jitter on continuous donors so exact real values are
    not echoed verbatim.
  * direct identifiers should be dropped before synthesis (see `drop` arg).
"""

import random
from . import _io
from . import _tree


def _is_numeric(values):
    present = [v for v in values if not _io.is_missing(v)]
    if not present:
        return False
    for v in present:
        try:
            float(str(v).replace(",", ""))
        except ValueError:
            return False
    return True


def _to_float(v):
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _marginal_draw(values, n, min_leaf, rng):
    """Sample n values from the empirical marginal, suppressing rare cells."""
    counts = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    pool = [v for v in values if counts[v] >= min_leaf]
    if not pool:                       # everything rare -> fall back to all
        pool = list(values)
    return [rng.choice(pool) for _ in range(n)]


def type_columns(columns, names):
    """Return (is_num, typed) for the given column names.
    Numeric columns become floats (missing -> None); others become strings."""
    is_num, typed = {}, {}
    for c in names:
        numeric = _is_numeric(columns[c])
        is_num[c] = numeric
        if numeric:
            typed[c] = [(_to_float(v) if not _io.is_missing(v) else None) for v in columns[c]]
        else:
            typed[c] = [("" if _io.is_missing(v) else str(v)) for v in columns[c]]
    return is_num, typed


def stringify(typed, names):
    """Turn typed synthetic columns back into CSV-ready strings."""
    out = {}
    for c in names:
        vals = []
        for v in typed[c]:
            if v is None:
                vals.append("")
            elif isinstance(v, float):
                vals.append(str(int(v)) if v.is_integer() else ("%.6g" % v))
            else:
                vals.append(str(v))
        out[c] = vals
    return out


def synth_core(real, is_num, visit, n, rng, fixed_real=None, fixed_synth=None,
               min_leaf=5, max_depth=12, smoothing=0.0):
    """Sequentially synthesize the `visit` columns and return typed output.

    real        : dict name->typed list (real data, for fitting)
    is_num      : dict name->bool covering every visited AND fixed column
    fixed_real  : dict name->typed list aligned to real rows — predictors that are
                  GIVEN, not synthesized (e.g. a child row's parent attributes).
    fixed_synth : dict name->typed list aligned to the n synthetic rows — the
                  given predictor values for each synthetic row.
    """
    fixed_real = fixed_real or {}
    fixed_synth = fixed_synth or {}
    fixed_names = list(fixed_real.keys())
    if visit:
        n_real = len(real[visit[0]])
    elif fixed_real:
        n_real = len(next(iter(fixed_real.values())))
    else:
        n_real = 0

    out = {c: [] for c in visit}
    done = []
    for c in visit:
        target_kind = "num" if is_num[c] else "cat"
        preds = fixed_names + done
        if not preds:
            donors = [v for v in real[c] if v is not None] if is_num[c] else real[c]
            out[c] = _marginal_draw(donors if donors else real[c], n, min_leaf, rng)
        else:
            pred = {p: (fixed_real[p] if p in fixed_real else real[p]) for p in preds}
            idx = list(range(n_real))
            root = _tree.build_tree(idx, real[c], preds, pred, is_num, target_kind,
                                    min_leaf=min_leaf, max_depth=max_depth)
            col_out = []
            for i in range(n):
                row = {}
                for p in preds:
                    row[p] = fixed_synth[p][i] if p in fixed_synth else out[p][i]
                col_out.append(_tree.sample_leaf(root, row, is_num, rng, smoothing))
            out[c] = col_out
        done.append(c)
    return out


def synthesize(header, columns, n=None, visit=None, drop=None,
               min_leaf=5, max_depth=12, smoothing=0.0, seed=12345):
    """Return (out_header, out_columns) of synthetic data for one flat table."""
    rng = random.Random(seed)
    drop = set(drop or [])
    visit = [c for c in (visit or header) if c in columns and c not in drop]
    n_real = len(columns[header[0]]) if header else 0
    n = n_real if n is None else n
    is_num, real = type_columns(columns, visit)
    out = synth_core(real, is_num, visit, n, rng,
                     min_leaf=min_leaf, max_depth=max_depth, smoothing=smoothing)
    return visit, stringify(out, visit)
