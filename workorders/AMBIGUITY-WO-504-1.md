AMBIGUITY REPORT   WO-504   projects/gosplan/src/gosplan/clean/ (no FAOSTAT loader written)
Question (one sentence):
What are the exact column names of the FAOSTAT QCL wide CSV (Production_Crops_Livestock_E_<Region>.csv) for the unit, the area/item/element names and the flag, and what is its encoding?
What the spec says / does not say (quote):
  Card: "Assuming a column name the registry does not record" is forbidden; "the tests assert the column names recorded in the registry rather than assumed ones".
  SOURCES.yaml faostat_qcl_bulk_europe_ussr download_plan: "read Production_Crops_Livestock_E_<Region>.csv (latin-1/UTF-8, wide format). Filter Area Code==228 ... Item Code 328 ... Element Code 5510 (Production, t) ... Keep the F flag column (A=official, X=unofficial, E=estimate)."
  Notes record one row positionally ("228","'810","USSR","328","'01921.01","Seed cotton, unginned","5510","Production","t", Y1961=4518000 (flag A)) but give no header for the M49 code, area name, CPC code, item name, element name, unit, or flag columns.
  docs/data_dictionary.md and gosplan.acquire.agriculture both say the flag column must survive into any derived table.
Options considered (A/B/...), and why the spec does not decide:
  A. Use FAOSTAT's conventional names (Area, Item, Element, Unit, Y1961F, ...) from memory - forbidden (not recorded).
  B. Read positionally using the quoted row - the order of the leading fields is quoted but the position/name of the flag columns among the Y-columns is not, and a loader that drops the flag violates the registry's own instruction.
  C. Load only Area Code / Item Code / Element Code / Y#### and derive unit from "Element Code 5510 (Production, t)" - drops the flag and cannot give units for 5312/5419, which the plan also names.
  D. Write no loader until the header (and encoding) is recorded - chosen.
  Encoding "latin-1/UTF-8" also leaves the decoding choice open.
Impact if the wrong option is picked:
  A silently mis-named or dropped flag column erases the official (A) vs unofficial (X) distinction the registry records for USSR seed cotton vs lint; a wrong encoding corrupts area/item names.
Tests blocked:
  None frozen; test_clean_loaders.py has no FAOSTAT test. Unblock by recording the full header line of the Europe and Asia CSVs and their encoding in SOURCES.yaml (one inspection of the downloaded file).
