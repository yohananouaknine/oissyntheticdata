# oissyntheticdata

**Pure-Python sequential CART synthesis — in the `synthpop` tradition, with zero third-party dependencies.**

> An **OIS** tool · [ois.co.il](https://ois.co.il) · maintained by Dr Yohanan Ouaknine
> ([ORCID 0000-0002-4186-7351](https://orcid.org/0000-0002-4186-7351))

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20632932.svg)](https://doi.org/10.5281/zenodo.20632932)

`oissyntheticdata` generates a synthetic copy of a sensitive dataset that preserves the
*relationships between variables*, not just each column's marginal shape. It is
built for the secure-research workflow used by statistical agencies: **develop
and debug your analysis on the synthetic data off-site, then run the final code
on the real data on-premises and release only vetted aggregate results.**

It imports only the Python standard library (`csv`, `json`, `math`, `random`,
`statistics`, `zipfile`, `xml.etree`), so it can run inside a locked secure
environment with no `pip install` and is small enough to read and audit in full.

The approach was first deployed in a secure justice-research setting (a study of
terrorist recidivism after the 2011 Shalit prisoner exchange, run on-premises at
the Israel Prison Service under Research Committee authorization); this package
generalises and opens it. OIS offers deployment, validation, and training services
to government research units and academic researchers around the open core.

---

## Why this exists

This follows a well-established paradigm in statistical disclosure control. The
synthetic data is *test data* that should resemble the real data closely but is
never used for final inference; the code developed on it is what gets run on the
confidential data (Nowok, Raab & Dibben 2016; US Census Bureau SIPP Synthetic
Beta). `oissyntheticdata` is a dependency-free re-implementation of the core engine those
tools use — **sequential CART synthesis** (Reiter 2005) — packaged for locked
environments.

It complements a metadata-only synthesizer (which preserves each column's shape
but not the joint structure): `oissyntheticdata` fits on the real microdata on-premises
and therefore reproduces conditional relationships, at the cost of touching raw
records (so it must run inside the secure environment).

---

## How it works (the engine)

Synthesis proceeds **one column at a time** in a chosen visit order:

1. **First column** — drawn from its own empirical marginal, with cells smaller
   than `min_leaf` suppressed.
2. **Each later column `Y`** — a CART (classification tree if `Y` is categorical,
   regression tree if continuous) is grown on the **real data** to predict `Y`
   from the columns already synthesized. Every leaf keeps the list of *real*
   `Y` values that reached it (its "donors").
3. **Drawing** — for each synthetic row, route it down the tree using the values
   already generated for that row, reach a leaf, and **sample a donor** from that
   leaf (optionally jittered for continuous columns). Sampling from donors — not
   predicting a point — is what reproduces the conditional distribution.

Because each column is predicted from the previously synthesized columns, the
joint distribution is assembled sequentially (the standard `synthpop` approach).

```
visit:  c1 -> c2 -> c3 -> ...
c1 ~ marginal(c1)
c2 ~ leaf_donor( CART(c2 ~ c1) , synthetic c1 )
c3 ~ leaf_donor( CART(c3 ~ c1,c2) , synthetic c1,c2 )
...
```

---

## Confidentiality model

- **`min_leaf` (k, default 5):** no leaf and no marginal cell is built from fewer
  than `k` real records, so every drawn value blends ≥ k individuals and is never
  traceable to one person. This also caps tree depth and prevents the tree from
  memorizing individuals.
- **`smoothing` (default 0):** optional Gaussian jitter on continuous donors,
  bounded to the leaf's range, so exact real values are not echoed verbatim.
- **`drop`:** direct identifiers (national ID, names, record keys) should be
  dropped before synthesis — `oissyntheticdata` does not attempt to anonymize them.
- **Only synthetic data leaves; the real data never does.** The intended use is
  to take the synthetic file off-site for development and re-run final code on the
  real data in place.

`oissyntheticdata` is a disclosure-control aid, not a formal privacy guarantee. For a
mathematical guarantee, combine it with differential privacy or apply output
checking (statistical disclosure control) to anything released.

---

## Design decisions and trade-offs

The value of `oissyntheticdata` is in its design choices, which are deliberately narrow:

- **Where the synthesizer may run is a first-class concern.** `oissyntheticdata` fits on
  real microdata to preserve joint structure, so it runs *on-premises*; only the
  synthetic output leaves. A metadata-only synthesizer can run off-site but
  preserves only per-column structure. Choosing fidelity-with-on-prem-execution
  over portability-with-lower-fidelity is intentional, and the two roles are kept
  as separate tools so the confidentiality reasoning stays explicit.
- **Donor-leaf sampling, not point prediction.** Drawing a real value from the
  matching leaf reproduces the conditional distribution; predicting a mean would
  not.
- **One confidentiality invariant.** `min_leaf` (`k`) applies the same `k`-record
  floor to every marginal cell, tree leaf, fan-out estimate, and surrogate key,
  instead of scattering ad hoc thresholds.
- **Relational by conditioning, not joining.** Children are synthesized
  conditioned on the parent's synthetic attributes and linked by surrogate keys,
  preserving referential integrity without materialising a real join.
- **Build on, don't reinvent.** The estimator is the established CART-synthesis
  method; the new work is the dependency-free, auditable, relational realisation
  for locked environments.

Scope boundaries are equally deliberate: single-parent schemas only, no enforced
high-order interactions or arithmetic identities, and no formal privacy guarantee
(see Limitations).

## Governance, support & contributing

`oissyntheticdata` is maintained in the open under the MIT license. Questions, bug reports,
and change proposals go through public GitHub Issues and Pull Requests; see
[`CONTRIBUTING.md`](CONTRIBUTING.md). Decisions are made by the maintainer(s)
listed in [`CITATION.cff`](CITATION.cff) via the public issue/PR process. There is
no private support channel — keeping development and discussion public is part of
the project's auditability goal. Releases are versioned and recorded in
[`CHANGELOG.md`](CHANGELOG.md).

## Generative AI disclosure

A generative AI assistant (Claude, Anthropic) was used to help draft and refactor
parts of the code and documentation. All output was reviewed, tested, and edited
by the author(s), who take full responsibility for the design, correctness, and
integrity of the software. The design decisions and abstractions above, and the
testing and documentation practices, are the author(s)' own. Contributors are
asked to disclose non-trivial AI assistance (see `CONTRIBUTING.md`).

## Install

```bash
pip install oissyntheticdata
# or, in a locked environment, just copy the oissyntheticdata/ folder next to your code
```

No dependencies. Python 3.7+.

## Usage

Command line:

```bash
python -m oissyntheticdata real.csv -o synthetic.csv --drop national_id --min-leaf 5
python -m oissyntheticdata data.xlsx -o synthetic.csv --visit "age,offense,violent" --smoothing 0.5
```

Library:

```python
import oissyntheticdata

# one call
oissyntheticdata.synthesize_file("real.csv", "synthetic.csv",
                        drop=["national_id"], min_leaf=5)

# or step by step
header, cols = oissyntheticdata.read_table("real.xlsx")
out_header, out_cols = oissyntheticdata.synthesize(header, cols,
                                          drop=["national_id"], min_leaf=5)
oissyntheticdata.write_table("synthetic.csv", out_header, out_cols)
```

Key parameters: `n` (rows, default = real), `visit` (column order),
`drop` (identifiers to exclude), `min_leaf` (k), `max_depth`, `smoothing`, `seed`.

### Related tables (multi-table synthesis)

For data split across linked tables (e.g. one row per inmate, many judgements per
inmate), `synthesize_relational` keeps **referential integrity** and the
**parent → child structure**:

```python
import oissyntheticdata

oissyntheticdata.synthesize_relational_files(
    {"inmates": "inmates.csv", "judgements": "judgements.csv"},
    schema={
        "inmates":    {"key": "prisoner_id"},
        "judgements": {"key": "judgement_id",
                       "parent": "inmates", "foreign_key": "prisoner_id"},
    },
    out_dir="out", min_leaf=5,
)
# -> out/synthetic_inmates.csv, out/synthetic_judgements.csv
```

How it works: the parent is synthesized first and given fresh surrogate keys; a
regression CART models how many children each parent has (the fan-out) from the
parent's attributes; and each child's attributes are synthesized **conditioned on
its parent's synthetic attributes**. The result: every synthetic foreign key
points at a synthetic parent (0 orphan joins), the number of children per parent
is realistic, and parent → child relationships survive (e.g. high-risk parents
keep their child-row patterns). Supports a single-parent DAG — star, snowflake,
and parent → child → grandchild chains.

---

## Limitations

- Fits on real microdata, so **run it on-premises**; the synthetic *output* is
  what you take off-site.
- Relational synthesis covers a single-parent DAG (star / snowflake / chains).
  Many-to-many relationships and compound keys are not modelled — pre-join or
  pre-resolve them to a surrogate key first. Such inputs are rejected up front with
  a clear error (`NotImplementedError` for compound keys and many-to-many links,
  `ValueError` for missing or dangling references), never handled silently.
- CART captures pairwise/low-order structure well; very high-order interactions
  and exact arithmetic identities (e.g. `rate = a/b`) are not enforced.
- Pure Python: comfortable to a few thousand rows × a few dozen columns; larger
  data is slower than a compiled implementation.

---

## Lineage & sources

- Rubin, D.B. (1993). *Statistical disclosure limitation.* J. Official Statistics 9(2).
- Little, R.J.A. (1993). *Statistical analysis of masked data.* J. Official Statistics 9(2).
- Reiter, J.P. (2005). *Using CART to generate partially synthetic public use microdata.*
  J. Official Statistics 21(3).
- Reiter, Oganian & Karr (2009). *Verification servers.* Comput. Stat. Data Anal. 53(4):1475–1482.
  https://doi.org/10.1016/j.csda.2008.10.006
- Nowok, Raab & Dibben (2016). *synthpop: Bespoke Creation of Synthetic Data in R.*
  J. Statistical Software 74(11). https://doi.org/10.18637/jss.v074.i11
- Drechsler, J. (2011). *Synthetic Datasets for Statistical Disclosure Control.* Springer.
- US Census Bureau, *SIPP Synthetic Beta* + Cornell Synthetic Data Server (synthetic
  development data + validation on confidential files).

## Maintainer

Dr **Yohanan Ouaknine** — OIS ([ois.co.il](https://ois.co.il)),
[yohanan.ouaknine@ois.co.il](mailto:yohanan.ouaknine@ois.co.il),
[ORCID 0000-0002-4186-7351](https://orcid.org/0000-0002-4186-7351).
Department of Criminology, Ashkelon Academic College; formerly Head of the
Research Branch, Israel Prison Service.

## License

MIT — see `LICENSE`.

## Citation

If you use `oissyntheticdata`, please cite this software (see `CITATION.cff`;
archived on Zenodo, concept DOI [10.5281/zenodo.20632932](https://doi.org/10.5281/zenodo.20632932) — always resolves to the latest version)
and the methodological lineage above (Reiter 2005; Nowok, Raab & Dibben 2016). The
method was first applied in Ouaknine, Elisha & Hasisi (2026), *The Effect of Mass
Prisoner Release on Terrorist Recidivism: A Propensity Score Analysis of the Shalit
Deal* (in press).
