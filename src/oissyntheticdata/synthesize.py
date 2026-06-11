# -*- coding: utf-8 -*-
"""
Stage 02 - SYNTHESIZE (OFF-PREMISES, no real data).

Reads ``profile_*.json`` (from stage 01) and writes ``synthetic_<base>.csv``
whose STRUCTURE matches the real data: types, ranges, categorical levels
(including rare code paths), missingness, ID formats, and cross-file joins.

Priority is CODE-PATH COVERAGE, not statistical realism. The synthetic file
exists so an analysis script exercises every branch, filter, join and edge case
it will meet on the real data. Synthetic numbers are NEVER reported.

Reads ONLY the profile - never the real data.
"""

import os
import csv
import glob
import json
import random
import calendar
import datetime

from ._common import resolve_run_dir

ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGIT = "0123456789"
KEY_KINDS = ("identifier_unique", "identifier_group", "id_or_text")

DEFAULT_SEED = 12345
DEFAULT_ROW_MULTIPLIER = 1.0
DEFAULT_INJECT_EDGES = True
PROFILE_FILE = "profile.json"


# ------------------------------ per-column samplers --------------------------

def sample_numeric(col, n, inject_edges=DEFAULT_INJECT_EDGES):
    grid = [g / 100.0 for g in col["quantile_grid"]]
    qv = col["quantile_values"]
    out = []
    for _ in range(n):
        u = random.random()
        j = 0
        while j < len(grid) - 1 and u > grid[j + 1]:
            j += 1
        lo_g, hi_g = grid[j], grid[min(j + 1, len(grid) - 1)]
        lo_v, hi_v = qv[j], qv[min(j + 1, len(qv) - 1)]
        frac = 0.0 if hi_g == lo_g else (u - lo_g) / (hi_g - lo_g)
        out.append(lo_v + frac * (hi_v - lo_v))
    if inject_edges and n >= 2:
        out[0], out[1] = qv[0], qv[-1]
    if col.get("has_zero") and n >= 3:
        out[2] = 0.0
    if col.get("is_integer"):
        out = [int(round(x)) for x in out]
    return out


def sample_categorical(col, n, inject_edges=DEFAULT_INJECT_EDGES):
    labels = list(col["frequencies"].keys())
    weights = list(col["frequencies"].values())
    out = random.choices(labels, weights=weights, k=n)
    if inject_edges:
        for i, lab in enumerate(labels):
            if i < n:
                out[i] = lab
    return out


def sample_datetime(col, n):
    fmt = col.get("format", "%Y-%m-%d")
    lo = datetime.datetime.strptime(col["min"], fmt)
    hi = datetime.datetime.strptime(col["max"], fmt)
    span = max(int((hi - lo).total_seconds()), 1)
    out = []
    for _ in range(n):
        sec = random.randint(0, span)
        out.append((lo + datetime.timedelta(seconds=sec)).strftime(fmt))
    return out


def sample_seasonal_datetime(col, month_freqs, n):
    fmt = col.get("format", "%Y-%m-%d")
    lo = datetime.datetime.strptime(col["min"], fmt)
    hi = datetime.datetime.strptime(col["max"], fmt)
    span = max(int((hi - lo).total_seconds()), 1)
    months = [int(k) for k in month_freqs] if month_freqs else list(range(1, 13))
    mweights = [month_freqs[k] for k in month_freqs] if month_freqs else [1] * 12
    yf = col.get("year_freqs") or {}
    years = [int(k) for k in yf] if yf else list(range(lo.year, hi.year + 1))
    yweights = [yf[k] for k in yf] if yf else [1] * len(years)
    out = []
    for _ in range(n):
        d = None
        for _try in range(8):
            y = int(random.choices(years, weights=yweights, k=1)[0])
            m = int(random.choices(months, weights=mweights, k=1)[0])
            day = random.randint(1, calendar.monthrange(y, m)[1])
            cand = datetime.datetime(y, m, day)
            if lo <= cand <= hi:
                d = cand
                break
        if d is None:
            d = lo + datetime.timedelta(seconds=random.randint(0, span))
        out.append(d.strftime(fmt))
    return out


def sample_id(col, n):
    sig = col.get("dominant_signature") or ("D" * max(col.get("len_min", 6), 1))
    unique = col.get("is_unique_key", False)
    seen, out = set(), []
    while len(out) < n:
        val = "".join(random.choice(DIGIT) if ch == "D"
                      else random.choice(ALPHA) if ch == "A"
                      else ch for ch in sig)
        if unique and val in seen:
            continue
        seen.add(val)
        out.append(val)
    return out


