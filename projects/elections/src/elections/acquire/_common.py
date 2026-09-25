"""Shared plumbing for the elections acquirers: one polite, logged, idempotent download.

Every acquirer in this package funnels through :func:`fetch_file` so that all of them behave
the same way and none of them can quietly diverge from the programme's rules:

* the download goes through :func:`forensics_core.provenance.manifest.fetch`, which refuses to
  touch the network until ``config/forensics.toml`` carries a real contact string, paces
  requests per host, writes one line to ``data/fetch_log.jsonl`` for every attempt, and
  updates the ``SOURCES.yaml`` entry with what actually happened;
* an HTTP error is reported and returned, never raised, so one dead host cannot end the run;
* a file already on disk whose digest matches the registry is not requested again.

Two guards live here rather than in the individual acquirers because more than one source
needs them:

``held_with_digest``
    Local, pre-network idempotency for sources acquired in more than one request (the Figshare
    supplement resolves a metadata document before it can name the file to download). Without
    it, the second run of such an acquirer would re-download the payload because the registry
    digest recorded for the source belongs to only one of the two artefacts.

``challenge_marker``
    Some hosts answer a scripted client with HTTP 200 and an anti-bot interstitial. Recorded
    for this project against PubMed Central (``klimek_pnas_2012_si`` in ``SOURCES.yaml``:
    "PMC serves a reCAPTCHA interstitial"). A 20 KB challenge page saved as ``verified`` would
    be a false integrity claim, so acquirers that fetch HTML from such hosts check for it and
    report failure instead.
"""

from __future__ import annotations

from pathlib import Path

from forensics_core.provenance.manifest import RateLimiter, Source, fetch, sha256_file

from elections.acquire.registry import AcquireResult

#: Substrings that identify an anti-bot interstitial served with HTTP 200.
#:
#: Only the first two were observed for this project: ``data/SOURCES.yaml`` records for
#: ``klimek_pnas_2012_si`` that PMC returned a page titled "Checking your browser -
#: reCAPTCHA" in place of the article. The last two are defensive additions that no host in
#: this registry has been seen to serve; they are generic interstitial text, kept so that a
#: future block is reported as a block rather than saved as content, and they are not
#: evidence about any source here.
CHALLENGE_MARKERS: tuple[str, ...] = (
    # observed, klimek_pnas_2012_si
    "Checking your browser",
    "reCAPTCHA",
    # not observed for this project
    "Just a moment",
    "Enable JavaScript and cookies to continue",
)

#: How much of a downloaded HTML file is inspected for a challenge marker.
CHALLENGE_SNIFF_BYTES = 65_536


def held_with_digest(dest: Path, expected_sha256: str) -> bool:
    """True when ``dest`` already exists and hashes to ``expected_sha256``.

    Parameters
    ----------
    dest : pathlib.Path
        Candidate local file.
    expected_sha256 : str
        The digest the file must have, from ``SOURCES.yaml`` or from the ``download_plan``
        recorded there.

    Returns
    -------
    bool
        ``True`` if the file is already held and intact, so nothing needs to be requested.
    """
    return dest.exists() and sha256_file(dest) == expected_sha256.lower()


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
        ``None`` when the file does not look like an interstitial. Decoding errors are
        ignored: this is a heuristic on a possibly binary body, not a parser.
    """
    try:
        head = path.read_bytes()[:sniff_bytes].decode("utf-8", errors="replace")
    except OSError:
        return None
    return next((m for m in CHALLENGE_MARKERS if m in head), None)


def fetch_file(
    source: Source,
    data_dir: Path,
    *,
    url: str,
    dest_rel: str,
    expected_sha256: str | None = None,
    force: bool = False,
    max_bytes: int | None = None,
    limiter: RateLimiter | None = None,
) -> AcquireResult:
    """Download one file for ``source`` into ``data/raw/<dest_rel>`` and report the outcome.

    Parameters
    ----------
    source : forensics_core.provenance.manifest.Source
        The registry entry this download belongs to; only its ``id`` is used here, so an
        acquirer may fetch an artefact whose URL differs from the entry's landing page (the
        acquirer's docstring must then say where the URL came from).
    data_dir : pathlib.Path
        The project's ``data/`` directory.
    url : str
        Absolute URL to request. It must appear in the source's registry entry (``url``,
        ``evidence`` or ``download_plan``); no acquirer may construct one.
    dest_rel : str
        Destination path relative to ``data/raw``.
    expected_sha256 : str, optional
        Digest the download must have. Pass it only for artefacts whose bytes are stable:
        not, for instance, for Wayback pages, whose injected toolbar changes the body between
        fetches (see the ``cikrf_eng_2018_wayback`` verification note in ``SOURCES.yaml``).
    force : bool, default False
        Re-download even when the cached copy matches the registry digest.
    max_bytes : int, optional
        Abort the transfer if the body would exceed this size.
    limiter : forensics_core.provenance.manifest.RateLimiter, optional
        Override the per-host pace from ``config/forensics.toml``. Used where a source's own
        ``download_plan`` asks for a slower rate than the configured default and the shared
        configuration file is not this project's to edit.

    Returns
    -------
    AcquireResult
        ``ok`` is false, with the reason in ``detail``, for any non-200 status, transport
        error or digest mismatch. Nothing raises: the runner needs the rest of the registry
        to be attempted.
    """
    dest = data_dir / "raw" / dest_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    rec = fetch(
        url,
        dest,
        project_data_dir=data_dir,
        source_id=source.id,
        expected_sha256=expected_sha256,
        force=force,
        max_bytes=max_bytes,
        limiter=limiter,
    )
    if rec.skipped_cached:
        return AcquireResult(source.id, True, f"already held at raw/{dest_rel}", (dest,), True)
    if rec.error:
        return AcquireResult(source.id, False, f"{url}: {rec.error}")
    if rec.http_status not in (200, 206):
        return AcquireResult(source.id, False, f"{url}: HTTP {rec.http_status}")
    size = rec.bytes if rec.bytes is not None else dest.stat().st_size
    return AcquireResult(source.id, True, f"{size:,} bytes -> raw/{dest_rel}", (dest,))
