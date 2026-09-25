AMBIGUITY REPORT   WO-506   projects/gosplan/docs/GOSPLAN_ENV_COUPLING.md:section 2.2 (InjectionRecord.seed), OQ-2
Question (one sentence):
Which of a gosplan-env run's seeds goes into `InjectionRecord.seed`, which holds a single `int | None`?

What the spec says / does not say (quote):
gosplan-env CONTRACT rule 9: "All environment randomness goes through rng.draw(seed_env, purpose, *indices) ... seed_policy is separate." Rule 10: the manifest records "seeds" (plural). inject.InjectionRecord: "seed : int | None  The seed the injection ran with". WO-506 says to reuse the injection contract and does not address this.

Options considered (A/B/...), and why the spec does not decide:
(A) seed = seed_env. The environment randomness (audit draws and so on) reproduces, but the learned policy that produced the reports does not.
(B) seed = seed_policy.
(C) seed = None, with both seeds carried only in Dataset.meta. This loses the record's own reproducibility answer.
(D) Widen InjectionRecord to hold several seeds. That changes a library public type, which this card may not do.
Nothing whitelisted says which seed "the injection ran with" when the distortion is produced by a learned policy acting in a seeded environment.

Impact if the wrong option is picked:
A stored record claims a reproducibility it does not have. Two records that should differ can compare equal, or the reverse; equality excludes the seed, but provenance audits rely on it.

Tests blocked:
None yet. Blocks the adapter card.
