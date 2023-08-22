.DEFAULT_GOAL := all
sources = src

.PHONY: .pdm  ## Check that PDM is installed
.pdm:
	@pdm -V || echo 'Please install PDM: https://pdm.fming.dev/latest/\#installation'

.PHONY: .pre-commit  ## Check that pre-commit is installed
.pre-commit:
	@pre-commit -V || echo 'Please install pre-commit: https://pre-commit.com/'

.PHONY: install  ## Install the package, dependencies, and pre-commit for local development
install: .pdm .pre-commit
	pdm install --group :all
	pre-commit install --install-hooks

.PHONY: refresh-lockfiles  ## Sync lockfiles with requirements files.
refresh-lockfiles: .pdm
	pdm update --update-reuse --group :all

.PHONY: rebuild-lockfiles  ## Rebuild lockfiles from scratch, updating all dependencies
rebuild-lockfiles: .pdm
	pdm update --update-eager --group :all

.PHONY: lint  ## Lint python source files
lint: .pdm
	pdm run ruff $(sources)
	pdm run black $(sources) --check --diff

.PHONY: format  ## Auto-format python source files
format: .pdm
	pdm run black $(sources)
	pdm run ruff --fix $(sources)
	
.PHONY: codespell  ## Use Codespell to do spellchecking
codespell: .pre-commit
	pre-commit run codespell --all-files

.PHONY: typecheck  ## Perform type-checking
typecheck: .pre-commit .pdm
	pre-commit run typecheck --all-files

.PHONY: all  ## Run the standard set of checks performed in CI
all: lint typecheck codespell

.PHONY: clean  ## Clear local caches and build artifacts
clean:
	rm -rf `find . -name .DS_Store`
	rm -rf `find . -name __pycache__`
	rm -f `find . -type f -name '*.py[co]'`
	rm -f `find . -type f -name '*~'`
	rm -f `find . -type f -name '.*~'`
	rm -rf site
	rm -rf dist
	rm -rf .cache
	rm -rf .ruff_cache

.PHONY: docs  ## Generate the docs
docs:
	pdm run mkdocs build

.PHONY: help  ## Display this message
help:
	@grep -E \
		'^.PHONY: .*?## .*$$' $(MAKEFILE_LIST) | \
		sort | \
		awk 'BEGIN {FS = ".PHONY: |## "}; {printf "\033[36m%-19s\033[0m %s\n", $$2, $$3}'