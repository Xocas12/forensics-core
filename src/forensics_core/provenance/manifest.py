"""SOURCES.yaml registry, fetch logging, checksums and the polite-fetch network policy.

This module enforces the programme's hard rules for every project:

* **Provenance** - every dataset used by a pipeline has an entry in the project's
  ``SOURCES.yaml`` (:class:`Source`), and every fetch attempt (success, HTTP error or
  exception) appends one JSON line to ``<project data dir>/fetch_log.jsonl``
  (:class:`FetchRecord`, :func:`log_fetch`).
* **Integrity** - a source may only be marked ``verified`` when a SHA-256 digest and a
  local path are recorded (:func:`sha256_file`).
* **Politeness** - :func:`fetch` refuses to touch the network until a real contact string
  is configured (:func:`forensics_core.config.require_contact`), sends it in the
  ``User-Agent``, and paces requests per host with a token bucket (:class:`RateLimiter`).
  The contact-in-User-Agent requirement follows the U.S. SEC's EDGAR "fair access"
  guidance (SEC, *Accessing EDGAR Data*, www.sec.gov/os/accessing-edgar-data); the same
  policy is applied to every host, whether or not the host demands it.
* **Never fetch twice** - an already-downloaded file whose digest matches the registry is
  not re-requested (see :func:`fetch`, step 2).

References
----------
Fielding, R. and J. Reschke (eds.), 2014. *Hypertext Transfer Protocol (HTTP/1.1): Range
Requests*, RFC 7233, IETF. Sections 3.1 (``Range``) and 4.1 (206 Partial Content) define
the resume protocol implemented by :func:`fetch`.
Turner, J., 1986. New directions in communications (or which way to the information age?).
*IEEE Communications Magazine* 24(10), 8-15 - origin of the token bucket used by
:class:`RateLimiter`. The formulation used here (capacity, refill rate, blocking ``wait``)
is taken from the textbook restatement in Tanenbaum & Wetherall, *Computer Networks*, 5th
ed., section 5.4; confirm against Turner (1986) before quoting the primary text.

Notes
-----
This is the one subpackage that performs I/O by design; the statistical modules stay pure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import threading
import time
import warnings
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, get_args
from urllib.parse import urlsplit

import httpx
import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from forensics_core._types import jsonable
from forensics_core.config import load_config, require_contact

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

SOURCES_FILENAME = "SOURCES.yaml"
FETCH_LOG_FILENAME = "fetch_log.jsonl"

Access = Literal["free", "registration", "paywalled", "archive_visit", "manual_transcription"]
Status = Literal["verified", "unverified", "blocked", "partial"]

ACCESS_VALUES: tuple[str, ...] = get_args(Access)
STATUS_VALUES: tuple[str, ...] = get_args(Status)

#: Access modes for which there is legitimately no URL to record.
URL_OPTIONAL_ACCESS: frozenset[str] = frozenset({"archive_visit", "manual_transcription"})

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string with a ``Z`` suffix (millisecond precision)."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# --------------------------------------------------------------------------------------
# the registry model
# --------------------------------------------------------------------------------------


class Source(BaseModel):
    """One entry of a project's ``SOURCES.yaml`` registry.

    Unknown keys are kept (``extra="allow"``) so that project-specific annotations survive a
    read-modify-write cycle; :func:`validate_sources` warns about them rather than failing,
    which is the only way one project can extend the shared schema without breaking the
    others.

    Attributes
    ----------
    id : str
        Stable slug, unique within the file; the key used by :func:`update_source`.
    name, provider : str
        Human-readable dataset name and the organisation publishing it.
    url : str or None
        Download URL. May be ``None`` only when ``access`` is ``"archive_visit"`` or
        ``"manual_transcription"``, i.e. when no URL exists to begin with.
    access : Access
        How the data can be obtained: ``free``, ``registration``, ``paywalled``,
        ``archive_visit`` or ``manual_transcription``.
    status : Status
        ``verified`` (downloaded and hashed), ``unverified`` (tried, nothing usable yet),
        ``blocked`` (refused: paywall, 401/403, robots) or ``partial``.
    fetched_at : str or None
        ISO-8601 UTC timestamp of the last fetch attempt.
    http_status : int or None
        HTTP status of the last attempt.
    sha256, bytes, local_path : str or None, int or None, str or None
        Integrity record of the downloaded file. ``local_path`` is relative to the project
        directory. Required together when ``status == "verified"``.
    license : str or None
        Licence or terms-of-use identifier.
    notes : str
        Free text. Required (non-empty) when ``status == "unverified"``: it must say what
        was tried, so that a later reader does not walk a known dead end again.
    blocked_reason : str or None
        Required (non-empty) when ``status == "blocked"``.

    Raises
    ------
    pydantic.ValidationError
        If any of the cross-field rules above is violated.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    provider: str
    url: str | None
    access: Access
    status: Status
    fetched_at: str | None = None
    http_status: int | None = None
    sha256: str | None = None
    bytes: int | None = None
    local_path: str | None = None
    license: str | None = None
    notes: str = ""
    blocked_reason: str | None = None

    @field_validator("access", mode="before")
    @classmethod
    def _check_access(cls, v: Any) -> Any:
        if v not in ACCESS_VALUES:
            raise ValueError(f"access must be one of {list(ACCESS_VALUES)}; got {v!r}")
        return v

    @field_validator("status", mode="before")
    @classmethod
    def _check_status(cls, v: Any) -> Any:
        if v not in STATUS_VALUES:
            raise ValueError(f"status must be one of {list(STATUS_VALUES)}; got {v!r}")
        return v

    @field_validator("id", "name", "provider")
    @classmethod
    def _non_empty(cls, v: str, info: ValidationInfo) -> str:
        if not v.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string")
        return v

    @field_validator("sha256")
    @classmethod
    def _check_sha256(cls, v: str | None) -> str | None:
        if v is not None and not _SHA256_RE.match(v):
            raise ValueError(f"sha256 must be 64 hexadecimal characters; got {v!r}")
        return v

    @field_validator("bytes")
    @classmethod
    def _check_bytes(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError(f"bytes must be non-negative; got {v!r}")
        return v

    @field_validator("http_status")
    @classmethod
    def _check_http_status(cls, v: int | None) -> int | None:
        if v is not None and not 100 <= v <= 599:
            raise ValueError(f"http_status must be a valid HTTP status code; got {v!r}")
        return v

    @model_validator(mode="after")
    def _check_status_requirements(self) -> Source:
        if self.status == "blocked" and not (self.blocked_reason or "").strip():
            raise ValueError(
                'status="blocked" requires a non-empty blocked_reason saying who refused and why'
            )
        if self.status == "verified":
            # "verified" means the source was reached and confirmed to be what it claims.
            # That happens in two ways, and both must be accepted:
            #   (a) a probe during research: HTTP 200 at a recorded time, nothing downloaded
            #       into the project yet (local_path is null until `make data` runs);
            #   (b) an acquisition: the bytes are on disk, so local_path AND sha256 exist.
            # Requiring (b) unconditionally would force every source a human confirmed by
            # fetching to be mislabelled until the pipeline downloads it.
            # 206 counts: a ranged request that returns Partial Content proved the file is
            # there and served its first bytes, which is exactly how large files are probed
            # without downloading them.
            probed = self.http_status in (200, 206) and bool((self.fetched_at or "").strip())
            acquired = bool((self.local_path or "").strip())
            if not (probed or acquired):
                raise ValueError(
                    'status="verified" requires evidence: either a successful probe '
                    "(http_status=200 with fetched_at) or an acquired file (local_path)"
                )
        # Whenever a file is claimed on disk, its checksum must be there too -- at any status.
        if (self.local_path or "").strip() and not (self.sha256 or "").strip():
            raise ValueError(
                "local_path is set but sha256 is missing; a file we hold must be checksummed"
            )
        if self.status == "unverified" and not self.notes.strip():
            raise ValueError(
                'status="unverified" requires notes saying what was tried (URL, date, what '
                "came back), so the dead end is not walked twice"
            )
        if self.url is None and self.access not in URL_OPTIONAL_ACCESS:
            raise ValueError(
                "url may be null only when access is one of "
                f"{sorted(URL_OPTIONAL_ACCESS)}; got access={self.access!r}"
            )
        return self


def _error_messages(exc: ValidationError) -> list[str]:
    """Flatten a pydantic ValidationError into human-readable one-liners."""
    out: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"])
        msg = str(err["msg"]).removeprefix("Value error, ")
        out.append(f"{loc}: {msg}" if loc else msg)
    return out


def _dump_source(source: Source) -> dict[str, Any]:
    """Model field order first, then any extra keys the project added."""
    return source.model_dump(mode="python")


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a temporary file in the same directory + os.replace.

    A crash mid-write therefore leaves the previous registry intact rather than a truncated
    file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read_raw(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Read a SOURCES.yaml file into a list of raw mappings (no model validation)."""
    p = Path(path)
    with open(p, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(
            f"{p}: SOURCES.yaml must contain a YAML list of source mappings, got "
            f"{type(data).__name__}"
        )
    raw: list[dict[str, Any]] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"{p}: sources[{i}] must be a mapping, got {type(item).__name__}")
        non_string = [k for k in item if not isinstance(k, str)]
        if non_string:
            raise ValueError(f"{p}: sources[{i}] has non-string keys: {non_string}")
        raw.append(item)
    return raw


def load_sources(path: str | os.PathLike[str]) -> list[Source]:
    """Read and validate a ``SOURCES.yaml`` registry.

    Parameters
    ----------
    path : path-like
        The registry file.

    Returns
    -------
    list of Source

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    ValueError
        If the file is not a list of mappings, or if any entry fails validation. Use
        :func:`validate_sources` to collect *all* errors instead of failing on the first.
    """
    p = Path(path)
    raw = _read_raw(p)
    sources: list[Source] = []
    for i, item in enumerate(raw):
        try:
            sources.append(Source(**item))
        except ValidationError as exc:
            sid = item.get("id", "?")
            joined = "; ".join(_error_messages(exc))
            raise ValueError(f"{p}: sources[{i}] ({sid}): {joined}") from exc
    return sources


def save_sources(path: str | os.PathLike[str], sources: list[Source]) -> None:
    """Write a registry back to disk in model field order.

    The file is *rewritten* from the models: YAML comments, blank lines and the original key
    order of each entry are **not** preserved (pyyaml's safe loader discards them). Prose
    that must survive belongs in the ``notes`` field, not in a comment.

    Parameters
    ----------
    path : path-like
        Destination file; parent directories are created.
    sources : list of Source
        Entries to write, in the order given.

    Raises
    ------
    ValueError
        If any element is not a :class:`Source`.
    """
    payload = []
    for i, s in enumerate(sources):
        if not isinstance(s, Source):
            raise ValueError(f"sources[{i}] must be a Source, got {type(s).__name__}")
        payload.append(_dump_source(s))
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100)
    _atomic_write_text(Path(path), text)


def validate_sources(path: str | os.PathLike[str]) -> list[str]:
    """Check every entry of a registry and return human-readable errors.

    Parameters
    ----------
    path : path-like
        The registry file.

    Returns
    -------
    list of str
        Empty if the file is valid. Otherwise one string per problem, formatted
        ``"sources[i] (<id>): <error>"``.

    Warns
    -----
    UserWarning
        For keys that are not fields of :class:`Source`. Extra keys are *allowed* (a project
        may annotate its own registry), so they are a warning and never an error.

    Raises
    ------
    FileNotFoundError, ValueError
        If the file is missing or is not a YAML list of mappings - those are failures of the
        file as a whole rather than of one entry.
    """
    p = Path(path)
    raw = _read_raw(p)
    known = set(Source.model_fields)
    errors: list[str] = []
    unknown: list[str] = []
    seen: dict[str, int] = {}
    for i, item in enumerate(raw):
        sid = str(item.get("id", "?"))
        extra = sorted(set(item) - known)
        if extra:
            unknown.append(f"sources[{i}] ({sid}): {extra}")
        if sid in seen:
            errors.append(
                f"sources[{i}] ({sid}): duplicate id (first seen at sources[{seen[sid]}])"
            )
        else:
            seen[sid] = i
        try:
            Source(**item)
        except ValidationError as exc:
            errors.extend(f"sources[{i}] ({sid}): {msg}" for msg in _error_messages(exc))
    if unknown:
        warnings.warn(
            f"{p}: unknown keys (kept, but not part of the Source schema): " + "; ".join(unknown),
            UserWarning,
            stacklevel=2,
        )
    return errors


def _find_entry(raw: list[dict[str, Any]], source_id: str) -> int | None:
    for i, item in enumerate(raw):
        if str(item.get("id", "")) == source_id:
            return i
    return None


def update_source(path: str | os.PathLike[str], source_id: str, **fields: Any) -> Source:
    """Read-modify-write exactly one entry of a registry.

    The whole file is re-read, the matching entry is merged with ``fields`` and re-validated,
    and the file is rewritten through a temporary file + :func:`os.replace`, so a concurrent
    reader never sees a half-written registry. Entries other than ``source_id`` are written
    back exactly as they were parsed and are *not* re-validated, so one broken neighbour
    cannot block an unrelated update; comments are still lost, as in :func:`save_sources`.

    Parameters
    ----------
    path : path-like
        The registry file.
    source_id : str
        ``id`` of the entry to update.
    **fields
        Field values to overwrite.

    Returns
    -------
    Source
        The updated, validated entry.

    Raises
    ------
    ValueError
        If no entry has that id, or if the merged entry would be invalid (the file is then
        left untouched).
    """
    p = Path(path)
    raw = _read_raw(p)
    idx = _find_entry(raw, source_id)
    if idx is None:
        known = ", ".join(str(item.get("id", "?")) for item in raw) or "<none>"
        raise ValueError(f"{p}: no source with id={source_id!r}; known ids: {known}")
    merged = dict(raw[idx])
    merged.update(fields)
    try:
        updated = Source(**merged)
    except ValidationError as exc:
        joined = "; ".join(_error_messages(exc))
        raise ValueError(
            f"{p}: updating source {source_id!r} with {sorted(fields)} would make it invalid: "
            f"{joined}"
        ) from exc
    out = list(raw)
    out[idx] = _dump_source(updated)
    text = yaml.safe_dump(out, sort_keys=False, allow_unicode=True, width=100)
    _atomic_write_text(p, text)
    return updated


# --------------------------------------------------------------------------------------
# fetch log and checksums
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class FetchRecord:
    """One row of ``fetch_log.jsonl``: a single fetch attempt, successful or not.

    ``error`` is ``None`` only when the bytes landed on disk and (if one was supplied) the
    expected digest matched. ``skipped_cached`` marks an attempt that made no request at all
    because the file was already present with the digest the registry records.
    """

    source_id: str
    url: str
    tool: str
    started_at: str
    finished_at: str
    http_status: int | None
    bytes: int | None
    sha256: str | None
    local_path: str | None
    error: str | None
    skipped_cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))


def log_fetch(project_data_dir: Path, rec: FetchRecord) -> None:
    """Append one JSON line describing ``rec`` to ``<project_data_dir>/fetch_log.jsonl``.

    The directory is created if needed. Every attempt is logged, including failures: the log
    is the audit trail of what was tried, when, and what came back.
    """
    d = Path(project_data_dir)
    d.mkdir(parents=True, exist_ok=True)
    line = json.dumps(rec.to_dict(), ensure_ascii=False, sort_keys=False)
    with open(d / FETCH_LOG_FILENAME, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + "\n")


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    """SHA-256 of a file, read in ``chunk``-byte blocks.

    Parameters
    ----------
    path : Path
        File to hash.
    chunk : int, default 1048576
        Read block size in bytes.

    Returns
    -------
    str
        Lower-case hexadecimal digest.

    Raises
    ------
    ValueError
        If ``chunk`` is not positive.
    FileNotFoundError
        If the file does not exist.
    """
    if chunk <= 0:
        raise ValueError(f"chunk must be a positive number of bytes; got {chunk!r}")
    h = hashlib.sha256()
    with open(Path(path), "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


# --------------------------------------------------------------------------------------
# rate limiting
# --------------------------------------------------------------------------------------


class RateLimiter:
    """Thread-safe token bucket limiting requests to ``per_second`` on average.

    The bucket holds ``burst`` tokens and refills at ``per_second`` tokens per second;
    :meth:`wait` consumes one token, sleeping until one is available. With the default
    ``burst=1`` this is exactly "at most one request every ``1 / per_second`` seconds", with
    no credit accumulated while idle.

    Parameters
    ----------
    per_second : float
        Refill rate, requests per second. Must be positive.
    burst : float, default 1.0
        Bucket capacity in tokens (>= 1).
    monotonic : callable, optional
        Clock returning seconds; injectable so tests can drive it deterministically.
    sleep : callable, optional
        Blocking sleep; injectable for the same reason.

    Raises
    ------
    ValueError
        If ``per_second <= 0`` or ``burst < 1``.

    Notes
    -----
    Token bucket as in Turner (1986), *IEEE Communications Magazine* 24(10), 8-15; the
    capacity/refill formulation used here is taken from the textbook restatement in
    Tanenbaum & Wetherall, *Computer Networks*, 5th ed., section 5.4 (cited from memory -
    confirm against the primary text before quoting it).

    Examples
    --------
    >>> ticks = [0.0]
    >>> lim = RateLimiter(2.0, monotonic=lambda: ticks[0],
    ...                   sleep=lambda s: ticks.__setitem__(0, ticks[0] + s))
    >>> lim.wait(); ticks[0]          # the first call is free
    0.0
    >>> lim.wait(); ticks[0]          # the second waits 1/2 s
    0.5
    """

    def __init__(
        self,
        per_second: float,
        *,
        burst: float = 1.0,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        per_second = float(per_second)
        burst = float(burst)
        if not per_second > 0:
            raise ValueError(f"per_second must be > 0; got {per_second!r}")
        if not burst >= 1.0:
            raise ValueError(f"burst must be >= 1 token; got {burst!r}")
        self.per_second = per_second
        self.burst = burst
        self._monotonic = monotonic
        self._sleep = sleep
        self._lock = threading.Lock()
        self._tokens = burst
        self._last = monotonic()

    def wait(self) -> None:
        """Block until one token is available, then consume it."""
        with self._lock:
            now = self._monotonic()
            self._tokens = min(self.burst, self._tokens + (now - self._last) * self.per_second)
            self._last = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                delay = 0.0
            else:
                delay = (1.0 - self._tokens) / self.per_second
                self._tokens = 0.0
                # Charge the wait to the bucket now, while holding the lock, so concurrent
                # callers queue behind this one instead of all claiming the same slot.
                self._last = now + delay
        if delay > 0:
            self._sleep(delay)


_LIMITERS: dict[str, RateLimiter] = {}
_LIMITERS_LOCK = threading.Lock()


def get_rate_limiter(host: str, *, root: Path | None = None) -> RateLimiter:
    """Return the process-wide :class:`RateLimiter` for ``host``.

    The rate comes from ``config/forensics.toml`` via
    :meth:`forensics_core.config.HttpConfig.rate_limit_for`; a limiter is rebuilt when the
    configured rate has changed since it was created.

    Raises
    ------
    ValueError
        If ``host`` is empty.
    """
    if not host:
        raise ValueError("host must be a non-empty string")
    rate = load_config(root).rate_limit_for(host)
    with _LIMITERS_LOCK:
        limiter = _LIMITERS.get(host)
        if limiter is None or limiter.per_second != rate:
            limiter = RateLimiter(rate)
            _LIMITERS[host] = limiter
        return limiter


def reset_rate_limiters() -> None:
    """Drop every cached limiter.

    Maintenance hook for a long-lived process whose configuration changed underneath it (the
    cache is keyed by host and only notices a changed rate, not an edited configuration file
    that leaves the rate alone). It is *not* a test-only shim: code that wants a limiter of
    its own should pass ``limiter=`` to :func:`fetch` instead of resetting the shared cache.
    """
    with _LIMITERS_LOCK:
        _LIMITERS.clear()


# --------------------------------------------------------------------------------------
# fetching
# --------------------------------------------------------------------------------------


def _registry_entry(registry: Path, source_id: str) -> dict[str, Any] | None:
    """Raw registry mapping for ``source_id``, or None if unreadable or absent."""
    if not registry.exists():
        return None
    try:
        raw = _read_raw(registry)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        warnings.warn(f"{registry}: could not be read ({exc})", RuntimeWarning, stacklevel=3)
        return None
    idx = _find_entry(raw, source_id)
    return None if idx is None else raw[idx]


def _require_registry_entry(registry: Path, source_id: str) -> dict[str, Any]:
    """Raw registry mapping for ``source_id``, or a loud :class:`ValueError`.

    "Nothing enters a pipeline without a ``SOURCES.yaml`` entry": a fetch for a source the
    registry does not know is a mistake in the caller, not something to warn about after the
    bytes have already landed on disk. :func:`fetch` calls this before it makes any request,
    unless the caller passes ``require_registry=False``.
    """
    if not registry.exists():
        raise ValueError(
            f"{registry} does not exist, so this download could not be recorded anywhere. "
            "Create the project registry with an entry for "
            f"id={source_id!r}, or pass require_registry=False for a deliberate one-off "
            "download that is logged but not registered."
        )
    raw = _read_raw(registry)
    idx = _find_entry(raw, source_id)
    if idx is None:
        known = ", ".join(str(item.get("id", "?")) for item in raw) or "<none>"
        raise ValueError(
            f"{registry}: no source with id={source_id!r}; known ids: {known}. Add the entry "
            "before fetching, or pass require_registry=False."
        )
    return raw[idx]


def _project_relative(path: Path, project_dir: Path) -> str:
    """``path`` as a POSIX path relative to ``project_dir``.

    The registry is the artefact that enters git while the raw data does not, so
    ``local_path`` must mean the same thing on every machine (see INTERFACES.md: "``local_path``
    is relative to the project directory"). Forward slashes are used on every platform so
    that a registry written on Windows reads correctly elsewhere. A destination *outside* the
    project directory has no relative form and is recorded as a resolved absolute path.
    """
    p = Path(path).resolve()
    try:
        return p.relative_to(Path(project_dir).resolve()).as_posix()
    except ValueError:
        return str(p)


def _recorded_file_intact(entry: dict[str, Any] | None, project_dir: Path) -> bool:
    """True if the entry's ``local_path`` still exists and hashes to its recorded ``sha256``.

    Used by :func:`fetch` to decide whether a *failed* attempt should downgrade the entry: a
    transient failure does not un-verify data that is still on disk and still matches the
    digest the registry claims for it.
    """
    if not entry:
        return False
    recorded = entry.get("sha256")
    local = entry.get("local_path")
    if not recorded or not local:
        return False
    p = Path(str(local))
    if not p.is_absolute():
        p = Path(project_dir) / p
    try:
        return p.is_file() and sha256_file(p) == str(recorded).lower()
    except OSError:
        return False


#: ``Content-Range: bytes <first>-<last>/<complete-length>`` (RFC 7233 section 4.2).
_CONTENT_RANGE_RE = re.compile(r"^\s*bytes\s+(\d+)\s*-\s*(\d+)\s*/\s*(\d+|\*)\s*$", re.IGNORECASE)

#: Statuses that mean "the publisher refused", not "the transfer went wrong".
_BLOCKED_STATUSES: tuple[int, ...] = (401, 402, 403, 451)


def _parse_content_range(value: str | None) -> tuple[int, int, int | None] | None:
    """Parse a ``Content-Range`` header (RFC 7233 section 4.2).

    Returns ``(first, last, complete_length)`` with ``complete_length = None`` for ``"*"``, or
    ``None`` when the header is absent, malformed or has ``last < first``.
    """
    if value is None:
        return None
    m = _CONTENT_RANGE_RE.match(value)
    if m is None:
        return None
    first, last = int(m.group(1)), int(m.group(2))
    if last < first:
        return None
    complete = None if m.group(3) == "*" else int(m.group(3))
    return first, last, complete


def _placement_plan(resp: httpx.Response, start_byte: int) -> tuple[bool, int | None, str | None]:
    """Where does this response body belong? ``(append, complete_length, error)``.

    Only ``200`` (the whole representation) and ``206`` (a partial one) carry a body that can
    be assembled into the destination file. RFC 7233 section 4.1 requires the client to place
    a ``206`` payload according to its ``Content-Range``, so a ``206`` is appended **only**
    when the range it reports starts exactly where the local ``.part`` file ends; a ``206``
    that starts at byte 0 restarts the download, and any other offset - or a missing or
    unparseable ``Content-Range`` - is an error rather than a blind concatenation.

    Every other status (``204``, ``205``, ``304``, ...) is reported as an error: an empty or
    body-less response is not a completed download, and recording it as ``verified`` would be
    a false integrity claim.
    """
    status = resp.status_code
    if status == 200:
        return False, None, None
    if status != 206:
        return False, None, f"unexpected HTTP {status}: no complete response body"
    parsed = _parse_content_range(resp.headers.get("Content-Range"))
    if parsed is None:
        return (
            False,
            None,
            "206 Partial Content with an absent or unparseable Content-Range header "
            f"({resp.headers.get('Content-Range')!r})",
        )
    first, _last, complete = parsed
    if start_byte > 0 and first == start_byte:
        return True, complete, None
    if first == 0:
        return False, complete, None
    return (
        False,
        None,
        f"206 Content-Range starts at byte {first}, but the local part file ends at byte "
        f"{start_byte}; refusing to concatenate mismatched ranges",
    )


def _stream_to_part(
    resp: httpx.Response, part: Path, *, append: bool, already: int, max_bytes: int | None
) -> tuple[str | None, int]:
    """Stream a response body into ``part``.

    Returns ``(error, received)`` where ``received`` counts the bytes written by *this*
    response (excluding anything already in the part file) and ``error`` is None on success.
    """
    total = already if append else 0
    received = 0
    overflow = False
    with open(part, "ab" if append else "wb") as fh:
        for chunk in resp.iter_bytes():
            if max_bytes is not None and total + len(chunk) > max_bytes:
                overflow = True
                break
            fh.write(chunk)
            total += len(chunk)
            received += len(chunk)
    if overflow:
        # The partial file is useless: the resource is larger than we are allowed to take.
        part.unlink(missing_ok=True)
        return f"exceeded max_bytes ({max_bytes} bytes)", received
    return None, received


def _size_error(
    resp: httpx.Response,
    part: Path,
    *,
    received: int,
    complete_length: int | None,
    allow_empty: bool,
) -> str | None:
    """Cross-check the assembled file against what the response said it would be.

    Three checks, all of which would otherwise end as a confident ``verified`` entry over
    incomplete bytes: the body is shorter (or longer) than ``Content-Length`` declared; the
    assembled file does not have the complete length declared by ``Content-Range``; the file
    is empty (a captive portal, a proxy stub or a truncated response), which is accepted only
    when the caller explicitly asks for it with ``allow_empty=True``.

    ``Content-Length`` counts *encoded* bytes, so the check is skipped when the response
    carries a non-identity ``Content-Encoding`` (httpx hands over decoded bytes).
    """
    encoding = resp.headers.get("Content-Encoding", "").strip().lower()
    if encoding in ("", "identity"):
        declared = resp.headers.get("Content-Length")
        if declared is not None:
            try:
                n = int(declared)
            except ValueError:
                n = -1
            if n >= 0 and n != received:
                return f"incomplete body: Content-Length declared {n} bytes, received {received}"
    total = part.stat().st_size
    if complete_length is not None and total != complete_length:
        return (
            f"incomplete body: assembled {total} bytes, but Content-Range declared a complete "
            f"length of {complete_length}"
        )
    if total == 0 and not allow_empty:
        return "empty response body (0 bytes); pass allow_empty=True to record an empty file"
    return None


def _registry_fields(
    rec: FetchRecord, existing: dict[str, Any] | None, *, intact: bool = False
) -> dict[str, Any]:
    """Registry fields implied by one fetch attempt (see :func:`fetch`, step 5).

    On success the integrity fields are overwritten *and* ``blocked_reason`` is cleared, so a
    source that goes ``blocked`` -> ``verified`` does not keep advertising the refusal that is
    no longer true.

    On failure a dated note is always appended. What happens to ``status`` depends on
    ``intact``: when the file the entry points at is still there and still hashes to the
    recorded digest, the status is left exactly as it was (a failed *re*-fetch does not
    un-verify data that is demonstrably fine). Otherwise the entry is downgraded to
    ``blocked`` (401/402/403/451, and any 4xx other than 404 on a ``paywalled`` entry),
    ``unverified`` (404 - the thing is simply not there) or ``partial`` (everything else).
    """
    fields: dict[str, Any] = {"fetched_at": rec.finished_at, "http_status": rec.http_status}
    if rec.error is None and rec.sha256 is not None:
        fields.update(
            sha256=rec.sha256,
            bytes=rec.bytes,
            local_path=rec.local_path,
            status="verified",
            blocked_reason=None,
        )
        return fields

    reason = rec.error if rec.error is not None else f"HTTP {rec.http_status}"
    note = f"{rec.finished_at} {rec.url}: {reason}"
    old = str((existing or {}).get("notes") or "").strip()
    fields["notes"] = f"{old}\n{note}" if old else note
    if intact:
        return fields

    status = rec.http_status
    paywalled = str((existing or {}).get("access", "")) == "paywalled"
    if status in _BLOCKED_STATUSES:
        fields.update(status="blocked", blocked_reason=f"HTTP {status}")
    elif paywalled and status is not None and 400 <= status < 500 and status != 404:
        fields.update(status="blocked", blocked_reason=f"HTTP {status} (paywalled source)")
    else:
        fields["status"] = "unverified" if status == 404 else "partial"
    return fields


def fetch(
    url: str,
    dest: Path,
    *,
    project_data_dir: Path,
    source_id: str,
    headers: dict | None = None,
    resume: bool = False,
    max_bytes: int | None = None,
    force: bool = False,
    tool: str = "httpx",
    timeout: float | None = None,
    expected_sha256: str | None = None,
    allow_empty: bool = False,
    require_registry: bool = True,
    transport: httpx.BaseTransport | None = None,
    limiter: RateLimiter | None = None,
) -> FetchRecord:
    """Download one source politely, log the attempt, and update the registry.

    The six steps, in order:

    1. :func:`forensics_core.config.require_contact` - raises
       :class:`~forensics_core.config.ContactNotConfigured` **before any request** and before
       anything is written, so a repository still carrying the placeholder contact cannot
       touch the network (HARD RULE 6). Caller input is then validated in the same breath -
       the URL, ``expected_sha256`` and the existence of a registry entry for ``source_id`` -
       so that whether a bad call raises never depends on the state of the disk.
    2. Never fetch twice: if ``dest`` exists, the registry records a ``sha256`` for
       ``source_id``, that digest matches the file on disk and ``force`` is false, no request
       is made - a ``skipped_cached`` record is logged and returned. (Switched off by
       ``cache.never_refetch = false`` in the configuration.)
    3. Per-host :class:`RateLimiter` from the configuration, and a ``User-Agent`` carrying
       the configured contact string.
    4. Stream to ``dest`` + ``".part"``. With ``resume=True`` and an existing part file, send
       ``Range: bytes=<size>-`` (RFC 7233 section 3.1). Only ``200`` (whole body) and ``206``
       (partial body, placed according to its ``Content-Range`` as RFC 7233 section 4.1
       requires) count as a transfer; a ``206`` is appended only when its range starts exactly
       where the part file ends, a ``200`` means the server ignored the range and the download
       restarts from zero, and every other status is an error. The assembled file is
       cross-checked against ``Content-Length`` / ``Content-Range`` and, unless
       ``allow_empty``, refused when it is empty. On success the part file is renamed onto
       ``dest``.
    5. The attempt is **always** logged with :func:`log_fetch` - success, HTTP error or
       exception - and then the registry entry is updated: ``verified`` with digest, size and
       path (and ``blocked_reason`` cleared) on success; on failure a dated note plus
       ``blocked`` (401/402/403/451, or any 4xx bar 404 on a ``paywalled`` entry),
       ``unverified`` (404) or ``partial`` (anything else) - except that a failure leaves
       ``status`` alone when the file the entry points at is still present and still matches
       its recorded digest.
    6. The :class:`FetchRecord` is returned. HTTP and transport errors never raise.

    Parameters
    ----------
    url : str
        Absolute http(s) URL.
    dest : Path
        Final path of the downloaded file.
    project_data_dir : Path
        Project ``data/`` directory: holds ``fetch_log.jsonl`` and, optionally,
        ``SOURCES.yaml``. Its parent is the project directory that ``local_path`` is
        relative to.
    source_id : str
        Registry id this download belongs to.
    headers : dict, optional
        Extra request headers; they override the defaults, ``User-Agent`` included.
    resume : bool, default False
        Attempt a ranged resume from an existing ``.part`` file.
    max_bytes : int, optional
        Abort (and delete the part file) as soon as the body would exceed this size; the
        record's ``error`` is then ``"exceeded max_bytes (...)"``.
    force : bool, default False
        Re-download even when the cached copy matches the registry digest.
    tool : str, default "httpx"
        Recorded in the log; set it when a source is fetched by something else.
    timeout : float, optional
        Per-request timeout; defaults to ``http.default_timeout_seconds``.
    expected_sha256 : str, optional
        64 hexadecimal characters. If given and the digest differs, the file is kept as
        ``dest`` + ``".bad"`` and the record carries a ``sha256 mismatch`` error.
    allow_empty : bool, default False
        Accept a zero-byte body as a completed download. Off by default: an empty file
        recorded as ``verified`` (digest ``e3b0c442...``) is a false integrity claim, and an
        empty body is far more often a captive portal or a truncated response than a real
        empty dataset.
    require_registry : bool, default True
        Refuse (``ValueError``, before any request) to fetch a source that has no
        ``SOURCES.yaml`` entry, or into a project directory that has no registry at all. Set
        it to ``False`` for a deliberate one-off download that is logged but not registered.
    transport : httpx.BaseTransport, optional
        Injected transport; tests pass :class:`httpx.MockTransport` so that nothing in the
        test suite can reach the network.
    limiter : RateLimiter, optional
        Injected limiter, bypassing the per-host cache.

    Returns
    -------
    FetchRecord
        Always - HTTP status >= 400, unexpected statuses, transport exceptions, size aborts
        and digest mismatches are all reported through ``FetchRecord.error``. Its
        ``local_path`` is relative to the project directory, like the registry's.

    Raises
    ------
    forensics_core.config.ContactNotConfigured
        While the contact string is still the placeholder.
    ValueError
        If ``url`` is not an absolute http(s) URL, if ``expected_sha256`` is not a SHA-256
        digest, or if ``require_registry`` is set and the registry has no entry for
        ``source_id``.
    """
    cfg = require_contact()  # step 1 - before anything else

    dest = Path(dest)
    project_data_dir = Path(project_data_dir)
    project_dir = project_data_dir.resolve().parent
    registry = project_data_dir / SOURCES_FILENAME
    started = _utc_now_iso()

    # step 1 (continued) - validate the call itself, before any disk or network access, so
    # that a bad argument raises whether or not a cached copy happens to be lying around.
    split = urlsplit(url)
    if split.scheme not in ("http", "https") or not split.hostname:
        raise ValueError(f"fetch() needs an absolute http(s) URL with a host; got {url!r}")
    if expected_sha256 is not None and not _SHA256_RE.match(expected_sha256):
        raise ValueError(
            f"expected_sha256 must be 64 hexadecimal characters; got {expected_sha256!r}"
        )
    entry = (
        _require_registry_entry(registry, source_id)
        if require_registry
        else _registry_entry(registry, source_id)
    )

    # step 2 - never fetch twice
    if not force and cfg.never_refetch and dest.exists():
        recorded = (entry or {}).get("sha256")
        if recorded and sha256_file(dest) == str(recorded).lower():
            rec = FetchRecord(
                source_id=source_id,
                url=url,
                tool=tool,
                started_at=started,
                finished_at=_utc_now_iso(),
                http_status=None,
                bytes=dest.stat().st_size,
                sha256=str(recorded).lower(),
                local_path=_project_relative(dest, project_dir),
                error=None,
                skipped_cached=True,
            )
            log_fetch(project_data_dir, rec)
            return rec

    # step 3 - pacing and identification
    limiter = limiter if limiter is not None else get_rate_limiter(split.hostname)
    req_headers: dict[str, str] = {"User-Agent": cfg.user_agent(f"source={source_id}")}
    if headers:
        req_headers.update(headers)

    # step 4 - stream to <dest>.part, resuming if asked
    part = dest.with_suffix(dest.suffix + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    start_byte = 0
    if resume and part.exists():
        start_byte = part.stat().st_size
        if start_byte > 0:
            req_headers.setdefault("Range", f"bytes={start_byte}-")

    status: int | None = None
    error: str | None = None
    digest: str | None = None
    size: int | None = None
    local: str | None = None
    timeout_s = cfg.default_timeout_seconds if timeout is None else float(timeout)

    limiter.wait()
    try:
        with (
            httpx.Client(follow_redirects=True, timeout=timeout_s, transport=transport) as client,
            client.stream("GET", url, headers=req_headers) as resp,
        ):
            status = resp.status_code
            if status >= 400:
                error = f"HTTP {status}"
            else:
                append, complete_length, error = _placement_plan(resp, start_byte)
                if error is None:
                    error, received = _stream_to_part(
                        resp, part, append=append, already=start_byte, max_bytes=max_bytes
                    )
                    if error is None:
                        error = _size_error(
                            resp,
                            part,
                            received=received,
                            complete_length=complete_length,
                            allow_empty=allow_empty,
                        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    if error is not None and part.exists() and part.stat().st_size == 0:
        part.unlink(missing_ok=True)  # a zero-byte part file is not worth resuming from

    if error is None and status in (200, 206):
        try:
            os.replace(part, dest)
            digest = sha256_file(dest)
            size = dest.stat().st_size
            local = _project_relative(dest, project_dir)
            if expected_sha256 is not None and digest != expected_sha256.lower():
                bad = dest.with_suffix(dest.suffix + ".bad")
                os.replace(dest, bad)
                local = _project_relative(bad, project_dir)
                error = f"sha256 mismatch: expected {expected_sha256}, got {digest}"
        except OSError as exc:
            error = f"{type(exc).__name__}: {exc}"

    rec = FetchRecord(
        source_id=source_id,
        url=url,
        tool=tool,
        started_at=started,
        finished_at=_utc_now_iso(),
        http_status=status,
        bytes=size,
        sha256=digest,
        local_path=local,
        error=error,
        skipped_cached=False,
    )

    # step 5 - always log, then record the outcome in the registry
    log_fetch(project_data_dir, rec)
    if registry.exists():
        existing = _registry_entry(registry, source_id)
        intact = rec.error is not None and _recorded_file_intact(existing, project_dir)
        try:
            update_source(registry, source_id, **_registry_fields(rec, existing, intact=intact))
        except (OSError, ValueError) as exc:
            warnings.warn(
                f"{registry}: could not record the fetch of {source_id!r} ({exc})",
                RuntimeWarning,
                stacklevel=2,
            )
    return rec  # step 6


# --------------------------------------------------------------------------------------
# command line
# --------------------------------------------------------------------------------------


def _project_name(path: Path) -> str:
    """``projects/<name>/data/SOURCES.yaml`` -> ``<name>``; otherwise the parent directory."""
    parent = path.resolve().parent
    return parent.parent.name if parent.name == "data" else parent.name


def _print_table(header: Sequence[str], rows: Sequence[Sequence[str]], right: set[int]) -> None:
    widths = [max([len(h)] + [len(r[i]) for r in rows]) for i, h in enumerate(header)]

    def fmt(cells: Sequence[str]) -> str:
        return "  ".join(
            cells[i].rjust(w) if i in right else cells[i].ljust(w) for i, w in enumerate(widths)
        ).rstrip()

    print(fmt(header))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt(row))


def _cmd_validate(paths: Sequence[str]) -> int:
    failed = False
    for raw in paths:
        p = Path(raw)
        try:
            errors = validate_sources(p)
            n = len(_read_raw(p))
        except (OSError, ValueError, yaml.YAMLError) as exc:
            print(f"{p}: {exc}")
            failed = True
            continue
        if errors:
            failed = True
            for err in errors:
                print(f"{p}: {err}")
        else:
            print(f"{p}: OK ({n} sources)")
    return 1 if failed else 0


def _cmd_status(paths: Sequence[str]) -> int:
    header = ("project", "id", "access", "status", "bytes", "blocked_reason")
    rows: list[tuple[str, ...]] = []
    failed = False
    for raw in paths:
        p = Path(raw)
        try:
            sources = load_sources(p)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            print(f"{p}: {exc}")
            failed = True
            continue
        project = _project_name(p)
        rows.extend(
            (
                project,
                s.id,
                s.access,
                s.status,
                "" if s.bytes is None else str(s.bytes),
                s.blocked_reason or "",
            )
            for s in sources
        )
    _print_table(header, rows, right={4})
    return 1 if failed else 0


def _cmd_sha256(paths: Sequence[str]) -> int:
    failed = False
    for raw in paths:
        p = Path(raw)
        try:
            print(f"{sha256_file(p)}  {p}")
        except OSError as exc:
            print(f"{p}: {exc}")
            failed = True
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Command line for the registry: ``validate``, ``status`` and ``sha256``.

    Parameters
    ----------
    argv : sequence of str, optional
        Arguments excluding the programme name; defaults to ``sys.argv[1:]``.

    Returns
    -------
    int
        0 if everything checked out, 1 if any file was invalid or unreadable.
    """
    parser = argparse.ArgumentParser(
        prog="forensics-manifest",
        description="Validate and summarise SOURCES.yaml registries; checksum files.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="check registries; exit 1 on any error")
    p_validate.add_argument("paths", nargs="+", help="SOURCES.yaml files")

    p_status = sub.add_parser("status", help="table of registry entries")
    p_status.add_argument("paths", nargs="+", help="SOURCES.yaml files")

    p_sha = sub.add_parser("sha256", help="print the SHA-256 of each file")
    p_sha.add_argument("paths", nargs="+", help="files to hash")

    args = parser.parse_args(argv)
    if args.command == "validate":
        return _cmd_validate(args.paths)
    if args.command == "status":
        return _cmd_status(args.paths)
    return _cmd_sha256(args.paths)


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
