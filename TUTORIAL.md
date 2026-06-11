# Tutorial - synthetic data for your secure-environment study

*A practical, no-jargon guide to `oissyntheticdata` for researchers.*

You have sensitive data locked inside a secure environment, and an analysis to
write. The hard part isn't the statistics - it's that you can't comfortably
develop, debug and iterate on code while the real data sits behind a wall you're
not supposed to copy anything out of.

`oissyntheticdata` solves exactly that. It lets you build a **synthetic stand-in**
for your data that looks and behaves like the real thing structurally - same
columns, same types, same categories, same ranges, same joins - so you can
develop your whole analysis *outside* the secure environment, then run the
finished script *once* on the real data inside it.

You do not need to be a programmer to follow this. If you can run a command in a
terminal, you can use it.

---

## 1. The one picture to keep in your head

```
        INSIDE the secure room              OUTSIDE (your laptop)
        ─────────────────────               ─────────────────────
   ┌─────────────────────────┐
   │  your REAL data         │
   │         │               │
   │   ① profile  ───────────┼────────▶  a small "profile" file
   │                         │                    │
   │                         │             ② synthesize
   │                         │                    │
   │                         │            synthetic_data.csv
   │                         │                    │
   │                         │           …you write & debug your
   │                         │            whole analysis here…
   │                         │                    │
   │   ③ run your finished   │◀───────────  ONE finished script
   │      script on REAL data│
   └─────────────────────────┘
```

Two things - and only two - ever cross the wall:

1. On the way **out**: a *profile*. It is not your data. It is a page of
   summary numbers (averages, ranges, category counts) with the risky parts
   deliberately removed.
2. On the way **in**: your finished analysis script. Nothing else.

Your actual records never leave. That's the whole point, and it's what makes
your data owner comfortable.

---

## 2. What the synthetic data is for (and what it is *not*)

**It is for code-path coverage.** The synthetic file is engineered so your
analysis meets every situation it will meet on the real data: every category
(even the rare ones), every column type, missing values, the full range of each
number, dates across the right months, and joins between tables that line up.
If your script runs cleanly and correctly on the synthetic data, it will run on
the real data.

**It is *not* a source of results.** The synthetic numbers are made up. They are
realistic in *shape*, not in *value*. You never report a mean, a coefficient or
a p-value computed on synthetic data. Those come only from the real run inside.

> Rule of thumb: develop on synthetic, **report from real**.

> ## READ THIS FIRST
> **The synthetic data is ONLY for testing that your code runs.** Do not analyse
> it, do not run statistics or regressions on it, do not train models on it, and
> do not report any number from it. The numbers are deliberately meaningless;
> only their structure is real. If you run a regression here it will give you a
> confident-looking answer that means nothing. Every reported result must come
> from your finished code run on the real data, on-premises.

---

## 3. Setup (one minute)

If you have internet where you're developing:

```bash
pip install oissyntheticdata
```

Inside a locked environment with no internet and no `pip`? You don't need to
install anything. Copy the four files from the `scripts/` folder onto the
machine and run them directly - they use only Python's standard library and have
zero dependencies.

Check it's there:

```bash
oissyntheticdata --version
```

Throughout this guide you can use either form - they do the same thing:

| Friendly command | Same as |
|---|---|
| `oissyntheticdata profile …` | `python -m oissyntheticdata profile …` |
| `oissd profile …` | (short alias) |

---

## 4. A complete walk-through

Let's use a tiny made-up dataset so you can see every step and every file it
produces. (Your real data replaces this - the steps are identical.)

Make a folder and a small CSV called `study.csv`:

| participant_id | site | age | enrolled | outcome_score |
|---|---|---|---|---|
| 1 | Haifa | 34 | 2021-03-05 | 12.4 |
| 2 | Tel Aviv | 51 | 2021-07-19 | 9.8 |
| … | … | … | … | … |

