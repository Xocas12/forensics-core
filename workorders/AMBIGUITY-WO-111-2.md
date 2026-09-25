AMBIGUITY REPORT   WO-111   src/forensics_core/power/lookup.py:minimum_detectable_effect

Question (one sentence):
How is a sample size that lies inside the atlas's measured range but was not itself measured
(n = 200 in an atlas measured at 50, 100, 300, ...) answered?

What the spec says / does not say (quote):
"a gosplan card asking about n = 200 when the atlas starts at n = 50 gets an answer, and one
asking about n = 12 gets an exception saying the atlas does not cover it." So n = 200 must get
an answer. The card does not say what the answer is computed from. The existing
`atlas.minimum_detectable_effect` answers only an exactly measured n and raises otherwise, so it
refuses n = 200 too; `DEFAULT_SAMPLE_SIZES` is (50, 100, 300, 1000, ...), so 200 is never
measured by default.

Options considered (A/B/...), and why the spec does not decide:
A. Conservative floor: answer from the largest measured n not above the request (n = 100 for
   n = 200). Relies only on power being non-decreasing in n; never reports a number that was
   not measured, but overstates the minimum detectable effect.
B. Interpolate the power surface between the bracketing measured n (linear in n, or in log n,
   or in sqrt n), then take the smallest measured effect whose interpolated power reaches the
   target. Produces a number that was not measured.
C. Interpolate the minimum detectable effect itself between the two bracketing n.
D. Refuse anything not exactly measured (the current atlas.py behaviour) - contradicts the card.
Each gives a different reported number; B and C also need an interpolation scale nobody chose.
The card's own warning ("Silent extrapolation here would put an unearned number into a claim")
argues for A but does not state it.

Impact if the wrong option is picked:
The minimum detectable effect a gosplan card cites for its sample size changes, and under B/C
the cited number was never measured.

Tests blocked:
The "n = 200 gets an answer" behaviour. As built, an exactly measured n is answered (delegating
to `atlas.minimum_detectable_effect`, including its false-positive-rate check), n below the
smallest or above the largest measured n raises AtlasError (the refusal the card requires), and
an in-range unmeasured n raises NotImplementedError citing this report.
