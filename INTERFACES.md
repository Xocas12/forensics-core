# forensics_core — interface contract

This file fixes the public signatures of the shared library so that the four projects (and
parallel implementers) build against one stable surface. **Implementations may add keyword
arguments with defaults; they may not rename or remove anything listed here.** Where a
function is marked `STUB`, ship the signature, a docstring citing the method, and raise
`NotImplementedError("...")` with a one-line description of what remains.

Conventions that apply everywhere:

- Inputs are `numpy.typing.ArrayLike` (1-D unless stated) or `pandas` objects. Functions are
  pure: no global state, no I/O, no plotting. Non-finite values are dropped and the count of
  dropped values goes into `details["n_dropped"]`.
- Every test returns `forensics_core.TestResult` (or a frozen dataclass that *contains* one
  or more `TestResult`s and has `.to_dict()`). `pvalue` is two-sided unless
  `details["alternative"]` says `"less"` or `"greater"`.
- `weights` means observation weights (e.g. precinct size). When accepted, expected counts
  and test statistics are weighted; `n` reports the unweighted count and
  `details["effective_n"]` the Kish effective sample size.
- Randomness always flows through a `seed: int | None` argument → `np.random.default_rng`.
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
    details: dict[str, Any]
    def to_dict(self) -> dict
```

## `forensics_core.config`

Already implemented. `find_repo_root()`, `load_config()`, `require_contact()` →
`HttpConfig(contact, user_agent_prefix, default_timeout_seconds, rate_limits, never_refetch)`
with `.user_agent(purpose)`, `.rate_limit_for(host)`, `.contact_is_placeholder`.

---

## `digits/benford.py`

```python
DigitPosition = Literal["first", "second", "first_two"]

def benford_expected(position: DigitPosition = "first") -> np.ndarray
    # first: P(d) = log10(1 + 1/d), d = 1..9
    # second: P(d) = sum_{k=1..9} log10(1 + 1/(10k + d)), d = 0..9
    # first_two: P(d) = log10(1 + 1/d), d = 10..99

def digit_support(position: DigitPosition) -> np.ndarray   # the digit labels, same order

def leading_digits(x: ArrayLike, position: DigitPosition = "first") -> np.ndarray
    # returns int array; nonpositive / non-finite → excluded (caller sees fewer values);
    # "second" requires at least two significant digits, else excluded.

def digit_frequencies(x, position="first", weights=None) -> DigitTable
    # DigitTable(digits, observed, expected, observed_prop, expected_prop, n, effective_n)

def benford_test(x, position="first", weights=None,
                 statistics=("chi2", "mad", "kuiper")) -> BenfordResult
    # BenfordResult(table: DigitTable, chi2: TestResult, mad: TestResult, kuiper: TestResult)
    # MAD conformity bands (Nigrini 2012, Table 6.x — implementer must cite exact table):
    #   first:     [0, .006) close, [.006, .012) acceptable, [.012, .015) marginal, else nonconformity
    #   second:    [0, .008), [.008, .010), [.010, .012)
    #   first_two: [0, .0012), [.0012, .0018), [.0018, .0022)
    #   → mad.details["conformity"] holds the band label
    # kuiper: V = D+ + D- on the cumulative digit distribution; p-value via the Kuiper
    #   asymptotic series (Stephens 1970) — document the approximation.
```

## `digits/terminal.py`

```python
def terminal_digits(x: ArrayLike, k: int = 1) -> np.ndarray
    # last k decimal digits of round(x); values must be integer-valued (raise otherwise)

def terminal_digit_test(x, k=1, weights=None) -> TestResult
    # chi-square vs uniform over 10**k cells; details: observed, expected, max_abs_dev,
    # cell with largest excess. method = f"terminal_digit_{k}_chi2"

def terminal_digit_pair_test(x, weights=None) -> TestResult
    # last two digits independent & uniform (Beber & Scacco 2012): chi-square on 100 cells
    # plus details["adjacent_pair_excess"] (00,11,22..99 and adjacent-digit pairs)
```

## `digits/integer_pct.py`  (Kobak, Shpilkin & Pshenichnikov 2016, Ann. Appl. Stat.)

```python
def percentage(numerator: ArrayLike, denominator: ArrayLike) -> np.ndarray   # 100*num/den; den<=0 → nan