(If you'd like to generate one to practice with, paste this into a file
`make.py` and run `python make.py`:)

```python
import csv, random
random.seed(1)
sites = ["Haifa", "Tel Aviv", "Jerusalem", "Eilat"]
with open("study.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(
        ["participant_id", "site", "age", "enrolled", "outcome_score"])
    for i in range(1, 301):
        w.writerow([i, random.choice(sites), random.randint(18, 85),
                    "20%02d-%02d-%02d" % (random.randint(19, 23),
                                          random.randint(1, 12),
                                          random.randint(1, 28)),
                    round(random.gauss(10, 3), 1)])
```

### Step ① - INSIDE: profile the real data

Run this *inside* the secure environment, in the folder with your data:

```bash
oissyntheticdata profile study.csv
```

It creates a folder `output/run_001_<today>/` containing two files:

- `profile_study.json` - the machine-readable profile (this is what goes out).
- `profile_summary.md` - a human-readable summary you and the data owner can
  read together before anything leaves.

Open `profile_summary.md`. You'll see one row per column, for example:

| Column | Type | Missing % | Distinct | Notes |
|---|---|---|---|---|
| participant_id | identifier_unique | 0.0% | 300 | unique key, len 1-3 |
| site | categorical | 0.0% | 4 | 4 levels (0 rare hidden) |
| age | integer | 0.0% | 60 | range≈[19, 84], mean=51.2 |
| enrolled | datetime | 0.0% | … | 2019-01-… → 2023-12-… |
| outcome_score | float | 0.0% | … | range≈[3.1, 17.0], mean=10.0 |

**Look at what is - and isn't - in there.** This is the part to show your data
owner:

- `participant_id` is recorded only as *"a unique key, 1–3 characters"*. No ID
  value is listed.
- `site` keeps its category names and counts - but any category with fewer than
  **5** people would be hidden and shown as `RARE_001` (its count kept, its name
  dropped). Small groups can't be singled out.
- `age` and `outcome_score` report a mean and a range, but the range is the
  **1st–99th percentile**, not the true minimum and maximum - so a single
  unusual outlier can't leak through the "max".
- Free-text or code columns (none here) would be reduced to a *shape* like
  `DD-DDDDDD`, never the actual values.

That summary, and the `.json` beside it, is the only thing that leaves. Hand the
`output/run_001_<today>/` folder out of the environment.

### Step ② - OUTSIDE: build the synthetic data

On your laptop, in the folder that now holds the profile:

```bash
oissyntheticdata synthesize
```

This reads the profile **only** and writes `synthetic_study.csv` next to it. Open
it: same columns, same types, sites in roughly the right proportions, ages in the
right range, dates spread across the right months, an `enrolled_month` helper
column for seasonality, and made-up participant IDs.

This is your sandbox. Point your analysis script at `synthetic_study.csv` and
build everything - cleaning, filtering, joins, models, tables, figures - until it
runs end to end without errors and the outputs look sensible. Iterate as much as
you like; there's nothing sensitive here.

### Step ③ - INSIDE (a quick check): does the synthetic match?

Before you trust your sandbox, it's worth confirming the synthetic data is
structurally close to the real data. Back inside, run:

```bash
oissyntheticdata compare
```

This is a **control step the data owner runs**, not part of your analysis - it
peeks at the real data to score the match, and only the scores leave. It writes
`comparison_report.md`:

```
## `study`  -  fidelity index 0.95  (flagged: 0)

| Column        | Method   | Agreement | Note                         |
|---------------|----------|-----------|------------------------------|
| site          | kappa*   | 0.97      | overlap 0.98, coverage 100%  |
| age           | 1 - KS   | 0.96      | mean drift 0.4%              |
| outcome_score | 1 - KS   | 0.94      | mean drift 0.8%              |
| enrolled      | 1-KS date| 0.93      | date trend+season            |
```

How to read it:

