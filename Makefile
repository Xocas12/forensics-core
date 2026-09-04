# forensics-core — shared method library. Requires uv and GNU make.
UV ?= uv

.PHONY: setup test lint format clean

setup:
	$(UV) sync
	-$(UV) run pre-commit install

test:
	$(UV) run pytest -q

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

format:
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .hypothesis
