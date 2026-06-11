# -*- coding: utf-8 -*-
"""
Stage 03 - FIDELITY CHECK (ON-PREMISES, INSIDE-ONLY CONTROL).

Compares the REAL dataset against ``synthetic_<base>.csv`` and writes a
fidelity report (``comparison_report.md`` + ``comparison_<base>.csv``).

This is an inside-the-premises control step. It reads the real data, so it is
NEVER a researcher step and never runs off-site. It answers one question only:
"is the synthetic bed structurally close enough that my script will behave on
the real data the way it did off-site?" It is NOT a privacy test and NOT a
validity test of results (those come from the real run).

Metrics:
  * categorical -> kappa*  (chance-corrected distributional agreement)
        Po = sum min(p_i, q_i)     (overlap = 1 - total variation distance)
        Pe = sum p_i * q_i         (agreement expected by chance)
        kappa* = (Po - Pe) / (1 - Pe)
  * numeric / date -> 1 - KS       (max gap between empirical CDFs)
  * ID / text -> agreement of format signatures (values are MEANT to differ)
Only column-level scores leave the environment.
"""

import os
import csv
import glob
import json
import bisect
import datetime

from ._common import (
    MIN_CELL_COUNT, MAX_CATEGORIES, ID_NAME_HINTS, OUTPUT_PREFIXES,
    is_missing, to_float, parse_date_dt, signature, is_date_col, month_of,
    resolve_run_dir,
)
from ._io import load_columns

SYNTH_FILE = "synthetic_data.csv"
FLAG_BELOW = 0.80                 # agreement below this = "review before rerun"
EPOCH = datetime.datetime(1970, 1, 1)


def add_month_columns(cols):
    for name in list(cols):
        mname = name + "_month"
        if is_date_col(cols[name]) and mname not in cols:
            cols[mname] = [month_of(v) for v in cols[name]]
    return cols


def load_profile_kinds(base, run_dir):
    path = os.path.join(run_dir, "profile_%s.json" % base)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        rep = json.load(f)
    return {c["name"]: c["kind"] for c in rep["columns"]}


def detect_kind(values):
    present = [v for v in values if not is_missing(v)]
    if not present:
        return "empty", present
    if all(to_float(v) is not None for v in present):
        low = {v.lower() for v in present}
        if low <= {"0", "1", "true", "false", "yes", "no"} and len(set(present)) <= 3:
            return "categorical", present
        return "numeric", present
    if sum(1 for v in present if parse_date_dt(v)) / len(present) > 0.9:
        return "datetime", present
    if len(set(present)) / len(present) > 0.9 and len(set(present)) > MAX_CATEGORIES:
        return "id", present
    return "categorical", present


# ------------------------------ agreement metrics ----------------------------

def ks_similarity(a, b):
    a, b = sorted(a), sorted(b)
    if not a or not b:
        return None
    na, nb = len(a), len(b)
    ks = 0.0
    for g in sorted(set(a) | set(b)):
        ca = bisect.bisect_right(a, g) / na
        cb = bisect.bisect_right(b, g) / nb
        ks = max(ks, abs(ca - cb))
    return 1.0 - ks


def kappa_like(p, q):
    keys = set(p) | set(q)
    po = sum(min(p.get(k, 0), q.get(k, 0)) for k in keys)
    pe = sum(p.get(k, 0) * q.get(k, 0) for k in keys)
    kap = (po - pe) / (1 - pe) if (1 - pe) > 1e-9 else po
    coverage = (len([k for k in p if k in q]) / len(p)) if p else 0.0
    return po, kap, coverage


def props(values, pool_rare=False, map_synth_rare=False):
    counts = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    if pool_rare:
        pooled, rare = {}, 0
        for k, c in counts.items():
            if c < MIN_CELL_COUNT:
                rare += c
            else:
                pooled[k] = c
        if rare:
            pooled["__RARE__"] = pooled.get("__RARE__", 0) + rare
        counts = pooled
    if map_synth_rare:
        merged = {}
        for k, c in counts.items():
            key = "__RARE__" if str(k).startswith("RARE_") else k
            merged[key] = merged.get(key, 0) + c
        counts = merged
    total = sum(counts.values()) or 1
    return {k: c / total for k, c in counts.items()}


def heuristic_kind(name, rvals):
    nm = name.strip().lower()
    r_present = [v for v in rvals if not is_missing(v)]
    if not r_present:
        return "categorical"
    all_int = all(to_float(v) is not None and float(to_float(v)).is_integer() for v in r_present)
    if all_int and len(set(r_present)) == len(r_present):
        return "identifier_unique"
    if all_int and any(nm == h or nm.endswith("_" + h) for h in ID_NAME_HINTS) \
            and len(set(r_present)) > 20:
        return "identifier_group"
    k, _ = detect_kind(rvals)
    return k


