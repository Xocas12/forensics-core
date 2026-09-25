AMBIGUITY REPORT   WO-504   projects/gosplan/src/gosplan/clean/ (no plan-fraud loader written)
Question (one sentence):
What is the full header (and header row) of each sheet of harrison_plan_fraud dataset.xlsx, which column (if any) gives the year of each case, and what should the units / basis columns mean for a case index with no numeric series?
What the spec says / does not say (quote):
  SOURCES.yaml harrison_plan_fraud evidence: "three sheets named 'Fond R-9492 Case Index', 'Fond R-8131 Case Index', 'Fond 6 Case Index'. Column headers include Establishment, Accused, #Accused, Where, Branch." ("include" - not the full list; header row position not recorded.)
  Card: "Each loader returns a frame with a units column, a territorial-basis column ...". Seal (gosplan.seal.held_out_mask): a frame without region/series/year columns is refused while sealed unless the caller asserts declare_clean=True, which "using ... on a frame that does contain the anchor is a CONTRACT rule 5 violation".
Options considered (A/B/...), and why the spec does not decide:
  A. Load with header=first row and pass declare_clean=True on the strength of the paper's title period (1943-1962) - the header row is assumed and declare_clean is an assertion about content the registry does not verify (the file includes Uzbek agricultural cases).
  B. Locate the header row by the five recorded names and load all columns, units column = blank - loads free-text quantities ("Reported 515 instead of 315 tons") with no unit, and still cannot route through the seal without A's assertion.
  C. No loader until the full header, a year column and the intended treatment are recorded - chosen.
Impact if the wrong option is picked:
  An unverified declare_clean on a file containing Uzbek agricultural fraud cases is the exact route to the anchor that rule 5 forbids; an assumed header row mislabels the project's only second labelled source.
Tests blocked:
  None frozen. Unblock by recording the full header and header row of each sheet (and which column carries the case year) in SOURCES.yaml, and by the lead stating whether this case index belongs in gosplan.clean at all or in a separate labels module.
