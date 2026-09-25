# forensics_core - interface contract

This file fixes the public signatures of the shared library so that the four projects (and
parallel implementers) build against one stable surface. **Implementations may add keyword
arguments with defaults; they may not rename or remove anything listed here.** Where a
function is marked `STUB`, ship the signature, a docstring citing the method, and raise
`NotImplementedError("...")` with a one-line description of what remains.

**This document has been reconciled against the code as built** in
`src/forensics_core/`. Every place where the implementation departs from the contract as
originally written is marked `(changed during implementation: <reason>)`, so a reader can
see that the contract moved and why. Nothing below is aspirational: the signatures,
dataclass fields, defaults and returned column lists are the ones in the source, and no
entry is a `STUB` any more.

Conventions that apply everywhere:

- Inputs are `numpy.typing.ArrayLike` (1-D unless stated) or `pandas` objects. Functions are
  pure: no global state, no I/O, no plotting. Non-finite values are dropped and the count of
  dropped values goes into `details["n_dropped"]`.
  (changed during implementation: three subpackages reject non-finite input instead of
  dropping it, and say so. `reconcile` refuses `nan`/`inf` because dropping a measurement
  silently turns it into an unmeasured variable and changes the constraint system; use
  `reconcile.project_unmeasured` to do that on purpose. `dispersion.carlisle.combine_pvalues`
  refuses a non-finite p-value because it means an upstream test failed, and combining the
  rest would change the reference distribution without the caller knowing. `eval.metrics`
  refuses non-finite labels or scores because an unlabeled row must be dropped deliberately
  with `Dataset.labeled()`. All three still emit `details["n_dropped"] = 0` so the key can be
  read uniformly.)
- Every test returns `forensics_core.TestResult` (or a frozen dataclass that *contains* one
  or more `TestResult`s and has `.to_dict()`). `pvalue` is two-sided unless
  `details["alternative"]` says `"less"` or `"greater"`.
- `weights` means observation weights (e.g. precinct size). When accepted, expected counts
  and test statistics are weighted; `n` reports the unweighted count and
  `details["effective_n"]` the Kish effective sample size.
  (changed during implementation: every weighted p-value in `digits` is an approximation,
  because the null distribution is evaluated at the effective sample size and ignores the
  per-cell design effect a Rao-Scott correction would carry. The functions flag this with
  `details["weighted_pvalue_is_approximate"] = True` rather than leaving it to the reader.)
- Randomness always flows through a `seed: int | None` argument -> `np.random.default_rng`.
  (changed during implementation: `digits.integer_pct` also accepts an already-built
  `numpy.random.Generator` as `seed`, which is what lets `integer_excess_by_group` spawn one
  independent child stream per group from a single parent seed.)
- "Higher score = more suspicious" everywhere a per-unit score is returned.
- Docstrings cite the method's source (author, year, journal) and state any coefficient or
  threshold that was taken from a secondary source and still needs confirmation.
- Tests use synthetic data only (`tests/fixtures/synthetic_*`, or generated in the test).

---

## `forensics_core._types`

```python
@dataclass(frozen=True)
class TestResult:
    method: str
    statistic: float
    pvalue: float | None
    n: int
    details: dict[str, Any] = field(default_factory=dict)   # (changed: defaulted)
    def to_dict(self) -> dict[str, Any]
    def __str__(self) -> str

def jsonable(v: Any) -> Any        # (changed: new helper)
```

(changed during implementation: `details` gained a default factory so a result with nothing
worth keeping can be built without passing an empty dict. `to_dict` runs the whole structure
through the new module-level `jsonable`, which converts numpy scalars and arrays to plain
Python recursively; without it a `TestResult` holding an `np.ndarray` of observed counts is
not JSON-serialisable, and every result type in the library holds one. `jsonable` is used by
every `to_dict` in the library and is therefore part of the surface, though it is not a
test result itself.)

Re-exported at package level: `forensics_core.TestResult`, `forensics_core.__version__`.

## `forensics_core.config`

Already implemented. `find_repo_root(start=None)`, `load_config(root=None)`,
`require_contact(root=None)` ->
`HttpConfig(contact, user_agent_prefix, default_timeout_seconds, rate_limits, never_refetch)`
with `.user_agent(purpose="")`, `.rate_limit_for(host)`, `.contact_is_placeholder`.

(changed during implementation: the exception type `ContactNotConfigured` is part of the
surface, since callers outside the library catch it: `provenance.runner.main` does, to turn
an unconfigured contact into an exit code rather than a traceback. `load_config` is
`lru_cache`d on `root`, so an edited configuration file is not re-read within a process.)

---

## `digits/benford.py`

```python
DigitPosition = Literal["first", "second", "first_two"]
POSITIONS: tuple[str, ...] = ("first", "second", "first_two")
MAD_BANDS: dict[str, tuple[float, float, float]]     # (changed: exposed as a constant)
MAD_LABELS: tuple[str, str, str, str]                # (changed: exposed as a constant)
SIGNIFICANCE_RTOL: float = 1e-12                     # (changed: exposed as a constant)

def benford_expected(position: DigitPosition = "first") -> np.ndarray
    # first: P(d) = log10(1 + 1/d), d = 1..9
    # second: P(d) = sum_{k=1..9} log10(1 + 1/(10k + d)), d = 0..9
    # first_two: P(d) = log10(1 + 1/d), d = 10..99

def digit_support(position: DigitPosition = "first") -> np.ndarray   # (changed: default added)

def leading_digits(x: ArrayLike, position: DigitPosition = "first", *,
                   require_two_significant_digits: bool = True) -> np.ndarray
    # returns int array; nonpositive / non-finite -> excluded (caller sees fewer values);
    # "second" requires at least two significant digits, else excluded.

def digit_frequencies(x, position="first", weights=None, *,
                      require_two_significant_digits: bool = True) -> DigitTable

@dataclass(frozen=True)
class DigitTable:
    digits: np.ndarray
    observed: np.ndarray
    expected: np.ndarray
    observed_prop: np.ndarray
    expected_prop: np.ndarray
    n: int
    effective_n: float
    n_dropped: int = 0          # (changed: added)
    position: str = "first"     # (changed: added)
    def to_dict(self) -> dict[str, Any]

def benford_test(x, position="first", weights=None,
                 statistics=("chi2", "mad", "kuiper"), *,
                 require_two_significant_digits: bool = True) -> BenfordResult

@dataclass(frozen=True)
class BenfordResult:
    table: DigitTable
    chi2: TestResult | None = None      # (changed: optional, None when not requested)
    mad: TestResult | None = None
    kuiper: TestResult | None = None
    settings: dict[str, Any] = field(default_factory=dict)   # (changed: added)
    def to_dict(self) -> dict[str, Any]
```

MAD conformity bands (Nigrini 2012, ch. 6), now held in `MAD_BANDS` as the upper edges of
the close / acceptable / marginal bands:

```
first:     [0, .006) close, [.006, .012) acceptable, [.012, .015) marginal, else nonconformity
second:    [0, .008), [.008, .010), [.010, .012)
first_two: [0, .0012), [.0012, .0018), [.0018, .0022)
```

`mad.details["conformity"]` holds the band label, `details["bands"]` the numeric edges, and
`details["citation"]` records that the cut-offs come from a secondary restatement of
Nigrini's table and that the exact table number is still unconfirmed. The kuiper statistic
is `V = D+ + D-` on the cumulative digit distribution with the Stephens (1970) asymptotic
series for its tail; `details` carries `d_plus`, `d_minus` and the citation, which states
that the series assumes a continuous null and is therefore conservative on a discrete digit
support.

(changed during implementation, additive fields and one new keyword:

- `DigitTable` gained `n_dropped` (values excluded as non-finite, non-positive, or lacking
  the required significant digit) and `position`. Without them a table cannot say how much of
  the input it discarded, which the library-wide non-finite convention requires, and a table
  passed around on its own could not say which digit position it describes.
- `BenfordResult` gained `settings` and its three statistic fields became optional. Passing
  `statistics=("mad",)` must produce a result whose `chi2` and `kuiper` are absent rather
  than fabricated, so the fields default to `None`; `settings` records the position, the
  statistics actually requested, whether weights were used, and the value of
  `require_two_significant_digits`, so a stored result is self-describing.
- `require_two_significant_digits` is a keyword-only argument on `leading_digits`,
  `digit_frequencies` and `benford_test`, defaulting to `True`, which is the behaviour the
  contract fixed for `position="second"`. It exists because the exclusion rule is a
  convention, not a fact: a value such as `300.0` has a placeholder zero in the second place
  rather than a reported digit, and a caller working with data where every value is written
  to two digits may want the looser reading. The default keeps the contracted behaviour.
- `MAD_BANDS`, `MAD_LABELS` and `SIGNIFICANCE_RTOL` are module constants rather than numbers
  buried in the code, so a project can read the bands it is being judged against, and so the
  provenance warning attaches to a single object.
- Every `details` dict carries `effective_n`, `n_dropped`, `weighted` and, when weighted,
  `weighted_pvalue_is_approximate`.)

