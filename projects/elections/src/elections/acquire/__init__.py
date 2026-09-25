"""Acquisition for the elections project: one module per source, idempotent and cached.

Design rules, shared by all four projects in the programme:

* Every source has an entry in ``data/SOURCES.yaml`` **before** any code fetches it. The
  registry is the source of truth for what exists and how to get it; this package only
  executes what the registry describes.
* Fetching goes through :func:`forensics_core.provenance.manifest.fetch`, which refuses to
  run while the contact string in ``config/forensics.toml`` is a placeholder, rate-limits per
  host, logs every attempt to ``data/fetch_log.jsonl`` (successful or not), and never fetches
  the same file twice unless forced.
* A source that cannot be reached is reported, recorded and skipped. It never aborts the run
  and it never causes anything to be invented.
* Nothing here writes anything that was not downloaded. Derived files belong in
  ``elections.clean``, under ``data/interim`` and ``data/processed``.

Entry point::

    python -m elections.acquire --all       # every non-blocked source
    python -m elections.acquire <source_id> # one source
    python -m elections.acquire --list      # show the registry and exit
"""

from elections.acquire.registry import ACQUIRERS, register

__all__ = ["ACQUIRERS", "register"]
