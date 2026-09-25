AMBIGUITY REPORT   WO-504   projects/gosplan/src/gosplan/clean/ (no loaders for legacy formats)
Question (one sentence):
May a reader for legacy spreadsheet/series formats (xlrd for BIFF .xls; a Lotus .WK1 and MicroTSP .DB reader, or LibreOffice headless) be added to the gosplan dependencies, or should conversion be an external documented step?
What the spec says / does not say (quote):
  Card: "One of the workbook sources is in a legacy spreadsheet format the modern reader cannot open, and another archive holds files in formats from the same era. Record honestly which loaded and which need a converter."
  Write list excludes projects/gosplan/pyproject.toml; dependencies are pandas, openpyxl, ... - no xlrd (confirmed: `import xlrd` fails in the workspace venv).
  SOURCES.yaml harrison_sovietgrowth: "Excel 97-2003 BIFF8 ... Needs xlrd or LibreOffice to parse (old .xls)."
  harrison_ussr_ww2: "Old BIFF format (Version 1.0 header, codepage -535) - use xlrd/LibreOffice."
  wb_soviet_economic_decline: "Parse USSR.WK1 (Lotus 1-2-3) with python `lotus123`/`wk1` readers or LibreOffice; .DB files are MicroTSP".
Options considered (A/B/...), and why the spec does not decide:
  A. Add xlrd (and a WK1 reader) to pyproject - outside the write list; a dependency decision for the lead.
  B. Convert externally (LibreOffice headless -> CSV/xlsx) and load the converted file - the converted layout's sheet names/headers would then need recording in SOURCES.yaml; none are recorded today (ussr_ww2 has no sheet names recorded; sovietgrowth has the sheet name 'Appendix A. Basic data' but no headers; the WB .DB/.WK1 series have names but no units or bases).
  C. Write a hand-rolled BIFF/WK1 parser - large, error-prone, and still blocked by the unrecorded headers.
  Chosen: no loader; documented as "needs a converter" in docs/data_dictionary.md and gosplan.clean.UNLOADED.
Impact if the wrong option is picked:
  A dependency added without the lead's decision changes the environment for every project in the workspace; a guessed header layout after conversion would mislabel GNP/NMP series whose price bases (1937 prices, factor cost, post-1961 roubles) are the whole point of the index-number and redenomination traps.
Tests blocked:
  None frozen. Unblock by deciding A or B, then recording sheet names, header rows, units and price bases for harrison_sovietgrowth, harrison_ussr_ww2 (six workbooks) and wb_soviet_economic_decline in SOURCES.yaml.
