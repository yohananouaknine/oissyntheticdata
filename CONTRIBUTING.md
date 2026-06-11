# Contributing

Thanks for your interest in `oissyntheticdata`.

## Ground rules

- **Zero runtime dependencies.** The package must run on the Python standard
  library alone (Python >= 3.7). Do not add third-party runtime imports.
- **The boundary is sacred.** Stage 02 (`synthesize`) must never read the real
  data - only the profile. Stage 03 (`compare`) reads real data and is an
  inside-only control; keep it out of any "researcher" code path.
- **Single source of truth.** Edit the package in `src/oissyntheticdata/`. Never
  hand-edit `scripts/0*.py` - regenerate them:
  ```bash
  python tools/build_standalone.py
  ```

## Development

```bash
pip install -e ".[test]"
pytest -q                       # runs the round-trip equivalence test
python tools/build_standalone.py
```

The round-trip test profiles a tiny generated dataset, synthesises it, compares,
and asserts that the standalone scripts and the package produce identical output.
If you change any stage, run the bundler and the tests before opening a PR.

## Reporting issues

Open an issue at
https://github.com/yohananouaknine/oissyntheticdata/issues with a minimal
reproduction. Please do **not** attach real or confidential data.
