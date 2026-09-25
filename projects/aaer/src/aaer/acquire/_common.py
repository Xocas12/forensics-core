"""Shared plumbing for the aaer acquirers: one polite, logged, idempotent download.

Named after the ``_common.py`` that ``elections``, ``china`` and ``gosplan`` each carry, and
exposing the same single-file entry point, :func:`fetch_file`, so that a reader moving between
the four projects finds the same module and the same verb. The signatures are not identical
across the programme -- ``elections`` and ``china`` take ``url`` and ``dest_rel`` as keywords,
``gosplan`` and this module take them positionally, and ``gosplan`` passes a source id rather
than a ``Source`` -- so only the shape, not the call, is shared. :func:`challenge_marker` is
the same anti-bot guard with the same marker list as ``elections``. :func:`fetch_many` is the
one addition this project needs, because two of its registry ids cover many files each.

Everything here is a thin wrapper over :func:`forensics_core.provenance.manifest.fetch`, which
is the only thing in the programme allowed to touch the network. The wrappers add nothing to
the network policy; they only turn a :class:`~forensics_core.provenance.manifest.FetchRecord`
into an :class:`~aaer.acquire.registry.AcquireResult`, guard against challenge pages, and, for
multi-file sources, decide what still has to be downloaded.

Idempotence, and where its limits are
-------------------------------------
``fetch`` never downloads a file twice when the registry records a ``sha256`` for the source id
and the file on disk still matches it. That is a *per-source-id* check, so it works exactly for
one-file sources (:func:`fetch_file`).

A source id that covers many files -- the 34 pages of the AAER listing, the ~69 quarterly zips
of the Financial Statement Data Sets -- cannot use it, because ``SOURCES.yaml`` has one
``sha256`` field per entry and it will end up holding whichever file was written last.
:func:`fetch_many` therefore does its own check: a member file that already exists and is
non-empty is not requested again unless ``force`` is passed. That is weaker than a checksum
(it will not notice that a listing page has been re-published with new rows), and the way to
refresh such a source is ``--force``. The complete, per-file record is in
``data/fetch_log.jsonl``, which is appended to on every attempt including the skipped ones.

Challenge pages served with HTTP 200
------------------------------------
``fetch`` marks a registry entry ``verified`` and writes the body's sha256 into ``SOURCES.yaml``
on any HTTP 200. This project has already met bot fronts on three of the hosts in its registry,
each recorded there with the body that came back:

* ``www.sec.gov`` -- entry ``sec_fsds_quarterly_zips`` records a HEAD with a non-descriptive
  ``User-Agent`` answered with a 921-byte HTTP 403 ``AkamaiGHost`` page;
* ``tandfonline.com`` (``beneish_1999_faj_publisher``) and ``onlinelibrary.wiley.com``
  (``jar_erratum_2022``) -- 5,655 and 5,644 bytes of Cloudflare "Just a moment..." HTML,
  returned with HTTP 403.

The two publisher entries are ``blocked`` and have no acquirer, and every one of the three
bodies above arrived with an HTTP 403, which ``fetch`` already reports as a failure. **No
source in this registry has
been seen to return an interstitial with HTTP 200**, and neither has any in the ``elections``
registry the marker list came from, whose own recorded case (``klimek_pnas_2012_si``, a PMC
reCAPTCHA page) was also a 403. The guard has therefore never fired here and is precautionary.

What it is precautionary about is the one failure mode ``fetch`` cannot catch on its own: a 200
makes it write that body's digest into ``SOURCES.yaml`` and mark the entry ``verified``, so a
challenge page arriving with a 200 would be recorded as a good acquisition and would look
exactly like one. Every download whose destination is an HTML file is therefore sniffed for the
markers in :data:`CHALLENGE_MARKERS` and reported as a failure when one is found. The body is
left on disk and named in the failure detail so that a human can see what actually came back.
This is the same guard, with the same marker list, as ``elections/acquire/_common.py``.

The guard is a second line of defence, not a repair: ``fetch`` has already rewritten the
registry entry by the time the body can be sniffed, so a fired guard means the ``SOURCES.yaml``
entry for that id has to be re-checked by hand as well as the body inspected.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from forensics_core.provenance.manifest import FetchRecord, fetch

from aaer.acquire.registry import AcquireResult

#: Cap on any single download. The largest file the registry documents is the Bao et al.
#: analysis CSV at 47,782,071 bytes; recent FSDS quarterly zips are ~120 MB. 512 MB is well
#: above both and still low enough that a redirect to something enormous aborts rather than
#: filling the disk.
MAX_BYTES: int = 512 * 1024 * 1024

#: Substrings that identify an anti-bot interstitial served with HTTP 200. Copied verbatim from
#: ``elections/acquire/_common.py`` so that the two projects detect the same thing; that list
#: was taken from a reCAPTCHA interstitial actually observed by the elections registry. Of the
#: four, only "Just a moment" has been seen by this project (Cloudflare, on tandfonline.com and
#: onlinelibrary.wiley.com, and there with HTTP 403 rather than 200).
CHALLENGE_MARKERS: tuple[str, ...] = (
    # not observed for this project; carried over from elections (klimek_pnas_2012_si)
    "Checking your browser",
    "reCAPTCHA",
    # observed here only in HTTP 403 bodies, never in a 200: beneish_1999_faj_publisher
    # (tandfonline.com) and jar_erratum_2022 (onlinelibrary.wiley.com)
    "Just a moment",
    # not observed anywhere in the programme; generic interstitial text, purely defensive
    "Enable JavaScript and cookies to continue",
)

#: How much of a downloaded HTML file is inspected for a challenge marker.
CHALLENGE_SNIFF_BYTES = 65_536

#: Destination suffixes sniffed for a challenge marker by default. Only HTML is sniffed
#: automatically: a PDF or a zip returned as an interstitial fails its digest check or its
#: parse instead, and scanning a 120 MB zip for English text would be pointless.
HTML_SUFFIXES: tuple[str, ...] = (".html", ".htm")


def _describe(rec: FetchRecord) -> str:
    if rec.error:
        return f"HTTP {rec.http_status}: {rec.error}"
    return f"HTTP {rec.http_status}: unexpected status"


def challenge_marker(path: Path, *, sniff_bytes: int = CHALLENGE_SNIFF_BYTES) -> str | None:
    """Return the anti-bot marker found at the head of ``path``, or ``None``.

    Parameters
    ----------
    path : pathlib.Path
        A downloaded file, expected to be HTML.
    sniff_bytes : int, optional
        How many bytes of the head to inspect.

    Returns
    -------
    str or None
        The first marker from :data:`CHALLENGE_MARKERS` present in the head of the file, or
        ``None`` when the file does not look like an interstitial. Read and decoding errors
        are ignored: this is a heuristic on a possibly binary body, not a parser.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(sniff_bytes).decode("utf-8", errors="replace")
    except OSError:
        return None
    return next((m for m in CHALLENGE_MARKERS if m in head), None)


