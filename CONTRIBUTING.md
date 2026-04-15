# Contributing to ShieldPrompt

Thanks for your interest in improving ShieldPrompt. This guide covers how to
propose changes and how maintainers cut releases.

## Workflow

All changes land through pull requests — direct pushes to `main` are blocked
by branch protection. Every PR must be approved by a maintainer before it can
be merged.

1. **Fork** the repo (or create a branch if you have write access).
2. **Create a branch** off `main`:
   ```bash
   git checkout -b feat/short-description
   ```
3. **Install dev dependencies** in a virtualenv:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e '.[dev]'
   ```
4. **Make your changes.** Add or update tests under `tests/` for anything
   user-visible. Keep changes focused — smaller PRs get reviewed faster.
5. **Run the test suite** and make sure it passes:
   ```bash
   pytest -q
   ```
6. **Commit** with a clear message describing the *why*, not just the *what*.
7. **Push** and **open a PR** against `main`. Fill in the PR description with
   what changed and how to verify it.
8. Wait for review. A maintainer must approve before the PR can be merged.

## Code guidelines

- Python 3.9+ compatible.
- New entity types go in `src/shieldprompt/entities.py` plus the matching
  detector (regex or NER-based).
- No unscoped secrets, PII, or customer data in tests or fixtures.
- Keep third-party dependencies minimal. New runtime deps need justification
  in the PR description.

## Reporting bugs / security issues

- **Bugs** — open a GitHub issue with a minimal reproduction.
- **Security issues** — please email the maintainer privately first instead
  of opening a public issue.

---

## Releases

**Only the project owner (Chandan Kumar) can publish to PyPI.** The PyPI API
token is held by the owner and is not shared. Contributors and other
maintainers cannot cut releases — if a new release is needed, open an issue
requesting one.
