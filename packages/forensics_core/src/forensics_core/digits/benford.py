"""Benford's-law digit tests for the first, second and first-two digits.

The law itself is due to Newcomb, S. (1881), "Note on the frequency of use of the different
digits in natural numbers", *American Journal of Mathematics* 4(1): 39-40, and Benford, F.
(1938), "The law of anomalous numbers", *Proceedings of the American Philosophical Society*
78(4): 551-572. The forensic apparatus around it (first-two-digit test, MAD conformity
bands) follows Nigrini, M. J. (2012), *Benford's Law: Applications for Forensic Accounting,
Auditing, and Fraud Detection*, Wiley, chapter 6.

Three statistics are offered, because they fail differently:

``chi2``
    Pearson goodness of fit. Powerful, but its p-value collapses to zero for large ``n``
    even under forensically irrelevant deviations ("excess power", Nigrini 2012 ch. 6).
``mad``
    Mean absolute deviation between observed and expected digit proportions. It does not
    depend on ``n``, which is why Nigrini reads it against fixed conformity bands rather
    than a p-value.
``kuiper``
    Kuiper's V (Kuiper, N. H. 1960, "Tests concerning random points on a circle",
    *Proc. Koninklijke Nederlandse Akademie van Wetenschappen* A 63: 38-47), which is
    sensitive to a shift of the whole digit distribution rather than to a single cell.

All functions here are pure: no I/O, no globals, no plotting.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import numpy as np
from numpy.typing import ArrayLike

from forensics_core._types import TestResult, jsonable
from forensics_core.digits._common import (
    as_float_array,
    chi2_goodness_of_fit,
    kish_effective_n,
    validate_weights,
    weighted_counts,
)

DigitPosition = Literal["first", "second", "first_two"]

#: Digit positions this module understands.
POSITIONS: tuple[str, ...] = ("first", "second", "first_two")

#: Upper edges of the "close", "acceptable" and "marginally acceptable" MAD bands.
#:
#: Nigrini (2012), *Benford's Law*, Wiley, chapter 6, section "Mean Absolute Deviation" (the
#: cut-offs are usually quoted from Table 6.1 of that chapter). TAKEN FROM A SECONDARY
#: RESTATEMENT of Nigrini's table (the tabulation carried in this project's interface
#: contract), NOT from the primary text: confirm the exact table number and the exact
#: cut-offs against Nigrini (2012) before quoting them anywhere.
MAD_BANDS: dict[str, tuple[float, float, float]] = {
    "first": (0.006, 0.012, 0.015),
    "second": (0.008, 0.010, 0.012),
    "first_two": (0.0012, 0.0018, 0.0022),
}

#: Band labels, ordered from most to least conforming.
MAD_LABELS: tuple[str, str, str, str] = (
    "close conformity",
    "acceptable conformity",
    "marginally acceptable conformity",
    "nonconformity",
)

_MAD_CITATION = (
    "Nigrini (2012), Benford's Law, Wiley, ch. 6 (MAD conformity bands). Cut-offs taken from "
    "a secondary restatement of Nigrini's table; confirm the exact table against the primary "
    "text."
)

_KUIPER_CITATION = (
    "Kuiper (1960); asymptotic tail probability from Stephens (1970), JRSS B 32(1): 115-122, "
    "in the form given by Press et al., Numerical Recipes 3rd ed., section 14.3 ('kuiper'). "
    "The series assumes a continuous null; on a discrete digit support it is conservative "
    "(p-values biased upwards). Confirm against Stephens (1970) before quoting."
)

#: Relative tolerance used to decide whether a float carries a second significant digit.
SIGNIFICANCE_RTOL = 1e-12


def _check_position(position: str) -> str:
    if position not in POSITIONS:
        raise ValueError(f"position must be one of {POSITIONS}; got {position!r}")
    return position


def digit_support(position: DigitPosition = "first") -> np.ndarray:
    """Digit labels for ``position``, in the order used by every array in this module.

    Parameters
    ----------
    position : {"first", "second", "first_two"}
        Digit position.

    Returns
    -------
    numpy.ndarray
        ``1..9`` for ``"first"``, ``0..9`` for ``"second"``, ``10..99`` for ``"first_two"``.
    """
    _check_position(position)
    if position == "first":
        return np.arange(1, 10, dtype=np.int64)
    if position == "second":
        return np.arange(0, 10, dtype=np.int64)
    return np.arange(10, 100, dtype=np.int64)


def benford_expected(position: DigitPosition = "first") -> np.ndarray:
    """Benford probabilities for a digit position.

    ``P(first = d) = log10(1 + 1/d)`` for ``d = 1..9`` (Benford 1938);
    ``P(second = d) = sum_{k=1..9} log10(1 + 1/(10k + d))`` for ``d = 0..9``;
    ``P(first_two = d) = log10(1 + 1/d)`` for ``d = 10..99`` (Nigrini 2012, ch. 3).

    Parameters
    ----------
    position : {"first", "second", "first_two"}
        Digit position.

    Returns
    -------
    numpy.ndarray
        Probabilities aligned with :func:`digit_support`, summing to 1.
    """
    _check_position(position)
    if position == "first":
        return np.log10(1.0 + 1.0 / np.arange(1, 10, dtype=float))
    first_two = np.log10(1.0 + 1.0 / np.arange(10, 100, dtype=float))
    if position == "first_two":
        return first_two
    # second digit: marginalise the first-two-digit law over the leading digit
    return first_two.reshape(9, 10).sum(axis=0)


def _significand(v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Decompose strictly positive finite ``v`` into ``(significand, exponent)``.

    ``v = significand * 10**exponent`` with ``significand`` in ``[1, 10)``. The decomposition
    goes through ``log10`` rather than the decimal string, so it is correct for values such as
    ``0.000123`` where a string hack would read the padding zeros. The floor of the logarithm
    is corrected once in each direction to absorb rounding at exact powers of ten. Precision
    degrades for subnormal inputs (``v < 1e-308``), which are far outside the range of any
    reported quantity this library targets.
    """
    exponent = np.floor(np.log10(v))
    significand = v / np.power(10.0, exponent)
    high = significand >= 10.0
    exponent[high] += 1.0
    significand[high] /= 10.0
    low = significand < 1.0
    exponent[low] -= 1.0
    significand[low] *= 10.0
    # absorb float noise well below the ~1% relative gap between neighbouring digit pairs
    significand = np.round(significand, 12)
    high = significand >= 10.0
    exponent[high] += 1.0
    significand[high] /= 10.0
    return significand, exponent


