---
title: 'oissyntheticdata: profile-based synthetic data for secure research environments'
tags:
  - Python
  - synthetic data
  - statistical disclosure control
  - privacy
  - secure research
  - criminology
  - microdata
authors:
  - name: "Yohanan Ouaknine"
    orcid: 0000-0002-4186-7351
    corresponding: true
    affiliation: 1
affiliations:
  - name: "OIS, Israel (https://ois.co.il)"
    index: 1
date: 11 June 2026
bibliography: paper.bib
---

# Summary

`oissyntheticdata` generates a structurally faithful **synthetic** copy of a
sensitive dataset for use in secure research environments, with one defining
property: **the synthesizer never reads the confidential microdata**. Instead, an
on-premises stage distils the real data into a *disclosure-controlled profile* -
robust numeric bounds, k-suppressed categorical frequencies, format signatures
for identifiers, and the distribution of group sizes for fan-out keys - and the
off-premises stage rebuilds a synthetic dataset from that profile alone. The
profile is the only artefact that crosses the trust boundary on the way out;
later, only the analyst's aggregate results cross back in. The microdata stays
on-premises throughout.

The package is written entirely in the Python standard library, with **no
third-party runtime dependencies**, so it installs by copying one directory,
runs inside locked secure-research environments that forbid `pip`/`conda` and
have no internet access, and is small enough for a data owner to read and audit
in full. It operationalises the *develop-on-synthetic, run-on-real* workflow of
official statistics [@hundepool2012sdc], as deployed in the U.S. Census Bureau's
SIPP Synthetic Beta [@census_ssb]: analysts develop and debug analysis
code off-site against the synthetic data, then run the final, unchanged script
on the confidential data on-premises.

# Statement of need

Statistical disclosure control balances analytic utility against re-identification
risk [@hundepool2012sdc; @sweeney2002kanonymity]. Synthetic microdata is an
established route to that balance [@drechsler2011synthetic; @templ2015sdcmicro],
and high-fidelity generators such as sequential CART synthesis
[@nowok2016synthpop] reproduce the joint distribution well. Those generators,
however, must **read the real microdata** to fit their models, so the
synthesiser has to run inside the secure environment, and the synthetic output
itself can carry residual disclosure risk that must be separately controlled.

Many secure-research workflows do not need full multivariate realism. They need
a synthetic dataset that is *structurally* identical to the real one - same
column types, ranges, category levels (including the rare ones), missingness,
identifier formats, and cross-table joins - so that analysis code exercises every
branch, filter and join it will meet on the real data. For that purpose, the
load-bearing requirement is a clean boundary: the component that leaves the
secure environment should never have touched the microdata at all.

`oissyntheticdata` targets exactly this case. Its threat model is explicit and
narrow: the only thing that leaves the environment is a profile that, by
construction, contains no identifiable value - no raw record, no unsuppressed
small cell, no enumerated identifier, no true extreme. The synthetic data is
built for **code-path coverage rather than statistical realism**, and synthetic
numbers are never reported. This makes the tool a complement to, not a competitor
of, joint-distribution synthesisers: it trades multivariate fidelity for a
stronger and simpler disclosure boundary.

# Design and functionality

The workflow is a four-stage pipeline across a single trust boundary.

**Stage 00 (`add-month`, run anywhere).** A small preprocessor that inserts a
derived `<date>_month` column after each date column, so monthly seasonality
becomes an ordinary categorical that the rest of the pipeline can model.

**Stage 01 (`profile`, inside).** Reads the real data and writes a
disclosure-safe profile (`profile_<base>.json` plus a human-readable summary).
Each column is classified and reduced to a *shape* rather than its values:

- numeric columns keep a mean, a standard deviation and a quantile grid, with
  **robust bounds** (the 1st and 99th percentiles replace the true extremes, so
  outliers do not leak);
- categorical columns keep level frequencies, but any level with fewer than `k`
  records (default `k = 5`) is relabelled `RARE_###` - the count is kept, the
  label is dropped [@sweeney2002kanonymity];
- unique integer keys keep only the fact that they are unique, plus a length
  range;
- fan-out / foreign keys keep only the *distribution* of their group sizes,
  never an identifier tied to its count;
- high-cardinality text and identifiers keep only a format signature (e.g.
  `DD-DDDDDD`) and a length range; their values are never enumerated;
- date columns keep their format, range, and per-year / per-month shape.

Columns that are key-like in two or more files are flagged as shared relational
keys.

**Stage 02 (`synthesize`, outside).** Reads the profile - and only the profile -
and rebuilds each column by sampling from its stored shape: inverse-CDF sampling
over the quantile grid for numerics, stored frequencies for categoricals (every
level, including the rare ones, is forced to appear so downstream code meets it),
seasonal sampling for dates, and format-signature generation for identifiers.
For relational data the synthesiser mints one shared key pool per shared key:
the file in which the key is unique defines the parent pool, and child files draw
a subset, so synthetic child keys are always a subset of synthetic parent keys
and cross-file joins line up.

**Stage 03 (`compare`, inside-only control).** A control step, not an analyst
step. It reads the real data on-premises and scores how structurally close the
synthetic data is: a chance-corrected distributional agreement (`kappa*`) for
categoricals, `1 - KS` for numerics and dates, format-signature agreement for
identifiers, group-size agreement for fan-out keys, and cross-file referential
integrity. Only column-level scores leave the environment. It is explicitly not a
privacy test and not a validity test of analytic results - those come from the
real run.

# Reproducibility and audit

The four numbered scripts in `scripts/` are auto-generated from the package by a
bundler that inlines the shared I/O and helper modules, so each script is a
single self-contained, zero-dependency file suitable for carrying into and
auditing within a locked environment. The package and the standalone scripts
produce byte-identical output, and a round-trip test enforces that they remain in
sync. Synthesis is seeded, so a given profile yields a reproducible synthetic
dataset.

# Acknowledgements

Developed and maintained by OIS (https://ois.co.il). The disclosure-control
concept this package implements was first applied in research at the Israel
Prison Service research unit, in a study of terrorist recidivism following the
2011 Shalit prisoner exchange, under Research Committee authorization. This
package is a later, general, open implementation of that concept and was not
itself used in that research.

# References
