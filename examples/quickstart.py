# -*- coding: utf-8 -*-
"""
quickstart.py — minimal end-to-end oissyntheticdata example.

Run from the repository root:
    python examples/quickstart.py

It builds a tiny dataset with a deliberate cross-column rule (assaults are
always violent), synthesizes it, and shows that the rule survives synthesis —
something a column-by-column *marginal* synthesizer cannot guarantee.
"""

import csv
import os
import random
import sys
import tempfile

# Make the example runnable from the repo root before `pip install`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import oissyntheticdata


def build_real(path, n=1000, seed=0):
    rng = random.Random(seed)
    offenses = ["disorder", "refusal", "assault", "escape", "incitement"]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["prisoner_id", "age", "offense", "violent", "sentence_years"])
        for i in range(n):
            off = rng.choice(offenses)
            violent = 1 if off in ("assault", "escape") else 0
            sentence = round(rng.uniform(1, 12) + (6 if violent else 0), 1)
            w.writerow([i + 1, rng.randint(18, 70), off, violent, sentence])


def conditional_rates(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    agg = {}
    for r in rows:
        agg.setdefault(r["offense"], [0, 0])
        agg[r["offense"]][0] += int(r["violent"])
        agg[r["offense"]][1] += 1
    return {k: round(v[0] / v[1], 2) for k, v in sorted(agg.items())}


def main():
    d = tempfile.mkdtemp()
    real = os.path.join(d, "real.csv")
    syn = os.path.join(d, "synthetic.csv")

    build_real(real)

    # Drop the direct identifier; keep a k=5 floor on every donor pool.
    rows, cols = oissyntheticdata.synthesize_file(
        real, syn, drop=["prisoner_id"], min_leaf=5, seed=1)
    print("synthesized %d rows x %d cols -> %s\n" % (rows, cols, syn))

    print("P(violent | offense)")
    print("  real     :", conditional_rates(real))
    print("  synthetic:", conditional_rates(syn))
    print("\nThe conditional structure is preserved by the CART step.")


if __name__ == "__main__":
    main()
