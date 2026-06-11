# Quickstart

This walks the full pipeline on a tiny toy dataset so you can see each artefact.
Real or test data is never shipped with the package - generate or supply your own.

## 1. Make a toy dataset (stand-in for your real data)

```python
import csv, random
random.seed(0)
with open("people.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["person_id", "city", "joined", "score"])
    cities = ["Haifa", "Tel Aviv", "Jerusalem", "Eilat"]
    for i in range(1, 201):
        w.writerow([i, random.choice(cities),
                    "20%02d-%02d-%02d" % (random.randint(18, 23),
                                          random.randint(1, 12),
                                          random.randint(1, 28)),
                    round(random.gauss(50, 12), 2)])
```

## 2. INSIDE - profile the real data

```bash
oissyntheticdata profile people.csv
```

Writes `output/run_001_<date>/profile_people.json` and `profile_summary.md`.
Open the summary: numeric ranges are at P1/P99, small categories are hidden as
`RARE_###`, and `person_id` is recorded only as a unique key. This folder is what
leaves the secure environment.

## 3. OUTSIDE - synthesize from the profile only

```bash
oissyntheticdata synthesize
```

Writes `synthetic_people.csv` in the same run folder, built from the profile
alone. Same columns, types, ranges, levels and a `joined_month` companion - ready
for you to develop your analysis against.

## 4. INSIDE-ONLY control - check structural fidelity

```bash
oissyntheticdata compare
```

Writes `comparison_report.md` with a per-column agreement score and a fidelity
index. Columns below 0.80 are flagged for review before you trust the synthetic
bed.

## Python API equivalent

```python
import oissyntheticdata as oisd
run_dir, _ = oisd.profile(["people.csv"])
oisd.synthesize(run_dir=run_dir)
oisd.compare(run_dir=run_dir)
```
