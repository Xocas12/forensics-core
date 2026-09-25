"""The Soviet statistical annuals themselves: scans, page manifests, and one usable text.

This is the module where the project's real cost sits, and it deliberately acquires very
little. *Narodnoe khoziaistvo SSSR* is the primary reported series -- the thing whose
distortion the project is trying to bound -- and it exists, for practical purposes, only as
scanned printed tables.

**The optical character recognition is not fit for numbers.** The registry's inspection of
the 1985 volume is unambiguous: the cover title itself came out as a garbled string in place
of the printer's own words, and numeric rows lose their column separators entirely, so that a
row of eleven figures arrives as one run of digits and stray bars. Row and column alignment
is gone. Any digit test run on that text measures the OCR engine (``docs/known_traps.md``,
trap 9). Consequently:

* the bundled ``_djvu.txt`` derivative is **not** acquired as a data source for the annuals;
* what is acquired for the sample volume is the **hOCR**, whose word bounding boxes are the
  only artefact that can be used to rebuild column geometry, together with the page-number
  and scandata sidecars needed to map a table to its printed page;
* everything else is a **manifest**: the collection listing and one metadata document per
  volume, which is what :mod:`gosplan.transcribe` needs to open a transcription target and
  what a per-volume download would be driven from. Pulling every volume's derivatives is
  roughly 1.8 GB, and the page images roughly 10 GB; that is a deliberate, scoped decision,
  not something ``--all`` should do on its own.

**Coverage.** The archive.org collection holds 28 volumes and is missing 1957, 1959, 1960,
1962, 1966, 1967, 1971, 1976, 1981 and 1990. The volunteer library ``publ.lib.ru`` fills two
of those, 1960 and 1990 -- 1990 being the final annual -- and istmat.org claims to cover all
ten, in HTML rather than as images, which would make it the single most valuable source in
the project if its chapter pages really carry table text. Nobody has confirmed that they do.

**The republic annual is the weakest link and is not here at all.** *Narodnoe khoziaistvo
Uzbekskoi SSR* is the volume that covers the anchor, and no digitised copy was found on
archive.org, HathiTrust or publ.lib.ru. istmat.org lists six Uzbek editions, of which the
padding decade is represented only by 1988 and 1990. The 1957 edition is catalogued at the
Russian national digital library, which refuses non-Russian egress outright. See
``data/ACCESS_NOTES.md``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from gosplan.acquire._common import (
    fetch_file,
    hrefs,
    ia_download_url,
    ia_files,
    ia_search_docs,
    ia_select,
    many,
    read_json,
    read_text,
)
from gosplan.acquire.registry import AcquireResult, register

#: archive.org collection of scanned *Narodnoe khoziaistvo SSSR* annuals.
NARKHOZ_COLLECTION = "pub_narodnoe-khoziaistvo-sssr"

#: Derived files worth having per volume, in descending order of usefulness for table work.
#: ``hOCR`` carries word bounding boxes, which is the only way to rebuild column structure
#: from an existing scan without re-running OCR; the two sidecars map sequential scan images
#: to printed page numbers, without which page-level provenance cannot be recorded.
VOLUME_ASSET_FORMATS: tuple[str, ...] = ("hocr", "text pdf")
VOLUME_SIDECAR_SUFFIXES: tuple[str, ...] = ("_page_numbers.json", "_scandata.xml")

#: istmat.org Drupal node ids confirmed by scaffolding: the union series index and the Uzbek
#: SSR series index. Child editions hang off these as ``/node/<id>`` links whose slugs are
#: not derivable, which is why they are scraped rather than constructed.
ISTMAT_SERIES_NODES: dict[str, str] = {
    "sssr_series": "https://istmat.org/node/21341",
    "uzbek_ssr_series": "https://istmat.org/node/53397",
}

#: The one istmat.org file whose URL was confirmed by a successful request (25,088,236 bytes,
#: ``Content-Type: application/pdf``): the 1990 union annual, which archive.org lacks.
ISTMAT_NARKHOZ_1990_PDF = (
    "https://istmat.org/files/uploads/433/narodnoe_hozyaystvo_sssr_v_1990_g.pdf"
)

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(name: str) -> str:
    """Map a remote filename to an ASCII filename safe on every platform.

    The mirrors hold files whose names contain Cyrillic, spaces, quotes and brackets. The
    remote name is preserved in the fetch log and in the item metadata; only the local
    filename is sanitised.
    """
    cleaned = _UNSAFE.sub("_", name).strip("_")
    return cleaned or "file"


def volume_asset_urls(identifier: str, metadata: dict[str, Any]) -> list[tuple[str, int | None]]:
    """URLs of the table-usable derivatives of one scanned volume, with their sizes.

    Selection is by the ``format`` field of the item's file list, as the registry's download
    plan requires: archive.org filenames are not reliably derivable from the identifier, and
    an item may carry an encrypted (DRM) PDF alongside the open one.

    Parameters
    ----------
    identifier : str
        archive.org item identifier.
    metadata : dict
        Parsed ``https://archive.org/metadata/<identifier>`` response.

    Returns
    -------
    list of (str, int or None)
        Download URL and declared size in bytes for each selected file.
    """
    chosen = ia_select(
        metadata, formats=VOLUME_ASSET_FORMATS, suffixes=("_hocr.html", *VOLUME_SIDECAR_SUFFIXES)
    )
    out: list[tuple[str, int | None]] = []
    for f in chosen:
        name = str(f.get("name", ""))
        if not name or "_encrypted" in name:
            continue
        size = f.get("size")
        out.append((ia_download_url(identifier, name), int(size) if str(size).isdigit() else None))
    return out


@register("ia_narkhoz_collection")
def narkhoz_collection(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Enumerate the scanned annuals and store one metadata document per volume.

    Identifiers are read from the collection search rather than hardcoded, because the
    collection is a live archive.org facet and the registry's snapshot of it (28 volumes,
    with one identifier that looks mislabelled) is a description, not a contract.

    No page images, PDFs or hOCR are downloaded here. The metadata documents give file names,
    sizes and md5s, which is what makes a later per-volume pull idempotent, and
    :func:`volume_asset_urls` turns one of them into the download list for a volume that a
    transcription target actually needs.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")

    listing = fetch_file(source.id, data_dir, source.url, "narkhoz/collection.json", force=force)
    if not listing.ok or listing.path is None or not listing.path.exists():
        return AcquireResult(source.id, False, f"collection listing: {listing.detail}")

    docs = ia_search_docs(read_json(listing.path))
    identifiers = [str(d["identifier"]) for d in docs if d.get("identifier")]
    if not identifiers:
        return AcquireResult(
            source.id,
            False,
            f"collection listing fetched ({listing.detail}) but it names no identifiers",
            (listing.path,),
        )

    items = [
        (f"https://archive.org/metadata/{ident}", f"narkhoz/metadata/{safe_name(ident)}.json")
        for ident in identifiers
    ]
    result = many(source, data_dir, items, force=force)
    return AcquireResult(
        source.id,
        result.ok,
        f"{len(identifiers)} volumes listed; metadata {result.detail}",
        (listing.path, *result.paths),
        result.skipped_cached,
    )


@register("ia_narkhoz_1985_item")
def narkhoz_1985(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """The 1985 annual: metadata, hOCR word boxes and the page-number sidecars.

    This volume is the pipeline's worked example. It is inside the padding decade, it is
    confirmed to contain a raw-cotton table with republic shares running 1940-1985, and the
    Russian feminine adjective "Uzbekskaia" occurs 223 times in its text layer (the registry
    counted that inflected form alone, not every mention of Uzbekistan), so it is the natural
    first transcription target -- and it is also the volume whose OCR failure was measured,
    which is why the double-transcription requirement exists at all.

    The hOCR file is tens of megabytes and is the point of the fetch: word bounding boxes are
    what a table reconstruction needs. The ``_djvu.txt`` derivative is deliberately not taken.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")

    identifier = source.url.rstrip("/").rsplit("/", 1)[-1]
    meta = fetch_file(
        source.id,
        data_dir,
        source.url,
        f"narkhoz/metadata/{safe_name(identifier)}.json",
        force=force,
    )
    if not meta.ok or meta.path is None or not meta.path.exists():
        return AcquireResult(source.id, False, f"metadata: {meta.detail}")

    metadata = read_json(meta.path)
    assets = [url for url, _ in volume_asset_urls(identifier, metadata) if "_hocr" in url]
    sidecars = [
        ia_download_url(identifier, str(f["name"]))
        for f in ia_files(metadata)
        if str(f.get("name", "")).endswith(VOLUME_SIDECAR_SUFFIXES)
    ]
    wanted = assets + sidecars
    if not wanted:
        return AcquireResult(
            source.id,
            False,
            f"metadata fetched ({meta.detail}) but it lists no hOCR or page-number files",
            (meta.path,),
        )

    items = [(u, f"narkhoz/1985/{safe_name(u.rsplit('/', 1)[-1])}") for u in wanted]
    result = many(source, data_dir, items, force=force)
    return AcquireResult(
        source.id,
        result.ok,
        f"metadata + {result.detail}",
        (meta.path, *result.paths),
        result.skipped_cached,
    )


