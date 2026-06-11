# -*- coding: utf-8 -*-
"""
Stage 01 - PROFILE (ON-PREMISES, reads REAL data).

Reads the real data and writes a DISCLOSURE-SAFE metadata report
(``profile_<base>.json`` + ``profile_summary.md``). The report is the only
artefact that leaves this stage, so it carries no identifiable values:

  * rare categorical levels (count < ``min_cell_count``) keep their COUNT but
    lose their LABEL (relabelled ``RARE_001`` ...);
  * numeric extremes are reported at robust percentiles (P1/P99 by default);
  * ID / free-text columns are never enumerated - only a format signature
    (e.g. ``DD-DDDDDD``) and a length range leave;
  * fan-out keys keep only the *distribution* of group sizes, never an id tied
    to its count.

Standard library only - safe to run inside a locked secure environment.
"""

import os
import glob
import json
import datetime

from ._common import (
    MIN_CELL_COUNT, USE_ROBUST_BOUNDS, P_LOW, P_HIGH, QUANTILE_GRID,
    MAX_CATEGORIES, ID_NAME_HINTS, MIN_GROUP_KEYS, OUTPUT_PREFIXES,
    is_missing, to_float, looks_int, parse_date, signature, is_date_col,
    month_of, mean, std_dev, percentile, new_run_dir,
)
from ._io import load_table


def augment_with_months(header, rows):
    """Insert a derived '<datecol>_month' column (1-12) after each date column."""
    new_header, date_cols = [], []
    for name in header:
        new_header.append(name)
        if is_date_col([r.get(name, "") for r in rows]):
            mname = name + "_month"
            new_header.append(mname)
            date_cols.append((name, mname))
    for name, mname in date_cols:
        for r in rows:
            r[mname] = month_of(r.get(name, ""))
    return new_header


