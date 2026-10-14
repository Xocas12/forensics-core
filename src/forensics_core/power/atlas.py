"""Detection power as a function of sample size and effect size.

The single most valuable thing the calibration projects can hand the target project is not a
detector, it is a power curve. ``elections`` has about 95,000 precincts; ``gosplan`` will have
a few hundred sector-years. If integer-percentage excess has no power at n = 300 then gosplan
cannot use it, and knowing that before P4 saves a phase.

What a row of an atlas means
----------------------------
For a given method, sample size and effect size: draw ``n`` units from a population believed
clean, inject a distortion of that size with a mechanism the method did not help design, run
the method, and record whether it rejects at ``alpha``. Repeat. The rejection fraction is the
power.

The row at effect size zero is the **false-positive rate**, and it is not optional. A power
number without it cannot be read: a method that rejects everything has power 1.0 and is
useless. :func:`power_curve` always measures it and warns when it is far from nominal, and
:func:`minimum_detectable_effect` refuses to answer at a sample size where it is.

Far from nominal runs both ways. A rate far *above* nominal means rejections are partly the
method firing on nothing. A rate improbably far *below* it means either that the null the test
assumes does not match how the samples were drawn, or that the test is far more conservative
than its nominal level (a test that errors on most samples lands here too, because an error is
recorded as no rejection). Either way the power column is not the method's power at ``alpha``.
:func:`too_smooth_atlas` exists because of a case of the first kind: ``too_smooth_test``'s
default ``detrend="diff"`` run on the exchangeable samples :func:`power_curve` draws.

What this is not
----------------
This measures the power of a **test on a collection**, which is the question "at what sample
size can this method see an effect at all". It is not the ranking power of a per-unit detector,
which is a different question answered by the labelled projects through
``eval.harness.evaluate``. Both are needed and they are not interchangeable.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

    from forensics_core.dispersion.underdispersion import Detrend

#: The sample sizes the programme actually needs to span: from a Soviet sector-year panel at
#: the low end to a Russian precinct file at the high end.
DEFAULT_SAMPLE_SIZES: tuple[int, ...] = (50, 100, 300, 1000, 3000, 10000, 30000, 95000)

#: Columns :func:`power_curve` returns, in order.
ATLAS_COLUMNS = [
    "method",
    "n",
    "effect_size",
    "power",
    "power_se",
    "n_replicates",
    "alpha",
    "false_positive_rate",
]

#: A false-positive rate this far above nominal makes the power column unreadable, because
#: rejections are then partly the method firing on nothing.
FPR_TOLERANCE = 2.0

#: A false-positive rate this improbably far *below* nominal makes the power column unreadable
#: too. Under a calibrated test the rejections among ``n_replicates`` null draws are
#: Binomial(``n_replicates``, ``alpha``); a count whose lower-tail probability under that law is
#: below this level is flagged. A tail probability rather than a ratio, because "below half of
#: nominal" would flag a calibrated test 12 per cent of the time at 100 replicates, while this
#: flags one at most 1 time in 100 at any replicate count. The price is that it needs enough
#: replicates to say anything: below 90 replicates at ``alpha = 0.05`` not even zero rejections
#: is flagged.
FPR_LOW_TAIL = 0.01

#: The method name a too-smooth atlas starts with. The full name is ``too_smooth_<detrend>``,
#: the name :func:`~forensics_core.dispersion.underdispersion.too_smooth_test` reports itself.
TOO_SMOOTH_METHOD = "too_smooth"


class AtlasError(ValueError):
    """An atlas was asked for something it does not cover, or was built inconsistently."""


class AtlasCalibrationWarning(UserWarning):
    """A measured atlas has a zero-effect row whose false-positive rate is far from nominal.

    :func:`power_curve` warns at build time about exactly the sample sizes
    :func:`minimum_detectable_effect` will refuse, so the problem is visible to whoever reads
    the table and not only to whoever queries it.
    """


def _calibration_problem(n: int, fpr: float, alpha: float, n_replicates: float) -> str | None:
    """Why the zero-effect row at ``n`` makes the power column unreadable, or ``None``."""
    if not np.isfinite(fpr):
        return None
    if fpr > FPR_TOLERANCE * alpha:
        return (
            f"at n={n} the false-positive rate is {fpr:.3f} against a nominal {alpha:.3f}. "
            "The power column cannot be read while the method rejects this often on data "
            "with no injected effect."
        )
    if np.isfinite(n_replicates) and n_replicates > 0:
        from scipy import stats

        replicates = int(n_replicates)
        rejected = round(fpr * replicates)
        tail = float(stats.binom.cdf(rejected, replicates, alpha))
        if tail < FPR_LOW_TAIL:
            return (
                f"at n={n} the false-positive rate is {fpr:.3f} ({rejected} of {replicates} "
                f"null replicates rejected) against a nominal {alpha:.3f}, and a calibrated test "
                f"lands that low with probability {tail:.2g}. A rate this far below nominal means "
                "either that the null the test assumes does not match how the samples were "
                "drawn, or that the test is far more conservative than its nominal level; "
                f"either way the power column is not the method's power at alpha {alpha:.3f}."
            )
    return None


def _require_too_smooth_record(method: str, settings: Mapping[str, Any]) -> None:
    """Refuse a too-smooth atlas that does not say which ``detrend`` produced it.

    ``too_smooth_test`` answers a different question under each ``detrend``, and its default
    ``"diff"`` has essentially no power on the exchangeable samples :func:`power_curve` draws.
    A too-smooth number without its detrend beside it cannot be read, so every row carries it
    in the method name and the settings record it together with ``n_perm``.
    """
    if not method.startswith(TOO_SMOOTH_METHOD):
        return
    from typing import get_args

    from forensics_core.dispersion.underdispersion import Detrend

    detrend = settings.get("detrend")
    if (
        detrend not in get_args(Detrend)
        or method != f"{TOO_SMOOTH_METHOD}_{detrend}"
        or "n_perm" not in settings
    ):
        raise AtlasError(
            f"method {method!r} is a too-smooth atlas, which must record the detrend it ran "
            "with: name the method too_smooth_<detrend> and put 'detrend' and 'n_perm' in "
            f"settings (got settings={dict(settings)!r}). too_smooth_test answers a different "
            "question under each detrend, and its default 'diff' has essentially no power on "
            "the random-order samples power_curve draws. too_smooth_atlas records both."
        )


@dataclass(frozen=True)
class PowerSpec:
    """What one atlas was measured with, so two atlases are never silently compared.

    Estimator settings change power, so an atlas computed with different ones is a different
    atlas. Everything here is recorded beside the numbers.
    """

    method: str
    alpha: float
    n_replicates: int
    seed: int | None
    settings: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "alpha": self.alpha,
            "n_replicates": self.n_replicates,
            "seed": self.seed,
            "settings": dict(self.settings),
        }


def power_curve(
    population: np.ndarray,
    test: Callable[[np.ndarray], float],
    injector: Callable[[np.ndarray, float, np.random.Generator], np.ndarray],
    *,
    method: str,
    effect_sizes: Sequence[float],
    sample_sizes: Sequence[int] = DEFAULT_SAMPLE_SIZES,
    n_replicates: int = 200,
    alpha: float = 0.05,
    seed: int | None = 0,
    settings: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Measure power over a grid of sample sizes and effect sizes.

    Parameters
    ----------
    population : array
        Units believed clean, drawn from without replacement. Must be at least as large as the
        biggest requested sample size.
    test : callable
        ``test(sample) -> p-value``. Anything returning a p-value works; wrap a ``TestResult``
        with ``lambda s: my_test(s).pvalue``.
    injector : callable
        ``injector(sample, effect_size, rng) -> sample``. Must implement the *mechanism*, not
        the test run backwards; see :mod:`forensics_core.inject`. At effect size zero it must
        be a no-op, which this function checks.
    effect_sizes : sequence of float
        Zero is added if absent, because the false-positive row is what makes the rest
        readable.

    Returns
    -------
    pandas.DataFrame
        One row per ``(n, effect_size)`` with :data:`ATLAS_COLUMNS`. ``.attrs["spec"]`` carries
        the :class:`PowerSpec`.

    Raises
    ------
    AtlasError
        If the population is too small for the largest sample, the injector is not a no-op
        at effect size zero, or ``method`` names a too-smooth atlas (``too_smooth...``) without
        recording its ``detrend`` and ``n_perm`` (see :func:`too_smooth_atlas`).

    Warns
    -----
    AtlasCalibrationWarning
        For every sample size whose zero-effect row is far above nominal, or improbably far
        below it (:data:`FPR_LOW_TAIL`). These are the sample sizes
        :func:`minimum_detectable_effect` will refuse.
    """
    import pandas as pd

    _require_too_smooth_record(method, settings or {})

    pop = np.asarray(population, dtype=float)
    pop = pop[np.isfinite(pop)]
    sizes = sorted({int(n) for n in sample_sizes})
    effects = sorted({float(e) for e in effect_sizes} | {0.0})

    if not sizes:
        raise AtlasError("no sample sizes given")
    if pop.size < max(sizes):
        raise AtlasError(
            f"the population has {pop.size} usable values but the largest requested sample is "
            f"{max(sizes)}. Sampling is without replacement, because sampling with it would "
            "duplicate units and understate the variance the test is measuring."
        )

    rng = np.random.default_rng(seed)
    probe = pop[: min(pop.size, 1000)]
    if not np.allclose(injector(probe, 0.0, np.random.default_rng(0)), probe, equal_nan=True):
        raise AtlasError(
            "the injector is not a no-op at effect size zero, so the false-positive row would "
            "not measure the false-positive rate"
        )

    rows: list[dict[str, Any]] = []
    fpr_by_n: dict[int, float] = {}
    for n in sizes:
        for effect in effects:
            reject = 0
            for _ in range(n_replicates):
                sample = rng.choice(pop, size=n, replace=False)
                if effect != 0.0:
                    sample = injector(sample, effect, rng)
                try:
                    p = float(test(sample))
                except (ValueError, ZeroDivisionError, FloatingPointError):
                    continue
                if np.isfinite(p) and p <= alpha:
                    reject += 1
            power = reject / n_replicates
            if effect == 0.0:
                fpr_by_n[n] = power
            rows.append(
                {
                    "method": method,
                    "n": n,
                    "effect_size": effect,
                    "power": power,
                    # binomial standard error of the rejection fraction
                    "power_se": float(np.sqrt(power * (1.0 - power) / n_replicates)),
                    "n_replicates": n_replicates,
                    "alpha": alpha,
                    "false_positive_rate": np.nan,
                }
            )

    frame = pd.DataFrame(rows, columns=ATLAS_COLUMNS)
    frame["false_positive_rate"] = frame["n"].map(fpr_by_n)
    frame.attrs["spec"] = PowerSpec(
        method=method,
        alpha=alpha,
        n_replicates=n_replicates,
        seed=seed,
        settings=dict(settings or {}),
    )
    problems = [
        problem
        for n in sizes
        if (problem := _calibration_problem(n, fpr_by_n[n], alpha, n_replicates)) is not None
    ]
    if problems:
        warnings.warn(
            f"the {method!r} atlas has a zero-effect row out of calibration, and "
            "minimum_detectable_effect will refuse these sample sizes:\n  " + "\n  ".join(problems),
            AtlasCalibrationWarning,
            stacklevel=2,
        )
    return frame


