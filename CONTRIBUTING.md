# Contributing to Iobox

Thanks for your interest in contributing! Here's how to get started.

## Development setup

```bash
git clone https://github.com/timainge/iobox.git
cd iobox
uv sync
```

## Running tests

```bash
uv run pytest
```

## Making changes

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Add or update tests as needed
4. Run the test suite and make sure everything passes
5. Open a pull request

## Reporting bugs

Open an issue at https://github.com/timainge/iobox/issues with:

- What you expected to happen
- What actually happened
- Steps to reproduce
- Python version and OS

## Code style

- Keep it simple — avoid unnecessary abstractions
- Follow existing patterns in the codebase
- Tests go in `tests/unit/` or `tests/integration/`
