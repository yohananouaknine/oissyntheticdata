# Changelog

All notable changes to `oissyntheticdata` are documented here. This project follows
[Semantic Versioning](https://semver.org/) and the
[Keep a Changelog](https://keepachangelog.com/) format.

## [Unreleased]

## [1.0.0] — 2026-06-11

First stable release. Marks the public API (`synthesize`, `synthesize_relational`,
the CLI, and the confidentiality parameters) as stable and supported. No functional
change from the 0.2.1 pre-review hardening below; this release promotes the project
to 1.0 to reflect its production use and documented, tested, stable interface.

## [0.2.1] — 2026-06-11

### Changed (JOSS pre-review hardening)
- `_tree.py` (the from-scratch CART) rewritten for auditability: thorough
  explanatory comments throughout, and the recursive builder now receives its
  predictor columns explicitly instead of via module-level global state.
- Relational synthesis now **validates the schema up front** and fails with a clear,
  specific error on out-of-scope input — `NotImplementedError` for compound keys and
  many-to-many links (detected as a non-unique parent key), `ValueError` for missing
  or dangling key/parent references — instead of failing silently.
- `paper.bib`: the forthcoming Shalit-deal study marked precisely as *in press*.
- Added the Zenodo archive DOI (10.5281/zenodo.20632932) to the paper, README, and
  citation file; documented the out-of-scope error behaviour in the docs.

### Added
- Tests for the relational validation errors (compound key, missing foreign key,
  unknown parent, non-unique parent key).



### Added / Changed (documentation & process; no code change)
- Rebranded the package to **oissyntheticdata** (an OIS tool, https://ois.co.il),
  maintained by Dr Yohanan Ouaknine (ORCID 0000-0002-4186-7351).
- Recorded the method's real-world provenance: first deployed at the Israel Prison
  Service for a terrorist-recidivism study (Shalit deal) under Research Committee
  authorization (Protocol No. 58), presented at the Israeli Society of Criminology
  conference (May 2026); paper in publication.

### Added / Changed (documentation & process; no code change)
- Rewrote `paper.md` to follow JOSS's updated scope: foregrounds problem framing,
  design decisions and trade-offs, state of the field, quality control, and
  development/governance, with a generative-AI disclosure.
- Added `CONTRIBUTING.md` (contribution pathway, no-dependency and confidentiality
  ground rules, PR checklist, AI-assistance disclosure).
- Added Design-decisions, Governance/Support, and AI-disclosure sections to the README.
- Reframed `PUBLISHING.md`: Zenodo/Software Heritage for immediate citability;
  JOSS repositioned as a later milestone with its open-development eligibility bar.

## [0.2.0] — 2026-06-10

### Added
- **Relational (multi-table) synthesis** (`synthesize_relational`,
  `synthesize_relational_files`). Synthesizes a parent → child schema while
  preserving referential integrity (every synthetic foreign key points at a
  synthetic parent), the per-parent fan-out (modelled with a regression CART on
  parent attributes), and parent → child attribute correlation (child columns are
  synthesized conditioned on the parent's synthetic attributes). Supports a
  single-parent DAG: star, snowflake, and chains.
- Reusable typed core `synth_core` with support for *fixed* (given, not
  synthesized) predictor columns; `type_columns` / `stringify` helpers.

### Changed
- Internal refactor of `_synth` to share the synthesis core between single-table
  and relational synthesis. Single-table behaviour and outputs are unchanged.

## [0.1.0] — 2026-06-10

### Added
- Sequential CART synthesis engine (`oissyntheticdata.synthesize`) in the synthpop
  tradition: column-by-column synthesis, marginal draw for the first column,
  CART-with-donor-leaves for each subsequent column conditioned on the columns
  already synthesized.
- Pure-Python classification and regression trees (`oissyntheticdata._tree`) — no numpy
  or scikit-learn.
- Standard-library CSV and XLSX reading and CSV writing (`oissyntheticdata._io`).
- Confidentiality controls: `min_leaf` (k-record floor on every leaf and
  marginal cell), optional `smoothing` of continuous donors, and `drop` for
  excluding direct identifiers.
- Command-line interface: `python -m oissyntheticdata input.(csv|xlsx) -o out.csv`.
- One-call helper `oissyntheticdata.synthesize_file`.
- Test suite (`tests/test_synth.py`, stdlib `unittest`).

[1.0.0]: https://github.com/yohananouaknine/oissyntheticdata/releases/tag/v1.0.0
[0.2.0]: https://github.com/yohananouaknine/oissyntheticdata/releases/tag/v0.2.0
[0.1.0]: https://github.com/yohananouaknine/oissyntheticdata/releases/tag/v0.1.0
