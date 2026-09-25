# forensics — top-level targets for the library and its four projects. Requires `uv` (https://docs.astral.sh/uv/) and GNU make.
UV ?= uv
PROJECTS := elections aaer china gosplan

.PHONY: help setup test test-core lint format data data-status clean validate-sources $(addprefix data-,$(PROJECTS)) $(addprefix test-,$(PROJECTS))

help:
	@echo "make setup            install the uv workspace and pre-commit hooks"
	@echo "make test-core        the shared library only"
	@echo "make test             run every test suite (shared library + four projects)"
	@echo "make lint             ruff check + format check"
	@echo "make data             run `make data` in every project (never fabricates; fails loudly per source)"
	@echo "make data-<project>   one project: elections | aaer | china | gosplan"
	@echo "make validate-sources validate every projects/*/data/SOURCES.yaml against the schema"
	@echo "make clean            remove caches (never touches data/)"

setup:
	$(UV) sync --all-packages
	-$(UV) run pre-commit install

test:
	$(UV) run pytest -q

test-core:
	$(UV) run pytest -q packages/forensics_core/tests

# Static pattern rules: GNU make skips implicit-rule search for .PHONY targets, so a bare
# `test-%:` never matched `test-elections` and the per-project targets did nothing.
$(addprefix test-,$(PROJECTS)): test-%:
	$(UV) run pytest -q projects/$*/tests

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

format:
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

validate-sources:
	$(UV) run python -m forensics_core.provenance.manifest validate $(foreach p,$(PROJECTS),projects/$(p)/data/SOURCES.yaml)

# `make data` continues past a failing project so every project reports; the exit status is
# non-zero if any project had a blocked or failed source.
data:
	@status=0; for p in $(PROJECTS); do \
	  echo "=== projects/$$p: make data ==="; \
	  $(MAKE) -C projects/$$p data || status=1; \
	done; \
	$(MAKE) data-status; \
	exit $$status

$(addprefix data-,$(PROJECTS)): data-%:
	$(MAKE) -C projects/$* data

data-status:
	$(UV) run python -m forensics_core.provenance.manifest status $(foreach p,$(PROJECTS),projects/$(p)/data/SOURCES.yaml)

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .hypothesis
