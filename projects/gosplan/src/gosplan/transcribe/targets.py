"""What to transcribe, in priority order, and how much of it anyone has actually seen.

Every target below names a ``SOURCES.yaml`` id, so a template can never be generated for
material the registry does not record. The field that matters most is
:attr:`TranscriptionTarget.confirmed_present`: it is True only where the scaffolding session
opened the volume and saw the table. Everywhere else the first task is to find the table,
and the estimate of how much work the target is worth is a guess until someone does.

Priority is ordered by what the research question needs first, not by what is easiest:

1. the anchor's own physical series, in the volume where a cotton table was actually seen;
2. the same series across the padding decade, which is what a detector would be run on;
3. the republic-level volume that covers the anchor -- which nobody has a copy of;
4. plan fulfilment percentages, without which the bunching question cannot be asked at all;
5. the national-income identity, which is the reconciliation test;
6. value output by branch, which is the hidden-inflation test's numerator;
7. the physical output series that are its denominator;
8. an input-output table, which is print-only for every post-war year.

Targets 4 and 8 are the two where the project might simply find that the printed source does
not exist in an accessible form. Recording that would be a result about feasibility, and it
belongs in the README rather than being quietly dropped.
"""

from __future__ import annotations

from dataclasses import dataclass

from gosplan.transcribe.schema import CurrencyBasis, TerritorialBasis

__all__ = ["TARGETS", "TranscriptionTarget", "target_by_id"]


@dataclass(frozen=True)
class TranscriptionTarget:
    """One printed table (or family of tables) queued for manual transcription.

    Attributes
    ----------
    target_id : str
        Stable slug; also the template filename.
    source_id : str
        ``SOURCES.yaml`` id of the scan or catalogue record it comes from.
    priority : int
        1 is highest. Ordering rationale is in the module docstring.
    title_translit : str
        Working description of the table in ASCII. The Russian heading is deliberately not
        stored here: it must be copied off the page into ``title_ru`` by the transcriber, not
        supplied from memory by a program.
    why : str
        Which sub-question of ``docs/research_question.md`` this table serves.
    locator : str
        Everything known about where the table is: edition, chapter, page if known.
    expected_unit : str
        The unit the table is expected to use, as a prompt to check against the page. Never
        written into a template: a hint that turns into data is how a units error happens.
    expected_currency_basis : CurrencyBasis
        Same status as ``expected_unit``: a prompt, not a default.
    expected_territorial_basis : TerritorialBasis
        Same again.
    confirmed_present : bool
        True only when someone opened the volume and saw this table.
    cross_check_source_id : str or None
        A machine-readable source covering the same series, to be used as the independent
        second transcription in :mod:`gosplan.transcribe.compare` where one exists.
    notes : str
        Anything else the transcriber needs before starting.
    """

    target_id: str
    source_id: str
    priority: int
    title_translit: str
    why: str
    locator: str
    expected_unit: str
    expected_currency_basis: CurrencyBasis
    expected_territorial_basis: TerritorialBasis
    confirmed_present: bool
    cross_check_source_id: str | None = None
    notes: str = ""


