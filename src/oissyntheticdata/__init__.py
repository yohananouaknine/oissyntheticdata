# -*- coding: utf-8 -*-
"""
oissyntheticdata - profile-based synthetic data for secure research environments.

A study runs across one trust boundary:

    INSIDE (real data)        OUTSIDE (no real data)        INSIDE (control)
    -----------------         ----------------------        ----------------
    01 profile  ---------->   02 synthesize   ----...        03 compare
    real -> disclosure-safe   profile -> synthetic           real vs synthetic
    profile (the ONLY         (never sees the real           structural fidelity
    artefact that leaves)     data)                          (inside-only)

Only the profile and, later, the aggregate results cross the boundary - each
after the research unit authorises it. The real data never leaves.

Zero third-party runtime dependencies (standard library only): the package can
be copied into a locked environment that forbids pip/conda and has no internet,
and is small enough for a data owner to read and audit in full.

Public API
----------
    import oissyntheticdata as oisd

    # INSIDE: write a disclosure-safe profile of the real data
    run_dir, reports = oisd.profile(["real.csv"], base_dir="work")

    # OUTSIDE: build synthetic data from the profile only
    oisd.synthesize(run_dir=run_dir)

    # INSIDE-ONLY control: structural fidelity / referential integrity
    oisd.compare(run_dir=run_dir, base_dir="work")

The same four stages are available as the CLI ``oissyntheticdata
add-month|profile|synthesize|compare`` and as the standalone, zero-install
scripts in ``scripts/`` (carry those into the secure environment).
"""

__version__ = "2.1.0"

from .add_month import add_month_file, cli_main as _add_month_cli
from .profile import run_profile as profile, profile_column, profile_file
from .synthesize import run_synthesize as synthesize
from .compare import run_compare as compare

__all__ = [
    "__version__",
    "profile", "synthesize", "compare",
    "add_month_file", "profile_column", "profile_file",
]