def percentage_histogram(pct: ArrayLike, bin_width: float = 0.1,
                         weights=None, lo=0.0, hi=100.0) -> tuple[np.ndarray, np.ndarray]
    # bins centred so that every integer is a bin centre; returns (centres, counts)

def integer_excess(pct: ArrayLike, denominators: ArrayLike, *, tolerance: float = 0.05,
                   min_denominator: int = 100, neighbour_bins: int = 5,
                   n_mc: int = 200, seed=None, weights=None) -> IntegerExcessResult
    # Observed: number of observations within ±tolerance of an integer percentage.
    # Null: for each unit, re-draw the numerator as Binomial(den, num/den) (binomial noise
    #   model, KSP 2016 §2) n_mc times and recount → null mean/sd. Units with
    #   den < min_denominator are excluded (known trap: small precincts round honestly).
    # IntegerExcessResult(test: TestResult (z, one-sided p), observed, expected_mean,
    #   expected_sd, excess, per_integer: np.ndarray[101] of excess by integer,
    #   n_excluded_small, settings)

def integer_excess_by_group(pct, denominators, groups, **kw) -> pandas.DataFrame
    # one row per group with the fields above; used for region/year comparison
```

---

## `bunching/density.py`  (Chetty, Friedman, Olsen & Pistaferri 2011; Kleven & Waseem 2013)

```python
def bin_around(x: ArrayLike, threshold: float, bin_width: float,
               lo: float | None = None, hi: float | None = None,
               weights=None) -> tuple[np.ndarray, np.ndarray]
    # bin edges aligned so that `threshold` is an edge; returns (centres, counts)

def bunching_estimator(x: ArrayLike, threshold: float, *, bin_width: float,
                       exclude_below: float, exclude_above: float, poly_degree: int = 7,
                       lo=None, hi=None, integration_constraint: bool = False,
                       max_iter: int = 50, weights=None) -> BunchingResult
    # Fit counts_j = sum_k beta_k * centre_j^k + sum_{j in excluded} gamma_j 1[j] + e_j
    # Counterfactual in excluded window = polynomial part. Excess mass B = sum over
    # excluded bins below-or-at threshold of (observed - counterfactual); missing mass M =
    # same for bins above threshold. normalized_excess b = B / mean counterfactual count
    # per bin in the excluded window (Chetty et al. definition — state it).
    # integration_constraint=True: Chetty-style iterative upward shift of counts above the
    # threshold until B == M (mass conservation) — document convergence criterion.
    # BunchingResult(centres, counts, counterfactual, excluded_mask, excess_mass,
    #   missing_mass, normalized_excess, coefficients, threshold, settings)
```

## `bunching/notch.py`

```python
@dataclass(frozen=True)
class Notch:        # discontinuous payoff at threshold (e.g. bonus paid iff plan >= 100%)
    threshold: float
    side: Literal["above", "below"] = "above"   # where the reward lies
    label: str = ""

@dataclass(frozen=True)
class Kink:         # discontinuous slope (e.g. marginal bonus rate changes)
    threshold: float
    label: str = ""

def estimate_notch(x, notch: Notch, *, bin_width, exclude_below, exclude_above,
                   poly_degree=7, weights=None, **kw) -> BunchingResult
    # asymmetric window: bunching just on the rewarded side, hole (missing mass) on the
    # dominated side. Adds details["dominated_region"] = (threshold, threshold + exclude_above)

def estimate_kink(x, kink: Kink, *, bin_width, exclude_halfwidth, poly_degree=7,
                  weights=None, **kw) -> BunchingResult
    # symmetric window

def scan_candidate_notches(x, candidates: Sequence[float], *, bin_width, exclude_below,
                           exclude_above, poly_degree=7, weights=None,
                           side: Literal["above","below"]="above") -> pandas.DataFrame
    # "find the notch": one row per candidate threshold with excess_mass, missing_mass,
    # normalized_excess, n_in_window; sorted by normalized_excess descending.
    # Typical candidates: 100 (plan fulfilment), round vote shares, growth targets.
```

## `bunching/inference.py`

```python
def bootstrap_bunching(x, estimator: Callable[[np.ndarray], BunchingResult], *,
                       n_boot: int = 499, alpha: float = 0.05, seed=None,
                       method: Literal["residual", "pairs"] = "residual") -> BootstrapResult
    # residual: resample bin-level residuals (Chetty et al. 2011); pairs: resample units.
    # BootstrapResult(point, se, ci_low, ci_high, draws: np.ndarray, method, n_boot)

