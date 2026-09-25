"""Shared fixtures. Everything here is synthetic; no acquired data is used by the test suite."""

from __future__ import annotations

import zipfile
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

_FIXTURES = Path(__file__).parent / "fixtures"

#: The four tab-delimited members of an FSDS quarterly zip, and the fixture that stands in for
#: each. ``readme.htm`` is documentation and is not needed to exercise the loader.
FSDS_FIXTURE_MEMBERS: Mapping[str, str] = {
    "sub.txt": "synthetic_fsds_sub.txt",
    "num.txt": "synthetic_fsds_num.txt",
    "pre.txt": "synthetic_fsds_pre.txt",
    "tag.txt": "synthetic_fsds_tag.txt",
}


@pytest.fixture
def fixtures_dir() -> Path:
    """Directory holding the ``synthetic_*`` fixture files."""
    return _FIXTURES


@pytest.fixture
def make_fsds_zip() -> Callable[..., Path]:
    """Factory assembling a synthetic FSDS quarterly zip from the fixture text files.

    The zip is built rather than committed so that the fixture stays readable as plain text and
    so that a test can vary one member -- an absent table, a renamed column -- without a second
    binary blob in the repository.
    """

    def build(dest: Path, *, members: Mapping[str, str] | None = None) -> Path:
        chosen = members if members is not None else FSDS_FIXTURE_MEMBERS
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for member, fixture in chosen.items():
                zf.writestr(member, (_FIXTURES / fixture).read_text(encoding="utf-8"))
            zf.writestr("readme.htm", "<html><body>synthetic placeholder</body></html>")
        return dest

    return build


@pytest.fixture
def fsds_zip(tmp_path: Path, make_fsds_zip: Callable[..., Path]) -> Path:
    """A synthetic ``2020q4.zip`` holding annual filings for one synthetic firm."""
    return make_fsds_zip(tmp_path / "fsds" / "2020q4.zip")


@pytest.fixture
def listing_html() -> str:
    """The synthetic AAER listing page, as text."""
    return (_FIXTURES / "synthetic_aaer_listing_page.html").read_text(encoding="utf-8")
