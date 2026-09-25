AMBIGUITY REPORT   WO-506   projects/gosplan/docs/GOSPLAN_ENV_COUPLING.md:section 2.1 (Dataset.y), OQ-1
Question (one sentence):
How is the binary label `y` derived from the gap between `reported_quantity` and `true_quantity`: any nonzero gap, over-reporting only, or a relative threshold (and with what floating-point tolerance)?

What the spec says / does not say (quote):
WO-506: "That is a labelled dataset in the harness's own sense, where the label is derived from the gap between reported and true." It names no sign, no threshold and no tolerance. harness.Dataset only fixes the codomain: "1 = confirmed distortion, 0 = presumed clean, NaN = unlabeled". The gosplan-env README/ROADMAP list "hidden reserves and report shaving" (under-reporting) among Claim A phenomena and hold out "hidden reserves and shaving (row 7)" until the Phase-2 acceptance run.

Options considered (A/B/...), and why the spec does not decide:
(A) y = 1 iff reported_quantity != true_quantity (either sign, exact). This matches InjectionRecord.indices semantics ("positions where the returned series differs from the input"), so y == 1 and indices coincide.
(B) y = 1 iff reported_quantity > true_quantity (over-reporting / padding only). Under-reports become 0, so a shaving enterprise counts as "clean".
(C) y = 1 iff |reported - true| / true > tau (or a signed version), for some tau. This ignores trivial gaps, but tau is a free number no whitelisted file gives.
(D) Either of A or B with a float tolerance instead of exact inequality, if the simulator's reported value is computed arithmetically from the true one.
The card fixes the input to the rule (the gap) and not the rule itself. Under B or C, y and InjectionRecord.indices name different rows. Under A, before gosplan-env's G3, the label mixes in a held-out phenomenon.

Impact if the wrong option is picked:
Base rate, every rank metric, every power number and the falsification claim all change. A sign choice also decides whether a held-out gosplan-env phenomenon is measured early.

Tests blocked:
None exist yet. Blocks any library card that builds the frame -> Dataset adapter.
