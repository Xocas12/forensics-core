# projects/aaer — data / clean / test targets. Run from anywhere; uv resolves the workspace.
UV ?= uv
PROJECT := aaer
HERE := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

.PHONY: help data data-% status validate clean-interim clean test audit

help:
	@echo "make data            acquire every source in data/SOURCES.yaml that is not blocked (idempotent, logged)"
	@echo "make data-<id>       acquire one source by its SOURCES.yaml id"
	@echo "make status          print the registry table (id, access, status, bytes, blocked_reason)"
	@echo "make validate        validate data/SOURCES.yaml against the provenance schema"
	@echo "make clean-interim   delete data/interim and data/processed (never data/raw)"
	@echo "make test            run this project's tests"

# Refuses to run while config/forensics.toml still holds the placeholder contact (HARD RULE 6).
# Continues past blocked/unreachable sources, logging each attempt; exit status is non-zero if
# any source could not be acquired, so the failure is loud but the run completes.
data:
	cd $(HERE) && $(UV) run python -m $(PROJECT).acquire --all

data-%:
	cd $(HERE) && $(UV) run python -m $(PROJECT).acquire $*

status:
	cd $(HERE) && $(UV) run python -m forensics_core.provenance.manifest status data/SOURCES.yaml

validate:
	cd $(HERE) && $(UV) run python -m forensics_core.provenance.manifest validate data/SOURCES.yaml

clean-interim:
	find $(HERE)data/interim $(HERE)data/processed -type f ! -name .gitkeep -delete

clean: clean-interim

test:
	cd $(HERE) && $(UV) run pytest -q tests
