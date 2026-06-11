# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [2.2.0] - 2026-06-11

Major release: relational synthesis with auto-detected schema and within-row key pairing.

### Added
- Automatic relationship detection (stage 01) by value-inclusion: a shared column
  is treated as a link only when one file holds it uniquely (parent) and another
  file's values are a repeating subset (child). Type-agnostic, so integer, string,
  and date keys are all found, and shared attribute columns are correctly ignored.
- Relational synthesis (stage 02): each child row is attached to a real synthetic
  parent row; the link column and any inherited columns are copied from that parent.
  This gives referential integrity, realistic fan-out, and exact within-row key
  pairing at once (for example, a judgement's incident now belongs to that
  judgement's prisoner). Supports both the hierarchical ("deterrence") model and the
  simple shared-id ("merge by grouping") model.
- Detected schema is written to schema.json (names and fan-out quantiles only,
  disclosure-safe) and printed in stage 01.
- Stage 03 reports schema-driven referential integrity and within-row pairing,
  including links that are not id-named.

### Changed
- Single-file and no-relationship runs are unchanged (same output as before).

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
