#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
# AUTO-GENERATED self-contained script for stage 03 - DO NOT EDIT BY HAND.
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


# ---- stage 03 ----
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


def schema_integrity(run_dir):
    """Schema-driven referential integrity and within-row pairing on the synthetic
    data. Handles links that are not id-named (which the kind-based check misses)
    and verifies that inherited keys match their parent row."""
    p = os.path.join(run_dir, "schema.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        schema = json.load(f)
    files = schema.get("files", {})
    cache = {}

    def load(base):
        if base not in cache:
            sp = os.path.join(run_dir, "synthetic_%s.csv" % base)
            cache[base] = load_columns(sp) if os.path.exists(sp) else None
        return cache[base]

    lines = []
    for base in schema.get("order", list(files)):
        e = files.get(base, {})
        parent, link = e.get("parent"), e.get("link")
        if not parent or not link:
            continue
        cc, pc = load(base), load(parent)
        if not cc or not pc or link not in cc or link not in pc:
            continue
        pset = set(v for v in pc[link] if not is_missing(v))
        cvals = [v for v in cc[link] if not is_missing(v)]
        orphan = sum(1 for v in cvals if v not in pset)
        pct = 100.0 * orphan / max(len(cvals), 1)
        lines.append("- `%s` -> `%s` on `%s`: %s (%d orphan keys, %.1f%%)"
                     % (base, parent, link, "OK" if orphan == 0 else "BROKEN", orphan, pct))
        pmap = {}
        for i, k in enumerate(pc[link]):
            if not is_missing(k):
                pmap.setdefault(k, i)
        for c in (e.get("inherited") or []):
            if c not in cc or c not in pc or c.endswith("_month"):
                continue
            ok = tot = 0
            for j, k in enumerate(cc[link]):
                if k in pmap:
                    tot += 1
                    if cc[c][j] == pc[c][pmap[k]]:
                        ok += 1
            p2 = 100.0 * ok / max(tot, 1)
            lines.append("    - within-row pairing `%s` inherited from `%s`: %s (%.1f%% consistent)"
                         % (c, parent, "OK" if ok == tot else "PARTIAL", p2))
    return lines


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

    ri = schema_integrity(run_dir) or referential_integrity(reals, run_dir)

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

if __name__ == "__main__":
    run_compare(run_dir=(sys.argv[1] if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]) else None), base_dir=os.getcwd())
