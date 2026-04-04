.PHONY: test lint fmt type-check check hooks secrets

test:
	uv run pytest tests/unit tests/integration -v

lint:
	uv run ruff check src/ tests/

fmt:
	uv run ruff format src/ tests/

type-check:
	uv run mypy src/iobox/

secrets:
	uv run gitleaks detect --source . --config .gitleaks.toml

hooks:
	uv run pre-commit install
	@echo "Pre-commit hooks installed (includes secret scanning on every commit)"

check: lint type-check test
