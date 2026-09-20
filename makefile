.PHONY: install test lint format build docs typecheck coverage audit all

install:
	uv sync --locked

test:
	uv run --locked pytest

lint:
	uv run --locked ruff check .
	uv run --locked ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

build:
	uv build

docs:
	uv run --group docs mkdocs build --strict

typecheck:
	uv run --locked pyright

coverage:
	uv run --locked pytest --cov --cov-report=term-missing

audit:
	uv run --locked --group security python scripts/audit_dependencies.py

all: lint typecheck test build
