AMBIGUITY REPORT   WO-506   projects/gosplan/docs/GOSPLAN_ENV_COUPLING.md:section 1 (grain, true_quantity, notch), OQ-5
Question (one sentence):
Is one scalar per enterprise per period the simulator's reporting grain, what exactly does `true_quantity` measure, and is the bonus notch defined on `reported_quantity / plan_target`?

What the spec says / does not say (quote):
WO-506: "A tidy frame of enterprise by period with the reported quantity, the true quantity, the plan target, and the audit indicator." The whitelisted gosplan-env documents mention sectors ("2-enterprise, 2-sector" worked example), a quality mechanism (WO-021), `report_ratio` bounded at rho_max = 10, and a bonus B(rho). They do not define rho, the reporting grain, or what "true" means per period (output produced, quality-adjusted output, or something else). The simulator's PLAN and spec/ are not on this card's whitelist, and every body there is a stub.

Options considered (A/B/...), and why the spec does not decide:
Grain: (A) enterprise x period, scalar; (B) enterprise x sector x period; (C) enterprise x period with separate quantity and quality columns.
True quantity: (i) physical output produced in the period; (ii) quality-adjusted output; (iii) other.
Notch units: (a) the notch sits on reported/target; (b) it sits on another ratio (for example the undefined report_ratio).
Only the simulator's own specification can answer these. This card may not read it, and must not invent it.

Impact if the wrong option is picked:
Column set, row count (n), the running variable of every bunching estimator and the label all change.

Tests blocked:
None yet. Section 1 is written as a requirement; if gosplan-env cannot meet it, the grain question returns to the lead.
