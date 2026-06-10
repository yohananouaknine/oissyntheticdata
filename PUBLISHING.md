# Publishing `oissyntheticdata`

A practical, copy-paste guide to releasing `oissyntheticdata` as an open-source package
with a citable DOI. Four things are independent: **(A)** put the code on GitHub,
**(B)** publish to PyPI so people can `pip install oissyntheticdata`, **(C)** mint a Zenodo
DOI so the software is citable **now**, and **(D)** pursue a JOSS paper **later**,
once the project meets JOSS's open-development and impact criteria.

> **Citability path:** Do A + B + C now — a Zenodo (or Software Heritage) archival
> DOI makes the software citable immediately, and JOSS itself recognises these as
> valid ways to cite software. Treat JOSS (D) as a later milestone, not a launch
> step (see the eligibility notes there).

> Repository URLs are set to `github.com/yohananouaknine/oissyntheticdata`. The PyPI name
> `oissyntheticdata` was confirmed available on PyPI; if you ever rename, update
> `pyproject.toml` and the references below.


---

## 0. Prerequisites

```bash
python -m pip install --upgrade pip build twine
```

- A GitHub account (for A/C) and a PyPI account (for B): https://pypi.org/account/register/
- Enable 2-factor auth on PyPI (required) and create an **API token**
  (Account settings → API tokens). You will paste it as the password when
  uploading, with username `__token__`.

---

## A. GitHub repository

```bash
cd oissyntheticdata_pkg
git init
git add .
git commit -m "oissyntheticdata 0.1.0: pure-Python sequential CART synthesis"
git branch -M main
git remote add origin https://github.com/yohananouaknine/oissyntheticdata.git
git push -u origin main
```

Recommended repo hygiene:

- Add a `.gitignore` (at least: `__pycache__/`, `*.pyc`, `dist/`, `build/`,
  `*.egg-info/`, `.venv/`).
- Confirm `LICENSE` (MIT) is present at the root.
- The `README.md` renders as the project front page automatically.
- Tag the release so it is permanent and (optionally) archivable:

```bash
git tag -a v0.1.0 -m "oissyntheticdata 0.1.0"
git push origin v0.1.0
```

---

## B. Publish to PyPI

1. **Sanity-check the metadata** in `pyproject.toml` (name, version, URLs —
   confirm the name). Bump `version` here and in `oissyntheticdata/__init__.py`
   (`__version__`) and `CHANGELOG.md` for every release; they must agree.

2. **Build the distributions** (creates `dist/*.whl` and `dist/*.tar.gz`):

   ```bash
   python -m build
   ```

3. **Check them**:

   ```bash
   python -m twine check dist/*
   ```

4. **Upload to TestPyPI first** (a sandbox, so you can rehearse safely):

   ```bash
   python -m twine upload --repository testpypi dist/*
   # then test the install in a clean virtual environment:
   python -m venv /tmp/t && /tmp/t/bin/pip install \
       --index-url https://test.pypi.org/simple/ oissyntheticdata
   /tmp/t/bin/python -c "import oissyntheticdata; print(oissyntheticdata.__version__)"
   ```

5. **Upload to the real PyPI**:

   ```bash
   python -m twine upload dist/*
   # username: __token__   password: <your PyPI API token>
   ```

   Now anyone can `pip install oissyntheticdata`.

6. **For later releases**: bump the version, rebuild, re-upload. PyPI will not
   let you overwrite an existing version — always increment.

> Tip: you can fully automate B with a GitHub Action that publishes on every
> tagged release using PyPI **Trusted Publishing** (OIDC, no stored token).
> See https://docs.pypi.org/trusted-publishers/.

---

## C. Citable DOI via Zenodo

1. Sign in to https://zenodo.org with your GitHub account.
2. In Zenodo → **Settings → GitHub**, flip the switch **ON** for the `oissyntheticdata`
   repository.
3. Back on GitHub, **create a release** from the `v0.1.0` tag
   (Releases → Draft a new release → choose the tag → Publish).
4. Zenodo automatically archives that release and issues a DOI. Add the DOI
   badge it gives you to the top of `README.md`, and record the citation in
   `CHANGELOG.md`.

Optional: add a `CITATION.cff` file at the repo root so GitHub shows a "Cite
this repository" button. Minimal example:

```yaml
cff-version: 1.2.0
title: "oissyntheticdata: pure-Python sequential CART synthesis"
message: "If you use this software, please cite it."
authors:
  - family-names: "<your surname>"
    given-names: "<your given name>"
version: 0.1.0
date-released: 2026-06-10
license: MIT
repository-code: "https://github.com/yohananouaknine/oissyntheticdata"
```

---

## D. Later: a software paper (JOSS) — read the eligibility bar first

The **Journal of Open Source Software** (https://joss.theoj.org) reviews the
repository itself, and `paper.md` + `paper.bib` are already written. But under
JOSS's updated scope (2025+), a freshly created, AI-assisted package **is not yet
eligible**. Do not submit on launch. The relevant requirements:

- **Public open-development history.** Projects developed privately and then
  posted are ineligible until there is **at least six months of public history**
  before submission, with **versioned releases and public issues/pull requests**.
  Develop in the open from the start; a private build followed by a public dump
  does not qualify.
- **Extra scrutiny for very new / AI-assisted code.** Commit histories of only
  weeks, or signs of rapid AI-assisted generation, invite additional review to
  confirm genuine scholarship. Disclose AI assistance honestly (already done in
  `paper.md` and `README.md`) and let the public history demonstrate real work.
- **Evidence of reuse and significance, not effort.** JOSS now weighs research
  impact, design thinking, and open-source practice over lines of code. Show:
  analyses or workflows that use `oissyntheticdata`, external adopters/integrations, or a
  reproducible reference analysis/benchmark; the design decisions and trade-offs
  (in the README and `paper.md`); and good practice (tests, docs, governance,
  contribution pathway — all present).
- **Sustained value.** Short-lived, single-use codebases are out of scope.

**Roadmap to eligibility**

1. Make the GitHub repo public today; develop in the open (A + B + C above).
2. Cut tagged releases as features land; keep `CHANGELOG.md` current.
3. Use public Issues/PRs for real work; welcome outside contributions.
4. Accumulate evidence of use — a reproducible reference analysis (the examples
   are a start), and ideally an external study or adopter.
5. After ≥ 6 months of public history with releases and issues, submit `paper.md`
   to JOSS.

In the meantime, the Zenodo DOI (C) provides immediate, valid citability.

---

## Release checklist

- [ ] Version bumped in `pyproject.toml`, `oissyntheticdata/__init__.py`, `CHANGELOG.md` (all equal)
- [ ] `python -m unittest -v` passes
- [ ] `python -m build` and `python -m twine check dist/*` clean
- [ ] Rehearsed install from TestPyPI in a fresh venv
- [ ] Git tag pushed; GitHub release published (triggers Zenodo DOI)
- [ ] `pip install oissyntheticdata` works from a clean environment
