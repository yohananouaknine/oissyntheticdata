#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
# AUTO-GENERATED self-contained script for stage 00 - DO NOT EDIT BY HAND.
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

# ---- stage 00 ----
def add_month_file(path, out_path=None):
    """Write ``<name>_with_month.csv`` next to the input; return its path."""
    grid = load_grid(path)
    if not grid:
        raise ValueError("Empty file: %s" % path)
    header = [str(h).strip() for h in grid[0]]
    body = grid[1:]
    ncol = len(header)

    date_idx = []
    for j in range(ncol):
        column = [(r[j] if j < len(r) else "") for r in body]
        if is_date_col(column):
            date_idx.append(j)
    if not date_idx:
        return None  # nothing to add

    new_header = []
    for j in range(ncol):
        new_header.append(header[j])
        if j in date_idx:
            new_header.append(header[j] + "_month")

    def expand(row):
        out = []
        for j in range(ncol):
            val = row[j] if j < len(row) else ""
            out.append(val)
            if j in date_idx:
                out.append(month_of(val))
        return out

    if out_path is None:
        base = os.path.splitext(os.path.basename(path))[0]
        out_path = os.path.join(os.path.dirname(path) or ".", base + "_with_month.csv")
    write_csv(out_path, new_header, (expand(r) for r in body))
    return out_path, [header[j] + "_month" for j in date_idx]


def find_inputs(base_dir):
    import glob
    cands = []
    for ext in ("*.csv", "*.xlsx", "*.xls"):
        cands += glob.glob(os.path.join(base_dir, ext))
    cands = [c for c in cands
             if not os.path.basename(c).startswith(OUTPUT_PREFIXES)
             and "_with_month" not in os.path.basename(c)]
    return sorted(cands)


def cli_main(input_file=None, base_dir="."):
    if input_file:
        path = os.path.abspath(input_file)
    else:
        cands = find_inputs(base_dir)
        if not cands:
            raise FileNotFoundError("No CSV/XLSX file found; pass one explicitly.")
        path = cands[0]
    result = add_month_file(path)
    if result is None:
        print("[i] No date columns detected in %s - nothing to add."
              % os.path.basename(path))
        return
    out_path, added = result
    print("[OK] Added %d month column(s): %s" % (len(added), ", ".join(added)))
    print("     -> %s" % os.path.basename(out_path))

if __name__ == "__main__":
    cli_main(input_file=(sys.argv[1] if len(sys.argv) > 1 else None), base_dir=os.getcwd())
