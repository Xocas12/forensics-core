AMBIGUITY REPORT   WO-505   projects/gosplan/src/gosplan/clean/prosecutions.py (no loader written)
Question (one sentence):
Can a Harrison plan-fraud case be linked to any reported series the project holds, and if it can, which columns carry the case year, the region, the branch, and the reported and actual quantities (with units)? A loader cannot be written until that is known.
What the spec says / does not say (quote):
  Card: "If cases cannot be linked to a series, the dataset is context and not labels, and the card should say so and stop there." "Only if it survives that assessment does it become a positive-unlabelled label set." Must pass: "The loader produces case-level rows with the reported and actual quantities where the source records both".
  SOURCES.yaml harrison_plan_fraud evidence: "Column headers include Establishment, Accused, #Accused, Where, Branch." It names no year column and no reported or actual column, and does not record the header row. The sample quantities are prose inside a cell: "Reported 515 instead of 315 tons", "Overstated ploughing by 93 hectares", "Bonuses for the artel, 8,847 rubles". verification.verdict: not_verified; local_path: null.
  AMBIGUITY-WO-504-4 (unresolved) asks for the same headers and the same year column.
Options considered (A/B/...), and why the spec does not decide:
  A. A loader that takes the column mapping (sheet, header row, year/Where/Branch/reported/actual/unit) as a required argument, validates that it is present, emits s=1 only and routes through filter_sealed. Rejected. The evidence points to quantities in prose, not separate reported and actual columns, so the loader would be written for a file shape the registry gives reason to doubt. It would also fix public behaviour the card leaves open: output column names; what happens to rows with one quantity or none, since the third sample row has neither; and whether a quantity parsed from prose counts as "recorded". Above all, it would build a label set before linkability, the card's precondition, is established.
  B. Parse reported and actual quantities from the prose, using a pattern like "Reported X instead of Y <unit>". Rejected. The parsing rules and the direction of the quantities would be invented from three sample rows.
  C. No loader. PROSECUTION_LABELS.md states that linkability is undetermined, and the dataset is treated as context until the file is read. Chosen.
Impact if the wrong option is picked:
  A label set built on unverified linkage, or on invented parsing, would be the project's only second labelled source. It would sit beside a seal that can only be bypassed with declare_clean=True, on a file the registry says includes Uzbek agricultural cases.
Tests blocked:
  None frozen. projects/gosplan/tests/test_prosecutions.py is not written, because there is no loader for it to test. The card's completion command therefore finds no file to run.
  To unblock:
  (1) Acquire the file and check its sha256 against the registry.
  (2) Record in SOURCES.yaml the full header row, and its position, for each of the three sheets.
  (3) Record whether any column gives the year of the offence or the case.
  (4) Record whether reported and actual quantities are separate numeric columns, with units, or prose only.
  (5) Record the distinct values of Where and Branch, set against the region, sector and year keys of the series the project holds for 1943-1962.
  (6) The lead decides whether a case-level label set belongs in gosplan.clean or in a separate labels module (the open question in WO-504-4).
  (7) The lead decides whether Uzbek agricultural cases from 1943-1962 may be used to shape a detector that is later tested on the anchor. They are outside the seal's years, so the seal does not cover them, but the question is about the independence of the anchor test.
