# -*- coding: utf-8 -*-
"""Command-line interface:  python -m oissyntheticdata real.csv -o synthetic.csv"""

import sys
import argparse
from . import synthesize_file, __version__


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="oissyntheticdata",
        description="Pure-Python sequential CART synthesis (synthpop tradition, zero deps).")
    p.add_argument("input", help="real CSV or XLSX file")
    p.add_argument("-o", "--output", default="synthetic.csv", help="output CSV path")
    p.add_argument("-n", "--rows", type=int, default=None, help="number of synthetic rows")
    p.add_argument("--drop", default="", help="comma-separated columns to exclude (e.g. identifiers)")
    p.add_argument("--visit", default="", help="comma-separated synthesis order (default: file order)")
    p.add_argument("--min-leaf", type=int, default=5, help="minimum real records per leaf/cell (k)")
    p.add_argument("--max-depth", type=int, default=12, help="maximum tree depth")
    p.add_argument("--smoothing", type=float, default=0.0, help="continuous jitter (0 = off)")
    p.add_argument("--seed", type=int, default=12345)
    p.add_argument("--version", action="version", version="oissyntheticdata " + __version__)
    a = p.parse_args(argv)

    drop = [c.strip() for c in a.drop.split(",") if c.strip()]
    visit = [c.strip() for c in a.visit.split(",") if c.strip()] or None
    rows, cols = synthesize_file(a.input, a.output, n=a.rows, visit=visit, drop=drop,
                                 min_leaf=a.min_leaf, max_depth=a.max_depth,
                                 smoothing=a.smoothing, seed=a.seed)
    sys.stderr.write("[oissyntheticdata] wrote %d rows x %d cols -> %s\n" % (rows, cols, a.output))


if __name__ == "__main__":
    main()
