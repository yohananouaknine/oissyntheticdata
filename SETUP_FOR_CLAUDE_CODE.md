# Setup instructions for Claude Code

Goal: publish this package as a **public** repository at
`https://github.com/yohananouaknine/oissyntheticdata`, then cut a tagged release.
All file contents (URLs, author, license) are already set — no placeholders remain.

> Important: make the **first commit in public, under Yohanan Ouaknine's own git
> identity**. The repository's public open-development history starts now and
> cannot be backdated; JOSS's updated scope requires it. Do not import a
> pre-existing `.git` history (there is none in this bundle, by design).

## 0. Preconditions
- Run these from the extracted package root (the folder containing `pyproject.toml`).
- Confirm git identity is the author's:
  ```bash
  git config user.name "Yohanan Ouaknine"
  git config user.email "yohanan.ouaknine@ois.co.il"
  ```

## 1. Initialize and make the first commit
```bash
git init
git add .
git commit -m "oissyntheticdata 0.2.0: zero-dependency sequential CART synthesis, with relational support"
git branch -M main
```

## 2. Create the GitHub repo and push
If the GitHub CLI (`gh`) is available and authenticated:
```bash
gh repo create yohananouaknine/oissyntheticdata --public --source=. --remote=origin --push \
  --description "Zero-dependency sequential CART synthesis for secure research (synthpop tradition), with relational support. An OIS tool."
```
Otherwise create the empty repo at https://github.com/new (owner `yohananouaknine`,
name `oissyntheticdata`, Public, **no** README/.gitignore/license), then:
```bash
git remote add origin https://github.com/yohananouaknine/oissyntheticdata.git
git push -u origin main
```

## 3. Tag a release
```bash
git tag -a v0.2.0 -m "oissyntheticdata 0.2.0"
git push origin v0.2.0
gh release create v0.2.0 --title "oissyntheticdata 0.2.0" --notes-file CHANGELOG.md   # or draft on GitHub
```

## 4. Verify before finishing
```bash
python -m unittest discover -s tests -p "test_*.py" -v   # expect 5 tests OK
python examples/quickstart.py
python examples/relational.py
```

## 5. Optional follow-ups (see PUBLISHING.md)
- PyPI: `python -m build && python -m twine upload dist/*` (name `oissyntheticdata`
  is confirmed free).
- Zenodo: enable the repo in Zenodo, then publish the GitHub release to mint a DOI.
- Add GitHub "About": description above + topics
  (`synthetic-data`, `synthpop`, `privacy`, `statistical-disclosure-control`, `cart`).

## Repository "About" suggestion
Description: *Zero-dependency sequential CART synthesis for secure research
(synthpop tradition), with relational support. An OIS tool — ois.co.il.*