def profile_column(name, values,
                   min_cell_count=MIN_CELL_COUNT, use_robust=USE_ROBUST_BOUNDS,
                   p_low=P_LOW, p_high=P_HIGH, quantile_grid=QUANTILE_GRID,
                   max_categories=MAX_CATEGORIES, id_hints=ID_NAME_HINTS,
                   min_group_keys=MIN_GROUP_KEYS):
    present = [v for v in values if not is_missing(v)]
    n = len(values)
    n_missing = n - len(present)
    distinct = sorted(set(present))
    col = {"name": name, "n": n,
           "missing_rate": round(n_missing / n, 6) if n else 0.0,
           "n_unique": len(distinct)}
    if not present:
        col["kind"] = "empty"
        return col

    all_numeric = all(to_float(v) is not None for v in present)
    all_int = all_numeric and all(looks_int(v) for v in present)
    date_hits = sum(1 for v in present if parse_date(v)[0] is not None)
    is_date = (not all_numeric) and (date_hits / len(present) > 0.9)
    low = {v.lower() for v in present}
    is_bool = low <= {"0", "1", "true", "false", "yes", "no", "y", "n"} and len(distinct) <= 3
    nm = name.strip().lower()
    is_id_name = any(nm == h or nm.endswith("_" + h) for h in id_hints)

    # derived month columns are cyclic codes, not magnitudes -> categorical
    if nm.endswith("_month"):
        counts = {}
        for v in present:
            counts[v] = counts.get(v, 0) + 1
        freqs, rare_i = {}, 1
        for label, cnt in sorted(counts.items(), key=lambda kv: -kv[1]):
            if cnt < min_cell_count:
                freqs["RARE_%03d" % rare_i] = cnt
                rare_i += 1
            else:
                freqs[label] = cnt
        col.update({"kind": "categorical", "frequencies": freqs,
                    "rare_levels_suppressed": rare_i - 1, "derived_month": True})
        return col

    # integer identifiers are NOT measurements: handle before the numeric branch
    if all_int and len(distinct) == len(present):
        lengths = [len(v) for v in present]
        col.update({"kind": "identifier_unique",
                    "len_min": min(lengths), "len_max": max(lengths)})
        return col

    if all_int and is_id_name and len(distinct) > min_group_keys:
        counts = {}
        for v in present:
            counts[v] = counts.get(v, 0) + 1
        sizes = sorted(counts.values())
        grid = list(quantile_grid)
        gq = [percentile(sizes, p) for p in grid]
        if use_robust:
            gq[0] = percentile(sizes, p_low)
            gq[-1] = percentile(sizes, p_high)
        col.update({"kind": "identifier_group",
                    "n_groups": len(counts),
                    "group_size_grid": grid,
                    "group_size_quantiles": [round(x, 6) for x in gq]})
        return col

    if all_int and is_id_name:
        counts = {}
        for v in present:
            counts[v] = counts.get(v, 0) + 1
        col.update({"kind": "categorical",
                    "frequencies": {k: counts[k] for k in counts},
                    "rare_levels_suppressed": 0})
        return col

    if all_numeric and not is_bool:
        nums = sorted(to_float(v) for v in present)
        grid = list(quantile_grid)
        qv = [percentile(nums, p) for p in grid]
        if use_robust:
            qv[0] = percentile(nums, p_low)
            qv[-1] = percentile(nums, p_high)
        col.update({"kind": "integer" if all_int else "float",
                    "is_integer": all_int,
                    "mean": round(mean(nums), 6),
                    "std": round(std_dev(nums), 6),
                    "quantile_grid": grid,
                    "quantile_values": [round(x, 6) for x in qv],
                    "has_negative": any(x < 0 for x in nums),
                    "has_zero": any(x == 0 for x in nums)})

    elif is_date:
        parsed = [parse_date(v) for v in present]
        fmts = [f for _, f in parsed if f]
        fmt = max(set(fmts), key=fmts.count)
        dts = [d for d, _ in parsed if d is not None]
        yfreq = {}
        for d in dts:
            y = str(d.year)
            yfreq[y] = yfreq.get(y, 0) + 1
        col.update({"kind": "datetime", "format": fmt,
                    "min": min(dts).strftime(fmt), "max": max(dts).strftime(fmt),
                    "year_freqs": yfreq})

    elif is_bool:
        freq = {}
        for v in present:
            freq[v] = freq.get(v, 0) + 1
        col.update({"kind": "boolean", "frequencies": freq})

    elif len(distinct) <= max_categories:
        counts = {}
        for v in present:
            counts[v] = counts.get(v, 0) + 1
        freqs, rare_i = {}, 1
        for label, cnt in sorted(counts.items(), key=lambda kv: -kv[1]):
            if cnt < min_cell_count:
                freqs["RARE_%03d" % rare_i] = cnt
                rare_i += 1
            else:
                freqs[label] = cnt
        col.update({"kind": "categorical", "frequencies": freqs,
                    "rare_levels_suppressed": rare_i - 1})

    else:  # high-cardinality -> ID / free-text
        sigs = {}
        for v in present:
            s = signature(v)
            sigs[s] = sigs.get(s, 0) + 1
        dom = max(sigs, key=sigs.get)
        lengths = [len(v) for v in present]
        col.update({"kind": "id_or_text", "dominant_signature": dom,
                    "signature_coverage": round(sigs[dom] / len(present), 4),
                    "len_min": min(lengths), "len_max": max(lengths),
                    "is_unique_key": len(distinct) == len(present)})
    return col


