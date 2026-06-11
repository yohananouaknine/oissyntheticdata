#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
# AUTO-GENERATED self-contained script for stage 01 - DO NOT EDIT BY HAND.
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

# ---- from oissyntheticdata.relational ----
def _nonmissing(rows, c):
    return [r.get(c, "") for r in rows if not is_missing(r.get(c, ""))]


def _is_unique(rows, c):
    vals = _nonmissing(rows, c)
    return len(vals) > 0 and len(set(vals)) == len(vals)


def _determines(rows, a, b):
    """Does column a functionally determine column b (group by a -> constant b)?"""
    seen = {}
    for r in rows:
        av = r.get(a, "")
        if is_missing(av):
            continue
        bv = r.get(b, "")
        if av in seen:
            if seen[av] != bv:
                return False
        else:
            seen[av] = bv
    return True


def _fanout(rows, link_col, grid=QUANTILE_GRID, robust=USE_ROBUST_BOUNDS):
    """Distribution of children per parent (group sizes) as robust quantiles."""
    counts = {}
    for r in rows:
        v = r.get(link_col, "")
        if is_missing(v):
            continue
        counts[v] = counts.get(v, 0) + 1
    sizes = sorted(counts.values())
    g = list(grid)
    q = [percentile(sizes, p) for p in g]
    if robust and sizes:
        q[0] = percentile(sizes, P_LOW)
        q[-1] = percentile(sizes, P_HIGH)
    return g, [round(x, 6) for x in q], len(counts)


def _own_key(header, uniqmap):
    uniques = [c for c in header if uniqmap.get(c)]
    if not uniques:
        return None
    for c in uniques:
        cl = c.lower()
        if cl in ("id", "url") or cl.endswith(("_id", "_key", "_code")):
            return c
    return uniques[0]


def _topo(files):
    children = {b: [] for b in files}
    indeg = {b: 0 for b in files}
    for b, e in files.items():
        p = e["parent"]
        if p:
            children[p].append(b)
            indeg[b] += 1
    q = sorted(b for b in files if indeg[b] == 0)
    order = []
    while q:
        b = q.pop(0)
        order.append(b)
        for c in sorted(children[b]):
            indeg[c] -= 1
            if indeg[c] == 0:
                q.append(c)
        q.sort()
    for b in files:                       # any leftover (defensive: cycles)
        if b not in order:
            order.append(b)
    return order


def _all_int(values):
    if not values:
        return False
    for v in values:
        try:
            int(str(v))
        except (ValueError, TypeError):
            return False
    return True


