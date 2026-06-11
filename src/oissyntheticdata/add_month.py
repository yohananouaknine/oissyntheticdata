# -*- coding: utf-8 -*-
"""
Stage 00 - PREPROCESSOR (run anywhere).

For every date column in a CSV/XLSX file, insert a derived companion column
``<datecol>_month`` (month of year, 1-12) right after it, so an analysis can
capture monthly repetition / seasonality of events.

Run it on the real data on-premises before your analysis (so the real run has
the same ``<datecol>_month`` columns your script developed against). The
synthetic pipeline (01/02/03) already adds these columns itself; this stage is
for adding them to data the pipeline did not produce.
"""

import os

from ._common import is_date_col, month_of, OUTPUT_PREFIXES
from ._io import load_grid, write_csv


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