def profile_file(path, run_dir, add_month=True, **cfg):
    header, rows = load_table(path)
    if add_month:
        header = augment_with_months(header, rows)
    columns = [profile_column(name, [r[name] for r in rows], **cfg) for name in header]
    base = os.path.splitext(os.path.basename(path))[0]
    report = {"source_file": os.path.basename(path), "base": base,
              "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
              "n_rows": len(rows), "n_cols": len(header),
              "config": {"MIN_CELL_COUNT": cfg.get("min_cell_count", MIN_CELL_COUNT),
                         "USE_ROBUST_BOUNDS": cfg.get("use_robust", USE_ROBUST_BOUNDS),
                         "robust_bounds_pct": [cfg.get("p_low", P_LOW),
                                               cfg.get("p_high", P_HIGH)]},
              "columns": columns}
    with open(os.path.join(run_dir, "profile_%s.json" % base), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def summary_block(report):
    lines = ["## `%s`  (%d rows, %d cols)" % (report["source_file"],
                                              report["n_rows"], report["n_cols"]),
             "| Column | Type | Missing % | Distinct | Notes |", "|---|---|---|---|---|"]
    for c in report["columns"]:
        note = ""
        if c["kind"] == "categorical":
            note = "%d levels (%d rare hidden)" % (len(c["frequencies"]),
                                                   c.get("rare_levels_suppressed", 0))
        elif c["kind"] in ("integer", "float"):
            note = "range≈[%s, %s], mean=%s" % (c["quantile_values"][0],
                                                c["quantile_values"][-1], c["mean"])
        elif c["kind"] == "id_or_text":
            note = "signature %s, len %d-%d" % (c["dominant_signature"],
                                                c["len_min"], c["len_max"])
        elif c["kind"] == "datetime":
            note = "%s → %s" % (c["min"], c["max"])
        elif c["kind"] == "identifier_unique":
            note = "unique key, len %d-%d" % (c["len_min"], c["len_max"])
        elif c["kind"] == "identifier_group":
            note = "%d groups, sizes≈[%s, %s]" % (c["n_groups"],
                        c["group_size_quantiles"][0], c["group_size_quantiles"][-1])
        lines.append("| %s | %s | %.1f%% | %d | %s |"
                     % (c["name"], c["kind"], c["missing_rate"] * 100, c["n_unique"], note))
    return lines


def detect_shared_keys(reports):
    """Column names that are key-like in >=2 files -> shared relational keys."""
    KEY_KINDS = ("identifier_unique", "identifier_group", "id_or_text")
    seen = {}
    for rep in reports:
        for c in rep["columns"]:
            if c["kind"] in KEY_KINDS:
                seen.setdefault(c["name"], []).append((rep["base"], c["kind"]))
    return {name: files for name, files in seen.items() if len(files) >= 2}


def find_inputs(base_dir, input_file=None):
    if input_file:
        return [os.path.join(base_dir, input_file)] if not os.path.isabs(input_file) else [input_file]
    cands = []
    for ext in ("*.csv", "*.xlsx", "*.xls"):
        cands += glob.glob(os.path.join(base_dir, ext))
    cands = [c for c in cands
             if not os.path.basename(c).startswith(OUTPUT_PREFIXES)
             and "_with_month" not in os.path.basename(c)]
    if not cands:
        raise FileNotFoundError("No CSV/XLSX file found in %s." % base_dir)
    return sorted(cands)


def run_profile(inputs=None, base_dir=".", run_dir=None, add_month=True,
                quiet=False, **cfg):
    """Profile one or more files into a new run folder; return (run_dir, reports)."""
    paths = inputs if inputs else find_inputs(base_dir)
    if isinstance(paths, str):
        paths = [paths]
    paths = [p if os.path.isabs(p) else os.path.join(base_dir, p) for p in paths]
    if run_dir is None:
        run_dir = new_run_dir(base_dir)
    reports = [profile_file(p, run_dir, add_month=add_month, **cfg) for p in paths]
    shared = detect_shared_keys(reports)

    md = ["# Profiles (%d file%s)" % (len(reports), "" if len(reports) == 1 else "s"),
          "- Generated: %s" % datetime.datetime.now().isoformat(timespec="seconds"),
          "- Protections: min cell count = %d, robust bounds = %s"
          % (cfg.get("min_cell_count", MIN_CELL_COUNT),
             cfg.get("use_robust", USE_ROBUST_BOUNDS))]
    if shared:
        md.append("- **Shared relational keys detected:** " +
                  ", ".join("`%s` (%s)" % (k, ", ".join("%s:%s" % (b, kd) for b, kd in v))
                            for k, v in shared.items()))
    md.append("")
    for rep in reports:
        md += summary_block(rep) + [""]
    with open(os.path.join(run_dir, "profile_summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    if not quiet:
        rel = os.path.relpath(run_dir, base_dir)
        for rep in reports:
            print("[OK] Profiled %s -> %s/profile_%s.json"
                  % (rep["source_file"], rel, rep["base"]))
        if shared:
            print("     Shared relational keys: %s" % ", ".join(shared))
        print("     All outputs in: %s" % rel)
        print("     Metadata only - safe to take off-site (feed this folder to 02).")
    return run_dir, reports


def cli_main(input_file=None, base_dir=".", run_dir=None, **cfg):
    return run_profile(inputs=([input_file] if input_file else None),
                       base_dir=base_dir, run_dir=run_dir, **cfg)
