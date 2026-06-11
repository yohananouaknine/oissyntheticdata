# Publishing `oissyntheticdata` 2.1.0

Release in this order: **GitHub → PyPI → Zenodo**. GitHub holds the source and the
tag; PyPI distributes the installable package; Zenodo archives the tagged release
and mints the citable DOI. Do them in order because the Zenodo archive is created
from the GitHub release/tag.

All commands run from the repo root. Replace nothing except where noted.

## 0. Pre-flight (once per release)

```bash
python tools/build_standalone.py        # regenerate scripts/ from src/
pip install -e ".[test]"
pytest -q                               # round-trip + disclosure guarantees must pass
python -c "import oissyntheticdata as o; print(o.__version__)"   # -> 2.1.0
```

Confirm the version is `2.1.0` in **pyproject.toml**, **src/oissyntheticdata/__init__.py**,
**CITATION.cff**, and the top of **CHANGELOG.md**. Commit any changes.

## 1. GitHub

If the remote does not exist yet:

```bash
git init
git add .
git commit -m "oissyntheticdata 2.1.0: profile-based pipeline"
git branch -M main
git remote add origin https://github.com/yohananouaknine/oissyntheticdata.git
git push -u origin main
```

For a subsequent release, commit and push to `main`, then tag:

```bash
git tag -a v2.1.0 -m "2.1.0 - profile-based synthetic data pipeline"
git push origin v2.1.0
```

Then on github.com: **Releases → Draft a new release → choose tag `v2.1.0`**,
title `oissyntheticdata 2.1.0`, paste the 2.1.0 section of `CHANGELOG.md`, and
**Publish release**. (Leave Zenodo until step 3 - enabling the webhook first, see
below, makes this release auto-archive.)

## 2. PyPI

Build the distributions. `build`/`twine` are the usual tools; if they are not
available you can build with setuptools directly (no internet needed once
setuptools + wheel are present):

```bash
# preferred
python -m build                         # -> dist/oissyntheticdata-2.1.0.tar.gz + .whl

# fallback if `build` is unavailable
python - <<'PY'
from setuptools import build_meta as b
import os; os.makedirs("dist", exist_ok=True)
print(b.build_sdist("dist")); print(b.build_wheel("dist"))
PY
```

Check and upload (TestPyPI first is recommended):

```bash
python -m twine check dist/*
python -m twine upload --repository testpypi dist/*     # optional dry run
python -m twine upload dist/*                           # real PyPI
```

You will need a PyPI account and an API token (`__token__` as username). After
upload, verify:

```bash
pip install oissyntheticdata==2.1.0
```

## 3. Zenodo (DOI)

You already have a Zenodo record for 1.0.0 with concept DOI
`10.5281/zenodo.20632932` (it always resolves to the latest version).

**One-time setup:** at zenodo.org, log in with GitHub, open **Settings → GitHub**,
and flip the toggle **on** for the `yohananouaknine/oissyntheticdata`
repository. (Do this once; it installs the release webhook.)

**Each release:** because the webhook is on, publishing the GitHub release in
step 1 automatically creates a new **version** under the existing concept record
and mints a new version DOI. To attach it as a new version of the 1.0.0 record
rather than a brand-new record, use the same repository - Zenodo links them
automatically.

After Zenodo processes the release:

1. Copy the **2.1.0 version DOI** from the Zenodo record.
2. If you prefer to pin the citation to this version, set `doi:` in
   `CITATION.cff` to the 2.1.0 version DOI (otherwise leave the concept DOI,
   which always points at the latest). Commit the change.
3. Add the DOI badge to `README.md` if desired:
   `[![DOI](https://zenodo.org/badge/DOI/<your-doi>.svg)](https://doi.org/<your-doi>)`

## 4. (Optional) JOSS

`paper.md` + `paper.bib` are ready for a Journal of Open Source Software
submission. Submit at https://joss.theoj.org with the repository URL and the
archived Zenodo DOI from step 3.

## Checklist

- [ ] `python tools/build_standalone.py` run; `scripts/` regenerated
- [ ] `pytest -q` green
- [ ] version is `2.1.0` in pyproject, `__init__`, CITATION.cff, CHANGELOG
- [ ] pushed to GitHub `main`; tag `v2.1.0` pushed; GitHub release published
- [ ] `dist/*` built and `twine check` clean; uploaded to PyPI; `pip install` verified
- [ ] Zenodo GitHub toggle on; version DOI minted; CITATION.cff DOI updated if pinning