def too_smooth_atlas(
    population: np.ndarray,
    *,
    detrend: Detrend,
    effect_sizes: Sequence[float],
    sample_sizes: Sequence[int] = DEFAULT_SAMPLE_SIZES,
    n_perm: int = 199,
    n_replicates: int = 200,
    alpha: float = 0.05,
    seed: int | None = 0,
    settings: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Power of :func:`~forensics_core.dispersion.underdispersion.too_smooth_test` against
    smoothing, with the ``detrend`` it ran under recorded on every row.

    ``effect_size`` is the share of deviation variance removed: each sample goes through
    :func:`forensics_core.inject.inject_smoothing` with ``retain = 1 - effect_size``.

    ``detrend`` has no default, on purpose. :func:`power_curve` draws each sample without
    replacement and in random order, so every series the test sees here is exchangeable.
    ``"none"`` is the exact null for such a series. ``"diff"``, the test's own default, has
    essentially no power on it and a false-positive rate pinned near zero, and an atlas built
    that way reads as a weak, conservative test when the null simply does not match the
    samples. Choosing ``"none"`` does not make a result transfer to real series either: an
    honest series with positive lag-1 autocorrelation is not exchangeable in its levels, and
    that autocorrelation is what ``"none"`` tests for, so it rejects such a series; random-order
    samples cannot show that. Match ``detrend`` to how the population was
    generated, and quote it with every number.

    Every row's ``method`` is ``too_smooth_<detrend>``, the name the test reports itself, and
    the spec's settings record ``detrend``, ``n_perm`` and the injector beside the numbers.

    Parameters
    ----------
    population, effect_sizes, sample_sizes, n_replicates, alpha, seed
        As for :func:`power_curve`. ``effect_sizes`` must lie in ``[0, 1]``. ``seed`` also
        fixes the permutation seeds, so the atlas is reproducible from it.
    detrend : {"none", "linear", "diff"}
        Passed to ``too_smooth_test``. Required.
    n_perm : int, default 199
        Permutations per test. The smallest attainable p-value is ``1 / (n_perm + 1)``.
    settings : dict, optional
        Further settings to record, such as how the population was generated. They may not
        contradict ``detrend`` or ``n_perm``.

    Raises
    ------
    AtlasError
        On an unknown ``detrend``, an effect size outside ``[0, 1]``, or ``settings`` that
        contradict the measurement, before anything is measured.
    """
    from typing import get_args

    from forensics_core.dispersion.underdispersion import Detrend, too_smooth_test
    from forensics_core.inject import inject_smoothing

    if detrend not in get_args(Detrend):
        raise AtlasError(f"detrend must be one of {get_args(Detrend)}; got {detrend!r}")
    bad = [e for e in effect_sizes if not 0.0 <= float(e) <= 1.0]
    if bad:
        raise AtlasError(
            f"effect sizes {bad} are outside [0, 1]: a too-smooth effect size is the share of "
            "deviation variance removed, retain = 1 - effect_size"
        )
    record: dict[str, Any] = {
        "detrend": detrend,
        "n_perm": int(n_perm),
        "injector": "inject_smoothing(retain=1 - effect_size)",
    }
    extra = dict(settings or {})
    clash = {k: extra[k] for k in record if k in extra and extra[k] != record[k]}
    if clash:
        raise AtlasError(
            f"settings {clash} contradict the measurement, which records {record}; the record "
            "has to describe what was actually run"
        )

    # the permutation seeds come from their own stream, spawned from the same seed, so the atlas
    # is reproducible from ``seed`` without the permutations reusing the sampling draws
    perm_rng = np.random.default_rng(np.random.SeedSequence(seed).spawn(1)[0])

    def test(sample: np.ndarray) -> float:
        return too_smooth_test(
            sample, detrend=detrend, n_perm=n_perm, seed=int(perm_rng.integers(2**63))
        ).pvalue

    def injector(sample: np.ndarray, effect: float, rng: np.random.Generator) -> np.ndarray:
        return inject_smoothing(sample, retain=1.0 - effect)[0]

    return power_curve(
        population,
        test,
        injector,
        method=f"{TOO_SMOOTH_METHOD}_{detrend}",
        effect_sizes=effect_sizes,
        sample_sizes=sample_sizes,
        n_replicates=n_replicates,
        alpha=alpha,
        seed=seed,
        settings={**extra, **record},
    )


def minimum_detectable_effect(
    atlas: pd.DataFrame,
    n: int,
    *,
    target_power: float = 0.8,
    method: str | None = None,
    check_calibration: bool = True,
) -> float:
    """The smallest measured effect reaching ``target_power`` at sample size ``n``.

    This is the number a gosplan card quotes: "at the sample size available, this method can
    see an effect of at least X".

    Refuses rather than extrapolating. An atlas that does not cover ``n``, or whose measured
    effects never reach ``target_power`` there, raises. Silent extrapolation here would put an
    unearned number into a claim about the historical record, which is the specific failure
    this programme exists to avoid.

    Raises
    ------
    AtlasError
        If ``n`` is not in the atlas, no measured effect reaches the target, or the
        false-positive rate at that ``n`` is too far above nominal, or improbably far below it
        (:data:`FPR_LOW_TAIL`), for the power to be read.
    """
    frame = atlas if method is None else atlas[atlas["method"] == method]
    if frame.empty:
        raise AtlasError(f"the atlas has no rows for method {method!r}")

    at_n = frame[frame["n"] == int(n)]
    if at_n.empty:
        covered = sorted(frame["n"].unique())
        raise AtlasError(
            f"the atlas does not cover n={n}; it measured {covered}. It will not extrapolate: "
            "a power number invented between measured points is not a measurement."
        )

    if check_calibration:
        problem = _calibration_problem(
            int(n),
            float(at_n["false_positive_rate"].iloc[0]),
            float(at_n["alpha"].iloc[0]),
            float(at_n["n_replicates"].iloc[0]),
        )
        if problem is not None:
            raise AtlasError(
                f"{problem} Pass check_calibration=False to override, and say so wherever the "
                "number is reported."
            )

    reaching = at_n[(at_n["effect_size"] > 0) & (at_n["power"] >= target_power)]
    if reaching.empty:
        largest = float(at_n["effect_size"].max())
        best = float(at_n["power"].max())
        raise AtlasError(
            f"no measured effect reaches power {target_power} at n={n}; the largest effect "
            f"measured was {largest} and reached power {best:.2f}. The honest answer is that "
            "this method has no useful power at this sample size, not a number."
        )
    return float(reaching["effect_size"].min())


def detectable(
    atlas: pd.DataFrame,
    n: int,
    effect: float,
    *,
    target_power: float = 0.8,
    method: str | None = None,
) -> bool:
    """Whether an effect of that size is detectable at that sample size."""
    try:
        return effect >= minimum_detectable_effect(
            atlas, n, target_power=target_power, method=method
        )
    except AtlasError:
        return False


def save_atlas(atlas: pd.DataFrame, path: str | Path) -> Path:
    """Write an atlas to parquet, carrying its spec so it cannot be read without one."""
    import json

    try:
        import pyarrow  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised by the dev extra being present
        raise AtlasError(
            "saving an atlas needs pyarrow, which is an optional extra so that the library "
            "core stays small. Install it with: pip install 'forensics-core[parquet]'"
        ) from exc
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = atlas.copy()
    spec = atlas.attrs.get("spec")
    # pandas serialises DataFrame.attrs into the parquet metadata, and a PowerSpec is not JSON
    # serialisable, so the spec travels as a column instead and attrs is cleared on the copy.
    out.attrs = {}
    out["_spec"] = json.dumps(spec.to_dict() if spec else {})
    out.to_parquet(path, index=False)
    return path


def load_atlas(path: str | Path) -> pd.DataFrame:
    """Read an atlas back, restoring its spec into ``.attrs``."""
    import json

    import pandas as pd

    frame = pd.read_parquet(path)
    if "_spec" in frame.columns:
        raw = json.loads(frame["_spec"].iloc[0] or "{}")
        frame = frame.drop(columns=["_spec"])
        if raw:
            frame.attrs["spec"] = PowerSpec(
                method=raw.get("method", ""),
                alpha=float(raw.get("alpha", 0.05)),
                n_replicates=int(raw.get("n_replicates", 0)),
                seed=raw.get("seed"),
                settings=raw.get("settings", {}),
            )
    return frame
