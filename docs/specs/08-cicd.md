# Phase 8: CI/CD

**Status**: Not started
**Priority**: Medium — automates quality checks and publishing
**Scope change**: None (project infrastructure only)
**Depends on**: Phase 6 (pyproject.toml, ruff config)

---

## 8.1 CI Workflow

### Required Changes

**Create**: `.github/workflows/ci.yml`

Triggers on every push and PR to `main`. Two jobs:

**Lint job**:
- Checkout code
- Install ruff
- Run `ruff check src tests`
- Run `ruff format --check src tests`

**Test job** (matrix: Python 3.9, 3.10, 3.11, 3.12):
- Checkout code
- Install dependencies (`pip install -e ".[dev]"`)
- Run `pytest --cov=src --cov-report=xml --cov-fail-under=80`
- Upload coverage to Codecov (optional)

### Workflow Skeleton

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff
      - run: ruff check src tests
      - run: ruff format --check src tests

  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.9", "3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: pytest --cov=src --cov-report=xml --cov-fail-under=80
```

### Acceptance Criteria

- [ ] CI runs on every push to `main` and on PRs
- [ ] Lint job fails if ruff finds issues
- [ ] Test job runs across 4 Python versions
- [ ] Coverage threshold enforced at 80%
- [ ] All currently passing tests pass in CI

---

## 8.2 Release Workflow

### Required Changes

**Create**: `.github/workflows/release.yml`

Triggers on `v*` tag push. Uses PyPI Trusted Publishing (OIDC) — no API tokens stored in secrets.

### Prerequisites

1. Create PyPI project (or pending publisher) at pypi.org
2. Configure Trusted Publisher on PyPI pointing to the GitHub repo + workflow name
3. Create a `release` environment in GitHub repo settings (optional, for reviewer gate)

### Workflow Skeleton

```yaml
name: Release
on:
  push:
    tags: ["v*"]

jobs:
  test:
    uses: ./.github/workflows/ci.yml

  publish:
    needs: test
    runs-on: ubuntu-latest
    environment: release
    permissions:
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install build
      - run: python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
```

### Release Process

1. Update version in `pyproject.toml`
2. Commit: `git commit -m "bump version to 0.2.0"`
3. Tag: `git tag v0.2.0`
4. Push: `git push && git push --tags`
5. CI runs tests, then release workflow builds and publishes to PyPI

### Acceptance Criteria

- [ ] Tag push triggers release workflow
- [ ] Release runs CI tests first
- [ ] Build produces valid wheel and sdist
- [ ] Publish uses Trusted Publishing (no API token in secrets)
- [ ] Package appears on PyPI after successful release

---

## 8.3 Pre-commit Hooks

### Required Changes

**Create**: `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

### Setup

```bash
pip install pre-commit
pre-commit install
```

### Acceptance Criteria

- [ ] `pre-commit run --all-files` passes on current codebase
- [ ] Commits are automatically checked for lint and format issues
- [ ] Config documented in README or contributing guide

---

## Files Created

| File | Purpose |
|---|---|
| `.github/workflows/ci.yml` | Lint + test on push/PR |
| `.github/workflows/release.yml` | Build + publish on tag |
| `.pre-commit-config.yaml` | Local dev hooks |
