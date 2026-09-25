AMBIGUITY REPORT   WO-504   projects/gosplan/src/gosplan/clean/western_estimates.py:load_hokudai_sess
Question (one sentence):
Which rouble (old or new) and which territorial basis do the Hokkaido SESS series carry, given files spanning 1940-1989?
What the spec says / does not say (quote):
  Card: "Each loader returns a frame with a units column, a territorial-basis column and a currency-basis column where the series is monetary"; "The 1961 redenomination rescales monetary series by an order of magnitude".
  SOURCES.yaml hokudai_sess notes: "header 'CODE NUMBER,FULL NAME,UNIT,SOURCE,1940,...,1989' ... 'Mil. rubles', source 'Narkhoz.' ... note unit label says Mil. but magnitudes are bn rubles"; download_plan: "Also fetch SESS-d.html (linked description page) for codes/units." Nothing records currency or territorial basis.
  gosplan.transcribe.schema.CurrencyBasis: "unstated is not a member of this enumeration: a transcriber who cannot tell must leave the cell blank ... not record a guess."
Options considered (A/B/...), and why the spec does not decide:
  A. Mark monetary SESS series new_roubles (Narkhoz volumes of the 1980s usually restate) - a guess; not recorded.
  B. Leave currency_basis blank on every row and territorial_basis 'unstated' - chosen and implemented, because both follow the project's own vocabulary for "not known" and neither asserts anything; the loader is otherwise fully determined by the registry (header, 0.0 = missing).
  C. Withhold the loader entirely - discards a fully specified loader over a field that can honestly be blank.
Impact if the wrong option is picked:
  A wrong currency basis creates or hides a tenfold break at 1961. With B, downstream code must refuse monetary SESS series until the basis is recorded; the loader makes that visible (blank) rather than silent.
Tests blocked:
  None. test_sess_currency_basis_is_blank_because_the_registry_does_not_record_it pins option B; it should change once SESS-d.html has been read and the bases recorded in SOURCES.yaml.
