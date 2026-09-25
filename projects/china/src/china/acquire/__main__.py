"""``python -m china.acquire`` -- run the registry-driven acquisition for this project.

The runner itself is shared by all four projects and lives in
:mod:`forensics_core.provenance.runner`; this module only supplies the project's name, its
data directory, and the imports that populate the acquirer registry.
"""

from __future__ import annotations

import sys
from pathlib import Path

from forensics_core.provenance.runner import main as run

# Importing the source modules is what registers their acquirers.
from china.acquire import (  # noqa: F401  (imported for side effect)
    fallback,
    nbs_api,
    news,
    nightlights,
    pbc,
    wayback,
    yearbook,
)
from china.acquire.registry import ACQUIRERS

#: projects/china/data
DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Parameters
    ----------
    argv : list of str, optional
        Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns
    -------
    int
        ``0`` when every attempted source succeeded, ``1`` when any attempt failed. A run
        consisting only of gated sources exits ``0``.
    """
    return run(
        project="china",
        data_dir=DATA_DIR,
        acquirers=ACQUIRERS,
        argv=argv if argv is not None else sys.argv[1:],
    )


if __name__ == "__main__":
    raise SystemExit(main())
