# Contributing

Thanks for your interest in `oissyntheticdata`.

## Ground rules

- **No runtime dependency.** `gov_one.py` runs on the Python standard library alone
  (Python >= 3.8). Do not import another package: the file is carried into places
  where nothing can be installed.
- **Only aggregates leave.** Nothing that describes fewer than the minimum count of
  rows (5 by default) may reach the JSON, and no row is copied. The synthetic files
  are built from the JSON alone.
- **One source.** The tool is the single file `gov_one.py`. The `oissyntheticdata`
  package is a thin wrapper around it, and the version is read from the `VERSION`
  line of `gov_one.py`.
- **The R version writes the same JSON.** A change to what the profile contains has
  to be made in <https://github.com/yohananouaknine/oissyntheticdata-r> too.

## Development

```bash
python -m unittest discover -s tests
```

The test builds a small invented folder, profiles it, rebuilds synthetic files and
checks that an identifier and a rare label do not leave. The two demos
(`demo/`, `demo_suicide/`) are the longer checks: run the script that invents the
data, then `python gov_one.py` on both sides, then the analysis script.

## Reporting issues

Open an issue at
https://github.com/yohananouaknine/oissyntheticdata/issues with a minimal
reproduction. Please do **not** attach real or confidential data.
