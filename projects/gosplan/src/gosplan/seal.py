"""The seal on the held-out anchor.

This project has exactly one validation anchor, the Uzbek cotton affair. A detector chosen,
tuned or even eyeballed while its only test case is visible is fit and validated on the same
event, and the project's only real claim collapses. ``CONTRACT.md`` rule 5 therefore forbids
plotting, testing, scoring or summarising the anchor before gate G3 is signed.

A rule in a document is not enough, because the person who breaks it will be someone who
forgot. This module makes it something the code refuses to do.

What the seal is and is not
---------------------------
It is a guard against forgetting, not against a determined bypass. Anyone with write access to
this repository can create the unseal record by hand. That is deliberate and unavoidable: the
owner has to be able to lift the seal at G3, and no mechanism available here can distinguish
the owner lifting it deliberately from the owner lifting it early. What the seal does buy is
that lifting it is a **separate, deliberate, auditable act** that leaves a committed artefact,
rather than something that happens silently because a notebook cell had no filter on it.

What is permitted while sealed
------------------------------
Acquiring, transcribing, validating and checksumming the cotton data. Loading it into memory
through :func:`filter_sealed` so that the rest of a table stays usable. Counting how many rows
were withheld.

What is not
-----------
Any plot, statistic, score, distributional summary, or power curve fitted on it. Any
groupby that isolates the held-out unit. Any frame passing through code that cannot tell
whether it contains held-out rows.

The aggregate question
----------------------
A union-level cotton total for 1980 contains the Uzbek figure inside it. Refusing every
aggregate that touches a held-out number would make the project impossible, because the
union-level series is most of what exists. The rule drawn here is narrower than that and
narrower than it first appears:

    An aggregate is permitted. A breakdown that isolates the held-out unit is not.

So summing cotton output across republics is allowed even though the total contains Uzbek
cotton, because the total does not tell you the Uzbek figure. Grouping the same frame *by
republic* is refused, because the resulting table has a row that is the anchor. The line is
whether the output lets a reader read off, or closely bound, the held-out quantity.

This is the part of the seal most likely to be argued with later, and it should be: it is a
judgement about what counts as seeing something, not a fact. See ``docs/HELD_OUT.md``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

#: Repository root, found by walking up from this file.
_PROJECT_DIR = Path(__file__).resolve().parents[3]

#: The artefact that lifts the seal. It does not exist until a human writes it at G3, and it
#: must name the gate issue it was signed against, so that lifting the seal leaves a record
#: that can be read back and dated.
UNSEAL_RECORD = _PROJECT_DIR / "docs" / "G3_UNSEAL.md"

#: The line the unseal record must contain, exactly. Requiring a fixed declaration means the
#: file cannot be created by accident, and reading it tells you what was agreed.
UNSEAL_DECLARATION = "GATE G3 IS SIGNED AND THE GOSPLAN ANCHOR IS UNSEALED"

#: The token :func:`unseal` requires. It is not a secret and is not trying to be: the guard is
#: the recorded declaration, not the string.
UNSEAL_TOKEN = "g3-signed"

#: Set to any non-empty value to lift the seal for one process. This exists ONLY so the seal's
#: own tests can exercise the unsealed path without creating the record file. It is checked
#: after the record file, is never mentioned in user-facing errors, and must not appear in any
#: analysis code: a card that uses it is violating CONTRACT rule 5 by another route.
_TEST_OVERRIDE_ENV = "GOSPLAN_SEAL_TEST_OVERRIDE"


class SealedError(RuntimeError):
    """Raised when an operation would expose the held-out anchor.

    The message always says what was withheld, why, and what would lift it, because the person
    hitting this is usually someone who did not know the seal existed.
    """


@dataclass(frozen=True)
class HeldOut:
    """The rows nobody may look at before G3.

    Attributes
    ----------
    series : str
        Matched case-insensitively as a substring, so ``"cotton"`` catches "seed cotton",
        "cotton lint" and "raw cotton" without listing them.
    region : tuple of str
        Any of these region spellings, matched case-insensitively as substrings, identifies the
        held-out unit. Several spellings are recorded because the sources disagree.
    years : range
        Deliberately WIDER than the affair's own 1978 to 1983 window. A detector tuned on 1977
        and 1984 is still a detector tuned around the anchor, so the shoulder years are sealed
        too.
    reason : str
        Printed in every error, so the seal explains itself at the point of contact.
    """

    series: str = "cotton"
    region: tuple[str, ...] = ("uzbek", "uzbekistan", "uzbek ssr", "uzbekskaya")
    years: range = field(default_factory=lambda: range(1976, 1986))
    reason: str = (
        "the Uzbek cotton affair is this project's only validation anchor, so looking at it "
        "before the detectors are frozen would fit and validate them on the same event"
    )

    def matches(self, region: str, series: str, year: float | int | None) -> bool:
        """True if one row is held out. All three conditions must hold."""
        if year is None:
            return False
        try:
            y = int(year)
        except (TypeError, ValueError):
            return False
        if y not in self.years:
            return False
        if self.series not in str(series).casefold():
            return False
        r = str(region).casefold()
        return any(spelling in r for spelling in self.region)


#: The one held-out set in this project.
HELD_OUT = HeldOut()


def _record_lifts_seal() -> bool:
    if not UNSEAL_RECORD.is_file():
        return False
    try:
        text = UNSEAL_RECORD.read_text(encoding="utf-8")
    except OSError:
        return False
    return UNSEAL_DECLARATION in text


def is_sealed() -> bool:
    """True while the anchor is hidden.

    The seal is lifted only by the unseal record: a committed file containing
    :data:`UNSEAL_DECLARATION`, written by a human at G3.
    """
    if _record_lifts_seal():
        return False
    return not os.environ.get(_TEST_OVERRIDE_ENV)


def unseal(token: str) -> None:
    """Assert that the seal is lifted, or raise explaining what is missing.

    This does not itself lift the seal, and cannot: there is deliberately no code path that
    creates :data:`UNSEAL_RECORD`. Lifting the seal is a human act at G3 that leaves a
    committed artefact. This function is how analysis code checks.

    Raises
    ------
    SealedError
        If the token is wrong, or the unseal record is absent or does not carry the
        declaration.
    """
    if token != UNSEAL_TOKEN:
        raise SealedError(
            f"wrong unseal token. The anchor stays sealed. {HELD_OUT.reason}. "
            f"After gate G3 is signed, the record at {UNSEAL_RECORD} lifts the seal."
        )
    if is_sealed():
        raise SealedError(
            f"the anchor is sealed: {UNSEAL_RECORD} does not exist or does not contain the "
            f"declaration {UNSEAL_DECLARATION!r}. {HELD_OUT.reason}. Lifting the seal is a "
            "human act at gate G3, not something code may do."
        )


def held_out_mask(
    frame: pd.DataFrame,
    *,
    region_col: str = "region",
    series_col: str = "series",
    year_col: str = "year",
    held_out: HeldOut = HELD_OUT,
) -> Any:
    """Boolean mask of the held-out rows.

    Raises
    ------
    SealedError
        If the frame lacks a column needed to identify held-out rows while the seal is on. A
        frame that cannot be checked is refused rather than passed through: silently letting an
        unidentifiable frame past is exactly the failure this module exists to prevent, and a
        table with no region column may well BE the Uzbek series.
    """
    import numpy as np

    missing = [c for c in (region_col, series_col, year_col) if c not in frame.columns]
    if missing:
        if is_sealed():
            raise SealedError(
                f"cannot tell whether this frame contains the held-out anchor: it has no "
                f"{missing} column(s). Add them, or if the frame provably contains no Uzbek "
                "cotton data for 1976-1985, say so explicitly by passing declare_clean=True "
                "to filter_sealed. Guessing is not available while the seal is on."
            )
        return np.zeros(len(frame), dtype=bool)

    return np.array(
        [
            held_out.matches(r, s, y)
            for r, s, y in zip(frame[region_col], frame[series_col], frame[year_col], strict=True)
        ],
        dtype=bool,
    )


def filter_sealed(
    frame: pd.DataFrame,
    *,
    region_col: str = "region",
    series_col: str = "series",
    year_col: str = "year",
    held_out: HeldOut = HELD_OUT,
    declare_clean: bool = False,
) -> tuple[pd.DataFrame, int]:
    """Drop the held-out rows and report how many went.

    Returns ``(frame, n_withheld)``. While the seal is lifted this is a no-op returning
    ``(frame, 0)``, so analysis code can call it unconditionally and stop being correct only
    because someone remembered.

    ``declare_clean=True`` asserts that the caller knows the frame contains no held-out data,
    for tables that legitimately lack a region or series column. It is an assertion by the
    caller, recorded in the call site, not a bypass: it does not lift the seal for anything
    else, and using it on a frame that does contain the anchor is a CONTRACT rule 5 violation.
    """
    if not is_sealed():
        return frame, 0
    if declare_clean:
        return frame, 0
    mask = held_out_mask(
        frame,
        region_col=region_col,
        series_col=series_col,
        year_col=year_col,
        held_out=held_out,
    )
    n = int(mask.sum())
    return frame.loc[~mask], n


def check_grouping(
    frame: pd.DataFrame,
    by: str | list[str],
    *,
    region_col: str = "region",
    series_col: str = "series",
    year_col: str = "year",
    held_out: HeldOut = HELD_OUT,
) -> None:
    """Refuse a grouping that would isolate the held-out unit.

    An aggregate is permitted; a breakdown is not. Summing cotton across republics is allowed,
    because the total does not tell you the Uzbek figure. Grouping the same frame by republic
    is refused, because one of the resulting rows IS the anchor.

    The test is deliberately simple and slightly conservative: if the grouping keys include the
    region column and the frame still contains held-out rows, refuse. Anything subtler would
    need to reason about what an aggregate reveals, and being wrong in that direction is the
    expensive mistake.

    Raises
    ------
    SealedError
        If the grouping would isolate the anchor while the seal is on.
    """
    if not is_sealed():
        return
    keys = [by] if isinstance(by, str) else list(by)
    if region_col not in keys:
        return
    mask = held_out_mask(
        frame,
        region_col=region_col,
        series_col=series_col,
        year_col=year_col,
        held_out=held_out,
    )
    n = int(mask.sum())
    if n:
        raise SealedError(
            f"grouping by {keys} would isolate the held-out anchor: {n} row(s) of "
            f"{held_out.series} for {held_out.region[0]} in {held_out.years.start}-"
            f"{held_out.years.stop - 1} are still in this frame. {held_out.reason}. "
            "Aggregate without the region key, or call filter_sealed first and report how "
            "many rows were withheld."
        )