def placebo_test(x, threshold, estimator_factory: Callable[[float], Callable],
                 placebo_thresholds: Sequence[float]) -> TestResult
    # distribution of normalized_excess at placebo thresholds; p = share of placebos with
    # excess >= observed. details: placebo values.

def permutation_test(x, groups, statistic: Callable[[np.ndarray], float],
                     n_perm: int = 999, seed=None) -> TestResult
    # generic label-permutation test for group differences in any scalar statistic
```

---

## `dispersion/underdispersion.py`

```python
def dispersion_index(x: ArrayLike) -> float                       # var / mean

def variance_floor_test(x: ArrayLike, floor_variance: float, *, ddof: int = 1) -> TestResult
    # H0: Var(x) >= floor. Statistic (n-1) s^2 / floor ~ chi2(n-1) under Var = floor;
    # p = P(chi2 <= observed) (alternative="less"). details: s2, floor, ratio.

def implied_variance_floor(proxy: ArrayLike, elasticity: float) -> float
    # Var floor of an outcome that responds to a physical driver: elasticity^2 * Var(proxy).
    # E.g. yields vs rainfall. Document that this is a LOWER bound only if other shocks are
    # uncorrelated with the proxy.

def residual_underdispersion(series: ArrayLike, fitted: ArrayLike, floor_variance: float) -> TestResult
    # variance_floor_test on residuals series - fitted

def smoothness_ratio(series: ArrayLike) -> float
    # von Neumann ratio: mean squared successive difference / variance (≈2 for iid noise)

def too_smooth_test(series: ArrayLike, *, detrend: Literal["none","linear","diff"]="diff",
                    n_perm: int = 999, seed=None) -> TestResult
    # H0: successive changes are exchangeable. Statistic = smoothness_ratio; p from
    # permutation of successive differences (alternative="less": too smooth).

def rolling_variance_floor(series, floor_variance, window: int) -> pandas.DataFrame
    # per-window variance_floor_test results; flags where p < 0.05
```

## `dispersion/carlisle.py`  (Carlisle 2017, Anaesthesia 72:944; Carlisle & Loadsman 2017)

```python
def balance_pvalues(means: ArrayLike, sds: ArrayLike, ns: ArrayLike) -> float
    # one-way ANOVA p-value from group summary statistics (means, sds, ns of one variable)

def carlisle_test(means: np.ndarray, sds: np.ndarray, ns: np.ndarray,
                  *, method: Literal["stouffer", "fisher"] = "stouffer") -> CarlisleResult
    # rows = variables, cols = groups. Per-variable balance p-values; combined via
    # method; the "too good" direction is p-values piling up near 1.
    # CarlisleResult(per_variable: np.ndarray, combined: TestResult (alternative="greater"
    #   = too balanced), ks_uniformity: TestResult)

def combine_pvalues(p: ArrayLike, method="stouffer") -> TestResult
```

---

## `reconcile/balance.py`  (Narasimhan & Jordache 2000, ch. 3–5; Crowe 1996)

```python
def incidence_matrix(edges: Sequence[tuple[str, str]], nodes: Sequence[str] | None = None,
                     environment: str = "ENV") -> tuple[np.ndarray, list[str], list[str]]
    # A[node, edge] = +1 inflow, -1 outflow; the environment node is dropped
    # (sources/sinks are unconstrained). Returns (A, node_names, edge_names).

def reconcile(y: ArrayLike, A: np.ndarray, sigma: ArrayLike, b: ArrayLike | None = None
              ) -> ReconciliationResult
    # sigma: measurement std devs (1-D) or covariance (2-D). Weighted least squares with
    # linear constraints: x_hat = y - S A' (A S A')^-1 (A y - b), b defaults to 0.
    # ReconciliationResult(adjusted, adjustments, constraint_residuals, standardized_adjustments,
    #   objective, dof, A, sigma)  — standardized_adjustments = a_i / sqrt(Var(a)_ii),
    #   Var(a) = S A' (A S A')^-1 A S. Use pseudo-inverse if A S A' is singular; report rank.

def reconcile_table(flows: pandas.DataFrame, edges, sigma_col="sigma", value_col="value") -> pandas.DataFrame
    # convenience wrapper for a tidy flow table with columns [edge, value, sigma]
