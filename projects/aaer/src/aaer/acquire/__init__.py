"""Acquisition for the aaer project: one module per source family, idempotent and cached.

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
  :mod:`aaer.clean`, under ``data/interim`` and ``data/processed``.

Source families:

``sec_edgar``
    AAER listing pages and RSS, one sample release PDF, the SEC fair-access and API
    documentation pages, one ``companyfacts`` specimen. **Read that module's docstring before
    writing any new SEC client:** it states the 10 requests/second ceiling and the
    contact-bearing ``User-Agent`` requirement, and cites the registry entries that document
    them.
``fsds``
    Financial Statement Data Sets quarterly zips and documentation. 2009q1 is empty by design;
    the first quarter with rows is 2009q2.
``bao_replication``
    The Bao et al. (2020) JAR replication repository, which is the free substitute for
    Compustat on their sample.
``literature``
    Beneish (1999), the Crossref records, and the two *Econ Journal Watch* papers that are the
    only free route to the 2022 erratum's numbers.

Entry point::

    python -m aaer.acquire --all       # every non-blocked, non-gated source
    python -m aaer.acquire <source_id> # one source
    python -m aaer.acquire --list      # show the registry and exit
    python -m aaer.acquire --all --dry-run   # print the plan, make no request

Sources with no acquirer are not omissions to be fixed silently: the runner prints each one
with the registry's own reason. Purchase, registration and subscription tiers are set out in
``data/ACCESS_NOTES.md``.
"""

from aaer.acquire.registry import ACQUIRERS, register

__all__ = ["ACQUIRERS", "register"]
