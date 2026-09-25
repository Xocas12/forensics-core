AMBIGUITY REPORT   WO-506   projects/gosplan/docs/GOSPLAN_ENV_COUPLING.md:sections 2-3 (ground truth reference), OQ-6
Question (one sentence):
Is estimator recovery scored against the same-run true quantity, or against the DP's no-manipulation counterfactual that gosplan-env's estimator-bias study uses?

What the spec says / does not say (quote):
WO-506: "the label is derived from the gap between reported and true." gosplan-env ROADMAP section 7: "Estimator-bias curves from WO-034, scored against the DP's exact no-manipulation counterfactual." The card and the sibling name different references, and neither says how they relate.

Options considered (A/B/...), and why the spec does not decide:
(A) Same-run truth: the gap reported - true in the run that produced the reports. The Dataset/InjectionRecord mapping in section 2 assumes this.
(B) The DP counterfactual: what the distribution would have been with no manipulation incentive. This is what a bunching estimator's counterfactual density targets.
(C) Both, as separate reported numbers.
A bunching estimator's "excess mass" is defined relative to a counterfactual distribution, not relative to a per-row truth. The two references measure different things, and the card does not say which one "recovers a distortion that was really there" refers to.

Impact if the wrong option is picked:
The reported bias of every bunching estimator changes. Worse, a recovered-or-missed verdict can flip, and the falsification claim of section 3 could be made against the wrong reference.

Tests blocked:
None yet.
