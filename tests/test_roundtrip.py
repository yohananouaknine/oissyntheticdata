# -*- coding: utf-8 -*-
"""
Round-trip / drift-guard test.

Generates a tiny relational dataset, runs the full pipeline twice - once through
the installed package, once through the standalone scripts in scripts/ - and
asserts the two produce identical synthetic data and identical comparison
scores. Also checks the core disclosure guarantees of the profile.
"""

import os
import csv
import sys
import json
import shutil
import random
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")


def _make_data(d):
    """A parent (unique key) and a child (fan-out key) that share prisoner_id."""
    random.seed(7)
    with open(os.path.join(d, "parent.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["prisoner_id", "city", "age", "label"])
        for i in range(1, 121):
            w.writerow([i, random.choice(["A", "B", "C", "D"]),
                        random.randint(18, 80),
                        ("rare" if i <= 2 else random.choice(["x", "y", "z"]))])
    with open(os.path.join(d, "child.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["event_id", "prisoner_id", "event_date", "kind"])
        eid = 1
        for pid in range(1, 121):
            for _ in range(random.randint(1, 6)):
                w.writerow([eid, pid,
                            "20%02d-%02d-%02d" % (random.randint(18, 23),
                                                  random.randint(1, 12),
                                                  random.randint(1, 28)),
                            random.choice(["m", "n"])])
                eid += 1


def _run_package(workdir):
    import oissyntheticdata as oisd
    run_dir, _ = oisd.profile(["parent.csv", "child.csv"], base_dir=workdir, quiet=True)
    oisd.synthesize(run_dir=run_dir, quiet=True)
    oisd.compare(run_dir=run_dir, base_dir=workdir, quiet=True)
    return run_dir


def _run_scripts(workdir):
    env = dict(os.environ, PYTHONPATH="")  # prove the scripts need no package
    for stage in ("01_profile.py", "02_synthesize.py", "03_compare.py"):
        subprocess.check_call([sys.executable, os.path.join(SCRIPTS, stage)],
                              cwd=workdir, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    runs = [d for d in os.listdir(os.path.join(workdir, "output")) if d.startswith("run_")]
    return os.path.join(workdir, "output", sorted(runs)[-1])


@pytest.mark.skipif(not os.path.isdir(SCRIPTS), reason="scripts/ not present")
def test_package_equals_standalone(tmp_path):
    pkg_dir = tmp_path / "pkg"
    scr_dir = tmp_path / "scr"
    pkg_dir.mkdir(); scr_dir.mkdir()
    _make_data(str(pkg_dir))
    for name in ("parent.csv", "child.csv"):
        shutil.copy(pkg_dir / name, scr_dir / name)

    pkg_run = _run_package(str(pkg_dir))
    scr_run = _run_scripts(str(scr_dir))

    # synthetic data and comparison scores must be byte-identical
    for base in ("parent", "child"):
        for kind in ("synthetic", "comparison"):
            a = os.path.join(pkg_run, "%s_%s.csv" % (kind, base))
            b = os.path.join(scr_run, "%s_%s.csv" % (kind, base))
            assert open(a, "rb").read() == open(b, "rb").read(), \
                "%s_%s.csv differs between package and standalone script" % (kind, base)


def test_profile_disclosure_guarantees(tmp_path):
    import oissyntheticdata as oisd
    _make_data(str(tmp_path))
    run_dir, reports = oisd.profile(["parent.csv", "child.csv"],
                                    base_dir=str(tmp_path), quiet=True)
    parent = json.load(open(os.path.join(run_dir, "profile_parent.json")))
    cols = {c["name"]: c for c in parent["columns"]}

    # unique key carries no values, only a length range
    assert cols["prisoner_id"]["kind"] == "identifier_unique"
    assert "len_min" in cols["prisoner_id"] and "frequencies" not in cols["prisoner_id"]

    # numeric column reports robust bounds, not raw rows
    assert cols["age"]["kind"] in ("integer", "float")
    assert "quantile_values" in cols["age"]

    # rare category is suppressed: the 'rare' label (count 1 < k=5) must not appear
    labels = list(cols["label"]["frequencies"].keys())
    assert "rare" not in labels
    assert any(l.startswith("RARE_") for l in labels)


def test_referential_integrity(tmp_path):
    import oissyntheticdata as oisd
    _make_data(str(tmp_path))
    run_dir, _ = oisd.profile(["parent.csv", "child.csv"],
                              base_dir=str(tmp_path), quiet=True)
    oisd.synthesize(run_dir=run_dir, quiet=True)
    _, _, integrity = oisd.compare(run_dir=run_dir, base_dir=str(tmp_path), quiet=True)
    # the shared prisoner_id link must hold with no broken (orphan) keys
    assert any("prisoner_id" in line for line in integrity)
    assert not any("BROKEN" in line for line in integrity)
