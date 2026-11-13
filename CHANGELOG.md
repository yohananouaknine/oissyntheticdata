# Changelog

## [3.0.0] - 2026-11-12

A different tool under the same name. **Not compatible with 2.x.**

### Changed
- The package is now the single file `gov_one.py`: profile a whole folder of Excel / CSV files
  (every sheet), write aggregate-only JSON, rebuild synthetic files from the JSON, and give your own
  analysis script a statistics toolbox. Standard library only, as before.
- `import gov_one as g` (or `import oissyntheticdata as g`) replaces the 2.x functions.
- Commands: `oissyntheticdata [auto|profile|synth|check|settings]`, also available as `oissd`
  and `gov_one`.

### Removed
- The 2.x commands `add-month`, `profile` (old form), `synthesize`, `compare`, the functions
  `profile()`, `synthesize()`, `compare()`, `add_month_file()`, and the standalone `scripts/`.
  Profiles written by 2.x are not read. To keep 2.x: `pip install "oissyntheticdata<3"`.

### Added
- Links between tables found from the values, with rows per key and the share of parent rows
  that have any child row.
- Disclosure rules beyond rare-label suppression: complementary suppression in joint tables,
  dates by month and weekday only, quantiles rounded to four significant figures, id-number
  look-alikes and personal headers (English and Hebrew) described by shape only, a
  `profile_summary.md` listing what leaves.
- Structure carried in the JSON: joint counts for pairs of columns chosen by a tree, a second
  "given" column per column where a test finds one, durations between dates (within a table and
  across linked tables), "empty when" rules, ages recomputed from two dates.
- Statistics toolbox in pure Python: describe, crosstab, chi-square, Welch t, Mann-Whitney,
  proportion test, Pearson, Spearman, OLS (classical or Newey-West), interrupted time series,
  and an offline HTML report stamped "Synthetic test data — not findings" on synthetic files.
- `oissyntheticdata export [FOLDER]` copies `gov_one.py` and `analysis_template.py` out of the
  installation, to carry into premises where nothing can be installed.

### Tested
- On two invented folders only (a welfare office; suicide cases with welfare contacts), Python 3.15,
  Windows. Not yet on real ministry files.

## 2.2.0 and earlier

See the 2.2.0 release on PyPI for the history of the earlier, four-stage tool.
