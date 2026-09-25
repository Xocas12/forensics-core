"""Fetch logging, checksums, the SOURCES.yaml registry, and the network policy (contact
header, per-host rate limits, never-fetch-twice cache). Nothing enters a pipeline without
a SOURCES.yaml entry; every fetch attempt is logged, successful or not.

:mod:`~forensics_core.provenance.runner` holds the acquisition CLI every project's
``python -m <project>.acquire`` delegates to; its ``main`` is re-exported here as
:func:`run_acquisition` to avoid colliding with :func:`manifest.main`, the registry CLI.
"""

from forensics_core.provenance.manifest import (
    ACCESS_VALUES,
    FETCH_LOG_FILENAME,
    SOURCES_FILENAME,
    STATUS_VALUES,
    URL_OPTIONAL_ACCESS,
    Access,
    FetchRecord,
    RateLimiter,
    Source,
    Status,
    fetch,
    get_rate_limiter,
    load_sources,
    log_fetch,
    main,
    reset_rate_limiters,
    save_sources,
    sha256_file,
    update_source,
    validate_sources,
)

__all__ = [
    "ACCESS_VALUES",
    "FETCH_LOG_FILENAME",
    "SOURCES_FILENAME",
    "STATUS_VALUES",
    "URL_OPTIONAL_ACCESS",
    "Access",
    "FetchRecord",
    "RateLimiter",
    "Source",
    "Status",
    "fetch",
    "get_rate_limiter",
    "load_sources",
    "log_fetch",
    "main",
    "reset_rate_limiters",
    "save_sources",
    "sha256_file",
    "update_source",
    "validate_sources",
]

from forensics_core.provenance.runner import ATTEMPTABLE_STATUS, NEEDS_HUMAN
from forensics_core.provenance.runner import main as run_acquisition
from forensics_core.provenance.runner import plan as plan_acquisition

__all__ += [
    "ATTEMPTABLE_STATUS",
    "NEEDS_HUMAN",
    "plan_acquisition",
    "run_acquisition",
]