def compare_column(name, rvals, svals, kind=None):
    rec = {"column": name, "method": "-", "agreement": None, "note": "", "missing_drift": ""}
    r_present = [v for v in rvals if not is_missing(v)]
    s_present = [v for v in svals if not is_missing(v)]
    if kind is None:
        kind = heuristic_kind(name, rvals)
    nm = name.strip().lower()

    if kind == "identifier_unique":
        s_distinct = len(set(s_present))
        ratio = s_distinct / len(s_present) if s_present else 0.0
        rec.update(method="unique-key", agreement=ratio,
                   note="unique key kept (%d/%d distinct)" % (s_distinct, len(s_present)))

    elif kind == "identifier_group":
        rc, sc = {}, {}
        for v in r_present:
            rc[v] = rc.get(v, 0) + 1
        for v in s_present:
            sc[v] = sc.get(v, 0) + 1
        sim = ks_similarity(sorted(rc.values()), sorted(sc.values()))
        rec.update(method="group-size KS", agreement=sim,
                   note="per-group shape; groups %d→%d" % (len(rc), len(sc)))

    elif kind == "id_or_text":
        p = props([signature(v) for v in r_present])
        q = props([signature(v) for v in s_present])
        overlap, kap, _ = kappa_like(p, q)
        rec.update(method="signature", agreement=kap,
                   note="format match %.2f (values intentionally differ)" % overlap)

    elif kind == "datetime":
        a = [(parse_date_dt(v) - EPOCH).total_seconds() for v in r_present if parse_date_dt(v)]
        b = [(parse_date_dt(v) - EPOCH).total_seconds() for v in s_present if parse_date_dt(v)]
        rec.update(method="1 - KS (date)", agreement=ks_similarity(a, b), note="date trend+season")

    elif kind in ("categorical", "boolean"):
        p = props(r_present, pool_rare=True)
        q = props(s_present, map_synth_rare=True)
        overlap, kap, cov = kappa_like(p, q)
        if nm.endswith("_month"):
            rec.update(method="kappa* (month)", agreement=kap,
                       note="seasonality overlap %.2f, months %.0f%%" % (overlap, cov * 100))
        else:
            rec.update(method="kappa*", agreement=kap,
                       note="overlap %.2f, level coverage %.0f%%" % (overlap, cov * 100))

    else:  # numeric
        a = [to_float(v) for v in r_present]
        b = [to_float(v) for v in s_present]
        sim = ks_similarity(a, b)
        rmean = sum(a) / len(a) if a else 0
        smean = sum(b) / len(b) if b else 0
        drift = abs(rmean - smean) / (abs(rmean) + 1e-9)
        rec.update(method="1 - KS", agreement=sim, note="mean drift %.1f%%" % (drift * 100))

    rmiss = sum(1 for v in rvals if is_missing(v)) / len(rvals) if rvals else 0
    smiss = sum(1 for v in svals if is_missing(v)) / len(svals) if svals else 0
    rec["missing_drift"] = round(abs(rmiss - smiss), 4)
    return rec


def compare_one(real_path, run_dir):
    base = os.path.splitext(os.path.basename(real_path))[0]
    synth_path = os.path.join(run_dir, "synthetic_%s.csv" % base)
    if not os.path.exists(synth_path):
        synth_path = os.path.join(run_dir, SYNTH_FILE)
    if not os.path.exists(synth_path):
        return base, None, []
    real = load_columns(real_path)
    synth = load_columns(synth_path)
    add_month_columns(real)
    kinds = load_profile_kinds(base, run_dir)
    recs = []
    for name in real:
        if name not in synth:
            recs.append({"column": name, "method": "-", "agreement": None,
                         "note": "MISSING in synthetic", "missing_drift": ""})
        else:
            recs.append(compare_column(name, real[name], synth[name], kinds.get(name)))
    scored = [r["agreement"] for r in recs if r["agreement"] is not None]
    fidelity = round(sum(scored) / len(scored), 4) if scored else float("nan")
    return base, fidelity, recs


