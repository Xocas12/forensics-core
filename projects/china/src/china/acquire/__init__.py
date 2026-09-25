"""Acquisition for the china project: one module per source family, idempotent and cached.

Design rules, shared by all four projects in the programme:

* Every source has an entry in ``data/SOURCES.yaml`` **before** any code fetches it. The
  registry is the source of truth for what exists and how to get it; this package only
  executes what the registry describes, and no URL here was invented.
* Fetching goes through :func:`forensics_core.provenance.manifest.fetch`, which refuses to
  run while the contact string in ``config/forensics.toml`` is a placeholder, rate-limits per
  host, logs every attempt to ``data/fetch_log.jsonl``, and never fetches the same file twice
  unless forced.
* A source that cannot be reached is reported, recorded and skipped. It never aborts the run
  and it never causes anything to be invented or substituted.
* Nothing here writes anything that was not downloaded. Derived files belong in
  ``china.clean``, under ``data/interim`` and ``data/processed``.

What is here, and what deliberately is not
------------------------------------------
The bureau's portal cannot deliver a provincial series -- its legacy ``easyquery`` API is
blocked from this network and its replacement has an unknown values endpoint, see
:mod:`china.acquire.nbs_api` -- so the spine of this project is the yearbook web editions,
whose tables are JPEG scans. :mod:`china.acquire.yearbook` is
therefore the important module: it fetches contents frames, resolves tables by printed title
across every edition, and pulls the images. Turning an image into numbers is a stub in
:mod:`china.clean.yearbook`.

Sources the registry marks ``blocked`` get **no acquirer**, by design: the legacy
``easyquery.htm`` API in both languages, the China Electricity Council, and the two Earth
Observation Group nightlight products that now need an account. Paywalled and
registration-gated sources get none either; the shared runner reports them as needing a human
with the registry's own reason. ``data/ACCESS_NOTES.md`` lists every one of them.

One source is free, verified and deliberately partial: the harmonised nightlights product is
1.09 GB and is not part of a default run. See :mod:`china.acquire.nightlights`.

Entry point::

    python -m china.acquire --list        # the registry, with a mark on every acquirable id
    python -m china.acquire --all         # every attemptable source
    python -m china.acquire <source_id>   # one source
    python -m china.acquire --all --dry-run   # what would be attempted; makes no request
"""

from china.acquire.registry import ACQUIRERS, AcquireResult, register

__all__ = ["ACQUIRERS", "AcquireResult", "register"]
