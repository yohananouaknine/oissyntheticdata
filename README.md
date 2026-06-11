# oissyntheticdata

**Profile-based synthetic data for secure research environments.**
Zero third-party dependencies; Python standard library only.

> An **OIS** tool · [ois.co.il](https://ois.co.il) · maintained by Dr Yohanan Ouaknine
> ([ORCID 0000-0002-4186-7351](https://orcid.org/0000-0002-4186-7351))

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20632932.svg)](https://doi.org/10.5281/zenodo.20632932)

A sensitive dataset never leaves the secure environment. Instead, a
**disclosure-safe profile** of it crosses the boundary, and the synthesizer
rebuilds a structurally faithful *synthetic* copy **from the profile alone**, so
it never sees the real data. You develop and debug your analysis off-site on the
synthetic copy, then run the final, unchanged script on the real data
on-premises and release only vetted aggregate results.

> **New to this and just want to use it?** Start with the
> [researcher tutorial](TUTORIAL.md), a plain-language, end-to-end walk-through.

> ## READ THIS FIRST
> **The synthetic data is ONLY for testing that your code runs.** It exists so
> your script executes end to end: types line up, joins resolve, every category
> and edge case appears, nothing throws an error. **Do not analyse it.** Do not
> run statistics or regressions on it, do not fit or train models on it, and do
> not report any number from it. The numbers are deliberately meaningless; only
> their structure is real. Every result you report must come from running your
> finished, unchanged code on the real data, on-premises.

```
   INSIDE (real data)            OUTSIDE (no real data)          INSIDE (control)
   ..................            ......................          ................
   01 profile        --->        02 synthesize        ..>        03 compare
   real  -->  profile            profile  -->  synthetic         real vs synthetic
   (the ONLY artefact            (never reads the real           structural fidelity
    that leaves)                  data)                           + referential integrity
```

Only two things ever cross the boundary, each after the data owner authorises
it: the **profile** (going out) and, at the very end, your **aggregate results**
(coming back). The microdata stays put.

## Provenance

The disclosure-control concept this tool implements (develop your analysis on
disclosure-safe synthetic data, then run the final code on the real data in
place) was first applied in research at the Israel Prison Service research unit,
in a study of terrorist recidivism following the 2011 Shalit prisoner exchange,
under Research Committee authorization. This package is a later, general, open
implementation of that concept; the package itself was not used in that research.
OIS offers deployment, validation, and training services to government research
units and academic researchers around the open core.

## Why

Secure research environments forbid `pip`/`conda` and have no internet. This
package installs by copying one directory, runs on the standard library alone,
and is small enough for a data owner to read and audit in full. The synthetic
data is built for **code-path coverage**: every branch, filter, join and edge
case your analysis will hit on the real data, not statistical realism. Synthetic
numbers are never reported.

A higher-fidelity, joint-distribution synthesizer (sequential CART, in the
`synthpop` tradition) reproduces conditional relationships but must read the real
microdata, so it can only run on-premises. This profile pipeline takes the
opposite trade: lower joint fidelity in exchange for a stronger, simpler
boundary, because the component that leaves the environment never touched a real
record.

## Install

```bash
pip install oissyntheticdata
```

Or, for a locked environment with no internet: copy the four files in
[`scripts/`](scripts/) onto the machine and run them directly. No install, no
dependencies. Python 3.7+.

## The four stages

| Stage | Where | Reads real data? | Output |
|---|---|---|---|
| `00 add-month` | anywhere | no | `<file>_with_month.csv` (derives `<date>_month`) |
| `01 profile` | **inside** | yes | `profile_<base>.json`, `profile_summary.md` |
| `02 synthesize` | **outside** | **no** | `synthetic_<base>.csv` |
| `03 compare` | **inside only** | yes | `comparison_report.md`, `comparison_<base>.csv` |

`03 compare` is an inside-the-premises **control**, not a researcher step: it
reads the real data to confirm the synthetic bed is faithful enough, and only
column-level scores leave. It is never run off-site.

## Command line

```bash
# INSIDE: write a disclosure-safe profile of the real data (one or many files)
oissyntheticdata profile inmates.csv incidents.csv judgements.csv

# OUTSIDE: rebuild synthetic data from the profile only (acts on the newest run)
oissyntheticdata synthesize

# INSIDE-ONLY control: structural fidelity + cross-file referential integrity
oissyntheticdata compare
```

Stage 01 creates `output/run_NNN_YYYY-MM-DD/`; stages 02 and 03 act on the
newest run folder by default (or pass an explicit one). `oissd` is a short
alias, and `python -m oissyntheticdata ...` works too.

## Python API

```python
import oissyntheticdata as oisd

# INSIDE
run_dir, reports = oisd.profile(["inmates.csv", "incidents.csv"], base_dir="work")

# OUTSIDE (profile only)
oisd.synthesize(run_dir=run_dir)

# INSIDE-ONLY control
run_dir, fidelity, integrity = oisd.compare(run_dir=run_dir, base_dir="work")
```

## What the profile keeps (and hides)

The profile is the whole privacy posture. Per column it keeps a *shape*, never
identifiable values:

- **Unique integer key:** only "this is a unique key" plus a length range.
- **Fan-out / foreign key** (e.g. `prisoner_id`): only the *distribution* of
  group sizes; never an id tied to its count.
- **Numeric:** mean, standard deviation, and a quantile grid, with **robust
  bounds** (P1/P99 stand in for the true min/max so extremes do not leak).
- **Categorical:** level frequencies, but any level with fewer than `k` records
  (default `k = 5`) is relabelled `RARE_###`, count kept, label dropped.
- **High-cardinality text / id:** only a format signature (e.g. `DD-DDDDDD`) and
  a length range. Values are never enumerated.
- **Dates:** format, range, per-year and per-month shape (for seasonality).

Across files, columns that are key-like in two or more profiles become shared
relational keys, so the synthetic children join correctly onto the synthetic
parent.

## Relational example

```bash
oissyntheticdata profile inmates.csv incidents.csv judgements.csv
oissyntheticdata synthesize
oissyntheticdata compare
```

`inmates` is the parent (`prisoner_id` unique); `incidents` and `judgements`
are children sharing `prisoner_id` and `incident_id`. The synthesizer mints one
shared key pool per shared key, so synthetic child keys are a subset of the
synthetic parent keys. `compare` reports referential integrity (orphan keys, if
any) alongside per-column fidelity.

## Rebuilding joined or merged files

Stage 01 detects the relationships between your files from the data itself. A
shared column is treated as a link only when one file holds it uniquely (the
parent) and another file's values are a repeating subset of it (the child); this
is type-agnostic, so integer keys, string ids, and dates are all found, and a
column that merely shares a name but is a plain attribute is ignored. The
detected schema is printed and written to `schema.json` (names and fan-out
quantiles only, so it is disclosure-safe). If detection ever picks the wrong
parent on an unusual schema, you can override it.

Stage 02 then synthesizes in parent-before-child order and attaches each child
row to a real synthetic parent, copying the link column and any inherited
columns from that parent. This gives three things at once:

- Referential integrity: every synthetic child key resolves to a synthetic
  parent, so a group-by or a single-key join runs with zero orphan keys, and you
  can rebuild a merged or aggregated table from the synthetic files exactly as
  you would from the real ones.
- Realistic fan-out: the number of children per parent follows the real
  group-size distribution.
- Within-row key pairing: when a child carries a second key that the real data
  shows is fixed by its parent (for example a judgement's `prisoner_id` is fixed
  once its `incident_id` is known), that key is inherited from the matched
  parent, so the pairing is exact. A judgement's incident now belongs to that
  judgement's prisoner, not just to some valid prisoner.

This supports both the hierarchical model (files describing facets of one object,
merged at synthesis time) and the simple shared-id model (several files that the
research unit merges by grouping on a common id to check their interpretation).

## Confidentiality model

- **`k` (min cell count, default 5):** no categorical level, fan-out estimate,
  or surrogate key is reported from fewer than `k` real records, so nothing in
  the profile is traceable to one person.
- **Robust bounds:** numeric extremes are reported at P1/P99, not the true
  min/max, so a single outlier cannot leak through the range.
- **Identifiers are never enumerated:** only a format signature and length range
  leave; the synthesizer mints fresh keys.
- **Only the profile leaves; the real data never does.** Develop on the synthetic
  copy off-site, run final code on the real data in place, release only vetted
  aggregates.

`oissyntheticdata` is a disclosure-control aid, not a formal privacy guarantee. For a
mathematical guarantee, combine it with differential privacy or apply output
checking (statistical disclosure control) to anything released.

## How the standalone scripts are built

`scripts/00` to `scripts/03` are **auto-generated** from `src/oissyntheticdata/`
by `tools/build_standalone.py`, inlining the shared `_common` and `_io` modules
so each script is a single self-contained file. The package and the standalone
scripts therefore produce identical output; `tests/test_roundtrip.py` enforces
that they stay in sync.

## Government use of synthetic data

The develop-on-synthetic, run-on-real workflow is established practice at
national statistical agencies:

- U.S. Census Bureau, SIPP Synthetic Beta (SSB): researchers develop code on
  synthetic linked survey and administrative data, and Census staff run the
  validated code on the confidential data and release only vetted output.
  <https://census.gov/programs-surveys/sipp/guidance/sipp-synthetic-beta-data-product.html>
- U.S. Census Bureau, OnTheMap and LEHD LODES: the first production deployment of
  formal privacy (2008), built on partially synthetic origin-destination data.
  <https://lehd.ces.census.gov/>
- U.S. Census Bureau, "What Are Synthetic Data?" (2021 factsheet), covering the
  Longitudinal Business Database, SIPP, OnTheMap, and 2020 Decennial Census uses.
  <https://www.census.gov/content/dam/Census/library/factsheets/2021/what-are-synthetic-data/what-are-synthetic-data.pdf>

## Governance, support and contributing

`oissyntheticdata` is maintained in the open under the MIT license. Questions, bug
reports, and change proposals go through public GitHub Issues and Pull Requests;
see [`CONTRIBUTING.md`](CONTRIBUTING.md). Decisions are made by the maintainer(s)
listed in [`CITATION.cff`](CITATION.cff) via the public issue/PR process. There
is no private support channel; keeping development and discussion public is part
of the project's auditability goal. Releases are versioned and recorded in
[`CHANGELOG.md`](CHANGELOG.md).

## Generative AI disclosure

A generative AI assistant (Claude, Anthropic) was used to help draft and refactor
parts of the code and documentation. All output was reviewed, tested, and edited
by the author(s), who take full responsibility for the design, correctness, and
integrity of the software. Contributors are asked to disclose non-trivial AI
assistance (see `CONTRIBUTING.md`).

## Maintainer

Dr **Yohanan Ouaknine**, OIS ([ois.co.il](https://ois.co.il)),
[yohanan.ouaknine@ois.co.il](mailto:yohanan.ouaknine@ois.co.il),
[ORCID 0000-0002-4186-7351](https://orcid.org/0000-0002-4186-7351).
formerly Head of the Research Branch, Israel Prison Service.

## License

MIT (c) 2026 Yohanan Ouaknine and OIS. See [LICENSE](LICENSE).
If you use this software in research, please cite it; see
[CITATION.cff](CITATION.cff).