- **Agreement** runs 0–1; higher is closer. Roughly: above ~0.9 is excellent,
  0.8–0.9 is fine, below **0.80** gets **flagged** for a look.
- A flag doesn't mean something is broken - it means "the synthetic shape for
  this column is a bit off, so double-check any code path that leans heavily on
  it." Often it's a highly skewed variable; usually harmless for code coverage.
- The **fidelity index** is just the average across columns - a one-glance health
  score.

### Step ④ - INSIDE: the real run

When your script runs clean on synthetic and the comparison looks good, carry
**only the finished script** back into the secure environment and run it on the
real data. The numbers it produces now are your actual results - the ones you
report.

That's the full loop.

---

## 5. Working with several tables (relational data)

Real studies often span linked tables - say `participants.csv` (one row per
person) and `visits.csv` (many rows per person). Profile them together:

```bash
oissyntheticdata profile participants.csv visits.csv
oissyntheticdata synthesize
oissyntheticdata compare
```

The tool notices that, e.g., `participant_id` is a **unique key** in
`participants` and a **linking key** in `visits`, and builds the synthetic tables
so the links still hold: every synthetic visit points to a synthetic participant
that exists. The comparison report ends with a **referential integrity** check
confirming there are no "orphan" links. Your joins will behave on the real data
exactly as they did on the synthetic.

For a linking key like `participant_id`, the profile keeps only the *distribution
of how many rows each person has* - never a specific person tied to their count.

---

## 6. The five golden rules

1. **Only the profile leaves; only the script comes back.** Never carry data
   either way.
2. **Never report synthetic numbers.** Results come from the real run, full stop.
3. **Read `profile_summary.md` before anything leaves.** It's your disclosure
   receipt - and a good habit with your data owner.
4. **Treat `compare` as the data owner's control**, run inside. It's a structural
   check, not a privacy guarantee and not a results check.
5. **Keep the four files small and auditable.** That's deliberate - anyone can
   read them in full and see there's no magic.

---

## 7. Good-to-know details

- **Dates & seasonality.** For every date column the tool adds a companion
  `<date>_month` column (1–12) so monthly patterns survive into the synthetic
  data. If you want these on a non-pipeline file too, run
  `oissyntheticdata add-month yourfile.csv`.
- **Rare categories.** Anything appearing fewer than 5 times is hidden behind a
  `RARE_###` label (count kept). The synthesizer still emits at least one row of
  each, so your "what about the rare group?" code path is exercised.
- **Missing values.** Missingness rates are preserved, so your handling of blanks
  gets tested.
- **Reproducible.** Synthesis is seeded, so the same profile always yields the
  same synthetic file. Re-running `synthesize` won't move things under you.
- **Excel files.** CSV and `.xlsx` both work as input - no Excel or extra
  libraries needed.
- **It scales down, not just up.** Tiny test extracts work fine; you don't need
  the full dataset to profile.

---

## 8. Cheat sheet

```bash
# 0. (optional) add month columns to any file
oissyntheticdata add-month data.csv

# 1. INSIDE  - write the disclosure-safe profile (one or many files)
oissyntheticdata profile data.csv
oissyntheticdata profile participants.csv visits.csv      # relational

# 2. OUTSIDE - build the synthetic sandbox from the profile only
oissyntheticdata synthesize

# 3. INSIDE  - data owner's structural fidelity check
oissyntheticdata compare
```

Same three calls from Python, if you prefer:

```python
import oissyntheticdata as oisd
run_dir, _ = oisd.profile(["data.csv"])     # INSIDE
oisd.synthesize(run_dir=run_dir)            # OUTSIDE
oisd.compare(run_dir=run_dir)               # INSIDE (control)
```

---

That's it. Profile inside, build and debug outside, run the finished script
inside. Develop on synthetic, **report from real** - and your data never leaves
the room.

*Questions or trouble? Open an issue at
https://github.com/yohananouaknine/oissyntheticdata/issues (please never attach
real data).*
