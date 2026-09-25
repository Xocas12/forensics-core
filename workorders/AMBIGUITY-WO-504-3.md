AMBIGUITY REPORT   WO-504   projects/gosplan/src/gosplan/clean/ (no Maddison loader written)
Question (one sentence):
What unit and price base year does the Maddison 2023 'Full data' gdppc column carry, and is pop in thousands?
What the spec says / does not say (quote):
  Card: "Each loader returns a frame with a units column ..."; "the index-number problem means a growth rate is meaningless without its base year"; hard rule: never assume a unit or base year the registry does not record.
  SOURCES.yaml maddison_mpd2023 notes: "'Full data' has 131,145 rows, columns countrycode,country,region,year,gdppc,pop ... first 1860=1525.30 ... pop ... (year 1 = 3,900 thousand; 2022 = 294,378.63 thousand)". No unit or price base is recorded for gdppc; the pop unit is implied only by the word "thousand" in a value quotation.
Options considered (A/B/...), and why the spec does not decide:
  A. Fill gdppc's unit from general knowledge of the Maddison release - forbidden (not recorded).
  B. Write the loader with gdppc unit blank - produces a monetary real series with no base year, exactly what the card says "produces numbers that cannot be compared to anything"; and the hard rule says the loader for such a source is not written.
  C. Load pop only - a partial loader whose scope the card does not specify.
  D. No loader until the Notes sheet's unit/base statement is recorded in SOURCES.yaml - chosen.
Impact if the wrong option is picked:
  A wrong base year silently changes every Western-vs-official growth comparison (known_traps trap 3).
Tests blocked:
  None frozen. Unblock by recording the gdppc and pop units and price base from the workbook's Notes/Sources sheets in SOURCES.yaml.