def referential_integrity(reals, run_dir):
    KEY_KINDS = ("identifier_unique", "identifier_group", "id_or_text")
    synth_cols, keykind = {}, {}
    for rp in reals:
        base = os.path.splitext(os.path.basename(rp))[0]
        sp = os.path.join(run_dir, "synthetic_%s.csv" % base)
        if not os.path.exists(sp):
            continue
        synth_cols[base] = load_columns(sp)
        for name, kind in load_profile_kinds(base, run_dir).items():
            if kind in KEY_KINDS:
                keykind[(base, name)] = kind
    by_name = {}
    for (base, name) in keykind:
        by_name.setdefault(name, []).append(base)
    lines = []
    for name, bases in by_name.items():
        bases = [b for b in bases if b in synth_cols and name in synth_cols[b]]
        if len(bases) < 2:
            continue
        sets = {b: set(v for v in synth_cols[b][name] if not is_missing(v)) for b in bases}
        parent = None
        for b in bases:
            if keykind.get((b, name)) == "identifier_unique":
                parent = b
        if parent is None:
            parent = max(bases, key=lambda b: len(sets[b]))
        for b in bases:
            if b == parent:
                continue
            orphan = len(sets[b] - sets[parent])
            pct = 100.0 * orphan / max(len(sets[b]), 1)
            status = "OK" if orphan == 0 else "BROKEN"
            lines.append("- `%s`: %s ⊆ %s - %s (%d orphan keys, %.1f%%)"
                         % (name, b, parent, status, orphan, pct))
    return lines


def find_reals(base_dir, real_file=None):
    if real_file:
        return [os.path.join(base_dir, real_file)] if not os.path.isabs(real_file) else [real_file]
    cands = []
    for ext in ("*.csv", "*.xlsx", "*.xls"):
        cands += glob.glob(os.path.join(base_dir, ext))
    cands = [c for c in cands
             if not os.path.basename(c).startswith(OUTPUT_PREFIXES)
             and "_with_month" not in os.path.basename(c)]
    if not cands:
        raise FileNotFoundError("No real CSV/XLSX file found in %s." % base_dir)
    return sorted(cands)


def run_compare(run_dir=None, base_dir=".", reals=None, quiet=False):
    """Compare real files against their synthetic counterparts in run_dir."""
    if run_dir is None:
        run_dir = resolve_run_dir(base_dir)
    if reals is None:
        reals = find_reals(base_dir)
    elif isinstance(reals, str):
        reals = [reals]

    blocks, all_fidelity = [], []
    for rp in reals:
        base, fidelity, recs = compare_one(rp, run_dir)
        if recs is None or not recs:
            blocks.append("## `%s` - no matching synthetic_%s.csv found (skipped)" % (base, base))
            continue
        all_fidelity.append(fidelity)
        flagged = [r for r in recs if r["agreement"] is None or r["agreement"] < FLAG_BELOW]
        with open(os.path.join(run_dir, "comparison_%s.csv" % base), "w",
                  encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["column", "method", "agreement", "missing_drift", "note"])
            for r in recs:
                ag = "" if r["agreement"] is None else "%.4f" % r["agreement"]
                w.writerow([r["column"], r["method"], ag, r["missing_drift"], r["note"]])
        blk = ["## `%s`  -  fidelity index **%s**  (flagged: %d)"
               % (base, fidelity, len(flagged)),
               "", "| Column | Method | Agreement | Missing drift | Note |",
               "|---|---|---|---|---|"]
        for r in recs:
            ag = "" if r["agreement"] is None else "%.3f" % r["agreement"]
            blk.append("| %s | %s | %s | %s | %s |"
                       % (r["column"], r["method"], ag, r["missing_drift"], r["note"]))
        blocks.append("\n".join(blk))

    ri = referential_integrity(reals, run_dir)

    md = ["# Fidelity comparison (per file)",
          "Agreement: kappa* for categorical, 1 - KS for numeric/date, structural for keys.",
          "Only column-level scores leave the environment.", ""]
    md += [b + "\n" for b in blocks]
    md += ["## Cross-file referential integrity (synthetic joins)", ""]
    md += ri if ri else ["- No shared keys across files detected."]
    with open(os.path.join(run_dir, "comparison_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    if not quiet:
        for b in blocks:
            print("[OK]", b.splitlines()[0].replace("## ", "").replace("`", ""))
        if ri:
            broken = sum(1 for x in ri if "BROKEN" in x)
            print("     Referential integrity: %d shared-key link(s), %d broken." % (len(ri), broken))
        print("     Output folder: %s" % os.path.relpath(run_dir, base_dir))
    return run_dir, all_fidelity, ri


def cli_main(run_dir=None, base_dir=".", **kw):
    return run_compare(run_dir=run_dir, base_dir=base_dir, **kw)
