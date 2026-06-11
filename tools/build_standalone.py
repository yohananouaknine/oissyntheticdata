#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_standalone.py - regenerate the self-contained scripts in ``scripts/``
from the package in ``src/oissyntheticdata/``.

This is what makes "keep both" honest: the package modules are the single
source of truth, and each numbered script in ``scripts/`` is an *inlined*,
zero-install copy (the shared ``_common`` and ``_io`` modules are folded in) so
it can be carried into a locked secure environment and audited as one file.

Run from the repo root:   python tools/build_standalone.py
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "oissyntheticdata")
OUT = os.path.join(ROOT, "scripts")

# superset of standard-library imports needed by any stage
IMPORTS = [
    "import os", "import csv", "import sys", "import json", "import math",
    "import glob", "import random", "import bisect", "import calendar",
    "import zipfile", "import datetime", "import xml.etree.ElementTree as ET",
]

STAGES = {
    "00_add_month.py": dict(module="add_month.py", stage="00",
        runner='cli_main(input_file=(sys.argv[1] if len(sys.argv) > 1 else None), base_dir=os.getcwd())'),
    "01_profile.py": dict(module="profile.py", stage="01",
        runner='run_profile(base_dir=os.getcwd())'),
    "02_synthesize.py": dict(module="synthesize.py", stage="02",
        runner='run_synthesize(run_dir=(sys.argv[1] if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]) else None), base_dir=os.getcwd())'),
    "03_compare.py": dict(module="compare.py", stage="03",
        runner='run_compare(run_dir=(sys.argv[1] if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]) else None), base_dir=os.getcwd())'),
}

HEADER = (
    "#!/usr/bin/env python3\n"
    "# -*- coding: utf-8 -*-\n"
    "# ============================================================================\n"
    "# AUTO-GENERATED self-contained script for stage %s - DO NOT EDIT BY HAND.\n"
    "# Source of truth: src/oissyntheticdata/  (regenerate: python tools/build_standalone.py)\n"
    "# Zero third-party dependencies - copy this single file into the environment.\n"
    "# ============================================================================\n"
)


def strip_imports_and_docstring(src):
    """Remove the leading module docstring and all top-level import lines
    (stdlib and relative), including parenthesised multi-line imports."""
    # drop leading module docstring
    src = re.sub(r'\A\s*(#![^\n]*\n)?(# -\*-[^\n]*\n)?\s*""".*?"""\s*', "",
                 src, count=1, flags=re.DOTALL)
    out, skip_until_paren = [], False
    for line in src.splitlines():
        if skip_until_paren:
            if ")" in line:
                skip_until_paren = False
            continue
        if re.match(r'^(import |from )', line):
            if "(" in line and ")" not in line:
                skip_until_paren = True
            continue
        out.append(line)
    return "\n".join(out).strip("\n")


def build(script_name, spec):
    common = strip_imports_and_docstring(open(os.path.join(SRC, "_common.py"), encoding="utf-8").read())
    io = strip_imports_and_docstring(open(os.path.join(SRC, "_io.py"), encoding="utf-8").read())
    stage = strip_imports_and_docstring(open(os.path.join(SRC, spec["module"]), encoding="utf-8").read())
    parts = [
        HEADER % spec["stage"],
        "\n".join(IMPORTS),
        "\nHERE = os.path.dirname(os.path.abspath(__file__))\n",
        "# ---- from oissyntheticdata._common ----",
        common,
        "\n# ---- from oissyntheticdata._io ----",
        io,
        "\n# ---- stage %s ----" % spec["stage"],
        stage,
        "\nif __name__ == \"__main__\":",
        "    " + spec["runner"],
        "",
    ]
    text = "\n".join(parts)
    with open(os.path.join(OUT, script_name), "w", encoding="utf-8") as f:
        f.write(text)
    return script_name


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, spec in STAGES.items():
        build(name, spec)
        print("[OK] wrote scripts/%s" % name)


if __name__ == "__main__":
    main()
