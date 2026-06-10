# -*- coding: utf-8 -*-
"""Tests for oissyntheticdata — run with:  python -m unittest -v  (or pytest)."""

import csv
import os
import random
import tempfile
import unittest

import oissyntheticdata


def _make_real(path, n=1200, seed=0):
    rng = random.Random(seed)
    types = ["disorder", "assault", "escape", "refuse"]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pid", "age", "offense", "violent", "sentence"])
        for i in range(n):
            t = rng.choice(types)
            violent = 1 if t in ("assault", "escape") else 0
            w.writerow([i + 1, rng.randint(18, 70), t, violent,
                        round(rng.uniform(1, 20), 1)])


class TestPurepop(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.real = os.path.join(self.dir, "real.csv")
        self.syn = os.path.join(self.dir, "syn.csv")
        _make_real(self.real)

    def _load(self, path):
        with open(path) as f:
            return list(csv.DictReader(f))

    def test_shape_and_columns(self):
        rows, cols = oissyntheticdata.synthesize_file(self.real, self.syn, drop=["pid"])
        self.assertEqual(cols, 4)            # pid dropped
        self.assertEqual(rows, 1200)
        syn = self._load(self.syn)
        self.assertEqual(set(syn[0].keys()), {"age", "offense", "violent", "sentence"})

    def test_preserves_conditional(self):
        oissyntheticdata.synthesize_file(self.real, self.syn, drop=["pid"], seed=1)
        syn = self._load(self.syn)
        # assault/escape are always violent in the real data; must hold ~exactly
        for r in syn:
            if r["offense"] in ("assault", "escape"):
                self.assertEqual(r["violent"], "1")

    def test_reproducible_seed(self):
        oissyntheticdata.synthesize_file(self.real, self.syn, drop=["pid"], seed=7)
        a = open(self.syn).read()
        oissyntheticdata.synthesize_file(self.real, self.syn, drop=["pid"], seed=7)
        b = open(self.syn).read()
        self.assertEqual(a, b)

    def test_row_count_override(self):
        rows, _ = oissyntheticdata.synthesize_file(self.real, self.syn, drop=["pid"], n=300)
        self.assertEqual(rows, 300)


if __name__ == "__main__":
    unittest.main()


class TestRelational(unittest.TestCase):
    def _build(self):
        rng = random.Random(0)
        inm_hdr = ["prisoner_id", "sector", "violent"]
        inm = {c: [] for c in inm_hdr}
        for pid in range(1, 401):
            v = rng.choice([0, 0, 1])
            inm["prisoner_id"].append(str(pid))
            inm["sector"].append(rng.choice(["A", "B", "C"]))
            inm["violent"].append(str(v))
        ju_hdr = ["judgement_id", "prisoner_id", "offense"]
        ju = {c: [] for c in ju_hdr}
        jid = 1
        for i in range(400):
            v = int(inm["violent"][i])
            k = rng.randint(2, 6) if v else rng.randint(0, 2)
            for _ in range(k):
                ju["judgement_id"].append(str(jid))
                ju["prisoner_id"].append(inm["prisoner_id"][i])
                ju["offense"].append("assault" if v else "fraud")
                jid += 1
        return (inm_hdr, inm), (ju_hdr, ju)

    def test_referential_integrity_and_link(self):
        import oissyntheticdata
        inm, ju = self._build()
        res = oissyntheticdata.synthesize_relational(
            {"inmates": inm, "judgements": ju},
            schema={"inmates": {"key": "prisoner_id"},
                    "judgements": {"key": "judgement_id",
                                   "parent": "inmates", "foreign_key": "prisoner_id"}},
            min_leaf=5, seed=2)
        (_, ic), (_, jc) = res["inmates"], res["judgements"]
        pks = set(ic["prisoner_id"])
        # every child foreign key points at a synthetic parent
        self.assertTrue(all(fk in pks for fk in jc["prisoner_id"]))
        # surrogate keys are unique
        self.assertEqual(len(set(ic["prisoner_id"])), len(ic["prisoner_id"]))
        # parent -> child link preserved: violent parents -> assault offenses
        vmap = {ic["prisoner_id"][i]: ic["violent"][i] for i in range(len(ic["prisoner_id"]))}
        for fk, off in zip(jc["prisoner_id"], jc["offense"]):
            if vmap.get(fk) == "1":
                self.assertEqual(off, "assault")
