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
useless. :func:`power_curve` always measures it, and :func:`power_lookup` refuses to answer
from an atlas whose false-positive rate is far from nominal.

A test that refuses to answer has not answered
----------------------------------------------
A replicate on which the test raises (too few units left after exclusion, a counterfactual that
cannot be fitted) is neither a rejection nor a non-rejection. Counting it as a non-rejection
pulls both power and the false-positive rate towards zero by the refusal share, which can hide
a test that rejects five times nominal under the calibration guard. So power and the
false-positive rate are computed over the replicates that answered, and the refusals are
reported beside them in ``n_failed`` and ``refusal_share``. A cell where no replicate answered
has power ``NaN``: there is nothing to read.

What this is not
----------------
This measures the power of a **test on a collection**, which is the question "at what sample
size can this method see an effect at all". It is not the ranking power of a per-unit detector,
which is a different question answered by the labelled projects through
``eval.harness.evaluate``. Both are needed and they are not interchangeable.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

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
    "n_failed",
    "refusal_share",
]

#: The columns that record refusals. An atlas saved before they existed lacks them; it loads
#: with them set to ``NaN`` ("not recorded"), never to zero, which would be a claim.
REFUSAL_COLUMNS = ("n_failed", "refusal_share")

#: A false-positive rate this far above nominal makes the power column unreadable, because
#: rejections are then partly the method firing on nothing.
FPR_TOLERANCE = 2.0


class AtlasError(ValueError):
    """An atlas was asked for something it does not cover, or was built inconsistently."""


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
        the :class:`PowerSpec`. ``power`` and ``false_positive_rate`` are fractions of the
        replicates on which ``test`` answered; ``n_failed`` counts the replicates on which it
        raised ``ValueError``, ``ZeroDivisionError`` or ``FloatingPointError``, and
        ``refusal_share`` is ``n_failed / n_replicates``. A cell with no answered replicate has
        ``power`` (and, at effect zero, ``false_positive_rate``) ``NaN``.

    Raises
    ------
    AtlasError
        If the population is too small for the largest sample, or the injector is not a no-op
        at effect size zero.
    """
    import pandas as pd

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
            failed = 0
            for _ in range(n_replicates):
                sample = rng.choice(pop, size=n, replace=False)
                if effect != 0.0:
                    sample = injector(sample, effect, rng)
                try:
                    p = float(test(sample))
                except (ValueError, ZeroDivisionError, FloatingPointError):
                    # a refusal is not a non-rejection; see the module docstring
                    failed += 1
                    continue
                if np.isfinite(p) and p <= alpha:
                    reject += 1
            power, power_se = rejection_fraction(reject, n_replicates - failed)
            if effect == 0.0:
                fpr_by_n[n] = power
            rows.append(
                {
                    "method": method,
                    "n": n,
                    "effect_size": effect,
                    "power": power,
                    "power_se": power_se,
                    "n_replicates": n_replicates,
                    "alpha": alpha,
                    "false_positive_rate": np.nan,
                    "n_failed": failed,
                    "refusal_share": failed / n_replicates if n_replicates else np.nan,
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
    return frame


def rejection_fraction(rejections: int, answered: int) -> tuple[float, float]:
    """``(fraction, binomial standard error)`` over the replicates that answered.

    ``(nan, nan)`` when none answered: a cell where the test never gave an answer has no
    rejection rate, and zero would be a claim that it never rejects.
    """
    if answered <= 0:
        return float("nan"), float("nan")
    fraction = rejections / answered
    return fraction, float(np.sqrt(fraction * (1.0 - fraction) / answered))


def minimum_detectable_effect(
    atlas: pd.DataFrame,
    n: int,
    *,
    target_power: float = 0.8,
    method: str | None = None,
    check_calibration: bool = True,
    max_refusal_share: float | None = None,
) -> float:
    """The smallest measured effect reaching ``target_power`` at sample size ``n``.

    This is the number a gosplan card quotes: "at the sample size available, this method can
    see an effect of at least X".

    Refuses rather than extrapolating. An atlas that does not cover ``n``, or whose measured
    effects never reach ``target_power`` there, raises. Silent extrapolation here would put an
    unearned number into a claim about the historical record, which is the specific failure
    this programme exists to avoid.

    Parameters
    ----------
    max_refusal_share : float, optional
        When given, a cell whose test refused on more than this share of its replicates is
        not used: the false-positive row at ``n`` refuses the query outright, and an effect
        row is skipped as unmeasured. ``None`` (the default) applies no share limit, though a
        false-positive row on which the test never answered is always refused.

    Raises
    ------
    AtlasError
        If ``n`` is not in the atlas, no measured effect reaches the target, the
        false-positive rate at that ``n`` is too far above nominal for the power to be read,
        or the false-positive rate at that ``n`` was not measured because the test refused.
    """
    if max_refusal_share is not None and not 0.0 <= max_refusal_share <= 1.0:
        raise AtlasError(f"max_refusal_share must be in [0, 1]; got {max_refusal_share}")
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

    if "refusal_share" in at_n.columns:
        shares = at_n["refusal_share"].astype(float)
        zero_shares = shares[at_n["effect_size"] == 0.0]
        zero_share = float(zero_shares.max()) if not zero_shares.empty else float("nan")
        if np.isfinite(zero_share) and (
            zero_share >= 1.0 or (max_refusal_share is not None and zero_share > max_refusal_share)
        ):
            raise AtlasError(
                f"at n={n} the test refused on {zero_share:.0%} of the replicates with no "
                "injected effect, so the false-positive rate there is not measured well enough "
                "to read the power column. A refusal is not a non-rejection."
            )
        if max_refusal_share is not None:
            at_n = at_n[~(shares > max_refusal_share)]

    if check_calibration:
        fpr = float(at_n["false_positive_rate"].iloc[0])
        alpha = float(at_n["alpha"].iloc[0])
        if np.isfinite(fpr) and fpr > FPR_TOLERANCE * alpha:
            raise AtlasError(
                f"at n={n} the false-positive rate is {fpr:.3f} against a nominal {alpha:.3f}. "
                "The power column cannot be read while the method rejects this often on data "
                "with no injected effect. Pass check_calibration=False to override, and say "
                "so wherever the number is reported."
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


def with_refusal_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """``frame`` with :data:`REFUSAL_COLUMNS` present, added as ``NaN`` if it predates them.

    ``NaN`` means "not recorded": an atlas measured before refusals were counted may have
    counted them as non-rejections, and filling zero would claim it did not.
    """
    missing = [column for column in REFUSAL_COLUMNS if column not in frame.columns]
    if not missing:
        return frame
    out = frame.copy()
    for column in missing:
        out[column] = np.nan
    return out


def load_atlas(path: str | Path) -> pd.DataFrame:
    """Read an atlas back, restoring its spec into ``.attrs``."""
    import json

    import pandas as pd

    frame = with_refusal_columns(pd.read_parquet(path))
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