def apply_missing(values, rate):
    if rate <= 0:
        return values
    return ["" if random.random() < rate else v for v in values]


def inv_cdf(grid01, qv, u):
    j = 0
    while j < len(grid01) - 1 and u > grid01[j + 1]:
        j += 1
    lo_g, hi_g = grid01[j], grid01[min(j + 1, len(grid01) - 1)]
    lo_v, hi_v = qv[j], qv[min(j + 1, len(qv) - 1)]
    frac = 0.0 if hi_g == lo_g else (u - lo_g) / (hi_g - lo_g)
    return lo_v + frac * (hi_v - lo_v)


def sample_identifier_unique(col, n):
    ids = list(range(1, n + 1))
    random.shuffle(ids)
    return [str(x) for x in ids]


def sample_identifier_group(col, n):
    n_groups = max(1, int(col["n_groups"]))
    grid = [g / 100.0 for g in col["group_size_grid"]]
    qv = col["group_size_quantiles"]
    sizes = [max(1, int(round(inv_cdf(grid, qv, random.random())))) for _ in range(n_groups)]
    total = sum(sizes)
    scaled = [max(1, int(round(s * n / total))) for s in sizes] if total else [1] * n_groups
    diff = n - sum(scaled)
    while diff != 0:
        i = random.randrange(n_groups)
        if diff > 0:
            scaled[i] += 1; diff -= 1
        elif scaled[i] > 1:
            scaled[i] -= 1; diff += 1
    out = []
    for gid, size in enumerate(scaled, start=1):
        out.extend([gid] * size)
    random.shuffle(out)
    return [str(x) for x in out[:n]]


# ------------------------------ relational key pools -------------------------

def load_profiles(run_dir):
    files = glob.glob(os.path.join(run_dir, "profile_*.json"))
    reports = []
    for f in sorted(files):
        with open(f, encoding="utf-8") as fh:
            reports.append(json.load(fh))
    if not reports and os.path.exists(os.path.join(run_dir, PROFILE_FILE)):
        with open(os.path.join(run_dir, PROFILE_FILE), encoding="utf-8") as fh:
            r = json.load(fh)
            r.setdefault("base", "data")
            reports.append(r)
    return reports


def build_key_pools(reports):
    seen = {}
    for rep in reports:
        for c in rep["columns"]:
            if c["kind"] in KEY_KINDS:
                seen.setdefault(c["name"], []).append((rep, c))
    pools = {}
    for name, lst in seen.items():
        if len(lst) < 2:
            continue
        parent_n = None
        for rep, c in lst:
            if c["kind"] == "identifier_unique":
                parent_n = rep["n_rows"]
        if parent_n is None:
            parent_n = max(c.get("n_groups", rep["n_rows"]) for rep, c in lst)
        pool = list(range(1, int(parent_n) + 1))
        random.shuffle(pool)
        pools[name] = [str(x) for x in pool]
    return pools


def assign_unique_from_pool(pool, n):
    if n <= len(pool):
        return list(pool[:n])
    extra = [str(x) for x in range(len(pool) + 1, n + 1)]
    return list(pool) + extra


def assign_group_from_pool(col, pool, n):
    n_groups = min(max(1, int(col["n_groups"])), len(pool))
    chosen = list(pool[:n_groups])
    grid = [g / 100.0 for g in col["group_size_grid"]]
    qv = col["group_size_quantiles"]
    sizes = [max(1, int(round(inv_cdf(grid, qv, random.random())))) for _ in range(n_groups)]
    total = sum(sizes)
    scaled = [max(1, int(round(s * n / total))) for s in sizes] if total else [1] * n_groups
    diff = n - sum(scaled)
    while diff != 0:
        i = random.randrange(n_groups)
        if diff > 0:
            scaled[i] += 1; diff -= 1
        elif scaled[i] > 1:
            scaled[i] -= 1; diff += 1
    out = []
    for gid, size in zip(chosen, scaled):
        out.extend([gid] * size)
    random.shuffle(out)
    return out[:n]


# ------------------------------ generate one file ----------------------------