TARGETS: tuple[TranscriptionTarget, ...] = (
    TranscriptionTarget(
        target_id="narkhoz_1985_raw_cotton",
        source_id="ia_narkhoz_1985_item",
        priority=1,
        title_translit="Raw cotton (khlopok-syrets), state and collective farm shares, 1940-1985",
        why=(
            "The anchor's physical series, in the one volume whose contents were actually "
            "inspected. It is the pipeline's worked example and the first table on which the "
            "double-transcription disagreement rate should be measured."
        ),
        locator=(
            "Narodnoe khoziaistvo SSSR v 1985 g., archive.org item "
            "narodnoe-khoziaistvo-sssr_1985; the table was found in the item's text layer, "
            "page not yet resolved -- use the _page_numbers.json sidecar to fix it"
        ),
        expected_unit="thousand tonnes (confirm against the table's own column head)",
        expected_currency_basis=CurrencyBasis.NOT_MONETARY,
        expected_territorial_basis=TerritorialBasis.PRESENT_BOUNDARIES,
        confirmed_present=True,
        cross_check_source_id="faostat_qcl_bulk_europe_ussr",
        notes=(
            "The union total can be checked against FAOSTAT seed cotton for the same years "
            "(area 228, item 328, element 5510), which is an independent series rather than "
            "a second reading of the same page. A disagreement there is a finding about the "
            "sources; a disagreement between two transcriptions of this page is an error rate."
        ),
    ),
    TranscriptionTarget(
        target_id="narkhoz_raw_cotton_1975_1989",
        source_id="ia_narkhoz_collection",
        priority=2,
        title_translit="Raw cotton output, annual volumes covering the padding decade",
        why=(
            "Sub-question 2 and the anchor window. One year is an example; the series is what "
            "a detector is run on, and successive editions restate earlier years, which is "
            "itself evidence: a figure that changes between editions was revised, and by whom "
            "and when is recoverable."
        ),
        locator=(
            "archive.org collection pub_narodnoe-khoziaistvo-sssr. The collection holds 28 "
            "volumes and lacks 1976 and 1981, both inside the window; publ.lib.ru and "
            "istmat.org are the fallbacks for missing years."
        ),
        expected_unit="thousand tonnes (confirm per edition)",
        expected_currency_basis=CurrencyBasis.NOT_MONETARY,
        expected_territorial_basis=TerritorialBasis.PRESENT_BOUNDARIES,
        confirmed_present=False,
        cross_check_source_id="faostat_qcl_bulk_europe_ussr",
        notes=(
            "Transcribe the same year from two editions wherever both exist. Restatement "
            "between editions must be recorded in definition_note, never silently overwritten."
        ),
    ),
    TranscriptionTarget(
        target_id="uzbek_ssr_annual_cotton",
        source_id="rusneb_uzbek_annual",
        priority=3,
        title_translit="Narodnoe khoziaistvo Uzbekskoi SSR: cotton output and procurement",
        why=(
            "The anchor is a republic-level event and this is the republic-level source. "
            "Union totals dilute a republic's padding by whatever the other republics did."
        ),
        locator=(
            "No digitised copy has been located that anyone can open. The 1957 edition is "
            "catalogued at rusneb.ru, which returns 403 to non-Russian egress; istmat.org "
            "lists six editions of which only 1988 and 1990 fall near the window."
        ),
        expected_unit="thousand tonnes (unconfirmed)",
        expected_currency_basis=CurrencyBasis.NOT_MONETARY,
        expected_territorial_basis=TerritorialBasis.PRESENT_BOUNDARIES,
        confirmed_present=False,
        cross_check_source_id="usda_psd_cotton_bulk",
        notes=(
            "This is the project's weakest link and it is blocked on a person, not on code. "
            "Until a copy exists, republic-level work rests on whatever the union volumes "
            "print by republic, which is less than the republic annual would give."
        ),
    ),
    TranscriptionTarget(
        target_id="narkhoz_plan_fulfilment",
        source_id="ia_narkhoz_collection",
        priority=4,
        title_translit="Plan fulfilment percentages by branch or ministry",
        why=(
            "Sub-question 3: bunching at 100 percent, the bonus threshold. Without a printed "
            "distribution of fulfilment percentages there is nothing to test for a notch."
        ),
        locator=(
            "Not located. Whether the annuals print a fulfilment distribution at a unit level "
            "fine enough to bin, rather than a handful of aggregate percentages, is unknown "
            "and is the first thing to establish."
        ),
        expected_unit="percent of plan",
        expected_currency_basis=CurrencyBasis.NOT_MONETARY,
        expected_territorial_basis=TerritorialBasis.PRESENT_BOUNDARIES,
        confirmed_present=False,
        notes=(
            "A dozen aggregate percentages cannot support a bunching estimator. If that is "
            "all the annuals print, the honest conclusion is that this sub-question needs "
            "enterprise-level records from RGAE, which cannot be obtained remotely."
        ),
    ),
    TranscriptionTarget(
        target_id="narkhoz_national_income_produced_and_used",
        source_id="ia_narkhoz_collection",
        priority=5,
        title_translit="National income produced and national income used, by component",
        why=(
            "Sub-question 1: the two presentations must reconcile to each other through "
            "losses and the foreign balance, which makes this the natural first test of "
            "forensics_core.reconcile on official Soviet figures."
        ),
        locator="Chapter on general economic indicators in each annual; page varies by edition.",
        expected_unit="million or billion roubles (the annuals vary; read the column head)",
        expected_currency_basis=CurrencyBasis.NEW_ROUBLES,
        expected_territorial_basis=TerritorialBasis.PRESENT_BOUNDARIES,
        confirmed_present=False,
        cross_check_source_id="hokudai_sess",
        notes=(
            "The Hokkaido SRC sections 121 (national income produced, 18 files) and 122 "
            "(national income used, 13 files) are a machine-readable transcription of the "
            "same Narkhoz series and should be treated as an independent second "
            "transcription. Read the file names off SESS.html rather than constructing them: "
            "the registry recorded the section codes and counts, and the only file actually "
            "fetched during scaffolding was S111.csv. Two caveats from the registry: missing "
            "values are coded 0.0, and at least one series' unit label disagrees with its "
            "magnitudes."
        ),
    ),
    TranscriptionTarget(
        target_id="narkhoz_gross_output_by_branch",
        source_id="ia_narkhoz_collection",
        priority=6,
        title_translit="Gross output of industry by branch, in value terms",
        why=(
            "Sub-question 2, the numerator of the hidden-inflation comparison: value "
            "aggregates that should be underpinned by the physical series in target 7."
        ),
        locator="Industry chapter of each annual.",
        expected_unit="million or billion roubles at stated prices",
        expected_currency_basis=CurrencyBasis.NEW_ROUBLES,
        expected_territorial_basis=TerritorialBasis.PRESENT_BOUNDARIES,
        confirmed_present=False,
        notes=(
            "Three things must be copied, not inferred: the price base year, whether the "
            "figure is gross, net or normative-net output, and whether pre-1961 years are "
            "restated in new roubles. All three go in definition_note and currency_basis."
        ),
    ),
    TranscriptionTarget(
        target_id="narkhoz_physical_output_selected",
        source_id="ia_narkhoz_collection",
        priority=7,
        title_translit="Physical output of selected products (steel, coal, cement, grain, cotton)",
        why=(
            "The denominator of the hidden-inflation comparison and the input to the "
            "underdispersion test in sub-question 4."
        ),
        locator="Industry and agriculture chapters of each annual.",
        expected_unit="tonnes, thousand tonnes or million tonnes, per product",
        expected_currency_basis=CurrencyBasis.NOT_MONETARY,
        expected_territorial_basis=TerritorialBasis.PRESENT_BOUNDARIES,
        confirmed_present=False,
        notes=(
            "Physical series were plan targets too and were padded (known_traps trap 7), so "
            "these are not a clean control. They are the other half of a comparison, not "
            "truth."
        ),
    ),
    TranscriptionTarget(
        target_id="soviet_input_output_table",
        source_id="hathitrust_ge_tempo_1966_io",
        priority=8,
        title_translit="Soviet input-output table, 1966 or 1972, in adjusted factor cost values",
        why=(
            "Sub-question 1's strongest form: an input-output table is a set of accounting "
            "identities dense enough for gross-error detection to localise which nodes need "
            "the largest corrections."
        ),
        locator=(
            "Print only. The GE-TEMPO transformation of the 1966 table is search-only in "
            "HathiTrust; the Treml volumes are library material. No machine-readable "
            "post-war Soviet I-O table was found on Harvard Dataverse, Zenodo or GitHub."
        ),
        expected_unit="million roubles at adjusted factor cost",
        expected_currency_basis=CurrencyBasis.NEW_ROUBLES,
        expected_territorial_basis=TerritorialBasis.PRESENT_BOUNDARIES,
        confirmed_present=False,
        cross_check_source_id="harrison_ussr_ww2",
        notes=(
            "Blocked on a library visit or an interlibrary loan. Harrison's 1940-1945 "
            "matrices are machine-readable and are the only I-O material available now: use "
            "them to exercise the reconciliation code, and do not present a wartime result "
            "as a statement about the 1960s or 1970s."
        ),
    ),
)


def target_by_id(target_id: str) -> TranscriptionTarget:
    """Look up one target by its slug.

    Raises
    ------
    KeyError
        If no target has that id, with the known ids in the message.
    """
    for t in TARGETS:
        if t.target_id == target_id:
            return t
    known = ", ".join(t.target_id for t in TARGETS)
    raise KeyError(f"unknown transcription target {target_id!r}; known targets: {known}")
