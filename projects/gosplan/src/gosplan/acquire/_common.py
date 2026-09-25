"""Shared plumbing for the gosplan acquirers: one polite fetch, and pure parsing helpers.

Everything that touches the network goes through :func:`fetch_file`, a thin wrapper over
:func:`forensics_core.provenance.manifest.fetch` that turns a
:class:`~forensics_core.provenance.manifest.FetchRecord` into the programme's
:class:`~gosplan.acquire.registry.AcquireResult` vocabulary. The parsing helpers below are
deliberately pure and network-free so that they can be unit-tested against small synthetic
inputs; the acquirers are then thin enough to read at a glance.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from forensics_core.provenance.manifest import fetch

from gosplan.acquire.registry import AcquireResult

#: Upper bound applied to every download that has no separately justified ceiling. The
#: largest artefact any gosplan acquirer is expected to pull is a scanned yearbook PDF or a
#: yearbook hOCR file (tens of megabytes); anything past this is a redirect to something
#: unexpected, and aborting is cheaper than filling the disk.
DEFAULT_MAX_BYTES = 192 * 1024 * 1024

#: Characters left unescaped by :func:`encode_path`. ``%`` is included so that a link
#: scraped in already-encoded form is not encoded a second time.
_PATH_SAFE = "/%:@!$&()*+,;=~-._"

_HREF_RE = re.compile(
    r"""<a\b[^>]*?\bhref\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.IGNORECASE | re.DOTALL
)


@dataclass(frozen=True)
class FileOutcome:
    """Result of one file within a multi-file acquirer."""

    url: str
    ok: bool
    detail: str
    path: Path | None = None
    cached: bool = False


def fetch_file(
    source_id: str,
    data_dir: Path,
    url: str,
    dest_rel: str,
    *,
    force: bool = False,
    expected_sha256: str | None = None,
    resume: bool = False,
    max_bytes: int | None = DEFAULT_MAX_BYTES,
    headers: dict[str, str] | None = None,
) -> FileOutcome:
    """Fetch one URL into ``data/raw/<dest_rel>`` and classify the outcome.

    Parameters
    ----------
    source_id : str
        ``SOURCES.yaml`` id the download belongs to; the fetch is refused if it has no entry.
    data_dir : Path
        The project's ``data/`` directory.
    url : str
        Absolute URL, taken verbatim from the registry entry or its ``download_plan``.
    dest_rel : str
        Destination path relative to ``data/raw``.
    force : bool, default False
        Re-download even when the cached copy matches the registry digest.
    expected_sha256 : str, optional
        Pass only for artefacts that are genuinely immutable (Wayback snapshots, archive.org
        item files, a versioned release spreadsheet). Bulk statistical files that the
        publisher revises on a schedule -- FAOSTAT, USDA PSD -- must **not** be pinned, or a
        legitimate republication is reported as corruption.
    resume : bool, default False
        Send a ranged request when a ``.part`` file is present. Needed for hosts that
        truncate long responses.
    max_bytes : int, optional
        Abort the transfer past this size.
    headers : dict, optional
        Extra request headers.

    Returns
    -------
    FileOutcome
        ``ok`` False for HTTP errors, transport errors, size aborts and digest mismatches;
        no exception is raised for any of them.
    """
    dest = data_dir / "raw" / dest_rel
    rec = fetch(
        url,
        dest,
        project_data_dir=data_dir,
        source_id=source_id,
        force=force,
        expected_sha256=expected_sha256,
        resume=resume,
        max_bytes=max_bytes,
        headers=headers,
    )
    if rec.skipped_cached:
        return FileOutcome(url, True, f"already held at raw/{dest_rel}", dest, True)
    if rec.error or rec.http_status not in (200, 206):
        return FileOutcome(
            url, False, f"HTTP {rec.http_status}: {rec.error or 'unexpected status'}"
        )
    size = rec.bytes or 0
    return FileOutcome(url, True, f"{size:,} bytes -> raw/{dest_rel}", dest)


def single(source: Any, data_dir: Path, url: str, dest_rel: str, **kw: Any) -> AcquireResult:
    """Acquire exactly one file and report it as an :class:`AcquireResult`."""
    out = fetch_file(source.id, data_dir, url, dest_rel, **kw)
    paths = (out.path,) if out.path is not None else ()
    return AcquireResult(source.id, out.ok, out.detail, paths, out.cached)


def many(source: Any, data_dir: Path, items: Sequence[tuple[str, str]], **kw: Any) -> AcquireResult:
    """Acquire several files for one registry id and aggregate the outcome.

    The run is not aborted by a failure part-way through: every item is attempted, and the
    summary names the ones that failed. ``ok`` is True only when every item succeeded, so a
    partial acquisition is a loud failure with the successful files still on disk.
    """
    outcomes = [fetch_file(source.id, data_dir, url, rel, **kw) for url, rel in items]
    ok = [o for o in outcomes if o.ok]
    bad = [o for o in outcomes if not o.ok]
    cached = [o for o in ok if o.cached]
    paths = tuple(o.path for o in ok if o.path is not None)
    detail = f"{len(ok)}/{len(outcomes)} files ({len(cached)} already held)"
    if bad:
        shown = "; ".join(f"{o.url.rsplit('/', 1)[-1]}: {o.detail}" for o in bad[:3])
        more = f" (+{len(bad) - 3} more)" if len(bad) > 3 else ""
        detail = f"{detail}; failed: {shown}{more}"
    return AcquireResult(
        source.id,
        not bad and bool(outcomes),
        detail,
        paths,
        bool(outcomes) and len(cached) == len(outcomes),
    )


