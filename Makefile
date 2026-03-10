.PHONY: test lint fmt type-check check

test:
	uv run pytest tests/unit tests/integration -v

lint:
	uv run ruff check src/ tests/

fmt:
	uv run ruff format src/ tests/

type-check:
	uv run mypy src/iobox/

check: lint type-check test
