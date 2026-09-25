# Test fixtures

Everything here is synthetic. No row, name or total corresponds to a real polling station,
and none of it came from the acquired data. The real files are not in this repository and are
never used by the test suite.

## `synthetic_2011_duma.csv`, `synthetic_2018_presidential.csv`

Six rows each, shaped like the raw files the loader reads: 29 columns for 2011 and 24 for
2018, in the documented order, so that `elections.clean.schema.verify_header` and the
positional column map are exercised end to end.

Two deliberate departures from the real files:

- **Region and commission names are obviously fake** (`Testonia`, `Faketown Republic`,
  `Nowhere Krai`, `1 Alpha`) and the source URLs use the reserved `.invalid` domain.
- **Header labels are synthetic strings**, of the form `SYN<index> <token>`, carrying only
  the substring that `schema.HEADER_RULES` checks for that column. The real Russian protocol
  labels were not transcribed into this repository: only some of them are quoted verbatim in
  `data/SOURCES.yaml`, so writing out the rest would be inventing source text. What the
  fixtures test is therefore the rule mechanism, not the exact wording of a real header.

The numbers are small and chosen so that expected values can be worked out by hand:

- the ballot identity `invalid + valid == in_mobile_boxes + in_stationary_boxes` holds on
  every row of both files;
- registered voters sum to 3,850 (2011) and 3,680 (2018);
- the winner's votes sum to 1,095 (2011, index 26) and 1,080 (2018, index 18);
- turnout on the ballots-in-boxes basis is exactly 0.70, 0.60, 0.50, undefined, 0.50, 0.60 in
  2011, and on the ballots-issued basis 0.72 in the first row, so the two definitions can be
  told apart;
- one row in each file has zero registered voters, which is the division guard;
- sizes span the documented bands, including two 2011 stations below the 100-voter floor.

Because the row counts and totals are tiny, the tests that exercise the *passing* branch of
`elections.clean.checks` monkeypatch the anchor constants to the fixture's own values. The
anchors themselves (95,225 rows, 109,229,337 registered voters, and so on) are asserted as
constants, and their violation is tested against the unpatched values.
