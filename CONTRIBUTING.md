# Contributing to oissyntheticdata

Contributions are welcome and reviewed in the open. `oissyntheticdata` is developed
publicly; please propose and discuss changes through the repository rather than
sending private patches.

## Ways to contribute

- **Report a problem or ask a question** — open a GitHub Issue. For bugs, include
  a minimal example, the expected vs. actual behaviour, your Python version, and
  the `oissyntheticdata` version.
- **Propose a change** — open an Issue first to discuss scope and design, then a
  Pull Request referencing it. Small, focused PRs are easier to review.
- **Improve documentation or examples** — these are first-class contributions.

## Ground rules that protect the project's goals

`oissyntheticdata` exists to be auditable and to run in locked secure environments, so two
constraints are non-negotiable:

1. **No third-party runtime dependencies.** Everything under `oissyntheticdata/` must import
   only the Python standard library. CI and review will reject runtime imports of
   external packages. (Test/build tooling is exempt, but keep it minimal.)
2. **Confidentiality is a design property, not an afterthought.** Any change that
   could weaken disclosure control — e.g. relaxing the `min_leaf` floor, echoing
   raw values, or reproducing identifiers — must be justified explicitly in the PR
   and documented.

## Development setup

```bash
git clone https://github.com/yohananouaknine/oissyntheticdata.git
cd oissyntheticdata
python -m unittest discover -s tests -p "test_*.py" -v
python examples/quickstart.py
python examples/relational.py
```

## Pull request checklist

- [ ] Standard library only under `oissyntheticdata/`
- [ ] Tests added or updated; `python -m unittest discover -s tests` passes
- [ ] Public API changes reflected in `README.md` and `CHANGELOG.md`
- [ ] Version bumped in `pyproject.toml`, `oissyntheticdata/__init__.py`, `CHANGELOG.md` if releasing
- [ ] Confidentiality impact considered and noted

## Code of conduct

Be respectful and constructive. Maintainers may edit, close, or decline
contributions that fall outside the project's scope (see the limitations section
of the README).

## Disclosure of AI assistance

If you used a generative AI assistant to help prepare a contribution, you remain
fully responsible for it: review, test, and understand the code before submitting,
and note non-trivial AI assistance in the PR description.
