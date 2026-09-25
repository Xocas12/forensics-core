AMBIGUITY REPORT   WO-111   src/forensics_core/power/lookup.py:minimum_detectable_effect, detectable

Question (one sentence):
What does the `aggregation` argument select in a stored atlas, and what values besides "unit"
does it take?

What the spec says / does not say (quote):
The card's signatures carry `aggregation="unit"` and nothing else about it. The atlas format
(`ATLAS_COLUMNS` in atlas.py: method, n, effect_size, power, power_se, n_replicates, alpha,
false_positive_rate) has no aggregation dimension. `aggregation.aggregation_ladder` produces a
different table (`LADDER_COLUMNS`: level, semantics, effect_size, n_units, mean_group_size, ...)
whose level names are chosen by the caller and whose second axis is the semantics
("sum_then_ratio" / "mean_of_ratios"), not n. The string "unit" is not a defined value anywhere
in the whitelist.

Options considered (A/B/...), and why the spec does not decide:
A. Add an `aggregation` column to the frozen atlas format (a power curve per aggregation level),
   with "unit" meaning the ungrouped power_curve output. Needs a rule for how a ladder level
   becomes a power-vs-n curve, and a place for the semantics.
B. Make `aggregation` a string of the form "<level>/<semantics>" matched against ladder tables
   stored alongside atlases.
C. Only "unit" is supported for now; everything else refuses.
The choice changes the frozen format that other repositories cite.

Impact if the wrong option is picked:
The frozen format would need a breaking change later, or an aggregated query would silently be
answered from unit-level power, which aggregation.py measures to be far higher than aggregated
power for integer-percentage tests.

Tests blocked:
None. As built, aggregation="unit" is answered from the atlas rows (which power_curve measures
without aggregation) and any other value raises NotImplementedError citing this report.