## `digits/terminal.py`

```python
def terminal_digits(x: ArrayLike, k: int = 1) -> np.ndarray
    # last k decimal digits of round(x); values must be integer-valued (raise otherwise)

def terminal_digit_test(x, k=1, weights=None) -> TestResult
    # chi-square vs uniform over 10**k cells; method = f"terminal_digit_{k}_chi2"
    # details: k, digits, observed, expected, observed_prop, expected_prop, max_abs_dev,
    #   max_excess_cell, max_excess, df, n_dropped, effective_n, weighted,
    #   weighted_pvalue_is_approximate, alternative, citation

def terminal_digit_pair_test(x, weights=None) -> TestResult
    # last two digits independent & uniform (Beber & Scacco 2012): chi-square on 100 cells
    # method = "terminal_digit_pair_chi2"; details as above plus adjacent_pair_excess
```

(changed during implementation, details only:

- `k` is bounded to `1..9` and the input must be integer-valued to within 1e-9; a magnitude
  at or above `2**53` raises, because float64 no longer represents every integer there and
  the last digit would be an artefact of the representation. The magnitude is used, so
  `-123` and `123` share the terminal digits.
- `details["adjacent_pair_excess"]` is a two-family mapping, not a single number: keys
  `"repeated"` (00, 11, ..., 99) and `"adjacent"` (01, 10, 12, 21, ...), each carrying
  `cells`, `observed_prop`, `expected_prop`, `excess`, a normal-approximation `z`, its
  two-sided `pvalue` and `fraud_direction`. The direction matters as much as the magnitude:
  Beber and Scacco report a *deficit* of repeats and an *excess* of adjacent pairs, so a
  single unsigned number could not be read.
- `max_excess_cell` reports the digit with the largest positive excess, and
  `terminal_digit_test` also reports `max_excess`, its size.)

## `digits/integer_pct.py`  (Kobak, Shpilkin & Pshenichnikov 2016, Ann. Appl. Stat.)

```python
def percentage(numerator: ArrayLike, denominator: ArrayLike) -> np.ndarray   # 100*num/den; den<=0 -> nan

def percentage_histogram(pct: ArrayLike, bin_width: float = 0.1,
                         weights=None, lo: float = 0.0, hi: float = 100.0
                         ) -> tuple[np.ndarray, np.ndarray]
    # bins centred so that every integer is a bin centre; returns (centres, counts)

def integer_excess(pct: ArrayLike, denominators: ArrayLike, *, tolerance: float = 0.05,
                   min_denominator: int = 100, neighbour_bins: int = 5,
                   n_mc: int = 200, seed: int | np.random.Generator | None = None,
                   weights=None) -> IntegerExcessResult

@dataclass(frozen=True)
class IntegerExcessResult:
    test: TestResult            # z statistic, one-sided ("greater") p-value
    observed: float
    expected_mean: float
    expected_sd: float
    excess: float
    per_integer: np.ndarray     # length 101: observed minus null mean, by integer 0..100
    n_excluded_small: int
    settings: dict[str, Any]
    def to_dict(self) -> dict[str, Any]

def integer_excess_by_group(pct, denominators, groups, **kw) -> pandas.DataFrame
    # columns: group, n, observed, expected_mean, expected_sd, excess, excess_per_unit,
    #          z, pvalue, mc_pvalue, n_excluded_small
```

Null: for each unit, re-draw the numerator as `Binomial(den, num/den)` (binomial noise
model, KSP 2016 section 2) `n_mc` times and recount, giving the null mean and sd. Units with
`den < min_denominator` are excluded (known trap: small precincts round honestly).

(changed during implementation:

- `seed` accepts a `numpy.random.Generator` as well as an int, and
  `integer_excess_by_group` spawns one child generator per group from the parent seed, so
  the whole table is reproducible from a single seed and no two groups share a stream.
- `integer_excess` raises when a percentage lies outside `[0, 100]`: the binomial null is
  undefined there, and silently clipping would manufacture the very spike being tested for.
- `test.details` carries more than the headline z: `mc_pvalue`, the plain Monte Carlo
  `(1 + #{null >= observed}) / (n_mc + 1)`, which is the safer number when `n_mc` is small or
  the null count is far from normal; `neighbour_mean`, `neighbour_excess` and
  `neighbour_bins_used`, a model-free cross-check against equally wide neighbouring bins
  (offsets that would run past the half-integer are dropped, so with the defaults 8 of the
  requested 10 bins are used); `n_at_boundary`, the count of units at exactly 0% or 100%,
  which sit on an integer in the data and in every null draw alike and so cannot create a
  spurious excess; and `observed_per_integer` / `expected_per_integer`, the two vectors whose
  difference is `per_integer`.
- `integer_excess_by_group` does not raise when one group has no usable unit: that row is
  reported with `n = 0` and null statistics, so one empty region does not sink the table.
  It also documents the meaning of `per_integer` as a difference, since a caller reading only
  the field name might expect the raw observed counts.)

---

## `bunching/density.py`  (Chetty, Friedman, Olsen & Pistaferri 2011; Kleven & Waseem 2013)

```python
BunchingSide = Literal["below", "above"]     # (changed: new)

def bin_around(x: ArrayLike, threshold: float, bin_width: float,
               lo: float | None = None, hi: float | None = None,
               weights=None) -> tuple[np.ndarray, np.ndarray]
    # bin edges aligned so that `threshold` is an edge; returns (centres, counts)

def bunching_estimator(x: ArrayLike, threshold: float, *, bin_width: float,
                       exclude_below: float, exclude_above: float, poly_degree: int = 7,
                       lo=None, hi=None, integration_constraint: bool = False,
                       max_iter: int = 50, weights=None,
                       bunching_side: BunchingSide = "below",   # (changed: added)
                       tol: float = 1e-6                        # (changed: added)
                       ) -> BunchingResult

@dataclass(frozen=True)
class BunchingResult:
    centres: np.ndarray
    counts: np.ndarray
    counterfactual: np.ndarray
    excluded_mask: np.ndarray
    excess_mass: float
    missing_mass: float
    normalized_excess: float
    coefficients: np.ndarray
    threshold: float
    settings: dict[str, Any] = field(default_factory=dict)
    @property
    def details(self) -> dict[str, Any]     # alias of settings (the name this file uses)
    @property
    def imbalance(self) -> float            # |B - M|
    def to_dict(self) -> dict[str, Any]
```

Fit `counts_j = sum_k beta_k * z_j^k + sum_{j in excluded} gamma_j 1[j] + e_j` with
`z = (centre - threshold) / bin_width`. Counterfactual in the excluded window is the
polynomial part. Excess mass `B` is summed `(observed - counterfactual)` over the excluded
bins on the bunching side; missing mass `M` is summed `(counterfactual - observed)` over the
excluded bins on the other side. Both are reported as positive magnitudes, so mass
conservation reads `B == M`. `normalized_excess b = B / mean counterfactual count per bin
over the whole excluded window` (Chetty et al. definition; some implementations average only
over the bunching side, which changes `b` but not `B`).

`settings` holds `bin_width`, `lo`, `hi`, `n_bins`, `poly_degree`, `exclude_below`,
`exclude_above`, `n_excluded_below`, `n_excluded_above`, `bunching_side`,
`integration_constraint`, `max_iter`, `tol`, `n_iter`, `converged`, `stop_reason`,
`shift_factor`, `mean_counterfactual_excluded`, `imbalance`, `n`, `n_dropped`,
`n_out_of_range`, `n_in_window`, `weighted`, `effective_n`.

(changed during implementation:

- `bunching_side` is new and defaults to `"below"`, which reproduces the contracted
  behaviour (the classic tax kink or notch: the reward lies below the threshold and agents
  bunch just under it). It exists because this programme's central case is the opposite one:
  a bonus paid if and only if reported output reaches 100% of plan puts the excess at and
  just *above* the threshold. Without the switch the estimator would report the pile-up as
  missing mass and the hole as excess.
- `tol` is new: the integration constraint iterates, so its convergence criterion must be a
  documented parameter rather than a hidden constant. The iteration stops when
  `|B_t - B_{t-1}| <= tol * max(1, |B_t|)`, capped at `max_iter`, and records `n_iter`,
  `converged`, `stop_reason` and the final `shift_factor` in `settings`.
- `details` is a read-only alias of `settings`. The contract named the dictionary `details`;
  the implementation named the field `settings` to match every other result type in the
  library, and exposes both names so neither reader is wrong.
- `imbalance` (`|B - M|`) is exposed as a property because it is the diagnostic that says
  whether the integration constraint did its job.
- `bin_around` bins half-open on the right, so an observation exactly at the threshold counts
  as *above* it, and a relative tolerance of 1e-9 is applied before flooring so that a value
  one ulp below an edge lands in the upper bin. Observations outside `[lo, hi)` are excluded
  from the histogram and counted in `settings["n_out_of_range"]`.)

