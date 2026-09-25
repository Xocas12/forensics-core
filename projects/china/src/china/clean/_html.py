"""Minimal HTML helpers shared by the yearbook and central-bank loaders.

Deliberately regular expressions and not a parser. Every page this project reads is a flat
list of links produced by a content-management system: the yearbook's contents frame, the
central bank's report index and its per-year pages. There is no nesting to walk and no
JavaScript to run, and a regular expression that fails is easier to reason about than a
parser that silently repairs malformed markup into something plausible.

Encoding is a real hazard here, not a detail: the yearbook pages declare ``gb2312`` and the
central bank's pages are UTF-8, so decoding is always explicit and never guessed from the
bytes alone.
"""

from __future__ import annotations

import html as _html
import re
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = ["Anchor", "decode_html", "iter_anchors", "strip_tags"]

_ANCHOR_RE = re.compile(
    r"<a\b[^>]*?href\s*=\s*(?P<q>[\"'])(?P<href>[^\"']*)(?P=q)[^>]*>(?P<text>.*?)</a\s*>",
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]*>")


@dataclass(frozen=True)
class Anchor:
    """One ``<a href=...>`` link.

    Attributes
    ----------
    href : str
        The target exactly as written in the markup.
    text : str
        The link text with tags and entities removed and whitespace collapsed.
    """

    href: str
    text: str


def decode_html(raw: bytes, encodings: Sequence[str] = ("utf-8", "gb18030")) -> str:
    """Decode a page, trying each encoding in turn.

    Parameters
    ----------
    raw : bytes
        Bytes as served.
    encodings : sequence of str, default ``("utf-8", "gb18030")``
        Encodings to try strictly, in order.

    Returns
    -------
    str
        The decoded page. If every candidate fails, the first is applied again with
        replacement characters rather than raising: a single bad byte in a footnote must not
        cost the whole page.
    """
    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode(encodings[0], errors="replace")


def strip_tags(fragment: str) -> str:
    """Remove tags and entities from a markup fragment and collapse whitespace.

    Parameters
    ----------
    fragment : str
        Markup.

    Returns
    -------
    str
        Plain text.
    """
    return " ".join(_html.unescape(_TAG_RE.sub(" ", fragment)).split())


def iter_anchors(text: str) -> list[Anchor]:
    """All quoted-href links in a page, in document order.

    Unquoted ``href`` attributes are not matched. None of the pages this project reads uses
    them, and matching them loosely would pick up fragments of scripts.

    Parameters
    ----------
    text : str
        Decoded page.

    Returns
    -------
    list of Anchor
        Possibly empty. An empty result from a page that should have links means the fetch
        returned something else, and callers are expected to treat it as an error.
    """
    return [
        Anchor(match.group("href").strip(), strip_tags(match.group("text")))
        for match in _ANCHOR_RE.finditer(text)
    ]
