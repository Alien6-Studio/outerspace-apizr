.PHONY: install test lint format build docs all

install:
	uv sync --locked

test:
	uv run --locked pytest

lint:
	uv run --locked ruff check src tests scripts
	uv run --locked ruff format --check src tests scripts

format:
	uv run ruff check --fix src tests scripts
	uv run ruff format src tests scripts

build:
	uv build

docs:
	uv run --group docs mkdocs build --strict

all: lint test build
