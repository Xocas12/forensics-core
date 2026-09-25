"""Harmonised DMSP and VIIRS nightlights: free, anonymous, and 1.09 GB, so opt-in.

The nightlight proxy is the one physical series in this project that is genuinely open. The
Earth Observation Group's own products now sit behind a Keycloak login, and since 1 June 2026
programmatic access to them is limited to paid subscribers, so both of those registry entries
are ``blocked`` and have no acquirer. The harmonised product on Figshare needs no account: a
ranged GET on a file identifier returned 206 with TIFF magic bytes and no cookie.

Li, Zhou, Zhao and Zhao (2020), *Scientific Data*; dataset version 10 at
doi:10.6084/m9.figshare.9828827, CC BY 4.0, 1992-2024, 34 GeoTIFFs, 1,091,935,532 bytes.

**Why the rasters are not part of a default run.** They are a gigabyte, they are global when
the project needs one country, and nothing downstream can use them until a zonal-statistics
step over provincial boundaries exists, which it does not. A default ``make data`` that spends
a gigabyte on a file no code reads is a bad default. So this acquirer fetches the article
metadata, thirteen kilobytes, which is step one of the registry's own download plan and the
only way to enumerate the file identifiers; the rasters come down only when
``CHINA_ACQUIRE_NIGHTLIGHTS`` is set in the environment, or when
:func:`download_rasters` is called directly.

Note also that provincial boundaries are **not** in this project's registry. Zonal statistics
need a boundary file, and acquiring one is an open question recorded in the README, not
something to be solved by reaching for whatever shapefile is nearest.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
from forensics_core.provenance.manifest import Source

from china.acquire._common import fetch_file, fetch_files
from china.acquire.registry import AcquireResult, register

__all__ = [
    "ARTICLE_ID",
    "ARTICLE_METADATA_REL",
    "EXPECTED_FILE_COUNT",
    "EXPECTED_TOTAL_BYTES",
    "OPT_IN_ENV_VAR",
    "download_rasters",
    "figshare_download_url",
    "parse_figshare_article",
]

#: Figshare article holding the harmonised product.
ARTICLE_ID = 9828827

#: Where the article metadata lands under ``data/raw``.
ARTICLE_METADATA_REL = f"nightlights/figshare_article_{ARTICLE_ID}.json"

#: Environment variable that opts a run in to the rasters. Any value other than the empty
#: string, ``"0"``, ``"false"`` or ``"no"`` counts as opting in.
OPT_IN_ENV_VAR = "CHINA_ACQUIRE_NIGHTLIGHTS"

#: What the registry recorded for version 10, used as an integrity check on the metadata
#: rather than as an assumption: a different count or total means the dataset was revised and
#: the citation in the docs needs updating.
EXPECTED_FILE_COUNT = 34
EXPECTED_TOTAL_BYTES = 1_091_935_532

#: Ceiling per raster. The largest file the registry lists is 40,862,548 bytes.
_MAX_RASTER_BYTES = 256 * 1024 * 1024

#: Columns of the frame :func:`parse_figshare_article` returns.
FILE_COLUMNS: tuple[str, ...] = ("file_id", "name", "size", "computed_md5", "download_url")


def figshare_download_url(file_id: int | str) -> str:
    """Download URL for one Figshare file identifier.

    The redirect this URL issues points at a signed object-store URL that expires in about ten
    seconds and accepts GET only, so it must be followed at download time and never resolved
    in advance or probed with HEAD.

    Parameters
    ----------
    file_id : int or str
        Figshare file identifier from the article metadata.

    Returns
    -------
    str
        Absolute URL.
    """
    return f"https://ndownloader.figshare.com/files/{file_id}"


def parse_figshare_article(payload: bytes | str) -> pd.DataFrame:
    """Parse the article metadata into one row per file.

    Parameters
    ----------
    payload : bytes or str
        The article JSON.

    Returns
    -------
    pandas.DataFrame
        Columns :data:`FILE_COLUMNS`, with ``size`` numeric and ``download_url`` built by
        :func:`figshare_download_url`. The frame's ``attrs`` carry ``title``, ``doi`` and
        ``license`` when the response has them, so the citation travels with the data.

    Raises
    ------
    ValueError
        If the body is not JSON, or is JSON without a ``files`` list. Figshare answers a
        missing article with an error object rather than an empty list, so a missing ``files``
        key means the request failed, not that the article is empty.
    """
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"article metadata is not JSON: {exc}") from exc
    if not isinstance(obj, dict) or not isinstance(obj.get("files"), list):
        raise ValueError("article metadata has no 'files' list; the request did not succeed")

    frame = pd.DataFrame(
        [
            {
                "file_id": entry.get("id"),
                "name": str(entry.get("name", "")),
                "size": entry.get("size"),
                "computed_md5": str(entry.get("computed_md5") or ""),
                "download_url": figshare_download_url(entry.get("id")),
            }
            for entry in obj["files"]
            if isinstance(entry, dict)
        ],
        columns=list(FILE_COLUMNS),
    )
    frame["size"] = pd.to_numeric(frame["size"], errors="coerce").astype("Int64")
    license_value = obj.get("license")
    frame.attrs.update(
        {
            "title": obj.get("title", ""),
            "doi": obj.get("doi", ""),
            "license": (
                license_value.get("name", "")
                if isinstance(license_value, dict)
                else str(license_value or "")
            ),
        }
    )
    return frame


def _opted_in() -> bool:
    value = os.environ.get(OPT_IN_ENV_VAR, "").strip().lower()
    return value not in {"", "0", "false", "no"}


def download_rasters(source: Source, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Download every GeoTIFF the article metadata lists. About 1.09 GB.

    Reads the metadata already on disk rather than re-requesting it, so this can be called
    long after the metadata was acquired and will download exactly the files that metadata
    describes.

    Parameters
    ----------
    source : forensics_core.provenance.manifest.Source
        The registry entry to attribute the downloads to.
    data_dir : Path
        The project's ``data/`` directory.
    force : bool, default False
        Re-download files already on disk.

    Returns
    -------
    AcquireResult
        Failing, with an explanation, if the metadata is not on disk yet.
    """
    metadata_path = data_dir / "raw" / ARTICLE_METADATA_REL
    if not metadata_path.exists():
        return AcquireResult(
            source.id,
            False,
            f"article metadata not acquired yet; expected {ARTICLE_METADATA_REL}",
        )
    try:
        files = parse_figshare_article(metadata_path.read_bytes())
    except (OSError, ValueError) as exc:
        return AcquireResult(source.id, False, f"article metadata unusable: {exc}")

    work = [
        (str(url), f"nightlights/{name}")
        for url, name in zip(files["download_url"], files["name"], strict=True)
    ]
    return fetch_files(
        source, data_dir, work, force=force, max_bytes=_MAX_RASTER_BYTES, label="GeoTIFFs"
    )