def generate_file(report, pools, run_dir,
                  row_multiplier=DEFAULT_ROW_MULTIPLIER,
                  inject_edges=DEFAULT_INJECT_EDGES):
    n = max(1, int(round(report["n_rows"] * row_multiplier)))
    header = [c["name"] for c in report["columns"]]
    by_name = {c["name"]: c for c in report["columns"]}
    datetime_names = {c["name"] for c in report["columns"] if c["kind"] == "datetime"}

    month_dist, derived_month = {}, {}
    for c in report["columns"]:
        if c["name"].endswith("_month") and c["name"][:-6] in datetime_names \
                and c["kind"] in ("categorical", "boolean"):
            base = c["name"][:-6]
            freqs = {k: v for k, v in c["frequencies"].items()
                     if not str(k).startswith("RARE_")}
            if freqs:
                month_dist[base] = freqs
            derived_month[c["name"]] = base

    cols = {}
    for col in report["columns"]:
        name, kind = col["name"], col["kind"]
        if name in derived_month:
            continue
        shared_pool = pools.get(name)
        if shared_pool is not None and kind in KEY_KINDS:
            if kind == "identifier_group":
                vals = assign_group_from_pool(col, shared_pool, n)
            else:
                vals = assign_unique_from_pool(shared_pool, n)
        elif kind in ("integer", "float"):
            vals = sample_numeric(col, n, inject_edges)
        elif kind in ("categorical", "boolean"):
            vals = sample_categorical(col, n, inject_edges)
        elif kind == "datetime":
            if name in month_dist or col.get("year_freqs"):
                vals = sample_seasonal_datetime(col, month_dist.get(name), n)
            else:
                vals = sample_datetime(col, n)
        elif kind == "id_or_text":
            vals = sample_id(col, n)
        elif kind == "identifier_unique":
            vals = sample_identifier_unique(col, n)
        elif kind == "identifier_group":
            vals = sample_identifier_group(col, n)
        else:
            vals = [""] * n
        cols[name] = apply_missing(vals, col.get("missing_rate", 0.0))

    for mname, base in derived_month.items():
        fmt = by_name[base].get("format", "%Y-%m-%d")
        out = []
        for v in cols[base]:
            try:
                out.append(str(datetime.datetime.strptime(v, fmt).month))
            except (ValueError, TypeError):
                out.append("")
        cols[mname] = out

    out_name = "synthetic_%s.csv" % report.get("base", "data")
    with open(os.path.join(run_dir, out_name), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for i in range(n):
            w.writerow([cols[h][i] for h in header])
    return out_name, n, len(header)


def _load_schema(run_dir):
    p = os.path.join(run_dir, "schema.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


def _sample_column(col, n, inject_edges, month_dist):
    name, kind = col["name"], col["kind"]
    if kind in ("integer", "float"):
        return sample_numeric(col, n, inject_edges)
    if kind in ("categorical", "boolean"):
        return sample_categorical(col, n, inject_edges)
    if kind == "datetime":
        if name in month_dist or col.get("year_freqs"):
            return sample_seasonal_datetime(col, month_dist.get(name), n)
        return sample_datetime(col, n)
    if kind == "id_or_text":
        return sample_id(col, n)
    if kind == "identifier_unique":
        return sample_identifier_unique(col, n)
    if kind == "identifier_group":
        return sample_identifier_group(col, n)
    return [""] * n


def _attach_indices(n, n_parents, grid, quantiles):
    """Assign n child rows to parent row indices; fan-out follows the real
    group-size distribution, and a parent may receive zero children."""
    if n_parents <= 0:
        return [0] * n
    if quantiles:
        g = [x / 100.0 for x in grid]
        sizes = [max(0, int(round(inv_cdf(g, quantiles, random.random()))))
                 for _ in range(n_parents)]
    else:
        sizes = [1] * n_parents
    total = sum(sizes)
    if total <= 0:
        sizes = [1] * n_parents
        total = n_parents
    scaled = [int(round(s * n / total)) for s in sizes]
    diff = n - sum(scaled)
    while diff != 0:
        i = random.randrange(n_parents)
        if diff > 0:
            scaled[i] += 1
            diff -= 1
        elif scaled[i] > 0:
            scaled[i] -= 1
            diff += 1
    idx = []
    for i, s in enumerate(scaled):
        idx.extend([i] * s)
    idx = idx[:n]
    while len(idx) < n:
        idx.append(random.randrange(n_parents))
    random.shuffle(idx)
    return idx


def generate_relational(reports, schema, run_dir,
                        row_multiplier=DEFAULT_ROW_MULTIPLIER,
                        inject_edges=DEFAULT_INJECT_EDGES):
    """Synthesize files in topological order. A child row is attached to a real
    synthetic parent row; its link column and any inherited columns are copied
    from that parent, giving referential integrity, realistic fan-out, and exact
    within-row key pairing at once."""
    files = schema["files"]
    by_base = {r.get("base", "data"): r for r in reports}
    synth, outputs = {}, []
    for base in schema["order"]:
        rep = by_base.get(base)
        if rep is None:
            continue
        entry = files.get(base, {"parent": None, "link": None, "inherited": []})
        parent, link = entry.get("parent"), entry.get("link")
        inherited = set(entry.get("inherited") or [])
        n = max(1, int(round(rep["n_rows"] * row_multiplier)))
        header = [c["name"] for c in rep["columns"]]
        by_name = {c["name"]: c for c in rep["columns"]}
        datetime_names = {c["name"] for c in rep["columns"] if c["kind"] == "datetime"}

        month_dist, derived_month = {}, {}
        for c in rep["columns"]:
            if c["name"].endswith("_month") and c["name"][:-6] in datetime_names \
                    and c["kind"] in ("categorical", "boolean"):
                b = c["name"][:-6]
                freqs = {k: v for k, v in c["frequencies"].items()
                         if not str(k).startswith("RARE_")}
                if freqs:
                    month_dist[b] = freqs
                derived_month[c["name"]] = b

        attach = None
        if parent is not None and parent in synth:
            attach = _attach_indices(n, synth[parent]["n"],
                                     entry.get("fanout_grid"), entry.get("fanout_quantiles"))

        cols = {}
        for col in rep["columns"]:
            name = col["name"]
            if name in derived_month:
                continue
            from_parent = attach is not None and (name == link or name in inherited)
            if from_parent:
                src = synth[parent]["cols"].get(name)
                if src is not None:
                    cols[name] = [src[attach[i]] for i in range(n)]
                    continue
            vals = _sample_column(col, n, inject_edges, month_dist)
            cols[name] = vals if from_parent else apply_missing(vals, col.get("missing_rate", 0.0))

        for mname, b in derived_month.items():
            fmt = by_name[b].get("format", "%Y-%m-%d")
            out = []
            for v in cols.get(b, [""] * n):
                try:
                    out.append(str(datetime.datetime.strptime(v, fmt).month))
                except (ValueError, TypeError):
                    out.append("")
            cols[mname] = out

        out_name = "synthetic_%s.csv" % base
        with open(os.path.join(run_dir, out_name), "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            for i in range(n):
                w.writerow([cols[h][i] for h in header])
        synth[base] = {"cols": cols, "n": n}
        outputs.append((rep["source_file"], out_name, n, len(header)))
    return outputs


def run_synthesize(run_dir=None, base_dir=".", seed=DEFAULT_SEED,
                   row_multiplier=DEFAULT_ROW_MULTIPLIER,
                   inject_edges=DEFAULT_INJECT_EDGES, quiet=False):
    """Synthesize every profile in a run folder; return (run_dir, outputs)."""
    if run_dir is None:
        run_dir = resolve_run_dir(base_dir)
    random.seed(seed)
    reports = load_profiles(run_dir)
    if not reports:
        raise FileNotFoundError("No profile_*.json in %s. Run stage 01 first." % run_dir)
    schema = _load_schema(run_dir)
    relational = bool(schema and schema.get("files")
                      and any(e.get("parent") for e in schema["files"].values()))
    if relational:
        outputs = generate_relational(reports, schema, run_dir,
                                      row_multiplier=row_multiplier, inject_edges=inject_edges)
        if not quiet:
            for src, out_name, n, ncol in outputs:
                print("[OK] %s -> %s  (%d rows x %d cols)" % (src, out_name, n, ncol))
            print("     Relational synthesis: each child row was attached to a real synthetic")
            print("     parent, so single-key joins, group-bys, and within-row key pairing hold.")
            print("     Output folder: %s" % os.path.relpath(run_dir, base_dir))
            print("     Develop & debug OFF-premises; take ONLY the final script back on-site.")
        return run_dir, outputs

    pools = build_key_pools(reports)
    outputs = []
    for rep in reports:
        out_name, n, ncol = generate_file(rep, pools, run_dir,
                                          row_multiplier=row_multiplier,
                                          inject_edges=inject_edges)
        outputs.append((rep["source_file"], out_name, n, ncol))
        if not quiet:
            print("[OK] %s -> %s  (%d rows x %d cols)" % (rep["source_file"], out_name, n, ncol))
    if not quiet:
        if pools:
            print("     Shared relational keys: %s - child keys drawn from the same pool as"
                  % ", ".join(pools))
            print("     the parent, so your cross-file joins line up on the synthetic data.")
        print("     Output folder: %s" % os.path.relpath(run_dir, base_dir))
        print("     Develop & debug OFF-premises; take ONLY the final script back on-site.")
    return run_dir, outputs


def cli_main(run_dir=None, base_dir=".", **kw):
    return run_synthesize(run_dir=run_dir, base_dir=base_dir, **kw)