# --------------------------------------------------------------------------------------
# pure helpers: no network, unit-tested against synthetic inputs
# --------------------------------------------------------------------------------------


def hrefs(
    html: str, base: str | None = None, pattern: str | re.Pattern[str] | None = None
) -> list[str]:
    """Extract ``href`` values from HTML, case-insensitively, preserving document order.

    A regular expression rather than a parser on purpose: two of the pages this package
    reads (``publ.lib.ru``, ``opisi.rgae.ru``) are windows-1251 documents written with
    uppercase ``<A HREF=...>`` tags and unquoted attributes, which naive lowercase matching
    misses entirely -- the registry's ``publ_lib_ru_narkhoz`` download plan flags exactly
    that trap.

    Parameters
    ----------
    html : str
        Already-decoded document text. Decoding is the caller's job because the encoding
        differs per host (utf-8, windows-1251).
    base : str, optional
        When given, relative links are resolved against it.
    pattern : str or re.Pattern, optional
        Keep only hrefs matching this pattern (``re.search``, case-insensitive when a string
        is given).

    Returns
    -------
    list of str
        Matching hrefs, de-duplicated, in first-appearance order.
    """
    rx = re.compile(pattern, re.IGNORECASE) if isinstance(pattern, str) else pattern
    out: list[str] = []
    seen: set[str] = set()
    for m in _HREF_RE.finditer(html):
        href = next(g for g in m.groups() if g is not None).strip()
        if not href or href.startswith("#"):
            continue
        if rx is not None and not rx.search(href):
            continue
        full = urljoin(base, href) if base else href
        if full not in seen:
            seen.add(full)
            out.append(full)
    return out


def encode_path(url: str) -> str:
    """Percent-encode the path of ``url``, leaving an already-encoded path unchanged.

    Needed for the volunteer-scanned mirrors whose filenames contain quotes, brackets,
    parentheses and Cyrillic.
    """
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=quote(parts.path, safe=_PATH_SAFE)))


def ia_files(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """The ``files`` array of an archive.org ``/metadata/<id>`` response, or an empty list."""
    files = metadata.get("files")
    return [f for f in files if isinstance(f, dict)] if isinstance(files, list) else []


def ia_select(
    metadata: dict[str, Any],
    *,
    formats: Iterable[str] = (),
    suffixes: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Select archive.org item files by their declared ``format``, or failing that by suffix.

    Selecting on ``format`` is what the registry's ``ia_narkhoz_collection`` download plan
    prescribes: archive.org derives several artefacts per scan and the filenames are not
    reliably derivable from the identifier, but the ``format`` field ("Text PDF", "hOCR",
    "DjVuTXT", "Metadata") is.

    Parameters
    ----------
    metadata : dict
        Parsed ``https://archive.org/metadata/<identifier>`` response.
    formats : iterable of str
        Accepted ``format`` values, compared case-insensitively.
    suffixes : iterable of str
        Fallback: accepted filename suffixes, compared case-insensitively. Applied only to
        files whose format did not match, so an item that declares its formats properly is
        never matched twice.

    Returns
    -------
    list of dict
        The matching file entries, in the order archive.org listed them.
    """
    want_fmt = {f.casefold() for f in formats}
    want_sfx = tuple(s.casefold() for s in suffixes)
    out: list[dict[str, Any]] = []
    for f in ia_files(metadata):
        name = str(f.get("name", ""))
        fmt = str(f.get("format", "")).casefold()
        if want_fmt and fmt in want_fmt:
            out.append(f)
        elif want_sfx and name.casefold().endswith(want_sfx):
            out.append(f)
    return out


def ia_download_url(identifier: str, name: str) -> str:
    """The canonical archive.org download URL for one file of one item."""
    return encode_path(f"https://archive.org/download/{identifier}/{name}")


def ia_search_docs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """The ``response.docs`` list of an archive.org ``advancedsearch.php`` JSON response."""
    resp = payload.get("response")
    if not isinstance(resp, dict):
        return []
    docs = resp.get("docs")
    return [d for d in docs if isinstance(d, dict)] if isinstance(docs, list) else []


def ia_num_found(payload: dict[str, Any]) -> int | None:
    """``response.numFound`` from an archive.org search response, or None if absent."""
    resp = payload.get("response")
    if not isinstance(resp, dict):
        return None
    n = resp.get("numFound")
    return int(n) if isinstance(n, int) else None


def read_json(path: Path) -> dict[str, Any]:
    """Parse a JSON file that an acquirer has just downloaded; ``{}`` if it is not an object."""
    import json

    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload if isinstance(payload, dict) else {}


def read_text(path: Path, encoding: str = "utf-8") -> str:
    """Read a downloaded HTML page, replacing undecodable bytes rather than raising."""
    return path.read_text(encoding=encoding, errors="replace")
