"""Distortion injection: turn a series believed clean into a labelled test bed.

gosplan has one anchor, so power and false-positive rates cannot be estimated there from
labels. Injecting a distortion of known magnitude into data believed clean is the only way
to get an operating characteristic on the target's own data shape (ROADMAP.md, WO-102).

The one design rule that matters here: **an injector is not the estimator run backwards.**
``inject_rounding`` does not know what tolerance ``forensics_core.digits.integer_pct`` tests
at, and ``inject_bunching`` fits no counterfactual polynomial. Each injector implements the
mechanism -- what a person manufacturing the numbers would actually do to them -- and the
matching estimator must then recover the effect from the data alone. If an injector were
built from the test statistic that is supposed to catch it, every power curve built on it
would measure self-consistency between two halves of the same model and nothing else. The
test suite checks this the only way it can be checked from outside: a deliberately
mis-specified estimator must still recover a reduced but nonzero effect.

Discipline:

- Every injector is pure: no I/O, no globals, no plotting. Injection happens in memory,
  during evaluation. Injected data must never be written under any project's ``data/``
  directory, which also holds real observations.
- Every injector returns ``(values, InjectionRecord)``: a fresh array (the input is never
  mutated) and a record carrying the mechanism, the effect size, the indices actually
  changed and the seed. The record is what the power harness scores against, and it is what
  makes an injected dataset auditable rather than a black box.
- Randomness always flows through a ``seed: int | None`` argument to
  :func:`numpy.random.default_rng` (INTERFACES.md convention). Where a mechanism has no
  random component the seed is still accepted and recorded, so a stored record always
  answers the question "can this be reproduced?".

Effect sizes
------------
``fraction``   rounding: share of units snapped onto an integer percentage.
``mass``       bunching: share of the dominated-side window units moved just past the
               threshold; see the comparability note in :func:`inject_bunching`.
``magnitude``  padding: inflation applied to a contiguous block of periods.
``retain``     smoothing: fraction of the deviation variance left; ``1`` is the no-op.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np
from numpy.typing import ArrayLike

from forensics_core._types import jsonable

__all__ = [
    "InjectionRecord",
    "inject_bunching",
    "inject_padding",
    "inject_rounding",
    "inject_smoothing",
]

#: Which side of the threshold the manufactured pile-up sits on. Matches the ``side`` of
#: :class:`forensics_core.bunching.notch.Notch` and ``bunching_side`` of the estimator.
BunchSide = Literal["above", "below"]

#: How a block's inflation is applied: a ratio of the reported value, or an absolute amount.
PadMode = Literal["multiplicative", "additive"]

#: Absolute tolerance used when a position must be integer-valued (the padding block).
_POSITION_TOL = 1e-9


def _as_float_1d(x: ArrayLike, name: str) -> np.ndarray:
    """Coerce ``x`` to a 1-D float64 array, raising ``ValueError`` on unusable input.

    Injection needs finite values: a ``nan`` cannot be moved onto a threshold or snapped to
    an integer percentage, and silently dropping it would change the unit count the record
    is audited against, so non-finite input is rejected rather than dropped.
    """
    if hasattr(x, "to_numpy"):  # pandas Series / Index, including nullable dtypes
        try:
            arr = x.to_numpy(dtype=float, na_value=np.nan)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be numeric; got {type(x).__name__}") from exc
    else:
        try:
            arr = np.asarray(x, dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be numeric; got {type(x).__name__}") from exc
    if arr.ndim != 1:
        raise ValueError(f"{name} must be 1-D; got shape {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must be finite; injection is undefined on nan or inf")
    return np.asarray(arr, dtype=float)


def _check_share(name: str, value: float) -> float:
    """Validate an effect size that is a share of something: in ``[0, 1]`` and finite."""
    v = float(value)
    if not np.isfinite(v) or not 0.0 <= v <= 1.0:
        raise ValueError(f"{name} must lie in [0, 1]; got {value!r}")
    return v


def _changed(out: np.ndarray, original: np.ndarray, selected: np.ndarray) -> np.ndarray:
    """Ascending positions among ``selected`` where the value actually moved.

    A unit the mechanism selects but cannot change (a percentage that was already an
    integer, a tapered year still at factor 1) is not "touched" and is not recorded.
    """
    moved = selected[out[selected] != original[selected]]
    return np.sort(moved).astype(np.int64)


@dataclass(frozen=True, eq=False)
class InjectionRecord:
    """What was done to a series; the handle the power harness scores against.

    Attributes
    ----------
    mechanism : str
        ``"rounding"``, ``"bunching"``, ``"padding"`` or ``"smoothing"``.
    effect_size : float
        The injector's effect-size argument, verbatim: ``fraction`` for rounding, ``mass``
        for bunching, ``magnitude`` for padding, ``retain`` for smoothing. The mechanism
        name says which, because the four are not in one unit (WO-109 exists to build that
        vocabulary).
    indices : numpy.ndarray
        Positions (``int64``, ascending) where the returned series differs from the input.
    seed : int | None
        The seed the injection ran with; ``None`` is recorded as ``None``, and a
        deterministic mechanism records whatever it was given even though it uses nothing.
    """

    mechanism: str
    effect_size: float
    indices: np.ndarray
    seed: int | None

    def __eq__(self, other: object) -> bool:
        """Value equality, comparing ``indices`` elementwise.

        The generated ``__eq__`` cannot be used: comparing the ``indices`` arrays with ``==``
        returns an array, and the dataclass then calls ``bool()`` on it, which raises.

        Equality describes the INJECTION, not the run, so ``seed`` is deliberately excluded.
        Two records are equal when the same mechanism moved the same positions by the same
        effect size. A deterministic mechanism such as :func:`inject_padding` ignores its seed
        entirely, and two of its runs under different seeds produce byte-identical output; it
        would be incoherent to call those different injections. The seed is still carried on
        the record and in :meth:`to_dict` as provenance.
        """
        if not isinstance(other, InjectionRecord):
            return NotImplemented
        return (
            self.mechanism == other.mechanism
            and self.effect_size == other.effect_size
            and np.array_equal(self.indices, other.indices)
        )

    def __hash__(self) -> int:
        # indices is mutable, so it stays out of the hash; equality still checks it.
        return hash((self.mechanism, self.effect_size, int(self.indices.size)))

    def to_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))


# ----------------------------------------------------------------------------- rounding


def inject_rounding(
    values: ArrayLike, denominators: ArrayLike, *, fraction: float, seed: int | None = None
) -> tuple[np.ndarray, InjectionRecord]:
    """Snap ``fraction`` of the units onto an exactly integer percentage.

    The mechanism behind the sawtooth fingerprint that
    :mod:`forensics_core.digits.integer_pct` tests for (Kobak, Shpilkin and Pshenichnikov
    2016): a result manufactured to hit a target ("give him 65%") carries the numerator the
    target implies rather than the numerator a count produces. Each selected unit gets the
    nearest value whose percentage ``100 * value / denominator`` is exactly an integer: the
    percentage is rounded to the nearest integer (ties to even, numpy's rule) and the value
    recomputed from it. The percentage therefore moves by at most half a percentage point,
    which is what the mechanism costs; nothing constrains the total of ``values`` and no
    total is claimed.

    The injector knows nothing about any estimator: no tolerance enters, so the percentages
    it produces are exactly on the integers rather than merely inside whatever band a test
    happens to use.

    Parameters
    ----------
    values, denominators : array-like
        Equal-length 1-D numeric arrays; ``values`` are the numerators, ``denominators``
        the (positive) denominators. Both must be finite.
    fraction : float
        Share of units to snap, in ``[0, 1]``; the number of units is the rounded product
        with the sample size, drawn without replacement by ``seed``. A unit already sitting
        on an integer percentage is selected like any other; the mechanism changes nothing
        for it and it is not listed in the record.
    seed : int, optional
        Seeds :func:`numpy.random.default_rng`, which selects the units.

    Returns
    -------
    (values, InjectionRecord)
        A fresh array and its record. ``rec.indices`` lists the units whose value moved.

    Raises
    ------
    ValueError
        If the inputs are mis-shaped, non-finite or non-positive in ``denominators``, or
        ``fraction`` is outside ``[0, 1]``.
    """
    v = _as_float_1d(values, "values")
    d = _as_float_1d(denominators, "denominators")
    if v.size != d.size:
        raise ValueError(
            f"values and denominators must have the same length; got {v.size} and {d.size}"
        )
    if v.size == 0:
        raise ValueError("values is empty; there is nothing to inject into")
    if np.any(d <= 0):
        raise ValueError("denominators must be positive: a percentage is undefined otherwise")
    frac = _check_share("fraction", fraction)

    out = v.copy()
    n_selected = round(frac * v.size)
    indices = np.empty(0, dtype=np.int64)
    if n_selected:
        rng = np.random.default_rng(seed)
        chosen = rng.choice(v.size, size=n_selected, replace=False)
        pct = 100.0 * v[chosen] / d[chosen]
        out[chosen] = np.round(pct) * d[chosen] / 100.0
        indices = _changed(out, v, chosen)
    return out, InjectionRecord("rounding", frac, indices, seed)


# ------------------------------------------------------------------------------ bunching


def inject_bunching(
    values: ArrayLike,
    *,
    threshold: float,
    mass: float,
    window: float,
    side: BunchSide = "above",
    seed: int | None = None,
) -> tuple[np.ndarray, InjectionRecord]:
    """Move a share of units from the dominated side of a threshold to just past it.

    The mechanism behind a notch or bonus paid at a reported target: units that would land
    just on the dominated side of ``threshold`` are rewritten to land just past it, where
    the reward is. With ``side="above"`` the dominated side is just below the threshold and
    the pile lands in ``[threshold, threshold + window)``; with ``side="below"`` it is the
    mirror image. The half-open reading matches :func:`forensics_core.bunching.density.
    bin_around`, so a value exactly at the threshold counts as above it: it belongs to the
    dominated pool under ``side="below"`` and is left alone under ``side="above"``.

    No counterfactual is fitted and no density is estimated here. The mechanism needs only
    the threshold, the window and a share of the units inside it; the polynomial that the
    bunching estimator fits to recover the effect is that estimator's business, and none of
    it enters this function.

    Parameters
    ----------
    values : array-like
        1-D numeric sample of the running variable (plan fulfilment, vote share, ...).
        Must be finite.
    threshold : float
        Location of the notch. Finite.
    mass : float
        Share of the dominated-side pool to move, in ``[0, 1]``; the number of movers is
        the rounded product with the pool size, drawn without replacement by ``seed``.
    window : float
        Half-width of the band involved, in the units of ``values``: movers are drawn from
        the dominated side within ``window`` of the threshold and land just past it within
        the same distance. Positive and finite.
    side : {"above", "below"}, default "above"
        Which side of the threshold the pile lands on. The default is the bonus notch (a
        reward paid iff the reported value reaches the threshold), the case this programme
        centres on.
    seed : int, optional
        Seeds :func:`numpy.random.default_rng`, which selects the movers and draws their
        new values.

    Returns
    -------
    (values, InjectionRecord)
        A fresh array and its record. ``rec.indices`` lists the movers.

    Raises
    ------
    ValueError
        If ``threshold`` or ``window`` is not finite, ``window`` is not positive, ``mass``
        is outside ``[0, 1]``, ``side`` is unknown, ``values`` is unusable, or ``mass > 0``
        with an empty dominated-side pool (the requested effect is impossible there).

    Notes
    -----
    **Effect size and comparability.** ``mass`` is a share of the dominated-side pool: a
    fabricator moves units, not counterfactuals. Since the pool sits inside the excluded
    window of the matching analysis, the mover count is (to within the units that were
    already past the threshold) the excess mass ``B`` in observation units, and the
    recovered ``normalized_excess`` is ``B`` divided by the mean counterfactual count per
    bin, which depends on the bin width. Run the estimator with ``bin_width=window`` and
    ``exclude_below=exclude_above=window`` -- one bin on each side, so the pool is one
    bin's worth -- and the recovered ``normalized_excess`` is directly comparable with
    ``mass``; the test suite checks the two agree to within the polynomial fit error. At
    any other bin width the two differ by that width's share of the window and must be
    converted before they are compared (the common vocabulary is WO-109's job).
    """
    thr = float(threshold)
    if not np.isfinite(thr):
        raise ValueError(f"threshold must be finite; got {threshold!r}")
    w = float(window)
    if not np.isfinite(w) or w <= 0.0:
        raise ValueError(f"window must be a positive finite number; got {window!r}")
    m = _check_share("mass", mass)
    if side not in ("above", "below"):
        raise ValueError(f"side must be 'above' or 'below'; got {side!r}")
    v = _as_float_1d(values, "values")
    if v.size == 0:
        raise ValueError("values is empty; there is nothing to inject into")

    if side == "above":
        pool = np.flatnonzero((v >= thr - w) & (v < thr))
        dest_lo, dest_hi = thr, thr + w
    else:
        pool = np.flatnonzero((v >= thr) & (v < thr + w))
        dest_lo, dest_hi = thr - w, thr
    n_move = round(m * pool.size)
    if m > 0 and pool.size == 0:
        raise ValueError(
            f"no units on the dominated side of {thr:g} within window={w:g}; the requested "
            "mass cannot be injected here"
        )

    out = v.copy()
    indices = np.empty(0, dtype=np.int64)
    if n_move:
        rng = np.random.default_rng(seed)
        movers = rng.choice(pool, size=n_move, replace=False)
        out[movers] = rng.uniform(dest_lo, dest_hi, size=n_move)
        indices = _changed(out, v, movers)
    return out, InjectionRecord("bunching", m, indices, seed)


# ------------------------------------------------------------------------------- padding


def inject_padding(
    values: ArrayLike,
    *,
    years: ArrayLike,
    magnitude: float,
    mode: PadMode = "multiplicative",
    taper: int = 0,
    seed: int | None = None,
) -> tuple[np.ndarray, InjectionRecord]:
    """Inflate a contiguous block of periods by ``magnitude``.

    The padding mechanism of the programme's anchor episode (the Uzbek cotton affair of
    1978-1983: reported output padded across roughly a decade) and of the admitted Chinese
    episodes the P3 gate tests (ROADMAP.md): the reported level of a block of years is
    raised, leaving the rest of the series alone.

    ``taper`` spreads the onset over the first years of the block, so the block does not
    begin with the discontinuity a naive break test would find for the wrong reason -- the
    detector should fire on the padding, not on the seam. With ``taper=k > 0`` the block's
    first year is left at factor 1 and the inflation ramps linearly to its full value at
    the ``k``-th year of the block, staying there; the last year of the block always
    carries the full magnitude.

    The mechanism is deterministic: given the block and ``magnitude`` there is nothing left
    to draw. ``seed`` is accepted and recorded for interface uniformity, and two calls that
    differ only in seed return identical output.

    Parameters
    ----------
    values : array-like
        1-D series in time order. Must be finite.
    years : array-like of int
        Positions into ``values`` forming the block: distinct, in range, and contiguous
        (each consecutive pair one apart). Any order is accepted. A caller holding calendar
        years maps them to positions first, e.g. ``np.arange(20, 36)``.
    magnitude : float
        Size of the inflation, finite and ``>= 0``. Multiplicatively it multiplies the
        block by ``1 + magnitude`` (``0.3`` inflates by 30 percent); additively it adds
        ``magnitude`` in the units of ``values``.
    mode : {"multiplicative", "additive"}, default "multiplicative"
        How the inflation is applied. Multiplicative inflation preserves the relative shape
        inside the block exactly (with ``taper=0``); additive inflation shifts it.
    taper : int, default 0
        Number of leading years of the block over which the inflation ramps up linearly;
        ``0`` applies the full magnitude from the first year of the block.
    seed : int, optional
        Recorded in the output; the mechanism uses no randomness.

    Returns
    -------
    (values, InjectionRecord)
        A fresh array and its record. ``rec.indices`` lists the years whose value moved; a
        tapered year still at factor 1 is not listed.

    Raises
    ------
    ValueError
        If ``values`` is unusable, ``magnitude`` is negative or non-finite, ``mode`` is
        unknown, ``taper`` is negative or not an integer, or ``years`` is empty, holds
        duplicates or non-integer positions, reaches outside ``values``, or is not
        contiguous.
    """
    v = _as_float_1d(values, "values")
    if v.size == 0:
        raise ValueError("values is empty; there is nothing to inject into")
    mag = float(magnitude)
    if not np.isfinite(mag) or mag < 0:
        raise ValueError(f"magnitude must be finite and >= 0; got {magnitude!r}")
    if mode not in ("multiplicative", "additive"):
        raise ValueError(f"mode must be 'multiplicative' or 'additive'; got {mode!r}")
    if taper < 0 or int(taper) != taper:
        raise ValueError(f"taper must be a non-negative integer; got {taper!r}")
    taper_n = int(taper)

    pos_f = _as_float_1d(years, "years")
    if pos_f.size == 0:
        raise ValueError("years is empty; a block must name at least one position")
    if np.any(np.abs(pos_f - np.round(pos_f)) > _POSITION_TOL):
        raise ValueError("years must be integer positions into values")
    pos = np.round(pos_f).astype(np.int64)
    if np.unique(pos).size != pos.size:
        raise ValueError("years must be distinct positions")
    pos = np.sort(pos)
    if pos[0] < 0 or pos[-1] >= v.size:
        raise ValueError(
            f"years reach outside values: positions {pos[0]}..{pos[-1]} for length {v.size}"
        )
    if pos.size > 1 and np.any(np.diff(pos) != 1):
        raise ValueError("years must form one contiguous block")

    out = v.copy()
    if taper_n:
        ramp = np.minimum(np.arange(pos.size, dtype=float), float(taper_n)) / taper_n
    else:
        ramp = np.ones(pos.size, dtype=float)
    if mode == "multiplicative":
        out[pos] = v[pos] * (1.0 + mag * ramp)
    else:
        out[pos] = v[pos] + mag * ramp
    indices = _changed(out, v, pos)
    return out, InjectionRecord("padding", mag, indices, seed)


# ------------------------------------------------------------------------------ smoothing


def _local_trend(v: np.ndarray) -> np.ndarray:
    """Centred three-point moving average; endpoints average their two available points.

    This is the injector's own local level, deliberately not any fit the underdispersion
    tests would recognise: :func:`forensics_core.dispersion.underdispersion.
    variance_floor_test` is handed a variance floor from outside the data, and
    :func:`forensics_core.dispersion.underdispersion.too_smooth_test` detrends by
    differencing or by a linear trend, neither of which is a three-point average.
    """
    t = np.empty_like(v)
    t[1:-1] = (v[:-2] + v[1:-1] + v[2:]) / 3.0
    t[0] = (v[0] + v[1]) / 2.0
    t[-1] = (v[-2] + v[-1]) / 2.0
    return t


def inject_smoothing(
    values: ArrayLike, *, retain: float, seed: int | None = None
) -> tuple[np.ndarray, InjectionRecord]:
    """Shrink deviations from a local trend so the series keeps its level and loses variance.

    The "too clean" mechanism that :mod:`forensics_core.dispersion.underdispersion` tests
    for: a series is rewritten around its own local level with less noise than the
    underlying process permits. The local trend is the centred three-point moving average
    of the input (see :func:`_local_trend`), and each value becomes

    ``trend + sqrt(retain) * (value - trend)``

    so the variance of the deviations from the local trend is exactly ``retain`` of what it
    was. ``retain=1`` is the no-op (bit-exact); ``retain=0`` replaces the series with the
    local trend itself. The series keeps its level: the trend path is part of the output at
    every ``retain``, and the noise around it is all that shrinks.

    Nothing here runs an estimator backwards: the trend is the data's own three-point
    average, not a model any underdispersion test fits, and no variance floor enters the
    mechanism.

    Parameters
    ----------
    values : array-like
        1-D series in time order, at least three values. Must be finite.
    retain : float
        Fraction of the deviation variance left, in ``[0, 1]``. The deviations themselves
        are scaled by ``sqrt(retain)``: variance is quadratic in the scaling.
    seed : int, optional
        Recorded in the output; the mechanism is deterministic.

    Returns
    -------
    (values, InjectionRecord)
        A fresh array and its record. ``rec.indices`` lists the positions whose value
        moved; a position already exactly on the local trend does not move and is not
        listed.

    Raises
    ------
    ValueError
        If fewer than three values remain, a value is non-finite, or ``retain`` is outside
        ``[0, 1]``.
    """
    v = _as_float_1d(values, "values")
    if v.size < 3:
        raise ValueError(f"inject_smoothing needs at least 3 values; got {v.size}")
    keep = _check_share("retain", retain)
    trend = _local_trend(v)
    # written as v + (sqrt(retain) - 1) * (v - trend) so that retain == 1 adds exactly 0
    # and the no-op is bit-exact rather than correct up to a rounding of (v - trend).
    out = v + (np.sqrt(keep) - 1.0) * (v - trend)
    indices = _changed(out, v, np.arange(v.size))
    return out, InjectionRecord("smoothing", keep, indices, seed)
