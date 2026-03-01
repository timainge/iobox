# Phase 6: Packaging and Distribution

**Status**: Not started
**Priority**: Medium — prerequisite for PyPI publishing and library consumption
**Scope change**: None (project infrastructure only)
**Depends on**: None (can run in parallel with functional phases)

---

## 6.1 Replace setup.py with pyproject.toml

### Problem

`setup.py` is legacy. The Python ecosystem has standardized on `pyproject.toml` (PEP 621). Additionally:
- `pytest.ini` is a separate config file that could live in `pyproject.toml`
- No linter or type checker configuration exists
- Dependencies in `setup.py` are unpinned; `requirements.txt` has fully pinned transitive deps with no separation of dev vs runtime

### Required Changes

**Create**: `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "iobox"
version = "0.2.0"
description = "Gmail to Markdown converter — extract, search and save emails as Markdown files"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.9"
authors = [
    {name = "Tim", email = "tim@goodcollective.com.au"},
]
keywords = ["gmail", "email", "markdown", "cli"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "Intended Audience :: End Users/Desktop",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Communications :: Email",
    "Topic :: Utilities",
]
dependencies = [
    "google-api-python-client>=2.0",
    "google-auth-httplib2>=0.2",
    "google-auth-oauthlib>=1.0",
    "html2text>=2024.0",
    "typer>=0.9",
    "python-dotenv>=1.0",
    "python-dateutil>=2.8",
    "PyYAML>=6.0",
    "rich>=13.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=6.0",
    "pytest-mock>=3.0",
    "ruff>=0.5",
    "mypy>=1.0",
]
docs = [
    "mkdocs-material>=9.0",
    "mkdocstrings[python]>=0.25",
]
mcp = [
    "mcp>=1.2",
]

[project.urls]
Homepage = "https://github.com/yourusername/iobox"
Repository = "https://github.com/yourusername/iobox"
Documentation = "https://yourusername.github.io/iobox"

[project.scripts]
iobox = "iobox.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["src/iobox"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=src --cov-report=term --cov-report=html"
norecursedirs = [".* venv build dist"]
log_cli = true
log_cli_level = "INFO"

[tool.ruff]
target-version = "py39"
line-length = 100

[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP", "B", "C4"]

[tool.mypy]
python_version = "3.9"
warn_return_any = true
warn_unused_configs = true
```

**Delete**: `setup.py`, `pytest.ini`

**Keep**: `requirements.txt` (for pinned reproducible installs in dev, but add a comment noting `pyproject.toml` is the source of truth)

### Acceptance Criteria

- [ ] `pip install -e .` works with `pyproject.toml`
- [ ] `pip install -e ".[dev]"` installs dev dependencies
- [ ] `python -m build` produces a valid wheel
- [ ] `iobox --help` works after install
- [ ] All 80 unit tests pass
- [ ] `setup.py` and `pytest.ini` deleted

---

## 6.2 Version Single Source of Truth

### Problem

Version is hardcoded in three places:
- `src/iobox/__init__.py:8` — `__version__ = "0.1.0"`
- `src/iobox/cli.py:30` — `__version__ = "0.1.0"`
- `setup.py:5` — `version="0.1.0"`

### Required Changes

**File**: `src/iobox/__init__.py`

Replace hardcoded version with:
```python
try:
    from importlib.metadata import version, PackageNotFoundError
    __version__ = version("iobox")
except PackageNotFoundError:
    __version__ = "0.1.0"  # fallback for uninstalled dev
```

**File**: `src/iobox/cli.py`

Remove `__version__ = "0.1.0"` and import from package:
```python
from iobox import __version__
```

### Acceptance Criteria

- [ ] Version defined in exactly one place: `pyproject.toml [project] version`
- [ ] `iobox version` outputs correct version after `pip install -e .`
- [ ] `python -c "import iobox; print(iobox.__version__)"` works
- [ ] Unit test for version command still passes

---

## 6.3 Public API Surface

### Problem

`src/iobox/__init__.py` only exports `__version__`. Library consumers must know internal module names.

### Required Changes

**File**: `src/iobox/__init__.py`

Add re-exports of all public functions with `__all__`:

```python
from iobox.auth import get_gmail_service, check_auth_status
from iobox.email_search import search_emails, validate_date_format
from iobox.email_retrieval import get_email_content, download_attachment
from iobox.markdown_converter import convert_email_to_markdown, convert_html_to_markdown
from iobox.file_manager import (
    save_email_to_markdown, create_output_directory,
    check_for_duplicates, save_attachment,
)
from iobox.email_sender import send_message, compose_message, forward_email

__all__ = [
    "__version__",
    "get_gmail_service", "check_auth_status",
    "search_emails", "validate_date_format",
    "get_email_content", "download_attachment",
    "convert_email_to_markdown", "convert_html_to_markdown",
    "save_email_to_markdown", "create_output_directory",
    "check_for_duplicates", "save_attachment",
    "send_message", "compose_message", "forward_email",
]
```

### Acceptance Criteria

- [ ] `from iobox import search_emails, get_gmail_service` works
- [ ] `from iobox import *` imports only `__all__` members
- [ ] No circular import issues

---

## 6.4 py.typed Marker and __main__.py

### Required Changes

**Create**: `src/iobox/py.typed` (empty file) — PEP 561 marker for type checkers

**Create**: `src/iobox/__main__.py`

```python
from iobox.cli import app
app()
```

### Acceptance Criteria

- [ ] `python -m iobox --help` works
- [ ] `mypy` recognizes iobox type annotations (verify with `mypy --strict src/iobox/__init__.py`)

---

## 6.5 LICENSE File

### Required Changes

**Create**: `LICENSE` with MIT license text (required for PyPI publishing)

### Acceptance Criteria

- [ ] `LICENSE` file exists at project root
- [ ] MIT license with correct year and author name

---

## Files Created/Modified/Deleted

| Action | File |
|---|---|
| Create | `pyproject.toml` |
| Create | `src/iobox/py.typed` |
| Create | `src/iobox/__main__.py` |
| Create | `LICENSE` |
| Modify | `src/iobox/__init__.py` |
| Modify | `src/iobox/cli.py` |
| Delete | `setup.py` |
| Delete | `pytest.ini` |