@register("figshare_li2020_harmonized_ntl")
def harmonized_nightlights(source: Source, data_dir: Path, force: bool = False) -> AcquireResult:
    """Article metadata always; the 34 GeoTIFFs only when explicitly opted in.

    The metadata is thirteen kilobytes and is the file that enumerates the rasters, checks the
    dataset version and carries the licence and citation. The rasters are 1.09 GB and are
    skipped unless ``CHINA_ACQUIRE_NIGHTLIGHTS`` is set, which the result line says out loud
    so that nobody mistakes a fast run for a complete one.

    The file count and total size are compared against what the registry recorded for version
    10. A mismatch is reported, not treated as an error: Figshare versions this dataset, and a
    new version is news for the citation rather than a failed download.
    """
    result = fetch_file(
        source,
        data_dir,
        url=source.url or f"https://api.figshare.com/v2/articles/{ARTICLE_ID}",
        dest_rel=ARTICLE_METADATA_REL,
        force=force,
    )
    if not result.ok:
        return result

    notes: list[str] = []
    metadata_path = data_dir / "raw" / ARTICLE_METADATA_REL
    try:
        files = parse_figshare_article(metadata_path.read_bytes())
    except (OSError, ValueError) as exc:
        return AcquireResult(source.id, False, f"metadata fetched but unusable: {exc}")

    total = int(files["size"].sum()) if len(files) else 0
    if len(files) != EXPECTED_FILE_COUNT or total != EXPECTED_TOTAL_BYTES:
        notes.append(
            f"dataset changed since the registry was written: {len(files)} files / "
            f"{total:,} bytes against {EXPECTED_FILE_COUNT} / {EXPECTED_TOTAL_BYTES:,}"
        )

    if not _opted_in():
        detail = (
            f"{result.detail}; {len(files)} rasters ({total:,} bytes) listed and NOT "
            f"downloaded: optional target, set {OPT_IN_ENV_VAR}=1 or call "
            "china.acquire.nightlights.download_rasters()"
        )
        if notes:
            detail += "; " + "; ".join(notes)
        return AcquireResult(source.id, True, detail, result.paths)

    rasters = download_rasters(source, data_dir, force=force)
    detail = f"{result.detail}; {rasters.detail}"
    if notes:
        detail += "; " + "; ".join(notes)
    return AcquireResult(source.id, rasters.ok, detail, (*result.paths, *rasters.paths))