```

## `reconcile/gross_error.py`

```python
def global_test(res: ReconciliationResult, alpha: float = 0.05) -> TestResult
    # gamma = r' (A S A')^-1 r ~ chi2(rank A); details: critical value, reject

def measurement_test(res: ReconciliationResult, alpha: float = 0.05,
                     correction: Literal["sidak", "bonferroni", "none"] = "sidak") -> pandas.DataFrame
    # per-measurement z_i = a_i / sqrt(Var(a)_ii); flag |z_i| > z_{1 - beta/2},
    # beta = 1 - (1 - alpha)^(1/n) for sidak

def nodal_test(res: ReconciliationResult, alpha: float = 0.05) -> pandas.DataFrame
    # per-constraint z_j = r_j / sqrt((A S A')_jj)

def serial_elimination(y, A, sigma, b=None, alpha=0.05, max_removals=None) -> list[GrossErrorSuspect]
    # iteratively drop the measurement with the largest |z| (treat it as unmeasured: remove
    # its column and re-reconcile with the reduced system) until global_test passes.
    # GrossErrorSuspect(index, name, z, order_removed)
```

---

## `labels/pu.py`

```python
class ElkanNotoPU(BaseEstimator, ClassifierMixin):   # Elkan & Noto 2008, KDD
    def __init__(self, base_estimator=None, hold_out_ratio: float = 0.2, random_state=None)
    def fit(self, X, s)                # s ∈ {1 labeled positive, 0 unlabeled}
    def predict_proba(self, X)         # P(y=1|x) = g(x)/c, clipped to [0, 1]
    def decision_function(self, X)     # g(x)/c unclipped
    c_: float                          # estimated P(s=1|y=1)
    prior_: float                      # estimated P(y=1)

class BaggingPU(BaseEstimator, ClassifierMixin):     # Mordelet & Vert 2014, Pattern Recognit. Lett.
    def __init__(self, base_estimator=None, n_estimators: int = 50, k: int | None = None,
                 random_state=None)
    def fit(self, X, s)                # each round: all positives vs bootstrap of K unlabeled
    def decision_function(self, X)     # mean out-of-bag score for unlabeled; mean score for new X
    oob_scores_: np.ndarray

def estimate_class_prior(scores_labeled: ArrayLike, scores_unlabeled: ArrayLike,
                         method: Literal["elkan_noto"] = "elkan_noto") -> float
```

---

## `eval/metrics.py`

```python
def roc_auc(y_true, scores) -> float
def average_precision(y_true, scores) -> float
def precision_at_k(y_true, scores, k: int | float) -> float     # k int = count, float in (0,1) = fraction
def recall_at_k(y_true, scores, k) -> float
def ndcg_at_k(y_true, scores, k, gains: Literal["binary", "exponential"] = "binary") -> float
    # DCG = sum rel_i / log2(i + 1), i = 1..k; IDCG from ideal ordering. Bao et al. (2020)
    # report NDCG@k with k = 1% of test firm-years — support fractional k.
def rank_metrics(y_true, scores, ks=(0.01, 0.05, 0.10)) -> dict[str, float]
def bootstrap_metric(metric: Callable, y_true, scores, n_boot=499, alpha=0.05, seed=None) -> BootstrapResult
```

## `eval/harness.py`

```python
@dataclass
class Dataset:
    unit_id: pandas.Series          # unique per row
    X: pandas.DataFrame             # features (rows align with unit_id)
    y: pandas.Series | None         # 1 confirmed distortion, 0 presumed clean, NaN unlabeled
    groups: pandas.Series | None    # e.g. year / province / firm for grouped splits
    time: pandas.Series | None      # for temporal splits
    meta: dict                      # project, description, anchor events
    def labeled(self) -> "Dataset"; def positives(self) -> "Dataset"

class Detector(Protocol):
    name: str
    def fit(self, ds: Dataset) -> "Detector"      # may ignore labels (unsupervised)
    def score(self, ds: Dataset) -> np.ndarray    # higher = more suspicious, len == len(ds)

class FunctionDetector:   # wraps f(X: DataFrame) -> scores; fit is a no-op
class SklearnDetector:    # wraps any estimator with decision_function / predict_proba
class PUDetector:         # wraps labels.pu estimators; treats NaN y as unlabeled

