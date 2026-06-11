---
title: 'oissyntheticdata: zero-dependency sequential CART synthesis for secure research, with relational support'
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
    affiliation: "1, 2"
affiliations:
  - name: "OIS, Israel (https://ois.co.il)"
    index: 1
  - name: "Department of Criminology, Ashkelon Academic College, Israel"
    index: 2
date: 10 June 2026
bibliography: paper.bib
---

# Summary

`oissyntheticdata` generates a synthetic copy of a sensitive dataset that
preserves the *relationships between variables*, not merely each column's
marginal distribution. It implements **sequential CART synthesis** — the method
introduced for synthetic microdata by @reiter2005cart and popularised by the R
package `synthpop` [@nowok2016synthpop] — and contributes a **relational
(multi-table) extension** that keeps referential integrity and parent-to-child
structure. The package is written entirely in the Python standard library, with
**no third-party runtime dependencies**, so it installs by copying one directory,
runs inside locked secure-research environments that forbid `pip`/`conda` and have
no internet access, and is small enough for a data owner to read and audit in
full.

`oissyntheticdata` operationalises the *develop-on-synthetic, run-on-real*
workflow of official statistics: analysts develop and debug analysis code off-site
on synthetic data, then run the finished code on the confidential data
on-premises and release only vetted aggregates [@nowok2016synthpop;
@reiter2009verification]. The synthetic data is a rehearsal space, never the
source of published numbers. It is maintained by OIS (https://ois.co.il), which
offers supporting services to government research units and academic researchers.

# Statement of need

Confidential microdata in justice, health, tax, and social research cannot leave
the secure environment, yet analysts still need realistic data to write and
validate code. The author encountered this concretely while serving as Head of the
Research Branch at the Israel Prison Service (IPS) and conducting a study of
terrorist recidivism after the 2011 Shalit prisoner exchange [@ouaknine2026shalit]:
the analysis had to be run on-site at IPS, under Research Committee authorization
(Protocol No. 58), on a secure system with no internet, using a custom analysis
program restricted to the Python standard library, with only aggregate outputs
extracted. In that setting the analyst cannot install packages, cannot take data
out, and cannot iterate on the real data at will. The practical solution — extract
disclosure-controlled metadata, build synthetic data off-site, develop the
standard-library analysis script against it, and run the finished script on the
real data in place — is the workflow this package supports. `oissyntheticdata`
generalises and opens that approach.

Mature tools exist for parts of this problem — `synthpop` in R
[@nowok2016synthpop], the U.S. Census Bureau's SIPP Synthetic Beta with validation
on confidential files [@censusssb], and general frameworks such as the Synthetic
Data Vault [@patki2016sdv]. The contribution of `oissyntheticdata` is to meet two
requirements that arise together in the most restrictive secure settings and that
those tools do not jointly satisfy:

1. **Auditability with no dependencies.** The strictest environments prohibit
   external packages, and a data owner must be able to read the whole synthesizer
   before it touches confidential records. `oissyntheticdata` therefore implements
   CART, tree fitting, and CSV/XLSX I/O from the standard library alone.
2. **Relational integrity.** Administrative data is usually split across linked
   tables (one row per person; many records per person). Synthesizing each table
   independently severs the foreign-key relationships, so any analysis that joins
   tables behaves differently on synthetic than on real data — precisely the code
   paths the rehearsal is meant to exercise.

# Design and key decisions

The intellectual content is in the design choices, not the line count.

**Two synthesizers for two trust profiles.** A companion metadata-only synthesizer
can run *off*-premises because it never reads raw records, but preserves only
per-column structure. `oissyntheticdata` instead fits on the real microdata to
preserve joint structure, and so runs *on*-premises; only the synthetic output
leaves. Treating "where the synthesizer may run" as a first-class design axis keeps
the confidentiality reasoning explicit.

**Donor-leaf sampling, not prediction.** Each tree stores, at every leaf, the real
target values that reached it; synthesis draws a value from that pool. Sampling
donors rather than emitting a point estimate reproduces the conditional
distribution [@reiter2005cart].

**One confidentiality invariant.** A single parameter, `min_leaf` (`k`), enforces a
`k`-record floor on every marginal cell, tree leaf, fan-out estimate, and (via
surrogate keys) every identifier — one auditable invariant rather than scattered
thresholds.

**Relational by conditioning, not joining.** For linked tables the parent is
synthesized first and given fresh surrogate keys; a regression CART models the
number of children per parent from the parent's attributes; foreign keys are drawn
from the synthetic parent keys; and each child's columns are synthesized
*conditioned on its parent's synthetic attributes*. This preserves referential
integrity, attribute-dependent fan-out, and parent-to-child correlation without
materialising a real join. A single-parent DAG (star, snowflake, chains) is
supported; many-to-many and compound keys are deliberately out of scope and are
rejected at validation time with an explicit error (a `NotImplementedError` for
compound keys and many-to-many links — detected as a non-unique parent key — and a
`ValueError` for missing or dangling references) rather than failing silently.

**Build on, don't reinvent.** The estimator is the established CART-synthesis
method; the new work is the dependency-free, auditable, relational realisation for
locked environments.

# State of the field

`oissyntheticdata` sits in the synthetic-data-for-disclosure-control tradition
[@rubin1993; @little1993; @drechsler2011]. Relative to `synthpop`
[@nowok2016synthpop] it offers a dependency-free Python implementation with
relational support; relative to the Synthetic Data Vault [@patki2016sdv] it trades
breadth of models for auditability and zero dependencies; and it produces the
development data that verification/validation-server workflows rely on
[@reiter2009verification]. National programs use the same paradigm operationally
[@censusssb; @nowok2017uk].

# Real-world use and significance

The method this package implements was first deployed by the author at the Israel
Prison Service for a study of terrorist recidivism following the Shalit prisoner
exchange [@ouaknine2026shalit] — authorized by the IPS Research Committee (Protocol
No. 58), executed on-premises on real administrative records with a
standard-library analysis script, and released as aggregate results. That study was
presented at the annual conference of the Israeli Society of Criminology (May 2026)
and is in publication. `oissyntheticdata` packages the same approach for reuse by
other secure-research units, and OIS (https://ois.co.il) offers deployment,
validation, and training services around the open core.

# Quality control and reproducibility

The package ships a `unittest` suite covering output shape, reproducibility under a
fixed seed, single-table conditional fidelity, and relational referential
integrity. Two runnable reference analyses are included: one shows that a
deterministic conditional rule survives single-table synthesis where an independent
marginal synthesizer would break it; the other shows that, for linked tables, every
synthetic foreign key resolves (zero orphan joins), the per-parent fan-out tracks a
parent attribute, and a parent-to-child relationship is preserved.

# Development, governance, and contributions

`oissyntheticdata` is developed in the open under the MIT license, with versioned
releases archived on Zenodo (DOI: 10.5281/zenodo.20632933), a changelog, a citation
file, public issue tracking, and a contributing guide. Maintenance and decision
responsibilities are stated in the repository, and the design rationale lives in the
user-facing documentation.

# Generative AI disclosure

During the development of this software and the preparation of this manuscript, the
author used a generative AI assistant (Claude, Anthropic) to help draft and
refactor portions of the code and the text. All AI-assisted output was reviewed,
tested, and edited by the author, who takes full responsibility for the design,
correctness, and integrity of the software and this paper. The problem framing, the
design decisions and abstractions described above, and the testing and
documentation practices are the author's own.

# Acknowledgements

The author thanks the Israel Prison Service Research Committee for authorizing the
original study (Protocol No. 58), and acknowledges the methodological lineage of
synthetic data for statistical disclosure control, in particular the `synthpop`
authors and J. P. Reiter.

# References
