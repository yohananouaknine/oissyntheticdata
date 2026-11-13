# -*- coding: utf-8 -*-
"""The whole flow on a small invented folder: profile -> JSON -> synthetic -> toolbox.

    python -m unittest discover -s tests          (standard library only)
"""
import csv
import glob
import io
import json
import os
import random
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isfile(os.path.join(ROOT, "gov_one.py")):
    sys.path.insert(0, ROOT)                     # run from the source folder; otherwise the installed module
import gov_one as g

FIRST = ["Dana", "Omar", "Noa", "Yosef", "Lina", "Avi", "Sara", "Karim"]
LAST = ["Levi", "Cohen", "Haddad", "Mizrahi", "Peretz", "Nasser"]


def make_folder(folder, n=400, seed=7):
    rnd = random.Random(seed)
    clients, cases = [], []
    for i in range(n):
        district = rnd.choice(["North", "Centre", "South"])
        kind_w = {"North": [5, 2, 1], "Centre": [2, 5, 2], "South": [1, 2, 6]}[district]
        clients.append({"client_id": 10000 + i, "id_number": "%09d" % rnd.randrange(10 ** 9),
                        "full name": "%s %s" % (rnd.choice(FIRST), rnd.choice(LAST)),
                        "district": district, "age": rnd.randint(18, 90),
                        "town": "Rareville" if i < 2 else rnd.choice(["Alpha", "Beta", "Gamma", "Delta"])})
        for _ in range(rnd.choice([0, 1, 1, 2, 3])):
            cases.append({"case_no": 50000 + len(cases), "client_id": 10000 + i,
                          "case_type": rnd.choices(["aid", "youth", "elderly"], weights=kind_w)[0],
                          "opened": "2023-%02d-%02d" % (rnd.randint(1, 12), rnd.randint(1, 28)),
                          "amount": round(rnd.uniform(100, 5000), 2)})
    for name, rows in (("clients", clients), ("cases", cases)):
        with open(os.path.join(folder, name + ".csv"), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    return clients, cases


def quiet(fn, *a, **k):
    with redirect_stdout(io.StringIO()):
        return fn(*a, **k)


class Flow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="gov_one_test_")
        cls.prem, cls.home = os.path.join(cls.tmp, "premises"), os.path.join(cls.tmp, "home")
        os.makedirs(cls.prem)
        os.makedirs(cls.home)
        cls.clients, cls.cases = make_folder(cls.prem)
        quiet(g.main, ["profile", "--data", cls.prem])
        shutil.copytree(os.path.join(cls.prem, "to_send"), os.path.join(cls.home, "to_send"))
        quiet(g.main, ["synth", "--data", cls.home])
        cls.sent = ""
        for p in glob.glob(os.path.join(cls.prem, "to_send", "*")):
            with open(p, encoding="utf-8") as f:
                cls.sent += f.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_nothing_identified_leaves(self):
        numbers = set(re.findall(r"\d+", self.sent))
        self.assertFalse({c["id_number"] for c in self.clients} & numbers, "an id number is in the files to send")
        self.assertFalse({str(c["client_id"]) for c in self.clients} & numbers, "a client key is in the files to send")
        self.assertFalse({str(c["case_no"]) for c in self.cases} & numbers, "a case key is in the files to send")
        for c in self.clients:
            self.assertNotIn(c["full name"], self.sent)
        self.assertNotIn("Rareville", self.sent, "a label seen twice kept its name")

    def test_no_small_count(self):
        small = []

        def walk(o):
            if isinstance(o, dict):
                for key, v in o.items():
                    if key in ("frequencies", "value_freqs", "ym_freqs") and isinstance(v, dict):
                        small.extend(x for x in v.values() if isinstance(x, (int, float)) and 0 < x < 5)
                    elif key == "cells" and isinstance(v, dict):
                        small.extend(x for d in v.values() for x in d.values() if 0 < x < 5)
                    else:
                        walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        for p in glob.glob(os.path.join(self.prem, "to_send", "*.json")):
            with open(p, encoding="utf-8") as f:
                walk(json.load(f))
        self.assertEqual(small, [])

    def test_dates_keep_the_month_only(self):
        real_days = {c["opened"] for c in self.cases}
        found = set(re.findall(r"2023-\d{2}-\d{2}", self.sent))
        self.assertFalse({d for d in found & real_days if d[8:] not in ("01", "28", "29", "30", "31")})

    def test_synthetic_has_the_same_shape(self):
        real, syn = quiet(g.open_tables, self.prem), quiet(g.open_tables, self.home)
        self.assertEqual(sorted(real), sorted(syn))
        for name in real:
            self.assertEqual(real[name].header, syn[name].header)
            self.assertEqual(len(real[name]), len(syn[name]))
        keys = set(syn["clients"].col("client_id"))
        self.assertTrue(all(v in keys for v in syn["cases"].col("client_id")), "a synthetic case points to no client")
        self.assertFalse({c["id_number"] for c in self.clients} & set(syn["clients"].col("id_number")))

    def test_link_and_dependence_survive(self):
        syn = quiet(g.open_tables, self.home)
        rows = g.join(syn["cases"].rows, syn["clients"].rows, on="client_id")
        res = g.chi_square(g.crosstab(rows, "district", "case_type")[2])
        self.assertLess(res["p"], 0.001, "case type no longer depends on the client's district")

    def test_toolbox(self):
        self.assertAlmostEqual(g.p_chi2(3.841, 1), 0.05, places=3)
        self.assertAlmostEqual(g.p_t(2.776, 4), 0.05, places=3)
        self.assertEqual(g.safe(3), "<5")

    def test_same_module_under_the_pip_name(self):
        try:
            import oissyntheticdata as o
        except ImportError:
            self.skipTest("the oissyntheticdata wrapper is not importable here")
        self.assertIs(o.open_tables, g.open_tables)
        self.assertEqual(o.__version__, g.VERSION.split()[1])


if __name__ == "__main__":
    unittest.main()
