# -*- coding: utf-8 -*-
"""
Command-line interface.

    oissyntheticdata add-month  [FILE]          # 00  preprocessor (anywhere)
    oissyntheticdata profile    [FILE ...]      # 01  INSIDE  (reads real data)
    oissyntheticdata synthesize                 # 02  OUTSIDE (profile only)
    oissyntheticdata compare                    # 03  INSIDE-ONLY control

Stage 01 writes a new ``output/run_NNN_DATE/`` folder; 02 and 03 act on the
newest run folder by default (or pass ``--run-dir``). Same as running the four
standalone scripts in ``scripts/``.
"""

import argparse

from . import __version__
from .add_month import cli_main as _add_month_cli
from .profile import run_profile as _run_profile
from .synthesize import run_synthesize as _run_synthesize
from .compare import run_compare as _run_compare


def _split(s):
    return [c.strip() for c in s.split(",") if c.strip()]


def build_parser():
    p = argparse.ArgumentParser(
        prog="oissyntheticdata",
        description="Profile-based synthetic data for secure research "
                    "(profile -> synthesize -> compare). Zero dependencies.")
    p.add_argument("--version", action="version",
                   version="oissyntheticdata " + __version__)
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("add-month", help="00: insert <date>_month columns (run anywhere)")
    a.add_argument("input", nargs="?", default=None, help="CSV/XLSX file")
    a.add_argument("--dir", default=".", help="base directory (default: .)")

    pr = sub.add_parser("profile", help="01: INSIDE - write disclosure-safe profile")
    pr.add_argument("input", nargs="*", help="real CSV/XLSX file(s); default: auto-detect")
    pr.add_argument("--dir", default=".", help="base directory (default: .)")
    pr.add_argument("--run-dir", default=None, help="explicit run folder (default: new)")
    pr.add_argument("--min-cell-count", type=int, default=5, help="k: anonymise cells below this")
    pr.add_argument("--no-robust", action="store_true", help="use true min/max, not P1/P99")
    pr.add_argument("--no-month", action="store_true", help="do not derive <date>_month columns")

    sy = sub.add_parser("synthesize", help="02: OUTSIDE - build synthetic data from the profile")
    sy.add_argument("run_dir", nargs="?", default=None, help="run folder (default: newest)")
    sy.add_argument("--dir", default=".", help="base directory (default: .)")
    sy.add_argument("--seed", type=int, default=12345)
    sy.add_argument("--row-multiplier", type=float, default=1.0)
    sy.add_argument("--no-edges", action="store_true", help="do not force every level/edge to appear")

    cm = sub.add_parser("compare", help="03: INSIDE-ONLY control - structural fidelity check")
    cm.add_argument("run_dir", nargs="?", default=None, help="run folder (default: newest)")
    cm.add_argument("--dir", default=".", help="base directory (default: .)")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.command == "add-month":
        _add_month_cli(input_file=args.input, base_dir=args.dir)

    elif args.command == "profile":
        _run_profile(
            inputs=args.input or None, base_dir=args.dir, run_dir=args.run_dir,
            add_month=not args.no_month,
            min_cell_count=args.min_cell_count, use_robust=not args.no_robust)

    elif args.command == "synthesize":
        _run_synthesize(
            run_dir=args.run_dir, base_dir=args.dir, seed=args.seed,
            row_multiplier=args.row_multiplier, inject_edges=not args.no_edges)

    elif args.command == "compare":
        _run_compare(run_dir=args.run_dir, base_dir=args.dir)


if __name__ == "__main__":
    main()