@register("publ_lib_ru_narkhoz")
def publ_lib_ru(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """The volunteer DjVu library: the fallback for the 1960 and 1990 annuals.

    Three traps, all recorded in the registry and all handled here:

    1. the index is **windows-1251** and its links are uppercase ``<A HREF=...>`` tags, which
       lowercase-only matching misses (see :func:`gosplan.acquire._common.hrefs`);
    2. the filenames contain quotes, parentheses and brackets and must be percent-encoded
       rather than passed through as typed;
    3. **the server truncates long responses.** Scaffolding needed three resumed attempts to
       get one 10 MB zip, twice losing the tail of the response. Downloads therefore run with
       ranged resume enabled, and a run that reports a failure here should simply be repeated:
       each attempt continues the partial file rather than starting again.

    The files are DjVu with no text layer, so they are re-OCR or manual-transcription targets,
    not machine-readable sources.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")

    index_rel = "publ_lib_ru/index.html"
    idx = fetch_file(source.id, data_dir, source.url, index_rel, force=force)
    if not idx.ok or idx.path is None or not idx.path.exists():
        return AcquireResult(source.id, False, f"index: {idx.detail}")

    html = read_text(idx.path, encoding="cp1251")
    zips = hrefs(html, base=source.url, pattern=r"\.zip$")
    if not zips:
        return AcquireResult(
            source.id,
            False,
            f"index fetched ({idx.detail}) but no .zip links were found in it",
            (idx.path,),
        )

    items = [(u, f"publ_lib_ru/{safe_name(u.rsplit('/', 1)[-1])}") for u in zips]
    result = many(source, data_dir, items, force=force, resume=True)
    return AcquireResult(
        source.id,
        result.ok,
        f"index + {len(zips)} archives; {result.detail}",
        (idx.path, *result.paths),
        result.skipped_cached,
    )


@register("istmat_org")
def istmat(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """istmat.org: the two series indexes and the one file whose URL was confirmed.

    Strategically this is the most valuable source in the registry, because its chapter pages
    are HTML text rather than page images, and because it covers all ten years archive.org
    lacks plus six editions of the Uzbek republic annual. Two things stop it being treated as
    solved:

    * **Nobody has confirmed the HTML chapters contain table text.** Scaffolding saw chapter
      indexes only. Verify that on one chapter before any scraping strategy is built on it.
    * **The host is intermittently unreachable from here** -- connections to both ports timed
      out or were refused, then succeeded minutes later. That looks like an overloaded or
      filtered origin rather than a hard block, so a failure from this acquirer is worth
      retrying later; it is not evidence the material is gone.

    What is fetched: the union and Uzbek series index nodes, and the 1990 union annual PDF
    whose ``Content-Length`` was confirmed. Child edition pages are **not** crawled
    automatically -- the discovered node links are reported so that a scoped follow-up can
    take them -- because the content is CC BY-SA 4.0 and a share-alike obligation on derived
    tables is a decision for the project owner, not a side effect of ``--all``.
    """
    items = [(url, f"istmat/{slug}.html") for slug, url in ISTMAT_SERIES_NODES.items()]
    items.append((ISTMAT_NARKHOZ_1990_PDF, "istmat/narkhoz_sssr_1990.pdf"))
    result = many(source, data_dir, items, force=force)

    discovered: set[str] = set()
    for slug in ISTMAT_SERIES_NODES:
        page = data_dir / "raw" / "istmat" / f"{slug}.html"
        if page.exists():
            discovered.update(
                hrefs(read_text(page), base="https://istmat.org/", pattern=r"/node/\d+$")
            )
    extra = f"; {len(discovered)} child node links discovered (not crawled)" if discovered else ""
    return AcquireResult(
        source.id, result.ok, f"{result.detail}{extra}", result.paths, result.skipped_cached
    )


@register("ia_khanin_western_estimates")
def khanin_western_estimates(source: Any, data_dir: Path, *, force: bool = False) -> AcquireResult:
    """Khanin, *Sovetskii ekonomicheskii rost: analiz zapadnykh otsenok* (archive.org).

    Honest scope note: this is **not** either of the two Khanin texts the project actually
    wants. "Lukavaia tsifra" (Selyunin and Khanin, *Novyi mir* 1987 no. 2) and Khanin's 1991
    *Dinamika ekonomicheskogo razvitiia SSSR* are the sources behind the alternative growth
    estimates, and neither was found in a form anyone verified -- the registry's
    ``khanin_lukavaya_tsifra`` entry is marked unverified precisely because the page fetched
    for it turned out to be commentary quoting the article rather than the article. This
    later book is the only Khanin text confirmed freely readable, and it is acquired for the
    argument, not for its numbers.

    The item's text layer is taken first, as the registry advises, so that OCR quality can be
    judged for 600 KB rather than 33 MB. Filenames on this item contain Cyrillic and spaces
    and are therefore read from the metadata and percent-encoded, never constructed.
    """
    if not source.url:
        return AcquireResult(source.id, False, "registry entry has no url")

    identifier = source.url.rstrip("/").rsplit("/", 1)[-1]
    meta = fetch_file(
        source.id,
        data_dir,
        source.url,
        f"khanin/{safe_name(identifier)}_metadata.json",
        force=force,
    )
    if not meta.ok or meta.path is None or not meta.path.exists():
        return AcquireResult(source.id, False, f"metadata: {meta.detail}")

    metadata = read_json(meta.path)
    texts = ia_select(metadata, formats=("djvutxt",), suffixes=("_djvu.txt",))
    if not texts:
        return AcquireResult(
            source.id,
            False,
            f"metadata fetched ({meta.detail}) but it lists no text derivative",
            (meta.path,),
        )
    items = [
        (ia_download_url(identifier, str(f["name"])), f"khanin/{safe_name(str(f['name']))}")
        for f in texts
    ]
    result = many(source, data_dir, items, force=force)
    return AcquireResult(
        source.id,
        result.ok,
        f"metadata + {result.detail}",
        (meta.path, *result.paths),
        result.skipped_cached,
    )
