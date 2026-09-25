"""Thin helpers over :func:`forensics_core.provenance.manifest.fetch` for this project.

Two things every acquirer here needs and the shared library deliberately does not decide:

* **Multi-file sources.** Several registry entries stand for a whole family of files: one
  yearbook edition is a table of contents plus a handful of table images, one central-bank
  reporting year is thirty-odd PDFs. ``fetch`` keys its never-fetch-twice cache on the
  single ``sha256`` the registry holds for a source id, so for a family it can only protect
  one member. :func:`fetch_files` adds a per-file existence guard, so a re-run of a
  half-finished family costs nothing.

**Digests recorded for a family: read this before trusting ``Source.sha256``.**
``fetch`` does not only read the registry, it writes to it. On every success it rewrites the
entry's ``sha256``, ``bytes``, ``local_path`` and ``status`` with the fetched file's. A
registry entry has one such slot and :func:`fetch_files` issues one ``fetch`` per member under
one source id, so after a completed family crawl the entry's ``sha256`` belongs to whichever
member was fetched last, and the digest the registry was written with is gone. That is a
property of the shared library, which this project vendors as a submodule and does not edit;
it has been raised upstream as needing a flag that logs a family member to ``fetch_log.jsonl``
without touching the entry's integrity fields.

Two consequences, both of which the callers here are written around:

1. **The recorded digests do not survive run one.** The per-file record does survive, in
   ``data/fetch_log.jsonl``, which logs every attempt with its own url, bytes and sha256.
   That log, not ``SOURCES.yaml``, is the provenance record for anything fetched as a family.
2. **Never pass ``source.sha256`` as ``expected_sha256`` for a member of a family.** On the
   second run it would be a digest belonging to a different file, and the member would be
   renamed ``.bad`` and reported as a mismatch. Digests worth checking are held as module
   constants next to the acquirer instead (``yearbook.ANCHOR_SHA256``,
   ``yearbook.TOC_2024_EN_SHA256``, ``yearbook.TOC_2023_SHA256``);
   ``tests/test_acquire_registry.py`` checks them against the registry while its entries are
   still un-fetched, and against the registry's evidence prose, which a success never
   rewrites. ``source.sha256`` is safe only where the source
   id maps to exactly one file, as in ``csy_2015_grp_vintage`` and ``pbc_credit_statistics``.
* **Referer headers.** The scaffolding probes that verified the yearbook tables and the
  National Bureau of Statistics catalogue API sent a ``Referer``; that is recorded in each
  registry entry's ``download_plan`` and is reproduced by the callers here.

What is deliberately **not** reproduced: the browser ``User-Agent`` that some of those
probes used. Every request from this package carries the contact string configured in
``config/forensics.toml``, per the programme's fetch policy. If a host rejects that
User-Agent the run records the failure; it does not disguise itself to get around it. Where
that matters, the acquirer's docstring says so.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from forensics_core.provenance.manifest import Source, fetch

from china.acquire.registry import AcquireResult

__all__ = ["fetch_file", "fetch_files"]


def fetch_file(
    source: Source,
    data_dir: Path,
    *,
    url: str,
    dest_rel: str,
    headers: dict[str, str] | None = None,
    expected_sha256: str | None = None,
    force: bool = False,
    max_bytes: int | None = None,
) -> AcquireResult:
    """Acquire one file for ``source`` into ``data_dir / "raw" / dest_rel``.

    Parameters
    ----------
    source : forensics_core.provenance.manifest.Source
        The registry entry being acquired.
    data_dir : Path
        The project's ``data/`` directory.
    url : str
        Absolute URL, taken from the registry entry or built from a URL template that the
        entry's ``download_plan`` states verbatim. Never invented here.
    dest_rel : str
        Destination path relative to ``data/raw``.
    headers : dict of str to str, optional
        Extra request headers, merged over the defaults by ``fetch``.
    expected_sha256 : str, optional
        Digest to verify against. Pass it only for single-file sources; for a family of
        files the registry's digest belongs to one member and would fail the others.
    force : bool, default False
        Re-download even if a cached copy matches the registry digest.
    max_bytes : int, optional
        Abort the transfer if the body would exceed this size.

    Returns
    -------
    AcquireResult
        ``ok`` is False for any non-200 response or transport error. Nothing raises here:
        the run reports and continues.
    """
    dest = data_dir / "raw" / dest_rel
    rec = fetch(
        url,
        dest,
        project_data_dir=data_dir,
        source_id=source.id,
        headers=headers,
        expected_sha256=expected_sha256,
        force=force,
        max_bytes=max_bytes,
    )
    if rec.skipped_cached:
        return AcquireResult(source.id, True, f"already held at {dest_rel}", (dest,), True)
    if rec.error or rec.http_status != 200:
        return AcquireResult(
            source.id,
            False,
            f"HTTP {rec.http_status}: {rec.error or 'unexpected status'} ({url})",
        )
    size = rec.bytes if rec.bytes is not None else 0
    return AcquireResult(source.id, True, f"{size:,} bytes -> {dest_rel}", (dest,))


def fetch_files(
    source: Source,
    data_dir: Path,
    items: Iterable[tuple[str, ...]],
    *,
    headers: dict[str, str] | None = None,
    force: bool = False,
    max_bytes: int | None = None,
    label: str = "files",
) -> AcquireResult:
    """Acquire a family of files under one registry id, reporting one aggregate result.

    A member that is already on disk and non-empty is skipped without a request, because the
    registry can only hold one digest per source id and would otherwise force the whole
    family to be re-downloaded every run.

    Parameters
    ----------
    source : forensics_core.provenance.manifest.Source
        The registry entry the whole family belongs to.
    data_dir : Path
        The project's ``data/`` directory.
    items : iterable of tuple
        ``(url, dest_rel)``, ``(url, dest_rel, expected_sha256)`` or
        ``(url, dest_rel, expected_sha256, headers)``. ``dest_rel`` is relative to
        ``data/raw``. A digest is given only for members the registry actually recorded one
        for; the rest are fetched unverified. Per-item headers are merged over ``headers``
        and exist because the yearbook wants a ``Referer`` that names the edition.
    headers : dict of str to str, optional
        Extra request headers applied to every member.
    force : bool, default False
        Ignore the on-disk guard and re-download every member.
    max_bytes : int, optional
        Per-file size ceiling.
    label : str, default "files"
        Noun used in the result message, e.g. ``"table images"``.

    Returns
    -------
    AcquireResult
        ``ok`` is True only if every member either downloaded or was already held. The
        detail line always states how many were fetched, how many were already present and
        how many failed, naming the first few failures.

    Raises
    ------
    ValueError
        If an item is not a 2-, 3- or 4-tuple. A malformed work list is a coding error and
        must not be quietly skipped.
    """
    fetched: list[Path] = []
    cached: list[Path] = []
    failed: list[str] = []

    for item in items:
        digest: str | None = None
        item_headers: dict[str, str] | None = None
        if len(item) == 2:
            url, dest_rel = item
        elif len(item) == 3:
            url, dest_rel, digest = item  # type: ignore[assignment]
        elif len(item) == 4:
            url, dest_rel, digest, item_headers = item  # type: ignore[assignment]
        else:
            raise ValueError(f"expected a 2-, 3- or 4-tuple work item, got {item!r}")
        merged = {**(headers or {}), **(item_headers or {})}
        dest = data_dir / "raw" / dest_rel
        if dest.exists() and dest.stat().st_size > 0 and not force:
            cached.append(dest)
            continue
        rec = fetch(
            url,
            dest,
            project_data_dir=data_dir,
            source_id=source.id,
            headers=merged or None,
            expected_sha256=digest,
            force=force,
            max_bytes=max_bytes,
        )
        if rec.skipped_cached:
            cached.append(dest)
        elif rec.error or rec.http_status != 200:
            failed.append(f"{dest_rel} (HTTP {rec.http_status}: {rec.error or 'unexpected'})")
        else:
            fetched.append(dest)

    detail = f"{len(fetched)} {label} fetched, {len(cached)} already held, {len(failed)} failed"
    if failed:
        detail += "; " + "; ".join(failed[:3])
        if len(failed) > 3:
            detail += f"; and {len(failed) - 3} more"
    return AcquireResult(
        source.id,
        not failed,
        detail,
        (*fetched, *cached),
        skipped_cached=bool(cached) and not fetched and not failed,
    )
