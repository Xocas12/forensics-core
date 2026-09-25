"""Acquisition for the gosplan project: one module per source family, idempotent and cached.

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
* Nothing here writes anything that was not downloaded. Derived files belong to
  :mod:`gosplan.transcribe`, under ``data/transcription`` and ``data/interim``.

What is special about this project: **downloads are the small half of the job.** Most of the
Soviet source material exists only as scanned Russian-language printed tables whose bundled
optical character recognition is unusable for numeric columns (see
``ia_narkhoz_1985_item`` in the registry: the cover title itself came out garbled). What this
package acquires is (a) the genuinely machine-readable Western and international series that
bracket the official figures, and (b) the *scans and their page-level manifests*, which are
the input to the transcription pipeline in :mod:`gosplan.transcribe`, not to any analysis.

Entry point::

    python -m gosplan.acquire --all       # every non-blocked source with an acquirer
    python -m gosplan.acquire <source_id> # one source
    python -m gosplan.acquire --list      # show the registry and exit
"""

from gosplan.acquire.registry import ACQUIRERS, register

__all__ = ["ACQUIRERS", "register"]