def _digits_with_mask(
    values: np.ndarray,
    position: str,
    *,
    require_two_significant_digits: bool = True,
    rtol: float = SIGNIFICANCE_RTOL,
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(digits, mask)``; ``mask`` marks the elements of ``values`` that were used."""
    usable = np.isfinite(values) & (values > 0.0)
    v = values[usable]
    digits = np.zeros(v.size, dtype=np.int64)
    keep = np.ones(v.size, dtype=bool)
    if v.size:
        significand, exponent = _significand(v)
        first_two = np.floor(np.round(significand * 10.0, 9)).astype(np.int64)
        first_two = np.clip(first_two, 10, 99)
        first = first_two // 10
        if position == "first":
            digits = first
        elif position == "first_two":
            digits = first_two
        else:
            digits = first_two % 10
            if require_two_significant_digits:
                one_digit_value = first.astype(float) * np.power(10.0, exponent)
                keep = np.abs(v - one_digit_value) > rtol * v
    mask = np.zeros(values.size, dtype=bool)
    mask[np.flatnonzero(usable)[keep]] = True
    return digits[keep], mask


def leading_digits(
    x: ArrayLike,
    position: DigitPosition = "first",
    *,
    require_two_significant_digits: bool = True,
) -> np.ndarray:
    """Extract leading digits, dropping values for which the digit is undefined.

    Parameters
    ----------
    x : array-like
        1-D numeric input. Non-finite and non-positive values are excluded (Benford's law is
        stated for positive numbers; the sign is not part of the magnitude, so callers who
        want the digits of negative numbers should pass ``numpy.abs(x)`` explicitly).
    position : {"first", "second", "first_two"}
        Digit position.
    require_two_significant_digits : bool, default True
        Applies to ``position="second"`` only. A value such as ``300.0`` carries a single
        significant digit, so its second digit is a placeholder zero rather than a reported
        digit, and it is excluded. A value is deemed to have one significant digit when it
        equals ``d * 10**e`` to within a relative tolerance of 1e-12 (the smallest relative
        gap between neighbouring two-digit significands is about 1%, so the test is not
        borderline). Set to ``False`` for the looser convention that reads the second digit
        of every value.

    Returns
    -------
    numpy.ndarray
        ``int64`` digits, shorter than ``x`` whenever values were excluded.

    Raises
    ------
    ValueError
        If ``x`` is not 1-D numeric, or ``position`` is unknown.

    Examples
    --------
    >>> leading_digits([0.000123, 123.0, 9.99]).tolist()
    [1, 1, 9]
    >>> leading_digits([0.000123, 123.0, 9.99], "first_two").tolist()
    [12, 12, 99]
    """
    _check_position(position)
    values = as_float_array(x, "x")
    digits, _ = _digits_with_mask(
        values, position, require_two_significant_digits=require_two_significant_digits
    )
    return digits


@dataclass(frozen=True)
class DigitTable:
    """Observed and expected digit frequencies.

    Attributes
    ----------
    digits : numpy.ndarray
        Digit labels (see :func:`digit_support`).
    observed : numpy.ndarray
        Counts, or summed weights when ``weights`` is given.
    expected : numpy.ndarray
        Benford expectation on the same scale as ``observed``.
    observed_prop, expected_prop : numpy.ndarray
        The same two rows as proportions.
    n : int
        Number of values used (unweighted, after exclusions).
    effective_n : float
        Kish effective sample size (equals ``n`` without weights).
    n_dropped : int
        Values excluded as non-finite, non-positive, or lacking the required digit.
    position : str
        Digit position the table describes.
    """

    digits: np.ndarray
    observed: np.ndarray
    expected: np.ndarray
    observed_prop: np.ndarray
    expected_prop: np.ndarray
    n: int
    effective_n: float
    n_dropped: int = 0
    position: str = "first"

    def to_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))


def digit_frequencies(
    x: ArrayLike,
    position: DigitPosition = "first",
    weights: ArrayLike | None = None,
    *,
    require_two_significant_digits: bool = True,
) -> DigitTable:
    """Tabulate observed against Benford-expected digit frequencies.

    Parameters
    ----------
    x : array-like
        1-D numeric input; see :func:`leading_digits` for the exclusion rules.
    position : {"first", "second", "first_two"}
        Digit position.
    weights : array-like, optional
        Observation weights aligned with ``x`` (e.g. precinct size). ``observed`` then holds
        summed weights and ``effective_n`` the Kish (1965, *Survey Sampling*, Wiley, section
        8.2) effective sample size of the weights that survived exclusion.
    require_two_significant_digits : bool, default True
        Passed through to :func:`leading_digits`.

    Returns
    -------
    DigitTable

    Raises
    ------
    ValueError
        If no value survives exclusion, or every surviving weight is zero.
    """
    _check_position(position)
    values = as_float_array(x, "x")
    w = validate_weights(weights, values.size)
    digits, mask = _digits_with_mask(
        values, position, require_two_significant_digits=require_two_significant_digits
    )
    n = int(digits.size)
    if n == 0:
        raise ValueError(
            f"no usable values for the {position} digit: every element was non-finite, "
            "non-positive, or lacked the required significant digits"
        )
    support = digit_support(position)
    kept_w = None if w is None else w[mask]
    if kept_w is not None and not np.any(kept_w > 0):
        raise ValueError("every value that survived digit exclusion has zero weight")
    observed = weighted_counts(digits - int(support[0]), kept_w, support.size)
    total = float(observed.sum())
    expected_prop = benford_expected(position)
    return DigitTable(
        digits=support,
        observed=observed,
        expected=expected_prop * total,
        observed_prop=observed / total,
        expected_prop=expected_prop,
        n=n,
        effective_n=float(n) if kept_w is None else kish_effective_n(kept_w),
        n_dropped=int(values.size - n),
        position=position,
    )


def _mad_conformity(mad: float, position: str) -> str:
    """Nigrini (2012) conformity band for a mean absolute deviation. See :data:`MAD_BANDS`."""
    if position not in MAD_BANDS:
        raise ValueError(f"no MAD bands for position {position!r}")
    close, acceptable, marginal = MAD_BANDS[position]
    if mad < close:
        return MAD_LABELS[0]
    if mad < acceptable:
        return MAD_LABELS[1]
    if mad < marginal:
        return MAD_LABELS[2]
    return MAD_LABELS[3]


def _kuiper_pvalue(v: float, effective_n: float) -> float:
    """Asymptotic tail probability of Kuiper's V.

    ``Q_KP(lambda) = 2 * sum_{j>=1} (4 j^2 lambda^2 - 1) exp(-2 j^2 lambda^2)`` evaluated at
    ``lambda = (sqrt(n) + 0.155 + 0.24/sqrt(n)) * V`` (Stephens 1970; Press et al.,
    *Numerical Recipes* 3rd ed., section 14.3). The series is unusable for small ``lambda``,
    where the true probability is 1 to within its own accuracy; following Numerical Recipes
    the value is short-circuited to 1 below ``lambda = 0.4`` and the sum is clipped to
    ``[0, 1]``.
    """
    if not np.isfinite(v) or v < 0:
        raise ValueError(f"Kuiper V must be finite and non-negative; got {v}")
    if effective_n <= 0:
        raise ValueError("effective sample size must be positive")
    root_n = np.sqrt(effective_n)
    lam = (root_n + 0.155 + 0.24 / root_n) * v
    if lam < 0.4:
        return 1.0
    total = 0.0
    for j in range(1, 101):
        a = 2.0 * j * j * lam * lam
        if a > 700.0:  # exp(-a) underflows to zero
            break
        term = (4.0 * a - 2.0) * float(np.exp(-a))
        total += term
        if j > 1 and abs(term) < 1e-14:
            break
    return float(min(1.0, max(0.0, total)))


def _kuiper_statistic(
    observed_prop: np.ndarray, expected_prop: np.ndarray
) -> tuple[float, float, float]:
    """Kuiper ``V = D+ + D-`` on the cumulative digit distributions, ordered by digit."""
    diff = np.cumsum(observed_prop) - np.cumsum(expected_prop)
    d_plus = float(max(diff.max(), 0.0))
    d_minus = float(max((-diff).max(), 0.0))
    return d_plus + d_minus, d_plus, d_minus


@dataclass(frozen=True)
class BenfordResult:
    """Digit table plus the requested statistics. Statistics not requested are ``None``."""

    table: DigitTable
    chi2: TestResult | None = None
    mad: TestResult | None = None
    kuiper: TestResult | None = None
    settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return jsonable(asdict(self))


def benford_test(
    x: ArrayLike,
    position: DigitPosition = "first",
    weights: ArrayLike | None = None,
    statistics: tuple[str, ...] = ("chi2", "mad", "kuiper"),
    *,
    require_two_significant_digits: bool = True,
) -> BenfordResult:
    """Test digit frequencies against Benford's law.

    Parameters
    ----------
    x : array-like
        1-D numeric input; see :func:`leading_digits` for the exclusion rules.
    position : {"first", "second", "first_two"}
        Digit position.
    weights : array-like, optional
        Observation weights. Expected counts and statistics are weighted; ``n`` stays the
        unweighted count and ``details["effective_n"]`` holds the Kish effective sample size.
        Weighted p-values are APPROXIMATE: the chi-square and Kuiper null distributions are
        evaluated at the effective sample size, which ignores the cell-by-cell design effect
        a Rao-Scott correction would carry. ``details["weighted_pvalue_is_approximate"]``
        flags this.
    statistics : tuple of str, default ``("chi2", "mad", "kuiper")``
        Any subset of ``{"chi2", "mad", "kuiper"}``.
    require_two_significant_digits : bool, default True
        Passed through to :func:`leading_digits`.

    Returns
    -------
    BenfordResult
        ``table`` plus one :class:`~forensics_core.TestResult` per requested statistic. The
        MAD result has ``pvalue=None`` and carries the Nigrini conformity band in
        ``details["conformity"]``.

    Raises
    ------
    ValueError
        On an unknown position or statistic, mis-shaped weights, or an empty digit sample.

    Notes
    -----
    The chi-square p-value falls with sample size even for deviations too small to matter
    forensically (Nigrini 2012, ch. 6, "excess power"); read it next to the MAD band rather
    than on its own.
    """
    _check_position(position)
    requested = tuple(statistics)
    unknown = [s for s in requested if s not in ("chi2", "mad", "kuiper")]
    if unknown:
        raise ValueError(f"unknown statistics {unknown}; expected a subset of chi2/mad/kuiper")
    table = digit_frequencies(
        x,
        position,
        weights,
        require_two_significant_digits=require_two_significant_digits,
    )
    weighted = weights is not None
    common: dict[str, Any] = {
        "position": position,
        "digits": table.digits,
        "observed": table.observed,
        "expected": table.expected,
        "effective_n": table.effective_n,
        "n_dropped": table.n_dropped,
        "weighted": weighted,
    }
    if weighted:
        common["weighted_pvalue_is_approximate"] = True

    chi2_result: TestResult | None = None
    mad_result: TestResult | None = None
    kuiper_result: TestResult | None = None

    if "chi2" in requested:
        stat, pvalue, df = chi2_goodness_of_fit(
            table.observed_prop, table.expected_prop, table.effective_n
        )
        chi2_result = TestResult(
            method=f"benford_{position}_chi2",
            statistic=stat,
            pvalue=pvalue,
            n=table.n,
            details={**common, "df": df, "alternative": "greater"},
        )

    if "mad" in requested:
        mad = float(np.mean(np.abs(table.observed_prop - table.expected_prop)))
        close, acceptable, marginal = MAD_BANDS[position]
        mad_result = TestResult(
            method=f"benford_{position}_mad",
            statistic=mad,
            pvalue=None,
            n=table.n,
            details={
                **common,
                "conformity": _mad_conformity(mad, position),
                "bands": {
                    MAD_LABELS[0]: [0.0, close],
                    MAD_LABELS[1]: [close, acceptable],
                    MAD_LABELS[2]: [acceptable, marginal],
                    MAD_LABELS[3]: [marginal, float("inf")],
                },
                "citation": _MAD_CITATION,
            },
        )

    if "kuiper" in requested:
        v, d_plus, d_minus = _kuiper_statistic(table.observed_prop, table.expected_prop)
        kuiper_result = TestResult(
            method=f"benford_{position}_kuiper",
            statistic=v,
            pvalue=_kuiper_pvalue(v, table.effective_n),
            n=table.n,
            details={
                **common,
                "d_plus": d_plus,
                "d_minus": d_minus,
                "alternative": "greater",
                "citation": _KUIPER_CITATION,
            },
        )

    return BenfordResult(
        table=table,
        chi2=chi2_result,
        mad=mad_result,
        kuiper=kuiper_result,
        settings={
            "position": position,
            "statistics": list(requested),
            "weighted": weighted,
            "require_two_significant_digits": require_two_significant_digits,
        },
    )