## `bunching/notch.py`

```python
SCAN_COLUMNS: list[str]      # (changed: the scan table's column order, exposed)

@dataclass(frozen=True)
class Notch:        # discontinuous payoff at threshold (e.g. bonus paid iff plan >= 100%)
    threshold: float
    side: Literal["above", "below"] = "above"   # where the reward lies
    label: str = ""
    @property
    def dominated_side(self) -> str             # (changed: added)
    # __post_init__ validates: threshold finite, side one of the two

@dataclass(frozen=True)
class Kink:         # discontinuous slope (e.g. marginal bonus rate changes)
    threshold: float
    label: str = ""
    # __post_init__ validates: threshold finite

def estimate_notch(x, notch: Notch, *, bin_width, exclude_below, exclude_above,
                   poly_degree=7, weights=None, **kw) -> BunchingResult
    # asymmetric window; sets bunching_side from notch.side.
    # settings: dominated_region, dominated_side, side, specification="notch", notch_label

def estimate_kink(x, kink: Kink, *, bin_width, exclude_halfwidth, poly_degree=7,
                  weights=None, **kw) -> BunchingResult
    # symmetric window; settings: specification="kink", exclude_halfwidth, kink_label

def scan_candidate_notches(x, candidates: Sequence[float], *, bin_width, exclude_below,
                           exclude_above, poly_degree=7, weights=None,
                           side: Literal["above","below"]="above",
                           lo=None, hi=None, **kw) -> pandas.DataFrame
    # "find the notch": one row per candidate with [threshold, excess_mass, missing_mass,
    #   normalized_excess, n_in_window, side]; sorted by normalized_excess descending,
    #   index reset so row 0 is the best candidate.
    # Typical candidates: 100 (plan fulfilment), round vote shares, growth targets.
```

(changed during implementation:

- **`details["dominated_region"]`**. The contract fixed it at
  `(threshold, threshold + exclude_above)`. That is correct only for a notch whose reward
  lies *below* the threshold. The dominated region is always on the side agents do not want
  to be on, so with the contracted default `side="above"` the formula would place it on the
  rewarded side, where bunching rather than a hole is expected. The implementation returns
  `(threshold - exclude_below, threshold)` when `side == "above"` and the contracted
  `(threshold, threshold + exclude_above)` when `side == "below"`, and records
  `settings["dominated_side"]` alongside. `Notch.dominated_side` exposes the same reading on
  the specification object.
- `Notch` and `Kink` validate in `__post_init__`, so a non-finite threshold or an unknown
  side fails where it is written rather than deep inside a fit.
- `scan_candidate_notches` gained `lo` and `hi` because each candidate otherwise gets its own
  threshold-aligned grid; passing an explicit range is the only way to make the rows strictly
  comparable. It rejects duplicate or non-finite candidates, and names the offending
  candidate when one cannot be estimated instead of failing anonymously.
- `SCAN_COLUMNS` is exported so a caller can build an empty frame with the right schema, and
  so the column order is fixed in one place.)

## `bunching/inference.py`

```python
@dataclass(frozen=True)
class BootstrapResult:
    point: float
    se: float
    ci_low: float
    ci_high: float
    draws: np.ndarray
    method: str
    n_boot: int
    @property
    def bias(self) -> float                          # (changed: added)
    def covers(self, value: float) -> bool           # (changed: added)
    def to_dict(self) -> dict[str, Any]
    def to_test_result(self, method_name: str = "bunching_bootstrap") -> TestResult

def bootstrap_bunching(x, estimator: Callable[[np.ndarray], BunchingResult], *,
                       n_boot: int = 499, alpha: float = 0.05, seed=None,
                       method: Literal["residual", "pairs"] = "residual",
                       statistic: str | Callable[[BunchingResult], float] = "excess_mass"
                       ) -> BootstrapResult                     # (changed: statistic added)

def placebo_test(x, threshold, estimator_factory: Callable[[float], Callable],
                 placebo_thresholds: Sequence[float], *,
                 statistic: str | Callable = "normalized_excess",   # (changed: added)
                 add_one: bool = False                              # (changed: added)
                 ) -> TestResult

def permutation_test(x, groups, statistic: Callable[[np.ndarray], float],
                     n_perm: int = 999, seed=None) -> TestResult
```

`residual` resamples bin-level residuals (Chetty et al. 2011); `pairs` resamples units.
`placebo_test` compares the excess at the real threshold with the excess at placebo
thresholds; `p` is the share of placebos at least as extreme, and `details` carries the
placebo thresholds, their values, the count at least as extreme, and the placebo mean and sd.

(changed during implementation:

- `statistic` on `bootstrap_bunching` and `placebo_test` selects which scalar is
  bootstrapped or compared: `"excess_mass"`, `"missing_mass"`, `"normalized_excess"`, or any
  callable of a `BunchingResult`. The defaults differ on purpose. `bootstrap_bunching`
  defaults to `"excess_mass"`, the estimate itself; `placebo_test` defaults to
  `"normalized_excess"`, because the counterfactual level differs between thresholds and raw
  masses at different thresholds are not comparable.
- `add_one` on `placebo_test` switches to `(1 + #{placebo >= observed}) / (1 + n_placebo)`,
  the never-zero permutation p-value of Phipson and Smyth (2010). The default `False` is the
  plain share fixed by this contract, which can return exactly 0 and should not be reported
  as if a p-value of zero had been measured.
- `permutation_test` always uses the add-one form (there is no contract text to preserve
  here), tests two groups two-sided on `|T|` and more than two groups one-sided on the range
  `max_g - min_g`, and reports `per_group_statistic`, `group_sizes` and the permutation
  mean/sd in `details`.
- `BootstrapResult` gained `bias` (`mean(draws) - point`), `covers(value)` and
  `to_test_result()` so a bootstrap can be tabulated next to the tests. Note there are two
  `BootstrapResult` types in the library, this one and `eval.metrics.BootstrapResult`; they
  share field names but the `eval` one carries two extra fields (see below).
- The residual bootstrap resamples the residuals of the *full* regression, including the
  exact zeros of the saturated excluded bins, following the reference implementation; the
  docstring records that this makes it mildly conservative and that `pairs` is safer when bin
  counts are small. The pairs bootstrap resamples `x` only, so an estimator closing over a
  positional weight vector cannot be used with it.)

---

## `dispersion/underdispersion.py`

```python
def dispersion_index(x: ArrayLike, *, ddof: int = 1) -> float      # var / mean

def variance_floor_test(x: ArrayLike, floor_variance: float, *, ddof: int = 1) -> TestResult
    # H0: Var(x) >= floor. Statistic (n - ddof) s^2 / floor ~ chi2(n - ddof) under Var = floor;
    # p = P(chi2 <= observed) (alternative="less").
    # details: s2, floor, floor_variance, ratio, df, ddof, alternative, n_dropped.

def implied_variance_floor(proxy: ArrayLike, elasticity: float, *, ddof: int = 1) -> float
    # elasticity^2 * Var(proxy). A LOWER bound only if the other shocks are uncorrelated
    # with the proxy: state that assumption whenever the bound is used.

def residual_underdispersion(series: ArrayLike, fitted: ArrayLike, floor_variance: float,
                             *, ddof: int = 1) -> TestResult
    # variance_floor_test on residuals series - fitted;
    # method="residual_underdispersion", details adds mean_residual.

def smoothness_ratio(series: ArrayLike) -> float
    # von Neumann ratio: mean squared successive difference / variance (about 2 for iid noise)

def too_smooth_test(series: ArrayLike, *, detrend: Literal["none","linear","diff"]="diff",
                    n_perm: int = 999, seed=None) -> TestResult
    # H0: the analysed values are exchangeable. Statistic = smoothness_ratio OF THE ANALYSED
    # VALUES; p from permutation (alternative="less": too smooth).

def rolling_variance_floor(series, floor_variance, window: int, *,
                           ddof: int = 1, alpha: float = 0.05) -> pandas.DataFrame
    # columns: start, end, n, s2, statistic, pvalue, flag, n_dropped
```

