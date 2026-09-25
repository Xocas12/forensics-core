"""The false-positive control data: Kobak, Shpilkin & Pshenichnikov (2016) supplement.

This is the only source in the registry that carries elections the published literature does
**not** call anomalous. ``docs/validation_anchors.md`` Tier 2 requires the integer-percentage
test to be run on Poland 2010 and Spain 2011 in the same run as the Russian data, and the
false-positive rate reported next to every power number. Without this file that check cannot
be made, which is why a source whose Russian coverage duplicates the primary mirror is still
acquired.

The archive holds ten tab-separated tables in a reduced ten-column format (region,
constituency, polling station, registered voters, ballots issued in three lines, valid,
invalid, and the leader's votes only). Russia 2000-2012 is present; 2018 is not, because the
paper predates it. Licence: CC BY 4.0, DOI 10.6084/m9.figshare.3126883.v2.

Two fetches, one registry id
----------------------------
Figshare needs a metadata request before the payload can be named, and both requests are made
under the single id ``figshare_kobak_aoas2016_supp``, whose ``name`` is the 9.7 MB
supplementary zip. :func:`forensics_core.provenance.manifest.fetch` writes ``sha256``,
``bytes``, ``local_path`` and ``status: verified`` into that entry on any 200, so the metadata
request alone would leave the registry describing a 3 KB JSON document as though it were the
dataset. :func:`_restore_entry_state` is what stops that: the state the registry entry was
in is captured before the metadata step and put back whenever the payload step does not
succeed.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

from forensics_core.provenance.manifest import SOURCES_FILENAME, Source, update_source

from elections.acquire._common import fetch_file, held_with_digest
from elections.acquire.registry import AcquireResult, register

#: Figshare's public metadata document for article 3126883. Recorded in the entry's
#: ``evidence`` and ``download_plan`` fields; needed because the entry's ``url`` is the
#: JavaScript-rendered landing page, which answers a scripted client with an empty body.
FIGSHARE_API_URL = "https://api.figshare.com/v2/articles/3126883"

#: sha256 of ``kobakEtAl_AOAS2016_suppData.zip`` recorded in the entry's notes. The
#: independent verification pass re-downloaded the archive and confirmed its md5 and its ten
#: members; it did not restate the sha256, so a mismatch here means "re-check the source",
#: not automatically "corrupt download".
AOAS_ZIP_SHA256 = "31040bce65e085d9a14bb6193df2c21d0c348ddefa829a3e7d90d0be29c371a5"

#: The registry fields a successful fetch overwrites, and therefore the ones the metadata step
#: has to be able to give back: the integrity record (``sha256``, ``bytes``, ``local_path``),
#: the ``status`` that record justifies, the stamp of the attempt that wrote it
#: (``fetched_at``, ``http_status``) and the ``blocked_reason`` a success clears.
#:
#: ``notes`` is deliberately absent. The dated failure note the library appends there is the
#: honest record of the attempt and must survive; ``data/fetch_log.jsonl`` keeps a line for
#: each of the two requests either way.
#:
#: The fields listed here have to move together. ``status: verified`` is valid only with
#: evidence behind it - a 200 probe with a timestamp, or a file on disk - so putting the
#: digest back without the ``http_status`` and ``fetched_at`` that justified it would be
#: rejected by the registry's own validation and the false record would survive.
RESTORED_FIELDS: tuple[str, ...] = (
    "sha256",
    "bytes",
    "local_path",
    "status",
    "fetched_at",
    "http_status",
    "blocked_reason",
)

_ZIP_REL = "kobak_aoas2016/kobakEtAl_AOAS2016_suppData.zip"
_META_REL = "kobak_aoas2016/figshare_article_3126883.json"


def _capture_entry_state(source: Source) -> dict[str, Any]:
    """The entry's :data:`RESTORED_FIELDS` as the runner read them from ``SOURCES.yaml``.

    ``source`` is the entry :func:`forensics_core.provenance.runner.main` loaded from the
    registry immediately before calling this acquirer, so it is the state the file is in
    before the metadata step writes anything.
    """
    return {name: getattr(source, name) for name in RESTORED_FIELDS}


def _restore_entry_state(data_dir: Path, source_id: str, captured: dict[str, Any]) -> None:
    """Write ``captured`` back into the registry entry, undoing the metadata step's claim.

    The entry ends up as it was before the run except for ``notes``, which keeps the dated
    failure note the library appended for the payload attempt. That note and
    ``data/fetch_log.jsonl`` are where a failed attempt is recorded; the entry's own fields go
    back to describing the last fetch that actually established something.

    What this does not reconstruct: the status downgrade
    (``blocked``/``unverified``/``partial``) that a lone failing payload fetch would have
    produced. The metadata step's success already suppressed it, since the library leaves the
    status alone when the file the entry points at is present and matches its digest. The
    entry is therefore returned to the status it carried before the run, which is a statement
    about the source, not a claim that the archive is held.

    Failure to rewrite the registry is warned about rather than raised: the caller is
    reporting an acquisition failure already, and the warning names the risk explicitly.
    """
    registry = data_dir / SOURCES_FILENAME
    if not registry.exists():
        return
    try:
        update_source(registry, source_id, **captured)
    except (OSError, ValueError) as exc:
        warnings.warn(
            f"{registry}: could not restore the recorded state of {source_id!r} after a "
            f"failed payload fetch ({exc}); the entry may still describe "
            f"{_META_REL} as though it were the dataset",
            RuntimeWarning,
            stacklevel=2,
        )


@register("figshare_kobak_aoas2016_supp")
def kobak_aoas_supplement(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """Acquire the AOAS 2016 supplementary archive in the two steps Figshare requires.

    Figshare does not publish a stable direct link: the metadata document names a
    ``download_url`` that redirects to a presigned object-store URL valid for about ten
    seconds. So the metadata is fetched first and the payload URL is read out of it, exactly
    as the entry's ``download_plan`` describes.

    Because the two requests share one registry id, the digest recorded in ``SOURCES.yaml``
    can only describe one of the two artefacts, and the shared cache check in
    :func:`forensics_core.provenance.manifest.fetch` would therefore re-download the 9.7 MB
    archive on every run. The local digest check below is what makes the acquirer idempotent
    instead.

    For the same reason the entry's recorded state is captured before the metadata request and
    restored by :func:`_restore_entry_state` on every path that does not end with the archive
    on disk, so that a failed payload step cannot leave the registry claiming the 3 KB metadata
    document is the 9.7 MB dataset.
    """
    dest_zip = data_dir / "raw" / _ZIP_REL
    if not force and held_with_digest(dest_zip, AOAS_ZIP_SHA256):
        return AcquireResult(source.id, True, f"already held at raw/{_ZIP_REL}", (dest_zip,), True)

    captured = _capture_entry_state(source)
    meta = fetch_file(
        source,
        data_dir,
        url=FIGSHARE_API_URL,
        dest_rel=_META_REL,
        force=True,  # the payload URL inside it expires; a cached copy is worthless
    )
    if not meta.ok:
        # The metadata step failed, so it wrote no integrity record to undo; whatever the
        # library recorded about that failure is the truth about this attempt.
        return AcquireResult(source.id, False, f"metadata step failed: {meta.detail}")

    acquired = False
    try:
        try:
            record = json.loads(meta.paths[0].read_text(encoding="utf-8"))
            download_url = record["files"][0]["download_url"]
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            return AcquireResult(
                source.id,
                False,
                f"could not read files[0].download_url from {FIGSHARE_API_URL}: "
                f"{type(exc).__name__}: {exc}",
            )

        payload = fetch_file(
            source,
            data_dir,
            url=download_url,
            dest_rel=_ZIP_REL,
            expected_sha256=AOAS_ZIP_SHA256,
            force=force,
        )
        acquired = payload.ok
        if not payload.ok:
            return payload
        return AcquireResult(
            source.id,
            True,
            f"{payload.detail} (via {FIGSHARE_API_URL})",
            (meta.paths[0], *payload.paths),
        )
    finally:
        # Covers the returns above and any exception out of the payload step (a malformed
        # download_url makes fetch raise ValueError before it reaches the network).
        if not acquired:
            _restore_entry_state(data_dir, source.id, captured)
