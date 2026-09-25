"""``python -m elections.acquire`` - run the registry-driven acquisition for this project.

The runner itself is shared by all four projects and lives in
:mod:`forensics_core.provenance.runner`; this module only supplies the project's name, its
data directory, and the import that populates the acquirer registry.
"""

from __future__ import annotations

import sys
from pathlib import Path

from forensics_core.provenance.runner import main as run

# Importing the source modules is what registers their acquirers. One module per source
# family; the runner does the rest.
from elections.acquire import (  # noqa: F401  (imported for the registration side effect)
    anchors,
    commissions,
    controls,
    literature,
    uik_mirrors,
)
from elections.acquire.registry import ACQUIRERS

#: projects/elections/data
DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def main(argv: list[str] | None = None) -> int:
    return run(
        project="elections",
        data_dir=DATA_DIR,
        acquirers=ACQUIRERS,
        argv=argv if argv is not None else sys.argv[1:],
    )


if __name__ == "__main__":
    raise SystemExit(main())
