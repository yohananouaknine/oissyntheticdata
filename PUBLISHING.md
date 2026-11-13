# Publishing `oissyntheticdata`

Release in this order: **PyPI → GitHub → Zenodo**. The tag on GitHub must hold the
same files as the archive on PyPI.

The build tools (`build`, `twine`) live in a separate environment at home. They are
never installed in anything that runs on the premises.

## 0. Before a release

1. Change the `VERSION` line of `gov_one.py`. `pyproject.toml` reads the version from it.
2. Add the entry to `CHANGELOG.md`.
3. Set `version` and `date-released` in `CITATION.cff`.
4. Run the tests: `python -m unittest discover -s tests`

## 1. PyPI

```bash
python -m build
python -m twine check dist/*
```

Install the built wheel in a fresh environment and run `oissyntheticdata check` on a
demo folder. Then upload:

```bash
python -m twine upload --username __token__ dist/*
```

Paste the API token in the terminal when it is asked for. Do not write it in a file
of this repository.

## 2. GitHub

```bash
git add -A
git commit -m "oissyntheticdata X.Y.Z"
git tag -a vX.Y.Z -m "oissyntheticdata X.Y.Z"
git push origin main
git push origin vX.Y.Z
```

`.gitattributes` keeps every file byte for byte, so the tag can be compared with the
archive on PyPI.

## 3. Zenodo (DOI)

The concept DOI `10.5281/zenodo.20632932` always resolves to the latest archived
version. When the Zenodo switch is on for this repository (zenodo.org → Settings →
GitHub), publishing a **GitHub Release** for the tag archives it and gives the
version its own DOI: on github.com, Releases → Draft a new release → choose the tag →
paste the CHANGELOG entry → Publish release.

Pushing a tag alone does not create a Release and does not reach Zenodo.

## Status of 3.0.0

- PyPI: published 2026-11-12.
- GitHub: commit and tag `v3.0.0` pushed 2026-11-13.
- Zenodo: no Release was published for `v3.0.0`, so the latest archived version is
  an earlier one.
- `paper.md`, `paper.bib` and `oissyntheticdata_JOSS_paper.docx` describe the
  four-stage tool of version 2.2.0. They were left as they are.