def _wants_challenge_check(dest_rel: str, explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    return Path(dest_rel).suffix.lower() in HTML_SUFFIXES


def fetch_file(
    source,
    data_dir: Path,
    url: str,
    dest_rel: str,
    *,
    expected_sha256: str | None = None,
    force: bool = False,
    resume: bool = False,
    max_bytes: int | None = MAX_BYTES,
    check_challenge: bool | None = None,
) -> AcquireResult:
    """Acquire a single file into ``data/raw/<dest_rel>``.

    Parameters
    ----------
    source : forensics_core.provenance.manifest.Source
        The registry entry being acquired; only its ``id`` is used here.
    data_dir : Path
        The project's ``data/`` directory.
    url : str
        Absolute URL. Usually ``source.url``, but not always: a registry entry may describe a
        repository or a landing page while the file worth keeping sits elsewhere.
    dest_rel : str
        Destination path relative to ``data/raw``.
    expected_sha256 : str, optional
        Pass this only for content that is expected to be byte-stable (PDFs, zips, pinned
        CSVs). Do not pass it for HTML pages: the registry records digests for several pages
        whose bytes were already observed to drift between two probes days apart.
    force : bool, default False
        Re-download even when the cached copy matches the registry digest.
    resume : bool, default False
        Allow a ranged resume from a partial download. Worth setting for the large zips.
    max_bytes : int, optional
        Abort the download if the body would exceed this size.
    check_challenge : bool, optional
        Sniff the downloaded body for :data:`CHALLENGE_MARKERS`. ``None`` (the default) means
        sniff when ``dest_rel`` names an HTML file; ``True`` and ``False`` force the choice.

    Returns
    -------
    AcquireResult
        ``ok`` is false, with the reason in ``detail``, for any non-200 status, transport
        error, digest mismatch or challenge page. Nothing raises: the runner needs the rest of
        the registry to be attempted.
    """
    dest = data_dir / "raw" / dest_rel
    rec = fetch(
        url,
        dest,
        project_data_dir=data_dir,
        source_id=source.id,
        expected_sha256=expected_sha256,
        force=force,
        resume=resume,
        max_bytes=max_bytes,
    )
    if rec.skipped_cached:
        return AcquireResult(source.id, True, f"already held at {dest_rel}", (dest,), True)
    if rec.error or rec.http_status != 200:
        return AcquireResult(source.id, False, _describe(rec))
    if _wants_challenge_check(dest_rel, check_challenge):
        marker = challenge_marker(dest)
        if marker is not None:
            return AcquireResult(
                source.id,
                False,
                f"anti-bot interstitial, not the document (matched {marker!r}); body kept at "
                f"raw/{dest_rel} for inspection, and the SOURCES.yaml entry that fetch just "
                f"wrote must be re-checked",
            )
    return AcquireResult(source.id, True, f"{rec.bytes:,} bytes -> {dest_rel}", (dest,))


def fetch_many(
    source,
    data_dir: Path,
    items: Sequence[tuple[str, str]],
    *,
    expected: Mapping[str, str] | None = None,
    force: bool = False,
    resume: bool = False,
    unit: str = "files",
    max_failures_shown: int = 5,
    check_challenge: bool | None = None,
) -> AcquireResult:
    """Acquire many files under one registry id, reporting every failure and continuing.

    See the module docstring for why idempotence here is presence-on-disk rather than a
    checksum comparison, and note that ``fetch`` rewrites the single ``sha256`` / ``bytes`` /
    ``local_path`` triple of the registry entry once per downloaded file, so the entry ends up
    describing the last member written. ``data/fetch_log.jsonl`` holds the full record.

    Parameters
    ----------
    source : forensics_core.provenance.manifest.Source
        The registry entry being acquired.
    data_dir : Path
        The project's ``data/`` directory.
    items : sequence of (url, dest_rel)
        What to fetch, in order. ``dest_rel`` is relative to ``data/raw``.
    expected : mapping, optional
        ``dest_rel -> sha256`` for the members whose digest the registry actually records.
        Members absent from the mapping are fetched without a digest check.
    force : bool, default False
        Re-download every member, including ones already on disk.
    resume : bool, default False
        Allow ranged resume of partial downloads.
    unit : str, default "files"
        Word used in the summary line, e.g. ``"pages"`` or ``"quarterly zips"``.
    max_failures_shown : int, default 5
        How many failing members to name in the summary before truncating.
    check_challenge : bool, optional
        As in :func:`fetch_file`, applied per member. ``None`` sniffs the HTML members only.

    Returns
    -------
    AcquireResult
        ``ok`` is False if any member failed; the successful ones are still on disk and the
        run continues.
    """
    expected = dict(expected or {})
    paths: list[Path] = []
    new = held = 0
    failures: list[str] = []

    for url, dest_rel in items:
        dest = data_dir / "raw" / dest_rel
        if not force and dest.exists() and dest.stat().st_size > 0:
            held += 1
            paths.append(dest)
            continue
        rec = fetch(
            url,
            dest,
            project_data_dir=data_dir,
            source_id=source.id,
            expected_sha256=expected.get(dest_rel),
            force=force,
            resume=resume,
            max_bytes=MAX_BYTES,
        )
        if rec.skipped_cached:
            held += 1
            paths.append(dest)
        elif rec.error or rec.http_status != 200:
            failures.append(f"{dest_rel} ({_describe(rec)})")
        else:
            marker = (
                challenge_marker(dest)
                if _wants_challenge_check(dest_rel, check_challenge)
                else None
            )
            if marker is not None:
                failures.append(f"{dest_rel} (anti-bot interstitial, matched {marker!r})")
            else:
                new += 1
                paths.append(dest)

    shown = failures[:max_failures_shown]
    more = len(failures) - len(shown)
    detail = f"{new} new, {held} already held, {len(failures)} failed of {len(items)} {unit}"
    if shown:
        detail += "; " + "; ".join(shown) + (f"; +{more} more" if more else "")
    return AcquireResult(source.id, not failures, detail, tuple(paths))
