"""The seal must refuse to show the anchor, and must refuse to guess.

Every frame here is synthetic. The Uzbek rows carry obviously fake values, because a fixture
that looked like real cotton output would itself be a small violation of the thing being
tested.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from gosplan.seal import (
    HELD_OUT,
    UNSEAL_DECLARATION,
    UNSEAL_RECORD,
    UNSEAL_TOKEN,
    HeldOut,
    SealedError,
    check_grouping,
    filter_sealed,
    held_out_mask,
    is_sealed,
    unseal,
)

_OVERRIDE = "GOSPLAN_SEAL_TEST_OVERRIDE"


def panel() -> pd.DataFrame:
    """A tiny synthetic panel: two republics, two series, six years."""
    rows = []
    for region in ("Uzbek SSR", "Kazakh SSR"):
        for series in ("cotton", "wheat"):
            for year in (1975, 1977, 1980, 1983, 1986, 1990):
                rows.append(
                    {
                        "region": region,
                        "series": series,
                        "year": year,
                        "value": 100.0,  # deliberately flat and fake
                    }
                )
    return pd.DataFrame(rows)


@pytest.fixture
def sealed(monkeypatch):
    monkeypatch.delenv(_OVERRIDE, raising=False)
    return None


@pytest.fixture
def unsealed(monkeypatch):
    monkeypatch.setenv(_OVERRIDE, "1")
    return None


# ---------------------------------------------------------------- the seal is on by default


def test_the_anchor_is_sealed_in_this_repository(sealed):
    """The whole programme depends on this being true until G3."""
    assert is_sealed() is True
    assert not UNSEAL_RECORD.exists(), (
        f"{UNSEAL_RECORD} exists, which lifts the seal. It must not be created before G3 is signed."
    )


def test_unseal_refuses_while_the_record_is_absent(sealed):
    with pytest.raises(SealedError, match="the anchor is sealed"):
        unseal(UNSEAL_TOKEN)


def test_unseal_refuses_a_wrong_token(sealed):
    with pytest.raises(SealedError, match="wrong unseal token"):
        unseal("please")


def test_there_is_no_code_path_that_creates_the_unseal_record():
    """Lifting the seal is a human act at G3. If code could write the record, the seal would
    be decoration."""
    import gosplan.seal as seal_module

    source = Path(seal_module.__file__).read_text(encoding="utf-8")
    for forbidden in ("write_text", "open(UNSEAL_RECORD", "touch()", "mkdir"):
        assert forbidden not in source, f"seal.py contains {forbidden!r}"


# ---------------------------------------------------------------- withholding rows


def test_held_out_rows_are_exactly_the_uzbek_cotton_rows_in_window(sealed):
    df = panel()
    mask = held_out_mask(df)
    held = df.loc[mask]
    assert set(held["region"]) == {"Uzbek SSR"}
    assert set(held["series"]) == {"cotton"}
    assert set(held["year"]) == {1977, 1980, 1983}
    # 1975 and 1986 are outside the sealed window; wheat and Kazakh are untouched
    assert len(held) == 3


def test_filter_sealed_drops_them_and_says_how_many(sealed):
    df = panel()
    out, n = filter_sealed(df)
    assert n == 3
    assert len(out) == len(df) - 3
    assert not held_out_mask(out).any()


def test_the_window_is_wider_than_the_affair_itself():
    """1978 to 1983 is the affair; the seal covers 1976 to 1985, because a detector tuned on
    the shoulder years is still tuned around the anchor."""
    assert HELD_OUT.years.start < 1978
    assert HELD_OUT.years.stop - 1 > 1983
    assert HELD_OUT.matches("Uzbek SSR", "cotton", 1977) is True
    assert HELD_OUT.matches("Uzbek SSR", "cotton", 1985) is True
    assert HELD_OUT.matches("Uzbek SSR", "cotton", 1975) is False
    assert HELD_OUT.matches("Uzbek SSR", "cotton", 1986) is False


def test_region_and_series_matching_is_forgiving_about_spelling():
    for region in ("Uzbek SSR", "uzbekistan", "Uzbekskaya SSR", "UZBEK"):
        assert HELD_OUT.matches(region, "seed cotton, unginned", 1980) is True
    assert HELD_OUT.matches("Kazakh SSR", "cotton", 1980) is False
    assert HELD_OUT.matches("Uzbek SSR", "wheat", 1980) is False


def test_a_missing_year_never_matches():
    assert HELD_OUT.matches("Uzbek SSR", "cotton", None) is False
    assert HELD_OUT.matches("Uzbek SSR", "cotton", float("nan")) is False


# ---------------------------------------------------------------- refusing to guess


def test_a_frame_that_cannot_be_checked_is_refused_not_waved_through(sealed):
    """The dangerous case: a table with no region column may itself BE the Uzbek series."""
    df = pd.DataFrame({"year": [1980, 1981], "value": [1.0, 2.0]})
    with pytest.raises(SealedError, match="cannot tell whether this frame"):
        held_out_mask(df)
    with pytest.raises(SealedError, match="cannot tell whether this frame"):
        filter_sealed(df)


def test_declare_clean_is_an_assertion_by_the_caller_not_a_bypass(sealed):
    df = pd.DataFrame({"year": [1980, 1981], "value": [1.0, 2.0]})
    out, n = filter_sealed(df, declare_clean=True)
    assert n == 0
    assert len(out) == 2
    # It does not lift the seal for anything else.
    assert is_sealed() is True
    with pytest.raises(SealedError):
        held_out_mask(pd.DataFrame({"year": [1980]}))


# ---------------------------------------------------------------- aggregate vs breakdown


def test_an_aggregate_that_merely_contains_the_anchor_is_allowed(sealed):
    """A union-level total contains the Uzbek figure but does not reveal it."""
    df = panel()
    check_grouping(df, "year")
    check_grouping(df, ["series", "year"])


def test_a_breakdown_that_isolates_the_anchor_is_refused(sealed):
    df = panel()
    with pytest.raises(SealedError, match="would isolate the held-out anchor"):
        check_grouping(df, "region")
    with pytest.raises(SealedError, match="would isolate the held-out anchor"):
        check_grouping(df, ["region", "year"])


def test_grouping_by_region_is_fine_once_the_rows_are_withheld(sealed):
    """The intended workflow: filter first, report the count, then group freely."""
    df, n = filter_sealed(panel())
    assert n == 3
    check_grouping(df, ["region", "year"])


def test_grouping_by_region_is_fine_when_no_held_out_rows_are_present(sealed):
    df = panel()
    df = df[df["region"] == "Kazakh SSR"]
    check_grouping(df, "region")


# ---------------------------------------------------------------- the unsealed path


def test_everything_opens_once_the_seal_is_lifted(unsealed):
    df = panel()
    assert is_sealed() is False
    unseal(UNSEAL_TOKEN)
    out, n = filter_sealed(df)
    assert n == 0
    assert len(out) == len(df)
    check_grouping(df, "region")
    # held_out_mask still IDENTIFIES the anchor rows once unsealed, and must: WO-510 needs it
    # to build the anchor_holdout split. It is filter_sealed that stops withholding them.
    assert held_out_mask(df).sum() == 3


def test_a_wrong_token_still_fails_when_unsealed(unsealed):
    """The token check is about calling the function correctly, not about the seal state."""
    with pytest.raises(SealedError, match="wrong unseal token"):
        unseal("nope")


def test_the_declaration_string_is_what_the_record_must_carry():
    """Pinned so the record cannot be satisfied by an empty or accidental file."""
    assert "G3" in UNSEAL_DECLARATION
    assert "UNSEALED" in UNSEAL_DECLARATION


# ---------------------------------------------------------------- configurability


def test_a_different_held_out_set_can_be_passed_without_touching_the_default(sealed):
    other = HeldOut(series="wheat", region=("kazakh",), years=range(1980, 1982))
    df = panel()
    mask = held_out_mask(df, held_out=other)
    held = df.loc[mask]
    assert set(held["region"]) == {"Kazakh SSR"}
    assert set(held["series"]) == {"wheat"}
    assert set(held["year"]) == {1980}
    # the real seal is unchanged
    assert HELD_OUT.series == "cotton"
