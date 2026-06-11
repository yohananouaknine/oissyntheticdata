# -*- coding: utf-8 -*-
"""
Shared constants and helpers for the four pipeline stages.

Standard library only. This module carries the value-level helpers (missing
detection, numeric/date parsing, format signatures, robust percentiles) and the
``output/run_NNN_DATE/`` run-folder convention that the stages hand off through.
Everything here is identical in behaviour to the original standalone scripts;
it is factored out so the package has a single source of truth.
"""

import os
import datetime

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
