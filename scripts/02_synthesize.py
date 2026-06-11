#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
# AUTO-GENERATED self-contained script for stage 02 - DO NOT EDIT BY HAND.
# Source of truth: src/oissyntheticdata/  (regenerate: python tools/build_standalone.py)
# Zero third-party dependencies - copy this single file into the environment.
# ============================================================================

import os
import csv
import sys
import json
import math
import glob
import random
import bisect
import calendar
import zipfile
import datetime
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- from oissyntheticdata._common ----
# --- disclosure / parsing configuration (keep identical across all stages) ----
MIN_CELL_COUNT  = 5          # categories rarer than this are anonymised (k)
MAX_CATEGORIES  = 60         # above this an object column is treated as ID/free-text
ID_NAME_HINTS   = ("id", "key", "code")
MIN_GROUP_KEYS  = 20         # an '*_id' needs more than this many distinct values
                             # to be a fan-out key; fewer = a category code
QUANTILE_GRID   = [0, 5, 10, 25, 50, 75, 90, 95, 100]
USE_ROBUST_BOUNDS = True
P_LOW, P_HIGH   = 1.0, 99.0
MISSING_TOKENS  = {"", "na", "n/a", ".", "nan", "null", "none"}
DATE_FORMATS    = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d",
                   "%d-%m-%Y", "%Y-%m-%d %H:%M:%S"]
OUTPUT_PARENT   = "output"   # run folders live under <cwd>/output/
OUTPUT_PREFIXES = ("synthetic", "comparison", "profile")  # never treat outputs as input


# ==============================================================================
# Value helpers
# ==============================================================================

def is_missing(v):
    return str(v).strip().lower() in MISSING_TOKENS


def to_float(v):
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return None


def looks_int(v):
    f = to_float(v)
    return f is not None and float(f).is_integer()


def parse_date(v):
    """Return (datetime, format) or (None, None)."""
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(str(v).strip(), fmt), fmt
        except ValueError:
            continue
    return None, None


def parse_date_dt(v):
    """Return the datetime only (or None)."""
    return parse_date(v)[0]


def month_of(value):
    d = parse_date_dt(value)
    return str(d.month) if d else ""


def signature(value):
    return "".join("D" if ch.isdigit() else "A" if ch.isalpha() else ch
                   for ch in str(value))


def is_date_col(values):
    present = [v for v in values if not is_missing(v)]
    if not present or all(to_float(v) is not None for v in present):
        return False
    return sum(1 for v in present if parse_date_dt(v) is not None) / len(present) > 0.9


# ==============================================================================
# Statistics (standard library only)
# ==============================================================================

def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def std_dev(xs):
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5   # population SD


def percentile(sorted_xs, p):
    if not sorted_xs:
        return 0.0
    k = (len(sorted_xs) - 1) * p / 100.0
    f = int(k)
    c = k - f
    if f + 1 < len(sorted_xs):
        return sorted_xs[f] + c * (sorted_xs[f + 1] - sorted_xs[f])
    return sorted_xs[f]


# ==============================================================================
# Run-folder convention:  <base_dir>/output/run_NNN_YYYY-MM-DD/
# ==============================================================================

def runs_root(base_dir):
    root = os.path.join(base_dir, OUTPUT_PARENT)
    os.makedirs(root, exist_ok=True)
    return root


def existing_runs(base_dir):
    root = runs_root(base_dir)
    runs = []
    for d in os.listdir(root):
        full = os.path.join(root, d)
        if os.path.isdir(full) and d.startswith("run_"):
            try:
                runs.append((int(d.split("_")[1]), full))
            except (IndexError, ValueError):
                pass
    return sorted(runs)


def new_run_dir(base_dir):
    """Create the next numbered + dated run folder, e.g. output/run_001_2026-06-11/."""
    runs = existing_runs(base_dir)
    nxt = (runs[-1][0] + 1) if runs else 1
    path = os.path.join(runs_root(base_dir),
                        "run_%03d_%s" % (nxt, datetime.date.today().isoformat()))
    os.makedirs(path, exist_ok=True)
    return path


def newest_run_dir(base_dir):
    """Return the newest existing run folder, or base_dir as a legacy fallback."""
    runs = existing_runs(base_dir)
    return runs[-1][1] if runs else base_dir


def resolve_run_dir(base_dir, explicit=None):
    """explicit path (abs or relative to base_dir) wins; else newest run folder."""
    if explicit:
        return explicit if os.path.isabs(explicit) else os.path.join(base_dir, explicit)
    return newest_run_dir(base_dir)

# ---- from oissyntheticdata._io ----
def _col_index(cell_ref):
    """'AB12' -> zero-based column index using the letter part only."""
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def read_xlsx(path):
    """Read the first worksheet of an .xlsx into rows of strings (stdlib only)."""
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    T = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("a:si", ns):
                shared.append("".join(t.text or "" for t in si.iter(T)))
        sheet = "xl/worksheets/sheet1.xml"
        if sheet not in names:
            ws = sorted(n for n in names
                        if n.startswith("xl/worksheets/") and n.endswith(".xml"))
            sheet = ws[0]
        root = ET.fromstring(z.read(sheet))
        rows = []
        for row in root.iter("{%s}row" % ns["a"]):
            cells, maxi = {}, -1
            for c in row.findall("a:c", ns):
                ref = c.get("r", "")
                idx = _col_index(ref) if ref else len(cells)
                t = c.get("t")
                v = c.find("a:v", ns)
                if t == "s" and v is not None:
                    val = shared[int(v.text)]
                elif t == "inlineStr":
                    is_ = c.find("a:is", ns)
                    val = "".join(x.text or "" for x in is_.iter(T)) if is_ is not None else ""
                else:
                    val = v.text if v is not None else ""
                cells[idx] = val if val is not None else ""
                maxi = max(maxi, idx)
            rows.append([cells.get(i, "") for i in range(maxi + 1)])
        return rows


def read_csv_file(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return [row for row in csv.reader(f)]


def _read_raw(path):
    raw = read_xlsx(path) if path.lower().endswith((".xlsx", ".xls")) else read_csv_file(path)
    return [r for r in raw if any(str(c).strip() for c in r)]   # drop blank rows


def load_grid(path):
    """Return raw rows (header + body), blank rows dropped. [stage 00]"""
    return _read_raw(path)


def load_table(path):
    """Return (header:list[str], rows:list[dict]) from a CSV or XLSX file. [stage 01]"""
    raw = _read_raw(path)
    if not raw:
        return [], []
    header = [str(h).strip() for h in raw[0]]
    rows = []
    for r in raw[1:]:
        rows.append({header[i]: (str(r[i]).strip() if i < len(r) else "")
                     for i in range(len(header))})
    return header, rows


def load_columns(path):
    """Return dict {column_name: [string values]}. [stage 03]"""
    raw = _read_raw(path)
    if not raw:
        return {}
    header = [str(h).strip() for h in raw[0]]
    cols = {h: [] for h in header}
    for r in raw[1:]:
        for i, h in enumerate(header):
            cols[h].append(str(r[i]).strip() if i < len(r) else "")
    return cols


def write_csv(path, header, row_iter):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for row in row_iter:
            w.writerow(row)

# ---- stage 02 ----
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

if __name__ == "__main__":
    run_synthesize(run_dir=(sys.argv[1] if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]) else None), base_dir=os.getcwd())
