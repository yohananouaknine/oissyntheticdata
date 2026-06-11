# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [2.1.0] - 2026-06-11

Documentation and metadata corrections. No change to the synthesis or profiling
logic; the only output change is cosmetic (report text uses hyphens, not em-dashes).

### Changed
- Provenance clarified: the disclosure-control concept, not this package, was
  first applied in research at the Israel Prison Service research unit; this
  package is a later, general, open implementation of that concept.
- Maintainer affiliation corrected; removed the Ashkelon Academic College affiliation.
- Lineage and sources restricted to government uses of synthetic data (U.S. Census
  SIPP Synthetic Beta, OnTheMap / LEHD) with live links; academic references kept
  only where a resolving link exists, each now carrying a DOI/URL.
- Removed em-dashes throughout the documentation and report output.

## [2.0.0] - 2026-06-11

This is a **method change**, not a backward-compatible revision. 2.0.0 replaces
the sequential-CART synthesiser of 1.0.0 with the **profile-based pipeline**, in
which the synthesiser never reads the real microdata.

### Added
- Four-stage pipeline: `add-month` (00), `profile` (01), `synthesize` (02),
  `compare` (03), available as a CLI (`oissyntheticdata <stage>` / `oissd`), as
  an importable API (`oissyntheticdata.profile/synthesize/compare`), and as
  self-contained zero-install scripts in `scripts/`.
- Disclosure-controlled profile (stage 01): robust numeric bounds (P1/P99),
  k-suppression of rare categorical levels (default k=5), identifier format
  signatures, and group-size distributions for fan-out keys.
- Synthesis from the profile only (stage 02), including seasonal dates, forced
  appearance of every category (incl. rare), and shared relational key pools so
  cross-file joins line up.
- Inside-only fidelity control (stage 03): `kappa*`, `1 - KS`, signature
  agreement, group-size agreement, and cross-file referential integrity.
- `tools/build_standalone.py` regenerates the standalone scripts from the
  package, keeping a single source of truth; `tests/test_roundtrip.py` enforces
  package == standalone-script equivalence.

### Changed
- Synthesiser no longer reads the confidential microdata. The only artefact that
  leaves the secure environment is the disclosure-controlled profile.
- Paper, citation metadata and documentation rewritten to describe the
  profile-based method.

### Notes
- Zero third-party runtime dependencies (standard library only), unchanged.
- New release is a new version under the existing Zenodo concept record.

## [1.0.0] - 2026-06-10
- Initial release: zero-dependency sequential CART synthesis (synthpop
  tradition) with relational support.
