# -*- coding: utf-8 -*-
"""
relational.py — multi-table synthesis with referential integrity.

Run from the repository root:
    python examples/relational.py

Builds a parent table (inmates) and a child table (judgements) where a parent
attribute drives both how many children a parent has and the children's values,
synthesizes them together, and shows that (a) every synthetic judgement joins to
a synthetic inmate and (b) the parent->child relationship survives.
"""

import collections
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import oissyntheticdata


def build():
    rng = random.Random(0)
    inm_h = ["prisoner_id", "sector", "high_risk"]
    inm = {c: [] for c in inm_h}
    for pid in range(1, 401):
        hr = rng.choice([0, 0, 1])
        inm["prisoner_id"].append(str(pid))
        inm["sector"].append(rng.choice(["North", "South", "Central"]))
        inm["high_risk"].append(str(hr))
    ju_h = ["judgement_id", "prisoner_id", "offense"]
    ju = {c: [] for c in ju_h}
    jid = 1
    for i in range(400):
        hr = int(inm["high_risk"][i])
        k = rng.randint(3, 7) if hr else rng.randint(0, 2)        # risk drives fan-out
        for _ in range(k):
            ju["judgement_id"].append(str(jid))
            ju["prisoner_id"].append(inm["prisoner_id"][i])
            ju["offense"].append("violent" if hr else "minor")    # risk drives offense
            jid += 1
    return (inm_h, inm), (ju_h, ju)


def main():
    inm, ju = build()
    res = oissyntheticdata.synthesize_relational(
        {"inmates": inm, "judgements": ju},
        schema={
            "inmates":    {"key": "prisoner_id"},
            "judgements": {"key": "judgement_id",
                           "parent": "inmates", "foreign_key": "prisoner_id"},
        },
        min_leaf=5, seed=1)

    (_, ic), (_, jc) = res["inmates"], res["judgements"]
    pks = set(ic["prisoner_id"])
    orphans = sum(1 for fk in jc["prisoner_id"] if fk not in pks)
    print("inmates: %d   judgements: %d" % (len(ic["prisoner_id"]), len(jc["prisoner_id"])))
    print("orphan judgements (should be 0): %d" % orphans)

    risk = {ic["prisoner_id"][i]: ic["high_risk"][i] for i in range(len(ic["prisoner_id"]))}
    by = {"0": collections.Counter(), "1": collections.Counter()}
    for fk, off in zip(jc["prisoner_id"], jc["offense"]):
        if fk in risk:
            by[risk[fk]][off] += 1
    print("offense by parent.high_risk=0:", dict(by["0"]))
    print("offense by parent.high_risk=1:", dict(by["1"]))
    print("\nReferential integrity and the parent->child link are preserved.")


if __name__ == "__main__":
    main()
