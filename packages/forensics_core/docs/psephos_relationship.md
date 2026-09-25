# psephos and forensics_core

How this library relates to [`psephos`](https://github.com/Xocas12/psephos), the
election anomaly tool that implements two of the same method families, and what keeps the
two from drifting apart. Written for WO-112.

**Status: a recommendation for the lead to confirm.** WO-112 is an Owner LEAD card. The
option below is argued from the evidence, but it is not decided until the lead signs off.
One part of the implementation, how the parity test reaches psephos in CI, is open and has
its own ambiguity report, `workorders/AMBIGUITY-WO-112-1.md`.

This document contains no results. The only numbers in it are defaults and formulas read
from the two codebases.

What was read: in this library, `src/forensics_core/digits/integer_pct.py`,
`src/forensics_core/digits/terminal.py`, `INTERFACES.md` and `docs/method_transfer.md`; in
psephos (commit `05626a6`), `README.md`, `ROADMAP.md` and `src/psephos/methods/`. Nothing
else in either repository was read, and nothing in psephos was changed.

---

## 1. What overlaps

| Method family | psephos | forensics_core |
|---|---|---|
| Integer-percentage excess (Kobak, Shpilkin and Pshenichnikov 2016) | `psephos.methods.integer_pct.integer_excess`, `integer_excess_by_threshold` | `digits.integer_pct.integer_excess`, `integer_excess_by_group` |
| Last-digit uniformity (Beber and Scacco 2012) | `psephos.methods.digits.last_digit_uniformity` | `digits.terminal.terminal_digit_test(k=1)` |
| Last two digits, repeated against adjacent pairs | `psephos.methods.digits.last_two_digit_pairs` (descriptive; the direction is flagged unverified, psephos issue #7) | `digits.terminal.terminal_digit_pair_test` |

Both integer-percentage implementations use the same null: redraw each unit's numerator as
`Binomial(d, k / d)` and count units within `tolerance` of a whole-number percentage. Both
last-digit tests are the Pearson chi-square against a uniform 10-cell table with 9 degrees
of freedom. The methods are the same; the wrappers around them are not.

## 2. The two codebases have different jobs

- **forensics_core** is a research library: pure functions returning `TestResult`, no
  opinion about presentation, methods spanning elections, accounting, Chinese provincial
  statistics and Soviet statistics, and a contract that forbids running inferential analysis
  before its gate.
- **psephos** is a user-facing tool meant to be run today. Its README states the constraints
  that make it what it is: nothing is flagged without confounds printed beside it (enforced
  in `Finding`), size thresholds are swept, there is no fraud score, underpowered is a
  distinct outcome, and checks that would overclaim are left out on purpose. Those
  constraints are the point of psephos and do not belong in a research library.

psephos's own `ROADMAP.md` records the current state: "The two share methods and not code,
which is a live question tracked in forensics-core WO-112."

## 3. The options

From the card, with what each costs:

1. **Leave them separate and test them against each other.** Duplication stays; a
   cross-implementation test catches drift. The test is the deliverable.
2. **psephos depends on forensics-core.** Removes the duplication. Costs psephos its
   minimal dependency footprint (its README: "Dependencies are numpy, scipy and pandas") and
   ties a public tool to a research library's release cycle.
3. **Extract a third, smaller package** that both depend on. Cleanest in principle; three
   packages to maintain for two callers.
4. **forensics_core depends on psephos** for the election methods. Inverts the natural
   direction and drags a CLI into a library.

## 4. Recommendation: option 1 now, revisit option 2 if a third caller appears

For the lead to confirm. The argument:

- **The shared code is small and the differences are in the wrappers.** The overlapping
  statistic is a binomial redraw loop and a chi-square. What differs (section 5) is what
  each codebase does around it: exclusion rules, flagging, the p-value it headlines, the
  effect it reports. Sharing the core loop under option 2 or 3 would remove perhaps a few
  dozen lines and leave every one of those differences in place, because they are
  deliberate.
- **psephos's constraints would not survive option 4, and its footprint would not survive
  option 2 cheaply.** forensics_core is a workspace member of a research monorepo with
  projects gated by a contract; psephos is meant to be installed on its own by people who
  have never seen that contract.
- **Option 3 costs a third release cycle for two callers.** Not worth it at this size.
- **Option 1 makes drift visible, which is the actual problem the card names.** Under every
  option the cross-implementation test is worth having, so building it first loses nothing.
- **What would change the answer:** a third caller of the same methods (at which point the
  duplication is three-way and option 2 or 3 starts to pay), or psephos needing a method
  that only this library has.

**Weakness of option 1 as implemented, stated plainly:** psephos is not a dependency of this
workspace, so `tests/test_psephos_parity.py` runs only when psephos is importable, either
installed or pointed at by the environment variable `PSEPHOS_SRC` (the `src/` directory of
a psephos checkout). Where neither holds, which today includes CI, the three psephos tests
are **skipped**, with a reason that says drift is not being checked. A parity test that is
always skipped in CI catches nothing there. Closing that gap needs a file outside this
card's write list (the workspace `pyproject.toml` or the CI workflow), so the choice is
put to the lead in `workorders/AMBIGUITY-WO-112-1.md` rather than made here. Until it is
made, option 1's drift protection exists only on machines where someone runs the test with
psephos available.

## 5. Known differences a reader comparing outputs will hit

These are real, and each was read from the code rather than assumed.

### Integer percentages

| | psephos `integer_excess` | forensics_core `integer_excess` |
|---|---|---|
| Input | `numerator, denominator` | `pct, denominators` (build `pct` with `percentage`) |
| `n_mc` default | 500 | 200 |
| `min_denominator` default | 250 (`DEFAULT_MIN_DENOMINATOR`), and the audit runs `integer_excess_by_threshold` over `(100, 250, 500, 1000)` | 100, a parameter; no sweep |
| Headline p-value | the Monte Carlo p-value `(1 + #{null >= observed}) / (n_mc + 1)` | the one-sided normal approximation `norm.sf(z)`; the Monte Carlo p-value is in `details["mc_pvalue"]` |
| Flag | `STRONG` if `mc_p <= 2 / (n_mc + 1)` and `z >= 5`; `NOTABLE` if `mc_p <= 0.05`; else `OK` | none; the library does not flag |
| Effect | `effect = excess / n_used`, a share of units tested | `excess`, a count, in `IntegerExcessResult.excess`; the share is also reported, as `details["excess_share_of_units"]` |
| Too few units | fewer than 100 usable units returns `Flag.UNDERPOWERED` | runs on any positive number of units; raises only if none survive |
| Out-of-range units | a unit with `num < 0` or `num > den` is excluded and counted in `n_excluded` | a percentage outside `[0, 100]` raises |
| Exclusion counts | one `n_excluded` covering small, missing and out-of-range units | `n_excluded_small` and `details["n_dropped"]` separately |
| `sd = 0` | `z = nan`, flag `UNDERPOWERED` | `z = inf` and `pvalue = 0.0` if there is an excess, else `z = 0`, `pvalue = 1.0` |
| Weights, groups | neither | `weights=`; `integer_excess_by_group` |

Two consequences worth spelling out:

- **The two headline p-values are different quantities.** On strongly rounded data the
  library's normal-approximation p-value can be many orders of magnitude below psephos's,
  which cannot go below `1 / (n_mc + 1)` (1/501 at its default). Compare
  `details["mc_pvalue"]` with psephos's `pvalue`, not `test.pvalue`.
- **The card's note that the library "reports excess counts" is only half the picture.**
  It reports the count as the result field and the share of units in `details`; the
  psephos-comparable number exists, it is just not the headline.

**Why the Monte Carlo nulls are close but not always identical under the same seed.** The
library computes the binomial share as `pct / 100`, where `pct = 100 * k / d`; psephos
computes `k / d`. These can differ in the last bit, and a last-bit difference in `p` can
change an individual binomial draw. So identical seeds give null means that are usually
equal and occasionally a few draws apart. The parity test's tolerance allows for this.

### Last digits

| | psephos `last_digit_uniformity` | forensics_core `terminal_digit_test(k=1)` |
|---|---|---|
| Small counts | counts below `min_count = 100` are excluded | no size filter; the caller filters |
| Non-integers | rounded with `rint` | raise |
| Too few units | fewer than 100 returns `UNDERPOWERED` | any non-empty sample |
| Effect | total variation distance from uniform | `max_abs_dev`, `max_excess` |
| Flag | `STRONG` if `p <= 0.001` and TVD `>= 0.02`; `NOTABLE` if `p <= 0.05` | none |
| Weights | no | yes (p-value then approximate) |

On the same integer counts, filtered at 100, the statistic and p-value are the same
chi-square and agree to floating-point rounding.

## 6. The parity test

`tests/test_psephos_parity.py`, run by `uv run pytest -q tests/test_psephos_parity.py`.

| Test | Needs psephos | What it asserts, and to what tolerance |
|---|---|---|
| `test_last_digit_chi_square_agrees` | yes | same `n`, identical cell counts, chi-square statistic and p-value equal to relative 1e-9 |
| `test_integer_percentage_excess_agrees` | yes | units used, units excluded and the observed integer count exactly equal; null mean within `4 * sd * sqrt(2 / n_mc)` (four standard errors of the difference of two independent Monte Carlo means, which covers the last-bit effect above); effect share within that tolerance divided by `n` |
| `test_documented_psephos_defaults` | yes | the psephos defaults in section 5 are the ones in the psephos code |
| `test_documented_library_defaults` | no | the library defaults in section 5 are the ones in this code; runs everywhere |

Both implementations are called with the same explicit `tolerance`, `min_denominator`,
`n_mc` and `seed`, so the comparison is of the methods, not of their defaults. The data are
synthetic and generated in the test: 4000 precincts, a fifth of them reporting a
whole-number percentage, and 6000 vote counts with a mild last-digit distortion.

Run it against a local psephos checkout with:

```console
PSEPHOS_SRC=/path/to/psephos/src uv run pytest -q tests/test_psephos_parity.py
```

## 7. The Monte Carlo cutoff check the card asked for

The card: psephos flags `STRONG` against the attainable floor `1 / (n_mc + 1)` because a
fixed 0.001 cutoff is unreachable at its default of 500 replicates; check whether
`forensics_core.digits.integer_pct` has the same problem.

**Finding: it does not, within `integer_pct.py`.** The module compares no p-value against
any cutoff. The relevant lines (`src/forensics_core/digits/integer_pct.py`):

```python
218:    n_mc: int = 200,
...
358:        pvalue = float(stats.norm.sf(z))
...
361:        pvalue = 0.0 if excess > 0 else 1.0
362:    mc_pvalue = float((1.0 + np.sum(null_counts >= observed)) / (n_mc + 1.0))
```

The headline `test.pvalue` is the normal approximation, which has no floor, so any cutoff
applied to it is reachable. The Monte Carlo p-value is reported in `details["mc_pvalue"]`
and nothing in the module thresholds it.

**The latent hazard, recorded rather than fixed.** `details["mc_pvalue"]` has the floor
`1 / (n_mc + 1)`, which at the library default `n_mc = 200` is 1/201, about 0.004975. Any
caller that compares `mc_pvalue` with a cutoff below that (0.001, or a Bonferroni- or
Holm-adjusted threshold over a family of tests) can never reject, at the default `n_mc`.
Callers of `integer_excess` elsewhere in the library (the detector wrappers of WO-110, the
multiple-testing correction) are outside this card's whitelist and were **not** checked.
Whether any of them does this is a question for its own card; if one does, that is the bug
the card anticipated, and it lives in the caller, not in `integer_pct.py`.

## 8. What this document does not decide

- Whether the lead accepts option 1 (section 4).
- How the parity test reaches psephos in CI (`workorders/AMBIGUITY-WO-112-1.md`).
- Whether any caller thresholds `mc_pvalue` below its floor (section 7).
- Any change to psephos. If one is needed, it is an issue on that repository.
