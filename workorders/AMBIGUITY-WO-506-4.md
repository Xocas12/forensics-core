AMBIGUITY REPORT   WO-506   projects/gosplan/docs/GOSPLAN_ENV_COUPLING.md:section 2.1 (Dataset.X), OQ-4
Question (one sentence):
May the audit indicator `audited` be a feature in `Dataset.X`, or is it carried only as metadata?

What the spec says / does not say (quote):
WO-506 lists "the audit indicator" among the emitted columns but says nothing about whether detectors may see it. gosplan-env CONTRACT rule 5 keeps true quantities from the planner, but audit outcomes are not said to be observable in the historical archives either way.

Options considered (A/B/...), and why the spec does not decide:
(A) X = [reported_quantity, plan_target, audited]. A detector can use audit status, which is realistic only if archives record audits.
(B) X = [reported_quantity, plan_target], with audited kept outside X (as a column for conditioning or stratification by the consuming card).
The deciding fact is whether a Soviet archival series carries an audit indicator per enterprise-period. No whitelisted file says.

Impact if the wrong option is picked:
Under A, a supervised detector may partly learn "audited rows are the ones caught" and look stronger on simulated data than it can be on archives. That directly inflates the robustness claim this coupling exists to make honest.

Tests blocked:
None yet. Blocks the adapter card.