@dataclass
class EvalSpec:
    split: Literal["temporal", "group_kfold", "anchor_holdout", "none"] = "temporal"
    train_end: Any = None           # temporal: last training period (inclusive)
    n_splits: int = 5               # group_kfold
    anchor_mask: pandas.Series | None = None    # anchor_holdout: rows that ARE the anchor
    ks: tuple = (0.01, 0.05, 0.10)
    metrics: tuple = ("roc_auc", "average_precision", "ndcg_at_k", "precision_at_k")

@dataclass
class EvalReport:
    detector: str; dataset: str; spec: EvalSpec
    metrics: dict[str, float]; per_fold: list[dict]; n_train: int; n_test: int; n_pos_test: int
    def to_dict(self) -> dict; def summary_table(self) -> pandas.DataFrame

def evaluate(detector: Detector, ds: Dataset, spec: EvalSpec) -> EvalReport
def transfer(detector: Detector, source: Dataset, target: Dataset,
             source_spec: EvalSpec | None = None) -> TransferResult
    # fit on source (all labeled rows), score target; carry over the source-calibrated
    # score→precision curve so a target score can be read as "on the source project a score
    # this high had precision p". TransferResult(scores: pandas.DataFrame[unit_id, score, rank],
    #   source_report: EvalReport | None, calibration: pandas.DataFrame[score_threshold, precision, recall])

DETECTOR_REGISTRY: dict[str, Callable[[], Detector]]
def register_detector(name: str) -> Callable   # decorator
def make_detector(name: str, **kw) -> Detector
```

---

## `provenance/manifest.py`

```python
Access = Literal["free", "registration", "paywalled", "archive_visit", "manual_transcription"]
Status = Literal["verified", "unverified", "blocked", "partial"]

class Source(pydantic.BaseModel):
    id: str; name: str; provider: str; url: str | None
    access: Access; status: Status
    fetched_at: str | None = None; http_status: int | None = None
    sha256: str | None = None; bytes: int | None = None
    local_path: str | None = None; license: str | None = None
    notes: str = ""; blocked_reason: str | None = None
    # validators: blocked ⇒ blocked_reason non-empty; verified ⇒ sha256 and local_path set;
    # unverified ⇒ notes must say what was tried.

def load_sources(path) -> list[Source]
def save_sources(path, sources: list[Source]) -> None        # stable key order, preserves comments? (no: rewrite; note it)
def validate_sources(path) -> list[str]                       # [] if valid; else human-readable errors
def update_source(path, source_id: str, **fields) -> Source   # read-modify-write one entry

@dataclass(frozen=True)
class FetchRecord:
    source_id: str; url: str; tool: str; started_at: str; finished_at: str
    http_status: int | None; bytes: int | None; sha256: str | None
    local_path: str | None; error: str | None; skipped_cached: bool

def log_fetch(project_data_dir: Path, rec: FetchRecord) -> None   # append JSONL to <data>/fetch_log.jsonl
def sha256_file(path: Path, chunk: int = 1 << 20) -> str

class RateLimiter:                       # token bucket, per host, thread-safe
    def __init__(self, per_second: float); def wait(self) -> None

def fetch(url: str, dest: Path, *, project_data_dir: Path, source_id: str,
          headers: dict | None = None, resume: bool = False, max_bytes: int | None = None,
          force: bool = False, tool: str = "httpx", timeout: float | None = None,
          expected_sha256: str | None = None) -> FetchRecord
    # 1. require_contact()  — raises ContactNotConfigured (HARD RULE 6) before any request
    # 2. never fetch twice: if dest exists and SOURCES.yaml has sha256 for source_id and
    #    not force → log a skipped_cached record and return
    # 3. per-host RateLimiter from config; User-Agent from config
    # 4. stream to dest.part, Range-resume if resume and .part exists, rename on success
    # 5. ALWAYS log_fetch (success, HTTP error, exception); then update_source(...)
    #    with fetched_at/http_status/sha256/bytes/local_path/status (verified on 200,
    #    blocked with reason on 401/403/paywall, unverified on 404)
    # 6. return FetchRecord

def main(argv=None) -> int
    # CLI:  validate <SOURCES.yaml>...   → exit 1 on any error
    #       status   <SOURCES.yaml>...   → table: project, id, access, status, bytes, blocked_reason
    #       sha256   <file>...
```

`projects/*/data/SOURCES.yaml` is a YAML list of `Source` mappings. `local_path` is relative
to the project directory. Raw data never enters git; the registry does.
