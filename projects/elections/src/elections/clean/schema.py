"""The 2011/2018 column map, declared explicitly, and the header check that verifies it.

Why a map at all. The two source files do not share a schema: 2011 has 29 columns and 2018
has 24, the absentee-certificate protocol lines exist only in 2011, and the same quantity is
labelled differently between them (the registered-voter line reads "voters entered on the
list" in 2011 and "voters included in the list" in 2018). Stacking them on column names
would silently mis-align; stacking them on position would silently mis-align differently.
So the map is positional **and** checked against the header text, and the columns that exist
in only one election are named in :data:`MISSING_CANONICAL_COLUMNS` rather than being dropped
or quietly filled.

Provenance of the map. Canonical names and the meaning of every index are from
``docs/data_dictionary.md``. The 2018 header was recorded verbatim in ``data/SOURCES.yaml``
(entry ``dkobak_elections_2018``) and is reproduced by the rules below column by column. The
2011 header was recorded there in abbreviated form; its indices 13-18 are pinned to six
absentee-certificate lines because 29 columns minus 3 identifiers, 10 count lines, 2 loss
lines, 7 party lists and 1 URL leaves exactly six, and the data dictionary places eight
administrative lines at indices 13-20. If that arithmetic is wrong the header check fails
loudly on the real file, which is the point of having it.

A recorded conflict about that block. The registry does not agree with the six. Entry
``dkobak_elections_github`` says in so many words "5 absentee-certificate (otkrepitelnye
udostovereniya) lines", while entry ``dkobak_elections_2011`` gives no count at all, saying
only "then all protocol lines including absentee-certificate counts". The arithmetic is
preferred here because the same registry sentence that says five then enumerates 28 named
columns for a file it states has 29, so that listing is one column short of its own total,
whereas six is what the stated column count leaves once every other block is placed. Neither
reading is treated as settled: :func:`verify_header` is the arbiter at load time. It requires
the absentee stem at each of indices 13-18 and the loss line at 19, so if the block really is
five wide, loading the real file raises :class:`SchemaError` naming the indices that
disagreed, and the map is then corrected against the header itself rather than against either
note.

Cyrillic. Sources in this programme are ASCII-only, so the header tokens below are written as
escapes with an ASCII comment giving the transliteration and meaning. They are substrings,
not whole labels, chosen to be unambiguous: ``RU_VALID`` is a substring of ``RU_INVALID``, so
the valid-ballots rule excludes the invalid-ballots token.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

__all__ = [
    "ABSENTEE_COLUMNS",
    "CANDIDATE_COLUMNS_2018",
    "CANONICAL_COLUMNS",
    "COLUMN_POSITIONS",
    "COUNT_COLUMNS",
    "ELECTIONS",
    "ELECTION_DATES",
    "EXPECTED_N_COLUMNS",
    "IDENTIFIER_COLUMNS",
    "MISSING_CANONICAL_COLUMNS",
    "PARTY_COLUMNS_2011",
    "PROTOCOL_COLUMNS",
    "RAW_RELATIVE_PATHS",
    "WINNER_COLUMN",
    "WINNER_LABEL",
    "HeaderRule",
    "SchemaError",
    "canonical_columns_for",
    "column_positions",
    "contestant_columns",
    "verify_header",
]


class SchemaError(ValueError):
    """Raised when a source file does not have the shape the column map assumes."""


# --------------------------------------------------------------------------------------
# elections
# --------------------------------------------------------------------------------------

#: Election keys used everywhere downstream; also the value of the ``election`` column.
ELECTIONS: tuple[str, ...] = ("2011-duma", "2018-presidential")

#: Polling day, ISO-8601. From ``docs/validation_anchors.md``.
ELECTION_DATES: dict[str, str] = {
    "2011-duma": "2011-12-04",
    "2018-presidential": "2018-03-18",
}

#: Column count of each raw CSV, counted from the files during scaffolding.
EXPECTED_N_COLUMNS: dict[str, int] = {"2011-duma": 29, "2018-presidential": 24}

#: Where ``elections.acquire`` puts each raw file, relative to ``data/raw``.
RAW_RELATIVE_PATHS: dict[str, str] = {
    "2011-duma": "dkobak/2011.csv.zip",
    "2018-presidential": "dkobak/2018.csv.zip",
}

# --------------------------------------------------------------------------------------
# canonical names
# --------------------------------------------------------------------------------------

#: Station identifiers. ``uik`` is a bare number: there is no station name in either file.
IDENTIFIER_COLUMNS: tuple[str, ...] = ("region", "tik", "uik")

#: The twelve protocol lines both elections publish, in protocol order.
PROTOCOL_COLUMNS: tuple[str, ...] = (
    "registered",
    "ballots_received",
    "ballots_early",
    "ballots_in_station",
    "ballots_outside",
    "ballots_cancelled",
    "in_mobile_boxes",
    "in_stationary_boxes",
    "invalid",
    "valid",
    "lost_ballots",
    "unaccounted_ballots",
)

#: The six absentee-certificate lines, 2011 only, kept in file order. Six is the column count
#: the arithmetic leaves, against the "5 absentee-certificate lines" of registry entry
#: ``dkobak_elections_github``; the module docstring records that conflict and why the header
#: check, not either note, settles it.
#:
#: They are named by position and not by meaning on purpose. The individual labels were never
#: read verbatim from the 2011 header during scaffolding, only the fact that these columns are
#: the absentee-certificate block, so naming them "issued", "cancelled" and so on would be an
#: assumption dressed as a fact. Confirm each label against the file header before using any
#: one of them on its own; ``elections.clean.loader`` keeps the raw labels in the frame's
#: ``attrs["raw_header"]`` so that confirmation costs nothing.
ABSENTEE_COLUMNS: tuple[str, ...] = tuple(f"abs_line_{i}" for i in range(1, 7))

#: The seven 2011 party lists, in ballot order (``docs/data_dictionary.md``).
PARTY_COLUMNS_2011: tuple[str, ...] = (
    "party_1_spravedlivaya_rossiya",
    "party_2_ldpr",
    "party_3_patrioty_rossii",
    "party_4_kprf",
    "party_5_yabloko",
    "party_6_edinaya_rossiya",
    "party_7_pravoe_delo",
)

#: The eight 2018 candidates, in ballot order. The transliterations are the English column
#: names used by the independent Palladain scrape of the same election (``SOURCES.yaml``).
CANDIDATE_COLUMNS_2018: tuple[str, ...] = (
    "cand_1_baburin",
    "cand_2_grudinin",
    "cand_3_zhirinovsky",
    "cand_4_putin",
    "cand_5_sobchak",
    "cand_6_suraykin",
    "cand_7_titov",
    "cand_8_yavlinsky",
)

#: The contestant of record for each election: the one the published signatures are about.
WINNER_COLUMN: dict[str, str] = {
    "2011-duma": "party_6_edinaya_rossiya",
    "2018-presidential": "cand_4_putin",
}

#: Human-readable label written into the ``winner_label`` column.
WINNER_LABEL: dict[str, str] = {
    "2011-duma": "United Russia",
    "2018-presidential": "Putin",
}

#: Every integer-valued column of the tidy frame.
COUNT_COLUMNS: tuple[str, ...] = (
    "uik",
    *PROTOCOL_COLUMNS,
    *ABSENTEE_COLUMNS,
    *PARTY_COLUMNS_2011,
    *CANDIDATE_COLUMNS_2018,
    "winner_votes",
)

#: The tidy frame's columns, in order. One row per polling station per election. Columns that
#: an election does not have are present and null for that election's rows; which ones those
#: are is stated in :data:`MISSING_CANONICAL_COLUMNS`, not left to be discovered.
CANONICAL_COLUMNS: tuple[str, ...] = (
    "election",
    *IDENTIFIER_COLUMNS,
    *PROTOCOL_COLUMNS,
    *ABSENTEE_COLUMNS,
    *PARTY_COLUMNS_2011,
    *CANDIDATE_COLUMNS_2018,
    "winner_label",
    "winner_votes",
    "source_url",
)

#: Canonical columns that each election does **not** have, and which are therefore null for
#: every row of that election. 2018 abolished the absentee-certificate system, so those six
#: lines have no 2018 counterpart at all; the contestant columns are disjoint by definition.
MISSING_CANONICAL_COLUMNS: dict[str, tuple[str, ...]] = {
    "2011-duma": CANDIDATE_COLUMNS_2018,
    "2018-presidential": (*ABSENTEE_COLUMNS, *PARTY_COLUMNS_2011),
}


def contestant_columns(election: str) -> tuple[str, ...]:
    """Party or candidate vote columns for one election, in ballot order.

    Parameters
    ----------
    election : str
        One of :data:`ELECTIONS`.

    Returns
    -------
    tuple of str
        The seven party columns for 2011, the eight candidate columns for 2018.

    Raises
    ------
    SchemaError
        If ``election`` is not a known election key.
    """
    _require_election(election)
    return PARTY_COLUMNS_2011 if election == "2011-duma" else CANDIDATE_COLUMNS_2018


def canonical_columns_for(election: str) -> tuple[str, ...]:
    """Canonical columns that carry real values for one election.

    Parameters
    ----------
    election : str
        One of :data:`ELECTIONS`.

    Returns
    -------
    tuple of str
        :data:`CANONICAL_COLUMNS` minus the entries of :data:`MISSING_CANONICAL_COLUMNS`.
    """
    _require_election(election)
    missing = set(MISSING_CANONICAL_COLUMNS[election])
    return tuple(c for c in CANONICAL_COLUMNS if c not in missing)


def _require_election(election: str) -> None:
    if election not in ELECTIONS:
        raise SchemaError(f"unknown election {election!r}; expected one of {ELECTIONS}")


# --------------------------------------------------------------------------------------
# the positional map
# --------------------------------------------------------------------------------------


def _positions_2011() -> dict[int, str]:
    pos: dict[int, str] = {0: "region", 1: "tik", 2: "uik"}
    # indices 3-12: the ten count lines shared with 2018
    for offset, name in enumerate(PROTOCOL_COLUMNS[:10]):
        pos[3 + offset] = name
    # indices 13-18: the six absentee-certificate lines
    for offset, name in enumerate(ABSENTEE_COLUMNS):
        pos[13 + offset] = name
    pos[19] = "lost_ballots"
    pos[20] = "unaccounted_ballots"
    for offset, name in enumerate(PARTY_COLUMNS_2011):
        pos[21 + offset] = name
    pos[28] = "source_url"
    return pos


def _positions_2018() -> dict[int, str]:
    pos: dict[int, str] = {0: "region", 1: "tik", 2: "uik"}
    for offset, name in enumerate(PROTOCOL_COLUMNS[:10]):
        pos[3 + offset] = name
    pos[13] = "lost_ballots"
    pos[14] = "unaccounted_ballots"
    for offset, name in enumerate(CANDIDATE_COLUMNS_2018):
        pos[15 + offset] = name
    pos[23] = "source_url"
    return pos


#: ``election -> {zero-based column index in the raw CSV: canonical name}``.
COLUMN_POSITIONS: dict[str, dict[int, str]] = {
    "2011-duma": _positions_2011(),
    "2018-presidential": _positions_2018(),
}


def column_positions(election: str) -> dict[int, str]:
    """The raw-index to canonical-name map for one election.

    Parameters
    ----------
    election : str
        One of :data:`ELECTIONS`.

    Returns
    -------
    dict
        Zero-based column index in the raw CSV mapped to the canonical name.
    """
    _require_election(election)
    return dict(COLUMN_POSITIONS[election])


# --------------------------------------------------------------------------------------
# header tokens (Cyrillic, written as escapes so that this file stays ASCII)
# --------------------------------------------------------------------------------------

# "Chislo izbiratelei" - "number of voters", the opening of protocol line 1 in both files.
RU_VOTERS = "\u0427\u0438\u0441\u043b\u043e \u0438\u0437\u0431\u0438\u0440\u0430\u0442\u0435\u043b\u0435\u0439"
# "poluchennykh" - received (by the station).
RU_RECEIVED = "\u043f\u043e\u043b\u0443\u0447\u0435\u043d\u043d\u044b\u0445"
# "dosrochno" - early voting.
RU_EARLY = "\u0434\u043e\u0441\u0440\u043e\u0447\u043d\u043e"
# "pomeshcheni" - premises; stem shared by the in-premises and away-from-premises lines.
RU_PREMISES = "\u043f\u043e\u043c\u0435\u0449\u0435\u043d\u0438"
# "vne pomeshcheni" - away from the premises.
RU_OUTSIDE = "\u0432\u043d\u0435 \u043f\u043e\u043c\u0435\u0449\u0435\u043d\u0438"
# "pogashennykh" - cancelled (unused).
RU_CANCELLED = "\u043f\u043e\u0433\u0430\u0448\u0435\u043d\u043d\u044b\u0445"
# "perenosnykh" - mobile (ballot boxes).
RU_MOBILE = "\u043f\u0435\u0440\u0435\u043d\u043e\u0441\u043d\u044b\u0445"
# "statsionarnykh" - stationary (ballot boxes).
RU_STATIONARY = "\u0441\u0442\u0430\u0446\u0438\u043e\u043d\u0430\u0440\u043d\u044b\u0445"
# "nedeystvitelnykh" - invalid.
RU_INVALID = "\u043d\u0435\u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0445"
# "deystvitelnykh" - valid. A substring of RU_INVALID, hence the exclusion rule.
RU_VALID = "\u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0445"
# "utrachennykh" - lost.
RU_LOST = "\u0443\u0442\u0440\u0430\u0447\u0435\u043d\u043d\u044b\u0445"
# "ne uchtennykh" - not accounted for (on receipt).
RU_UNACCOUNTED = "\u043d\u0435 \u0443\u0447\u0442\u0435\u043d\u043d\u044b\u0445"
# "otkrepiteln" - stem of "absentee certificate".
RU_ABSENTEE = "\u043e\u0442\u043a\u0440\u0435\u043f\u0438\u0442\u0435\u043b\u044c\u043d"

#: Party-list keywords, 2011, in ballot order: A Just Russia, LDPR, Patriots of Russia, KPRF,
#: Yabloko, United Russia, Right Cause.
RU_PARTIES: tuple[str, ...] = (
    "\u0421\u041f\u0420\u0410\u0412\u0415\u0414\u041b\u0418\u0412\u0410\u042f \u0420\u041e\u0421\u0421\u0418\u042f",
    "\u041b\u0414\u041f\u0420",
    "\u041f\u0410\u0422\u0420\u0418\u041e\u0422\u042b \u0420\u041e\u0421\u0421\u0418\u0418",
    "\u041a\u041f\u0420\u0424",
    "\u042f\u0411\u041b\u041e\u041a\u041e",
    "\u0415\u0414\u0418\u041d\u0410\u042f \u0420\u041e\u0421\u0421\u0418\u042f",
    "\u041f\u0420\u0410\u0412\u041e\u0415 \u0414\u0415\u041b\u041e",
)

#: Candidate surnames, 2018, in ballot order: Baburin, Grudinin, Zhirinovsky, Putin, Sobchak,
#: Suraykin, Titov, Yavlinsky.
RU_CANDIDATES: tuple[str, ...] = (
    "\u0411\u0430\u0431\u0443\u0440\u0438\u043d",
    "\u0413\u0440\u0443\u0434\u0438\u043d\u0438\u043d",
    "\u0416\u0438\u0440\u0438\u043d\u043e\u0432\u0441\u043a\u0438\u0439",
    "\u041f\u0443\u0442\u0438\u043d",
    "\u0421\u043e\u0431\u0447\u0430\u043a",
    "\u0421\u0443\u0440\u0430\u0439\u043a\u0438\u043d",
    "\u0422\u0438\u0442\u043e\u0432",
    "\u042f\u0432\u043b\u0438\u043d\u0441\u043a\u0438\u0439",
)


@dataclass(frozen=True)
class HeaderRule:
    """What one raw column's header must look like for the positional map to be trusted.

    Attributes
    ----------
    canonical : str
        The canonical name this raw column is mapped to.
    equals : str or None
        Exact header text, for the ASCII columns (``region``, ``tik``, ``uik``, ``url``).
    contains : tuple of str
        Substrings that must all be present.
    excludes : tuple of str
        Substrings that must all be absent. Needed where one token is a substring of another.
    """

    canonical: str
    equals: str | None = None
    contains: tuple[str, ...] = ()
    excludes: tuple[str, ...] = field(default=())


def _shared_count_rules() -> dict[int, HeaderRule]:
    """Rules for indices 3-12, which are identical in both files."""
    return {
        3: HeaderRule("registered", contains=(RU_VOTERS,)),
        4: HeaderRule("ballots_received", contains=(RU_RECEIVED,)),
        5: HeaderRule("ballots_early", contains=(RU_EARLY,)),
        6: HeaderRule("ballots_in_station", contains=(RU_PREMISES,), excludes=(RU_OUTSIDE,)),
        7: HeaderRule("ballots_outside", contains=(RU_OUTSIDE,)),
        8: HeaderRule("ballots_cancelled", contains=(RU_CANCELLED,)),
        9: HeaderRule("in_mobile_boxes", contains=(RU_MOBILE,)),
        10: HeaderRule("in_stationary_boxes", contains=(RU_STATIONARY,)),
        11: HeaderRule("invalid", contains=(RU_INVALID,)),
        12: HeaderRule("valid", contains=(RU_VALID,), excludes=(RU_INVALID,)),
    }


def _identifier_rules() -> dict[int, HeaderRule]:
    return {
        0: HeaderRule("region", equals="region"),
        1: HeaderRule("tik", equals="tik"),
        2: HeaderRule("uik", equals="uik"),
    }


def _header_rules_2011() -> dict[int, HeaderRule]:
    rules = {**_identifier_rules(), **_shared_count_rules()}
    for offset, name in enumerate(ABSENTEE_COLUMNS):
        rules[13 + offset] = HeaderRule(name, contains=(RU_ABSENTEE,))
    rules[19] = HeaderRule("lost_ballots", contains=(RU_LOST,), excludes=(RU_ABSENTEE,))
    rules[20] = HeaderRule("unaccounted_ballots", contains=(RU_UNACCOUNTED,))
    for offset, (name, token) in enumerate(zip(PARTY_COLUMNS_2011, RU_PARTIES, strict=True)):
        rules[21 + offset] = HeaderRule(name, contains=(token,))
    rules[28] = HeaderRule("source_url", equals="url")
    return rules


def _header_rules_2018() -> dict[int, HeaderRule]:
    rules = {**_identifier_rules(), **_shared_count_rules()}
    rules[13] = HeaderRule("lost_ballots", contains=(RU_LOST,), excludes=(RU_ABSENTEE,))
    rules[14] = HeaderRule("unaccounted_ballots", contains=(RU_UNACCOUNTED,))
    for offset, (name, token) in enumerate(zip(CANDIDATE_COLUMNS_2018, RU_CANDIDATES, strict=True)):
        rules[15 + offset] = HeaderRule(name, contains=(token,))
    rules[23] = HeaderRule("source_url", equals="url")
    return rules


#: ``election -> {column index: HeaderRule}``, covering every column of the raw file.
HEADER_RULES: dict[str, dict[int, HeaderRule]] = {
    "2011-duma": _header_rules_2011(),
    "2018-presidential": _header_rules_2018(),
}


def verify_header(header: Sequence[str], election: str) -> None:
    """Check a raw CSV header against the positional map, raising on any disagreement.

    This is what stops the positional map from being a guess. It catches the failures the
    arithmetic checks in :mod:`elections.clean.checks` cannot: swapping the mobile and
    stationary ballot-box columns, or the valid and invalid columns, leaves every total and
    the ballot identity untouched while inverting the meaning of the analysis.

    Parameters
    ----------
    header : sequence of str
        The raw header row, in file order.
    election : str
        One of :data:`ELECTIONS`.

    Raises
    ------
    SchemaError
        If the column count is wrong, or if any column's header text fails its rule. The
        message names every failing index with the header text that was actually found, so a
        changed upstream file can be diagnosed without re-reading it by hand.
    """
    _require_election(election)
    expected_n = EXPECTED_N_COLUMNS[election]
    if len(header) != expected_n:
        raise SchemaError(
            f"{election}: expected {expected_n} columns, found {len(header)}. "
            "The column map in elections.clean.schema is positional and cannot be applied "
            "to a file of a different shape."
        )

    problems: list[str] = []
    for index, rule in sorted(HEADER_RULES[election].items()):
        text = str(header[index])
        if rule.equals is not None and text != rule.equals:
            problems.append(
                f"  [{index}] -> {rule.canonical}: expected {rule.equals!r}, found {text!r}"
            )
            continue
        missing = [tok for tok in rule.contains if tok not in text]
        present = [tok for tok in rule.excludes if tok in text]
        if missing or present:
            problems.append(
                f"  [{index}] -> {rule.canonical}: header {text!r} "
                f"is missing {missing!r} / must not contain {present!r}"
            )
    if problems:
        raise SchemaError(
            f"{election}: the raw header does not match the documented column map:\n"
            + "\n".join(problems)
        )