(changed during implementation:

- **`rolling_variance_floor` returns an extra `n_dropped` column**, and the same count is on
  `frame.attrs["n_dropped"]`. Non-finite observations are removed *before* windowing, which
  closes gaps, so `start` and `end` index the cleaned series and not the input. A caller
  reading a single row would otherwise have no way to know that the positional indices have
  been shifted. The value is a property of the whole input, repeated on every row.
- `rolling_variance_floor` also gained `ddof` and `alpha` as keyword arguments: `alpha` is
  the nominal per-window level behind the `flag` column, and it is emphatically not a
  family-wise rate, because overlapping windows make the p-values strongly dependent.
- `ddof` is keyword-only on `dispersion_index`, `variance_floor_test`,
  `implied_variance_floor` and `residual_underdispersion`. `variance_floor_test` requires
  `ddof >= 1`: the numerator is the sum of squares about the *sample* mean, so it carries at
  most `n - 1` degrees of freedom, and `ddof = 0` would refer a `chi2(n - 1)` quantity to a
  `chi2(n)` reference and over-reject. `residual_underdispersion` documents that a fit
  estimated on the same data needs `ddof = 1 + k`.
- `variance_floor_test` reports the floor under both names: `details["floor"]` is the name
  this contract fixed, `details["floor_variance"]` matches the argument name.
- `dispersion_index` raises when the mean is exactly zero rather than returning an infinity.
- `too_smooth_test`: `statistic` is the von Neumann ratio of the *analysed* values, which
  under the default `detrend="diff"` means `smoothness_ratio(np.diff(series))` and not
  `smoothness_ratio(series)`. `details["analysed"]` spells out which ("levels", "first
  differences", "linear-trend residuals") so the number cannot be misread, and `details` adds
  `n_analysed`, `null_mean`, `null_sd`, `null_q05` and `implied_lag1_autocorr`. The docstring
  carries a calibration warning that matters for use: the default `"diff"` is the exact test
  only for a random-walk-like series and has essentially no power against a smoothed
  mean-reverting path, which is the usual fabrication shape; use `"linear"` or `"none"`
  there. `n_perm` must be at least 2.
- `smoothness_ratio` raises on a series that is constant to within floating-point precision,
  rather than returning a ratio computed from rounding error; the guard is scaled by the
  magnitude of the original series, which is what makes it correct for detrended residuals.)

## `dispersion/carlisle.py`  (Carlisle 2017, Anaesthesia 72:944; Carlisle & Loadsman 2017)

```python
DEFAULT_CLIP: float = 1e-12          # (changed: exposed as a constant)

def balance_pvalues(means: ArrayLike, sds: ArrayLike, ns: ArrayLike) -> float
    # one-way ANOVA p-value from group summary statistics (means, sds, ns of one variable)

def combine_pvalues(p: ArrayLike, method: Literal["stouffer","fisher"] = "stouffer",
                    *, clip: float = DEFAULT_CLIP) -> TestResult    # (changed: clip added)

def carlisle_test(means: np.ndarray, sds: np.ndarray, ns: np.ndarray,
                  *, method: Literal["stouffer", "fisher"] = "stouffer",
                  clip: float = DEFAULT_CLIP) -> CarlisleResult

@dataclass(frozen=True)
class CarlisleResult:
    per_variable: np.ndarray    # one balance p-value per kept variable, in input order
    combined: TestResult        # alternative="greater" = too balanced
    ks_uniformity: TestResult
    def to_dict(self) -> dict[str, Any]
```

Rows are variables, columns are groups. Per-variable balance p-values are combined by
`method`; the "too good" direction is p-values piling up near 1.

(changed during implementation:

- `clip` is new. p-values are clipped into `[clip, 1 - clip]` before `Phi^-1` or `log`, so an
  exact 0 or 1 cannot produce an infinite statistic, and `details["n_clipped"]` reports how
  many were clipped. If that count is large the combined statistic is an artefact of the clip
  and must be read as "at least this extreme" rather than as a number.
- Both combination methods are oriented so that a large statistic means "too balanced".
  Stouffer reports `-z`; Fisher is applied to the *complements*,
  `X = -2 sum log(1 - p_i) ~ chi2(2k)`. The conventional lower-tail Fisher statistic is still
  reported, in `details["fisher_lower_tail_statistic"]` and its p-value, for anyone who wants
  the usual direction.
- `ns` may be 1-D of length `n_groups` and is then used for every variable, which is the
  usual case (the same randomised groups measured on every baseline variable). A 1-D `means`
  or `sds` is read as a single variable.
- `carlisle_test` drops rows with any non-finite summary statistic and overwrites
  `combined.details["n_dropped"]` with the real count; it also adds `n_variables`,
  `n_groups`, `mean_pvalue` and `share_pvalue_above_0p9`. `combine_pvalues` itself refuses
  non-finite input (see the conventions note above) and always emits `n_dropped = 0`.
- `balance_pvalues` handles the degenerate table explicitly instead of returning `nan`: when
  every reported SD is exactly zero it returns 0.0 if the means differ and 1.0 if they do
  not, the latter being perfect balance, which is itself the strongest possible signal.
- `ks_uniformity` is a one-sided KS test in the near-1 direction, `D- = sup [x - F_n(x)]`,
  which is `alternative="less"` in scipy's parametrisation; `details` records both the
  library-facing `alternative="greater"` (meaning too balanced) and the `scipy_alternative`
  actually passed, so the two conventions cannot be confused.)

---

## `reconcile/balance.py`  (Narasimhan & Jordache 2000, ch. 3-5; Crowe 1996)

```python
DEFAULT_RCOND: float = 1e-12          # (changed: exposed)
REDUNDANCY_TOL: float = 1e-10         # (changed: exposed)
CONSISTENCY_TOL: float = 1e-8         # (changed: exposed)
PROJECTION_ZERO_TOL: float = 1e-10    # (changed: exposed)

def incidence_matrix(edges, nodes: Sequence[str] | None = None, environment: str = "ENV",
                     *, edge_names: Sequence[str] | None = None
                     ) -> tuple[np.ndarray, list[str], list[str]]
    # edges: sequence of (source, target) pairs, (name, source, target) triples, or a
    #   mapping {name: (source, target)}                      (changed: triples and mapping)
    # A[node, edge] = +1 inflow, -1 outflow; the environment node is dropped
    # (sources/sinks are unconstrained). Returns (A, node_names, edge_names).

def reconcile(y: ArrayLike, A: np.ndarray, sigma: ArrayLike, b: ArrayLike | None = None, *,
              names: Sequence[str] | None = None,
              constraint_names: Sequence[str] | None = None,
              rcond: float = DEFAULT_RCOND,
              redundancy_tol: float = REDUNDANCY_TOL) -> ReconciliationResult
    # sigma: measurement std devs (1-D) or covariance (2-D). Weighted least squares with
    # linear constraints: x_hat = y - S A' (A S A')^+ (A y - b), b defaults to 0.

@dataclass(frozen=True, eq=False)
class ReconciliationResult:
    adjusted: np.ndarray
    adjustments: np.ndarray
    constraint_residuals: np.ndarray
    standardized_adjustments: np.ndarray      # a_i / sqrt(Var(a)_ii); nan where non-redundant
    objective: float
    dof: int                                  # rank(A S A')
    A: np.ndarray
    sigma: np.ndarray
    b: np.ndarray                             # (changed: added)
    adjustment_covariance: np.ndarray         # (changed: added) Var(a) = S A' (A S A')^+ A S
    constraint_covariance: np.ndarray         # (changed: added) V = A S A'
    constraint_covariance_pinv: np.ndarray    # (changed: added) V^+
    redundant: np.ndarray                     # (changed: added) bool per measurement
    max_constraint_violation: float           # (changed: added)
    names: tuple[str, ...] | None = None              # (changed: added)
    constraint_names: tuple[str, ...] | None = None   # (changed: added)
    @property
    def n(self) -> int
    @property
    def n_constraints(self) -> int
    @property
    def rank(self) -> int                     # alias of dof
    def measurement_names(self) -> list[str]  # defaults to x0, x1, ...
    def constraint_labels(self) -> list[str]  # defaults to c0, c1, ...
    def to_dict(self) -> dict[str, Any]

def reconcile_table(flows: pandas.DataFrame, edges, sigma_col="sigma", value_col="value", *,
                    edge_col: str = "edge", nodes=None, environment: str = "ENV",
                    b=None, edge_names=None) -> pandas.DataFrame
    # columns: edge, source, target, value, sigma, adjusted, adjustment,
    #          standardized_adjustment, redundant
    # attrs: objective, dof, n_constraints, node_names, max_constraint_violation

def project_unmeasured(A: np.ndarray, unmeasured: Sequence[int], b=None, *,
                       rcond: float = DEFAULT_RCOND,
                       zero_tol: float = PROJECTION_ZERO_TOL
                       ) -> tuple[np.ndarray, np.ndarray, np.ndarray]   # (changed: new)
    # Crowe's projection: (A_reduced, b_reduced, measured_column_indices)
```

(changed during implementation:

- `ReconciliationResult` carries the matrices the downstream tests need rather than making
  them recompute a pseudo-inverse. `gross_error.nodal_test` needs `constraint_covariance` to
  standardise an imbalance; `global_test` needs `dof`; `measurement_test` needs `redundant`
  to know which measurements were testable at all. `b`, `adjustment_covariance`,
  `constraint_covariance_pinv` and `max_constraint_violation` complete the record so a result
  can be audited without re-running the fit; `max_constraint_violation` is the numerical
  check that `A x_hat = b` really holds.
- `names` and `constraint_names` are carried through so the gross-error tables can be read
  by a human. `measurement_names()` and `constraint_labels()` supply `x0, x1, ...` and
  `c0, c1, ...` defaults, which is what fixes the `name` column of those tables.
- `standardized_adjustments` is `nan`, and `redundant` is `False`, for a measurement whose
  column of `A S` vanishes: no constraint can move it, `Var(a)_ii` is exactly zero, and the
  standardized adjustment is undefined rather than infinite. `REDUNDANCY_TOL` is the relative
  tolerance for that decision.
- `eq=False` on the dataclass: the fields are numpy arrays, so a generated `__eq__` would
  raise on truth-value ambiguity.
- `incidence_matrix` accepts named edges (triples or a mapping) as well as bare pairs.
  Parallel unnamed edges between the same two nodes get `#2`, `#3` suffixes, which is what
  makes `reconcile_table` able to match rows to edges by label. An isolated node is an error,
  since its row would be an empty constraint.
- `project_unmeasured` is new and is the correct meaning of "treat a measurement as
  unmeasured": partition `A = [A_m A_u]` and left-multiply by a basis of the left null space
  of `A_u` (Crowe, Garcia Campos and Hrymak 1983). Deleting a column while keeping the row
  would assert that the flow is *zero*, which is a different and usually false claim.
  `serial_elimination` uses it. Observability of the eliminated variables is not assessed.
- The four tolerance constants are module-level and documented, because every one of them is
  a judgement about what counts as numerical dust and a project may need to defend or change
  it. `PROJECTION_ZERO_TOL` in particular is scaled by a single global `max(1, max|A_m|)`,
  which assumes `A` has coefficients of comparable magnitude.
- Non-finite input is rejected everywhere in this module; see the conventions note.)

## `reconcile/gross_error.py`

```python
Correction = Literal["sidak", "bonferroni", "none"]
Elimination = Literal["project", "column"]        # (changed: new)
NODAL_VARIANCE_TOL: float = 1e-12                 # (changed: exposed)
EMPTY_ROW_TOL: float = 1e-12                      # (changed: exposed)

def critical_z(alpha: float, n_tests: int,
               correction: Correction = "sidak") -> tuple[float, float]   # (changed: new)
    # returns (critical value on the z scale, per-test level beta)

def global_test(res: ReconciliationResult, alpha: float = 0.05) -> TestResult
    # gamma = r' (A S A')^+ r ~ chi2(rank A)
    # details: alternative, dof, critical, reject, alpha, n_constraints, n_dropped

def measurement_test(res: ReconciliationResult, alpha: float = 0.05,
                     correction: Correction = "sidak", *,
                     n_tests: int | None = None) -> pandas.DataFrame   # (changed: n_tests)
    # per-measurement z_i = a_i / sqrt(Var(a)_ii); flag |z_i| > z_{1 - beta/2}
    # columns: [index, name, adjustment, z, abs_z, critical, flag]
    # attrs: alpha, beta, correction, critical, n_tests, n_redundant, dof

def nodal_test(res: ReconciliationResult, alpha: float = 0.05, *,
               correction: Correction = "none") -> pandas.DataFrame  # (changed: correction)
    # per-constraint z_j = r_j / sqrt((A S A')_jj)
    # columns: [index, name, residual, z, abs_z, critical, flag]
    # attrs: alpha, beta, correction, critical, n_tests

def serial_elimination(y, A, sigma, b=None, alpha=0.05, max_removals=None, *,
                       correction: Correction = "sidak",
                       names: Sequence[str] | None = None,
                       constraint_names: Sequence[str] | None = None,
                       elimination: Elimination = "project",
                       rcond: float = DEFAULT_RCOND) -> list[GrossErrorSuspect]
    # iteratively drop the measurement with the largest |z| (treat it as unmeasured: Crowe's
    # projection, so the constraint rows are recombined and the unknown flow cancels) until
    # global_test passes, max_removals is reached, or no constraint row is left.

@dataclass(frozen=True)
class GrossErrorSuspect:
    index: int
    name: str
    z: float
    order_removed: int
    critical: float = float("nan")             # (changed: added)
    objective_before: float = float("nan")     # (changed: added)
    objective_after: float = float("nan")      # (changed: added)
    pvalue_before: float | None = None         # (changed: added)
    pvalue_after: float | None = None          # (changed: added)
    dof_before: int = -1                       # (changed: added)
    dof_after: int = -1                        # (changed: added)
    global_reject_after: bool = True           # (changed: added)
    def to_dict(self) -> dict[str, Any]
```

**Column lists.** `measurement_test` and `nodal_test` both return
`[index, name, adjustment|residual, z, abs_z, critical, flag]`.
(changed during implementation: `abs_z` is an extra column. `abs_z = |z|` is the
"higher = more suspicious" score this contract requires, and it is what a shortlist is
sorted by; `z` keeps its sign, which carries the direction (negative means the reported value
was pulled *down* by reconciliation, positive that it was pulled up). Neither column can
replace the other, so both are returned. Rows stay in measurement or constraint order, so
sorting is the caller's explicit act. `z` and `abs_z` are `nan`, and `flag` is `False`, for a
measurement that is not redundant or a constraint whose residual variance is zero.)

**Family size.** (changed during implementation: `measurement_test` now sizes the
multiple-comparison family by the number of **testable** measurements, those with a finite
`z`, rather than by all `res.n` measurements. A non-redundant measurement has
`Var(a)_ii = 0`, cannot be moved by any constraint, and is never tested; counting it inflates
the Sidak or Bonferroni critical value and costs power on the measurements that *are*
testable. This also makes the two tables consistent: `nodal_test` has always counted only
testable constraints. The old convention remains available by passing
`n_tests=res.n` explicitly, and `n_tests=table.attrs["n_redundant"]` gives the
redundancy-based count; the family size actually used is recorded in `attrs["n_tests"]`.)

(changed during implementation, the rest:

- `critical_z(alpha, n_tests, correction)` is factored out and public, returning both the
  critical value and the per-test level `beta`, so a project can report the level split it
  ran at, and so the two tables and `serial_elimination` cannot drift apart.
- `nodal_test` gained a `correction` keyword defaulting to `"none"`, which is the test as
  published and as this contract fixed it: each node tested at level `alpha`. Pass `"sidak"`
  or `"bonferroni"` to control the family-wise error over the whole network instead.
- `global_test` handles a system with no redundancy (`dof == 0`) by reporting `pvalue = 1.0`
  and `critical = inf`, so `reject` is `False`, rather than dividing by a zero degree of
  freedom.
- `serial_elimination` gained `elimination`, `names`, `constraint_names`, `correction` and
  `rcond`. `elimination="project"` (the default) is Crowe's projection; `elimination="column"`
  is the naive column deletion, kept only for comparison, and it raises when a constraint row
  would be left with no measured variable. Running out of removable measurements or of
  constraint rows is a *stopping condition*, not an error: the suspects found so far are
  returned, with the last one's `objective_after = nan`, `pvalue_after = None`,
  `dof_after = 0` and `global_reject_after = True`, meaning the imbalance was never shown to
  be explained.
- `GrossErrorSuspect` gained the before/after global-test record. Each removal also removes a
  measured variable, so the degrees of freedom fall as the procedure runs; without
  `dof_before`/`dof_after` and the objective and p-value on both sides of a removal there is
  no way to tell a removal that fixed the imbalance from one that merely used up a
  constraint. `global_reject_after` on the last suspect is the summary of whether the
  elimination succeeded.
- Non-finite input is rejected, as in `balance`; `details["n_dropped"]` is therefore always
  0 here.)

Known stale docstring, to be fixed in code rather than here: `measurement_test`'s
`n_tests` parameter text still says the default is `res.n`. The code defaults to the number
of testable measurements, as described above.

---

## `labels/pu.py`

```python
class ElkanNotoPU(BaseEstimator, ClassifierMixin):   # Elkan & Noto 2008, KDD
    def __init__(self, base_estimator=None, hold_out_ratio: float = 0.2, random_state=None,
                 hold_out_unlabeled: bool = True)          # (changed: hold_out_unlabeled)
    def fit(self, X, s) -> ElkanNotoPU   # s in {1 labeled positive, 0 unlabeled}
    def predict_proba(self, X)           # [[1 - p, p]], p = clip(g(x)/c_, 0, 1)
    def decision_function(self, X)       # g(x)/c_ unclipped
    def predict(self, X)                 # (changed: added) hard labels at 0.5
    c_: float                            # estimated P(s=1|y=1)
    prior_: float                        # estimated P(y=1), clipped to [0, 1]
    prior_unclipped_: float              # (changed: added) the same ratio without the clip
    estimator_: Any                      # (changed: added) the fitted g
    hold_out_indices_: np.ndarray        # (changed: added)
    hold_out_unlabeled_indices_: np.ndarray   # (changed: added)
    classes_: np.ndarray                 # always array([0, 1])
    n_features_in_: int
    n_positive_: int
    n_unlabeled_: int

class BaggingPU(BaseEstimator, ClassifierMixin):     # Mordelet & Vert 2014, Pattern Recognit. Lett.
    def __init__(self, base_estimator=None, n_estimators: int = 50, k: int | None = None,
                 random_state=None, bootstrap: bool = True)     # (changed: bootstrap)
    def fit(self, X, s) -> BaggingPU     # each round: all positives vs a subsample of k unlabeled
    def decision_function(self, X, *, use_oob: bool = False)    # (changed: use_oob)
    def predict_proba(self, X)           # (changed: added)
    def predict(self, X)                 # (changed: added)
    oob_scores_: np.ndarray              # nan where a row was never out of bag
    oob_counts_: np.ndarray              # (changed: added)
    X_train_: np.ndarray                 # (changed: added)
    estimators_: list                    # (changed: added)
    score_kind_: str                     # (changed: added) "decision_function" | "predict_proba"
    k_: int                              # (changed: added)
    classes_: np.ndarray
    n_features_in_: int
    n_positive_: int
    n_unlabeled_: int

def estimate_class_prior(scores_labeled: ArrayLike, scores_unlabeled: ArrayLike,
                         method: Literal["elkan_noto"] = "elkan_noto",
                         *, clip: bool = True) -> float          # (changed: clip)
```

(changed during implementation:

- **`BaggingPU.decision_function` does not automatically return out-of-bag scores.** The
  contract annotated it "mean out-of-bag score for unlabeled; mean score for new X". As built
  it returns the plain bagged mean for every row, and the contracted behaviour is available
  through `use_oob=True`. The reason is that `X` carries no row identity: an estimator cannot
  know that a row it is asked to score is the same observation it trained on. Making the
  split automatic would mean matching on feature values on every call, and would make a row's
  score depend on whether an identical row happened to be in the training set. `oob_scores_`,
  indexed by training row and `nan` where no out-of-bag score exists, is the primary and
  unambiguous out-of-bag surface, and is what the unlabeled training pool should be ranked
  by.
- `hold_out_unlabeled` on `ElkanNotoPU` defaults to `True`, which holds out the same fraction
  of unlabeled rows as of positives. This removes the hold-out *dilution* bias: deleting only
  the held-out positives drops the labelled share of the training set from `c` to about
  `c (1 - hold_out_ratio)`, shrinking `g` and hence `c_` by the same factor. `False`
  reproduces the positives-only split of the widely copied reference implementations, which
  carries that bias. The intrinsic *overlap* bias of the `e1` estimator is unaffected by
  either setting.
- `prior_unclipped_` exists because a `prior_` of exactly 1.0 or 0.0 is a failure signal, not
  an estimate: it means the raw ratio left the unit interval and was clipped. The same
  reasoning gives `estimate_class_prior` its `clip` keyword, and its docstring says so.
- `bootstrap` on `BaggingPU` selects whether the `k` unlabeled points are drawn with
  replacement. Which of the two Mordelet and Vert used is recalled from a secondary summary
  and is flagged as unconfirmed in the docstring, so the choice is a parameter rather than an
  unstated assumption.
- `predict` and `predict_proba` are implemented on both classes because `ClassifierMixin`
  advertises them; `BaggingPU.predict_proba` averages the base estimators' probabilities and
  its docstring warns that each round is trained on an artificially balanced set, so `p` is
  not calibrated to the population prior.
- The `__sklearn_tags__` override on both classes exists only because this contract fixes the
  base-class order `(BaseEstimator, ClassifierMixin)`, which would otherwise leave the
  estimator type unset and make `sklearn.base.is_classifier` return `False`.
- `estimate_class_prior` drops non-finite scores before averaging; because it returns a bare
  float there is nowhere to report the dropped count, so the docstring states it instead.)

---

## `eval/metrics.py`

```python
Gains = Literal["binary", "exponential"]

def roc_auc(y_true, scores) -> float
def average_precision(y_true, scores) -> float
def precision_at_k(y_true, scores, k: int | float) -> float   # k int = count, float in (0,1) = fraction
def recall_at_k(y_true, scores, k: int | float) -> float
def ndcg_at_k(y_true, scores, k: int | float, gains: Gains = "binary") -> float
    # DCG = sum rel_i / log2(i + 1), i = 1..k; IDCG from ideal ordering. Bao et al. (2020)
    # report NDCG@k with k = 1% of test firm-years, so fractional k is supported.
def rank_metrics(y_true, scores, ks=(0.01, 0.05, 0.10), *,
                 gains: Gains = "binary", include_global: bool = True) -> dict[str, float]
def bootstrap_metric(metric: Callable, y_true, scores, n_boot=499, alpha=0.05, seed=None,
                     *, stratified: bool = False) -> BootstrapResult

@dataclass(frozen=True)
class BootstrapResult:
    point: float
    se: float
    ci_low: float
    ci_high: float
    draws: np.ndarray
    method: str
    n_boot: int
    alpha: float = 0.05     # (changed: added)
    n_failed: int = 0       # (changed: added)
    def to_dict(self) -> dict[str, Any]
```

`rank_metrics` keys: `"roc_auc"`, `"average_precision"`, and per cut-off
`"precision@<k>"`, `"recall@<k>"`, `"ndcg@<k>"`, where `<k>` is the integer count (`"5"`)
or the percentage for a fractional k (`"1%"`, `"10%"`).

(changed during implementation:

- `eval.metrics.BootstrapResult` is a second, separate type from
  `bunching.inference.BootstrapResult`. It shares the field names so the two tabulate
  together, but it adds `alpha` (the interval level, without which a stored interval cannot
  be read) and `n_failed` (replicates discarded because the metric was undefined on that
  resample, typically a draw with no positives). A large `n_failed` means the interval is
  unreliable, and silently returning a narrower interval computed from fewer draws would hide
  that. The two types are kept separate so the subpackages do not import each other.
- `stratified` on `bootstrap_metric` resamples positives and negatives separately, holding
  the base rate fixed. It answers a different question and gives narrower intervals, so it is
  off by default.
- `include_global` on `rank_metrics` allows scoring an all-positive or all-negative sample on
  the `@k` metrics alone; `roc_auc` and `average_precision` require both classes and raise
  otherwise.
- `k` semantics are enforced, not inferred: an int is a count, a float strictly inside
  `(0, 1)` is a fraction of `n` (`ceil`, floored at 1). A float such as `5.0` is rejected
  rather than silently read as a count, because the two meanings are not interchangeable.
  An int `k` greater than `n` raises.
- `precision_at_k` divides by `k` and never by `min(k, n_pos)`, so a list with fewer than `k`
  positives cannot reach 1.0. It is defined (and 0.0) with no positives at all;
  `recall_at_k` and `ndcg_at_k` raise there, because they are not.
- Ties keep input order (stable sort) in the `@k` metrics; `roc_auc` and `average_precision`
  are delegated to scikit-learn and are tie-order independent.
- Non-finite labels or scores raise; see the conventions note.)

## `eval/harness.py`

```python
SplitKind = Literal["temporal", "group_kfold", "anchor_holdout", "none"]

@dataclass
class Dataset:
    unit_id: pandas.Series          # unique per row
    X: pandas.DataFrame             # features (rows align with unit_id, positionally and by index)
    y: pandas.Series | None = None  # 1 confirmed distortion, 0 presumed clean, NaN unlabeled
    groups: pandas.Series | None = None    # e.g. year / province / firm for grouped splits
    time: pandas.Series | None = None      # for temporal splits
    meta: dict = field(default_factory=dict)   # project, description, anchor events
    def __len__(self) -> int                   # (changed: added)
    @property
    def n(self) -> int                         # (changed: added)
    @property
    def name(self) -> str                      # (changed: added) meta["name"], else meta["project"]
    def y_values(self) -> np.ndarray           # (changed: added) float array, NaN unlabeled
    def take(self, positions) -> Dataset       # (changed: added) positional subset
    def labeled(self) -> Dataset
    def positives(self) -> Dataset

@runtime_checkable
class Detector(Protocol):
    name: str
    def fit(self, ds: Dataset) -> Detector      # may ignore labels (unsupervised)
    def score(self, ds: Dataset) -> np.ndarray  # higher = more suspicious, len == len(ds)

class FunctionDetector:   # wraps f(X: DataFrame) -> scores; fit is a no-op
    def __init__(self, func, name: str = "function", *, higher_is_suspicious: bool = True)
class SklearnDetector:    # wraps any estimator with decision_function / predict_proba
    def __init__(self, estimator, name: str | None = None, *,
                 score_method: Literal["auto","decision_function","predict_proba"] = "auto")
class PUDetector:         # wraps labels.pu estimators
    def __init__(self, kind: Literal["elkan_noto","bagging"] = "elkan_noto",
                 base_estimator=None, name: str | None = None, **estimator_kwargs)
    def pu_labels(self, ds: Dataset) -> np.ndarray

@dataclass
class EvalSpec:
    split: SplitKind = "temporal"
    train_end: Any = None           # temporal: last training period (inclusive)
    n_splits: int = 5               # group_kfold
    anchor_mask: pandas.Series | None = None    # anchor_holdout: rows that ARE the anchor
    ks: tuple[int | float, ...] = (0.01, 0.05, 0.10)
    metrics: tuple[str, ...] = ("roc_auc", "average_precision", "ndcg_at_k", "precision_at_k")
    def to_dict(self) -> dict[str, Any]         # (changed: added)

@dataclass
class EvalReport:
    detector: str; dataset: str; spec: EvalSpec
    metrics: dict[str, float]; per_fold: list[dict]; n_train: int; n_test: int; n_pos_test: int
    in_sample: bool = False        # (changed: added)
    notes: tuple[str, ...] = ()    # (changed: added)
    def to_dict(self) -> dict; def summary_table(self) -> pandas.DataFrame

def evaluate(detector: Detector, ds: Dataset, spec: EvalSpec) -> EvalReport
def transfer(detector: Detector, source: Dataset, target: Dataset,
             source_spec: EvalSpec | None = None, *,
             fit_on: Literal["labeled", "all"] = "labeled",   # (changed: added)
             max_calibration_points: int = 100                # (changed: added)
             ) -> TransferResult

@dataclass(frozen=True)
class TransferResult:
    scores: pandas.DataFrame        # unit_id, score, rank; sorted by score descending
    source_report: EvalReport | None
    calibration: pandas.DataFrame   # score_threshold, precision, recall, n_selected
    detector: str = ""              # (changed: added)
    source: str = ""                # (changed: added)
    target: str = ""                # (changed: added)
    n_source_fit: int = 0           # (changed: added)
    def to_dict(self) -> dict[str, Any]

DETECTOR_REGISTRY: dict[str, Callable[..., Detector]]
def register_detector(name: str, *, overwrite: bool = False) -> Callable   # (changed: overwrite)
def make_detector(name: str, /, **kw: Any) -> Detector                     # (changed: positional-only)
```

Built-in registry entries, registered at import: `"function"`, `"sklearn"`,
`"pu_elkan_noto"`, `"pu_bagging"`.
(changed during implementation: the contract left the registry empty; shipping the four
wrappers under stable names is what lets a project name a detector in configuration instead
of importing it.)

(changed during implementation, the rest:

- `PUDetector` treats **both** `y == 0` and `y is NaN` as unlabeled (`s = 0`), not only NaN.
  This is the point of PU learning with enforcement data: "not prosecuted" is not "clean", so
  a presumed-clean 0 must not enter the fit as a negative. `SklearnDetector` does the
  opposite, taking the 0s at face value, and the two are documented against each other so the
  choice is visible at the call site. `pu_labels(ds)` exposes the `s` vector that will be
  handed to the estimator, so the choice can be inspected rather than trusted.
- `TransferResult.calibration` has four columns, not three: `n_selected` is added because a
  precision of 1.0 over two selected rows and over two hundred are different claims, and the
  curve is thinned to at most `max_calibration_points` rows, so the reader cannot infer the
  count. Thresholds are the distinct observed scores (a threshold always selects whole tie
  groups), returned ascending. The curve is computed on the source rows the detector was
  fitted on, so it is in-sample and optimistic: it is a translation table for score levels,
  not a performance claim. `source_spec` is how an honest out-of-sample number is obtained.
- `fit_on="all"` on `transfer` fits on every source row rather than the labeled ones, which
  is what a `PUDetector` wants when the unlabeled pool is informative. The default
  `"labeled"` is the contracted behaviour.
- `EvalReport.in_sample` and `notes` exist so a number cannot be read without its warning:
  `split="none"` fits and scores the same rows, and folds skipped for want of both classes in
  the labeled test rows are recorded in `per_fold` with a reason and left out of the averages
  rather than silently dropped. `per_fold` entries carry `fold`, `n_train`, `n_test`
  (labeled test rows), `n_test_rows` (all test rows scored), `n_pos_test`, `metrics`,
  `test_unit_ids`, `skipped` and `reason`.
- `EvalSpec` validates in `__post_init__` (unknown split or metric name, `n_splits < 2`, an
  empty or mistyped `ks`) and accepts `"recall_at_k"` in `metrics` alongside the four
  contracted names. `EvalSpec.to_dict` summarises `anchor_mask` by its size rather than
  copying it.
- `Dataset` validates on construction: `X` must be a DataFrame, companion series must match
  in length and index, `unit_id` must be unique, and `y` may hold only 0, 1 or NaN. An index
  mismatch is an error rather than something pandas resolves silently, because silent
  alignment is how labels end up on the wrong rows. `take`, `y_values`, `n`, `name` and
  `__len__` are the accessors the harness itself needs and are part of the surface.
- `Detector` is `@runtime_checkable`, and `evaluate`, `transfer` and `make_detector` all
  check against it, so a detector missing `score` fails with a clear message instead of an
  `AttributeError` mid-fold. Detectors are deep-copied per fold, so folds cannot leak.
- `register_detector` refuses to overwrite an existing name unless `overwrite=True`, so two
  projects cannot silently claim the same key. `make_detector`'s `name` is positional-only so
  that `**kw` can carry a detector's own `name=` argument without colliding with the registry
  key.
- Scores are validated on the way out of every detector: wrong length or any non-finite value
  raises, naming the detector.)

---

## `provenance/manifest.py`

```python
SOURCES_FILENAME = "SOURCES.yaml"
FETCH_LOG_FILENAME = "fetch_log.jsonl"
Access = Literal["free", "registration", "paywalled", "archive_visit", "manual_transcription"]
Status = Literal["verified", "unverified", "blocked", "partial"]
ACCESS_VALUES: tuple[str, ...]
STATUS_VALUES: tuple[str, ...]
URL_OPTIONAL_ACCESS: frozenset[str] = frozenset({"archive_visit", "manual_transcription"})

class Source(pydantic.BaseModel):        # model_config = ConfigDict(extra="allow")
    id: str; name: str; provider: str; url: str | None
    access: Access; status: Status
    fetched_at: str | None = None; http_status: int | None = None
    sha256: str | None = None; bytes: int | None = None
    local_path: str | None = None; license: str | None = None
    notes: str = ""; blocked_reason: str | None = None
    evidence: str = ""                       # (changed: added)
    download_plan: str = ""                  # (changed: added)
    verification: dict[str, Any] | None = None   # (changed: added)

def load_sources(path) -> list[Source]
def save_sources(path, sources: list[Source]) -> None   # rewrite: comments are NOT preserved
def validate_sources(path) -> list[str]                 # [] if valid; else human-readable errors
def update_source(path, source_id: str, **fields) -> Source   # read-modify-write one entry

@dataclass(frozen=True)
class FetchRecord:
    source_id: str; url: str; tool: str; started_at: str; finished_at: str
    http_status: int | None; bytes: int | None; sha256: str | None
    local_path: str | None; error: str | None; skipped_cached: bool = False
    def to_dict(self) -> dict[str, Any]

def log_fetch(project_data_dir: Path, rec: FetchRecord) -> None   # append JSONL to <data>/fetch_log.jsonl
def sha256_file(path: Path, chunk: int = 1 << 20) -> str

class RateLimiter:                       # token bucket, per host, thread-safe
    def __init__(self, per_second: float, *, burst: float = 1.0,
                 monotonic=time.monotonic, sleep=time.sleep)   # (changed: burst, injection)
    def wait(self) -> None
def get_rate_limiter(host: str, *, root: Path | None = None) -> RateLimiter   # (changed: new)
def reset_rate_limiters() -> None                                             # (changed: new)

def fetch(url: str, dest: Path, *, project_data_dir: Path, source_id: str,
          headers: dict | None = None, resume: bool = False, max_bytes: int | None = None,
          force: bool = False, tool: str = "httpx", timeout: float | None = None,
          expected_sha256: str | None = None,
          allow_empty: bool = False,                       # (changed: added)
          require_registry: bool = True,                   # (changed: added)
          transport: httpx.BaseTransport | None = None,    # (changed: added)
          limiter: RateLimiter | None = None               # (changed: added)
          ) -> FetchRecord

def main(argv: Sequence[str] | None = None) -> int
    # CLI (console script `forensics-manifest`):
    #       validate <SOURCES.yaml>...   -> exit 1 on any error
    #       status   <SOURCES.yaml>...   -> table: project, id, access, status, bytes, blocked_reason
    #       sha256   <file>...
```

`fetch` still runs the six steps in order: `require_contact()` before any request (and it
validates the URL, the expected digest and the registry entry in the same breath, so whether
a bad call raises never depends on the state of the disk); never fetch twice; per-host rate
limiter and configured User-Agent; stream to `dest.part` with optional `Range` resume, rename
on success; always `log_fetch`, then `update_source`; return the `FetchRecord`. HTTP and
transport errors are reported through `FetchRecord.error` and never raise.

**Validation rules on `Source`.** (changed during implementation: the `verified` rule is no
longer "sha256 and local_path set". It now requires evidence of one of two things:

- a **successful probe**: `http_status` in `(200, 206)` together with a `fetched_at`
  timestamp. Nothing has been downloaded into the project; the source was reached during
  research and confirmed to be what it claims. `206` counts because a ranged request that
  returns Partial Content proves the file is there and served its first bytes, which is
  exactly how a large file is probed without downloading it.
- an **acquisition**: `local_path` is set, so the bytes are on disk.

The two-state meaning is the point. `local_path` is null until the acquisition pipeline runs,
so requiring it unconditionally would force every source a human confirmed by fetching to be
mislabelled as unverified until `make data` had run. A reader can now tell the two states
apart: `verified` with no `local_path` means probed during research, `verified` with a
`local_path` means acquired into `data/raw`.

Separately, and at **any** status: whenever `local_path` is set, `sha256` must be set too. A
file we hold must be checksummed; a path with no digest is an unfalsifiable claim about the
contents of a file. The other rules are unchanged: `blocked` requires a non-empty
`blocked_reason`, `unverified` requires `notes` saying what was tried, and `url` may be null
only when `access` is `archive_visit` or `manual_transcription`.)

**New fields.** (changed during implementation: `evidence`, `download_plan` and
`verification` were added because HARD RULE 1 is only enforceable if a reader can audit it.
`evidence` records what the fetch actually returned (status, bytes, content type, what the
content was seen to contain), which is the audit trail behind `status`. `download_plan`
records how an idempotent acquirer should fetch the source (URL pattern, pagination,
parameters, expected sizes, rate limits), or what a human must do when it is gated; it is
what `provenance.runner` acquirers are written from. `verification` holds the result of an
INDEPENDENT re-fetch: `verdict` (`confirmed`, `downgrade`, `refuted` or `not_verified`),
`reason`, `checked_at` and `hunt`. One agent asserting that a URL works is not evidence; this
is where the second opinion lives.)

(changed during implementation, the rest of the module:

- `Source` sets `extra="allow"`, so project-specific annotations survive a read-modify-write
  cycle; `validate_sources` warns about unknown keys with a `UserWarning` rather than
  failing, which is the only way one project can extend the shared schema without breaking
  the other three. `validate_sources` also reports duplicate ids, which `load_sources` alone
  would not catch.
- `save_sources` and `update_source` write through a temporary file plus `os.replace`, so a
  concurrent reader never sees a half-written registry. `update_source` re-validates only the
  entry it touches and writes the others back exactly as parsed, so one broken neighbour
  cannot block an unrelated update. Comments and blank lines are lost either way, which is
  why prose belongs in `notes`.
- `RateLimiter` gained `burst` and injectable `monotonic`/`sleep` (the latter so its timing
  can be tested without sleeping). The default `burst=1.0` is exactly "at most one request
  every `1/per_second` seconds", with no credit accumulated while idle. `get_rate_limiter`
  holds the process-wide per-host cache and rebuilds a limiter when the configured rate
  changes; `reset_rate_limiters` is the maintenance hook for a long-lived process whose
  configuration changed underneath it.
- `fetch` gained four keywords. `allow_empty` is off by default because an empty file
  recorded as `verified` with the digest of the empty string is a false integrity claim, and
  an empty body is far more often a captive portal or a truncated response than a real empty
  dataset. `require_registry` is on by default, so a source with no `SOURCES.yaml` entry
  cannot be fetched at all (HARD RULE 1 in executable form); set it `False` for a deliberate
  one-off that is logged but not registered. `transport` is how the test suite guarantees
  nothing reaches the network. `limiter` bypasses the shared per-host cache.
- On failure `fetch` classifies the status rather than blanket-marking a source unverified:
  `blocked` on 401/402/403/451 and on any 4xx other than 404 for a `paywalled` entry,
  `unverified` on 404, `partial` otherwise. A failure leaves `status` alone when the file the
  entry points at is still present and still matches its recorded digest, so a transient
  network error cannot demote a source that is actually held.
- `FetchRecord.skipped_cached` has a default of `False` and marks an attempt that made no
  request because the file was already present with the digest the registry records.)

`projects/*/data/SOURCES.yaml` is a YAML list of `Source` mappings. `local_path` is relative
to the project directory. Raw data never enters git; the registry does.

## `provenance/runner.py`  (changed during implementation: new module)

The shared acquisition CLI. Every project's `python -m <project>.acquire` is a thin shim that
delegates to `main` here, so all four projects behave identically: same flags, same output,
same exit codes, same refusal to invent anything. It was added because four hand-written
acquisition entry points had already started to diverge, and the divergence was in exactly
the behaviour that has to be uniform to be trustworthy (what counts as a skip, what counts as
a failure, whether the contact string is checked before or after twenty requests).

```python
NEEDS_HUMAN: set[str] = {"registration", "paywalled", "archive_visit", "manual_transcription"}
ATTEMPTABLE_STATUS: set[str] = {"verified", "partial"}

def plan(sources: Sequence[Source], acquirers: Mapping[str, Callable[..., Any]],
         only: Sequence[str] | None = None
         ) -> tuple[list[Source], list[tuple[Source, str]]]
    # returns (attempt, skipped) where each skipped entry carries its reason

def main(*, project: str, data_dir: Path, acquirers: Mapping[str, Callable[..., Any]],
         argv: Sequence[str] | None = None) -> int
```

**Acquirer contract.** `acquirers` maps a `Source.id` to a callable invoked as
`fn(source, data_dir)`, plus `force=<bool>` when the callable's signature accepts a `force`
keyword (directly or through `**kwargs`); the signature is inspected rather than the call
being wrapped in `except TypeError`, which would swallow a genuine `TypeError` raised inside
the acquirer and silently re-run it. The return value is printed and is treated as a success
only if `getattr(result, "ok", False)` is true. An exception from one acquirer is caught,
reported as `[FAIL] <id>: <type>: <message>`, and the run continues.

**Flags.**

- `ids...` (positional): acquire exactly these source ids. An id that is not in the registry
  prints an error and exits 1.
- `--all`: acquire every attemptable source. Either `--all` or at least one id is required.
- `--list`: print the registry (sorted by status then id, with `*` marking ids that have an
  acquirer) and exit 0 without making any request.
- `--force`: passed on to acquirers that accept it, to re-download a file already held.
- `--dry-run`: print `[dry] <id>: would fetch <url>` for each attemptable source and fetch
  nothing. The contact check is skipped, because nothing will be requested.

`--list` and `--dry-run` make no network requests and are the only acquisition commands that
are safe to run while HARD RULE 3 is in force.

**Skip rules** (from `plan`). A source is skipped, with its reason echoed, when:

- there is no acquirer registered for its id. The reason distinguishes the cases: `access` in
  `NEEDS_HUMAN` reports `needs a human, see data/ACCESS_NOTES.md`; `status == "blocked"`
  echoes the registry's own `blocked_reason`; `status == "unverified"` says existence was
  never confirmed, so there is nothing to fetch; otherwise it says plainly that no acquirer
  is implemented for this id, which is a gap in the pipeline rather than a property of the
  source.
- or, when no explicit ids were given, its `status` is `blocked`, its `status` is not in
  `ATTEMPTABLE_STATUS`, or its `access` is in `NEEDS_HUMAN`.

Naming ids explicitly overrides the status and access filters but not the missing-acquirer
check: a user who asks for a specific id gets a real attempt or a clear explanation. After
the run, the ids that need a human are listed again with a pointer to
`projects/<project>/data/ACCESS_NOTES.md`.

**Exit codes.** `0` when every attempted source succeeded, including a run consisting only of
gated sources (nothing failed; there was simply nothing a machine could do) and a `--list` or
`--dry-run`. `1` when any attempt failed, when the registry file does not exist, when a named
id is not in the registry, or when `require_contact()` raises (the run then prints
`REFUSING TO FETCH` and the actionable message, before any request). The contact string is
checked once, up front, and only when there is something to attempt.

**Encoding.** `main` reconfigures `sys.stdout` to UTF-8 with `errors="replace"` before doing
anything else. Registry entries legitimately carry Cyrillic and Chinese source names; on a
Windows console at the default code page, printing one raises `UnicodeEncodeError` and the
process dies before listing a single source. Degrading the display of a few names is strictly
better than failing to print anything at all. A stream that cannot be reconfigured (a pipe
under test, a captured buffer) is left alone.

Note: `runner` is not re-exported from `forensics_core.provenance`; import it as
`from forensics_core.provenance.runner import main` (or `plan`).
</content>
</invoke>
