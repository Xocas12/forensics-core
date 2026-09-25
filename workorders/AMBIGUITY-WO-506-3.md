AMBIGUITY REPORT   WO-506   projects/gosplan/docs/GOSPLAN_ENV_COUPLING.md:sections 2.2-2.3 (effect_size, power curve), OQ-3
Question (one sentence):
What scalar is `InjectionRecord.effect_size` (and the x-axis of the simulated power curve), which simulated runs count as the zero-distortion arm, and is `power.atlas.power_curve` reused or is a separate entry point needed?

What the spec says / does not say (quote):
WO-506: "A power curve on realistic data" and "the same code path as an injected one". inject.InjectionRecord: "effect_size : float  The injector's effect-size argument, verbatim". atlas.power_curve: "injector(sample, effect_size, rng) -> sample ... At effect size zero it must be a no-op", and it draws from a clean population. The simulator has no single effect-size argument: its knobs are configuration parameters (for example audit rate and penalty), and its distortion is chosen by learning agents.

Options considered (A/B/...), and why the spec does not decide:
(A) effect_size = a realised statistic of the gap (share of rows with a gap, mean relative gap, ...). Each candidate statistic gives a different curve.
(B) effect_size = a configured incentive parameter of the run (for example a*pen). This is not in distortion units and not comparable with the injected mechanisms.
Zero arm: (i) runs whose realised gap is zero everywhere; (ii) runs under a configuration or agent that should not distort (for example a truthful heuristic agent); (iii) the same runs with reported replaced by true.
Atlas route: (a) adapt the simulated runs to power_curve's (population, injector) signature, which may not be possible because a run arrives already distorted; (b) a new library function emitting ATLAS_COLUMNS from (Dataset, InjectionRecord) pairs.
None of these is given by the card or by the whitelisted files.

Impact if the wrong option is picked:
The power curve's x-axis, the false-positive row and every minimum detectable effect read off the curve all change. Rule-9 controls depend on the zero-arm definition.

Tests blocked:
None yet. Blocks the adapter card and any simulated-atlas card.