def detect_schema(tables):
    """tables: {base: {"file": name, "header": [...], "rows": [dict, ...]}}.

    Returns {"files": {base: {parent, link, inherited, key, fanout_*}}, "order": [...]}.
    """
    bases = list(tables)
    uniq, valset, header = {}, {}, {}
    for b, t in tables.items():
        header[b] = t["header"]
        uniq[b], valset[b] = {}, {}
        for c in t["header"]:
            vals = _nonmissing(t["rows"], c)
            valset[b][c] = set(vals)
            uniq[b][c] = (len(vals) > 0 and len(set(vals)) == len(vals))

    def own(b):
        return _own_key(header[b], uniq[b])

    # 1:many links are unambiguous; 1:1 links (col unique in both) need a direction
    edges = {b: [] for b in bases}        # child -> list of (col, parent)
    one_to_one, seen_pair = [], set()
    for b in bases:
        for p in bases:
            if p == b:
                continue
            for c in header[b]:
                if c not in header[p]:
                    continue
                bv, pv = valset[b][c], valset[p][c]
                if not bv or not pv:
                    continue
                if uniq[p][c] and not uniq[b][c] and bv <= pv:
                    edges[b].append((c, p))                 # b is the many side
                elif uniq[p][c] and uniq[b][c] and bv == pv:
                    key = (min(b, p), max(b, p), c)
                    if key not in seen_pair:
                        seen_pair.add(key)
                        one_to_one.append((b, p, c))

    # resolve 1:1 direction: child = file with more other parents; then the file
    # whose own key is NOT this column; then a deterministic name order
    for a, bb, c in one_to_one:
        da, db = len(edges[a]), len(edges[bb])
        if da != db:
            child, parent = (a, bb) if da > db else (bb, a)
        elif (own(a) == c) != (own(bb) == c):
            child, parent = (a, bb) if own(a) != c else (bb, a)
        else:
            child, parent = max(a, bb), min(a, bb)
        edges[child].append((c, parent))

    files = {}
    for b in bases:
        links = edges[b]
        if not links:
            files[b] = {"file": tables[b]["file"], "parent": None, "link": None,
                        "inherited": [], "key": own(b),
                        "fanout_grid": None, "fanout_quantiles": None}
            continue
        # primary parent = link column with the most distinct values here (finest
        # grain); on a tie prefer an integer key, which synthesizes uniquely and
        # so keeps a parent join unambiguous
        primary_c, primary_p = max(
            links, key=lambda cp: (len(valset[b][cp[0]]), _all_int(valset[b][cp[0]])))
        phead = set(header[primary_p])
        inherited = [c for c in header[b]
                     if c != primary_c and c in phead
                     and not (c.endswith("_month") and c[:-6] in header[b])
                     and _determines(tables[b]["rows"], primary_c, c)]
        g, q, _ = _fanout(tables[b]["rows"], primary_c)
        files[b] = {"file": tables[b]["file"], "parent": primary_p, "link": primary_c,
                    "inherited": inherited, "key": own(b),
                    "fanout_grid": g, "fanout_quantiles": q}

    return {"files": files, "order": _topo(files)}


def schema_lines(schema):
    """Human-readable summary of the detected relationships."""
    lines = []
    for b in schema["order"]:
        e = schema["files"][b]
        if e["parent"]:
            extra = (" inheriting " + ", ".join(e["inherited"])) if e["inherited"] else ""
            lines.append("%s -> %s on %s%s" % (b, e["parent"], e["link"], extra))
        else:
            key = (" (key %s)" % e["key"]) if e["key"] else ""
            lines.append("%s: root%s" % (b, key))
    return lines

# ---- stage 01 ----
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


def _profile_one(path, run_dir, add_month=True, **cfg):
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
    return report, base, {"file": os.path.basename(path), "header": header, "rows": rows}


def profile_file(path, run_dir, add_month=True, **cfg):
    return _profile_one(path, run_dir, add_month=add_month, **cfg)[0]


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
    reports, tables = [], {}
    for p in paths:
        report, base, table = _profile_one(p, run_dir, add_month=add_month, **cfg)
        reports.append(report)
        tables[base] = table
    shared = detect_shared_keys(reports)

    schema = detect_schema(tables) if len(tables) > 1 else {"files": {}, "order": list(tables)}
    with open(os.path.join(run_dir, "schema.json"), "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)
    rels = schema_lines(schema) if any(e.get("parent") for e in schema["files"].values()) else []

    md = ["# Profiles (%d file%s)" % (len(reports), "" if len(reports) == 1 else "s"),
          "- Generated: %s" % datetime.datetime.now().isoformat(timespec="seconds"),
          "- Protections: min cell count = %d, robust bounds = %s"
          % (cfg.get("min_cell_count", MIN_CELL_COUNT),
             cfg.get("use_robust", USE_ROBUST_BOUNDS))]
    if rels:
        md.append("- **Detected relationships:**")
        md += ["    - %s" % r for r in rels]
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
        if rels:
            print("     Detected relationships:")
            for r in rels:
                print("       %s" % r)
        print("     All outputs in: %s" % rel)
        print("     Metadata only - safe to take off-site (feed this folder to 02).")
    return run_dir, reports


def cli_main(input_file=None, base_dir=".", run_dir=None, **cfg):
    return run_profile(inputs=([input_file] if input_file else None),
                       base_dir=base_dir, run_dir=run_dir, **cfg)

if __name__ == "__main__":
    run_profile(base_dir=os.getcwd())
