"""Adversarial clean data: generators whose explicit goal is to make a detector fire wrongly.

A false-positive rate measured on a control chosen by the person who built the detector is
weak evidence. They picked a control they expected to pass. This module holds the opposite:
data built by someone trying to make each detector fail, on processes that contain **no
distortion at all**.

Every generator here implements a mechanism from one of the four `known_traps.md` documents,
and every one of them produces honest data. That is the whole point. A precinct of 100 voters
reporting exactly 70.0% turnout did not cheat; it has 101 possible turnout values and one of
them is an integer. A series that jumps when Chongqing separates from Sichuan was not padded.
A digit test run on an OCR'd table detects the scanner.

The distinction from :mod:`forensics_core.inject`
--------------------------------------------------
``inject`` takes clean data and puts a distortion into it, then asks whether the detector
finds it. This module takes an honest process and asks whether the detector finds something
that is not there. The two together are the operating characteristic: ``inject`` measures
power, ``redteam`` measures the false positives that make power readable.

Neither is a control corpus. :mod:`forensics_core.control` scores real collections; these are
synthetic, and the module docstring there says why a synthetic null is the weakest kind of
evidence. A trap that fires is nonetheless a hard result: it means the detector has a failure
mode reachable by an honest process, and no amount of real-control passing makes that go away.

What ``truth`` carries, and why
-------------------------------
Every generator returns ``(values, TrapSample)`` and the sample's ``truth`` dict holds the
honest quantities the values were built from. This is what lets a test assert that nothing was
injected — not by trusting the docstring, but by checking the arithmetic: removing a level
shift restores the original series exactly, a reweighted index is built from physically
identical quantities, an OCR'd table differs from its source only at the digit positions the
caller allowed.

Discipline (as :mod:`forensics_core.inject`)
--------------------------------------------
Pure functions, no I/O, no globals. Randomness through ``seed`` to
:func:`numpy.random.default_rng`. Generated data is never written under any project's
``data/`` directory.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import ArrayLike
from scipy import stats

__all__ = [
    "TRAPS",
    "RedTeamError",
    "RedTeamResult",
    "TrapSample",
    "TrapSpec",
    "casualties",
    "format_redteam_table",
    "heterogeneous_mixture",
    "level_shift",
    "ocr_firing_threshold",
    "ocr_gate",
    "ocr_noise",
    "red_team",
    "reweighting",
    "small_units",
    "survivors",
]


class RedTeamError(ValueError):
    """A trap was built or interpreted in a way that would misstate what it shows."""


@dataclass(frozen=True)
class TrapSpec:
    """Where a trap comes from, so a firing result can be traced to a documented confound."""

    trap_id: str
    project: str
    document_section: str
    summary: str


#: The traps these generators implement, keyed by id. The id is `<project>-<section number>`
#: and points at that project's `docs/known_traps.md`. A generator that does not name one of
#: these is not a red-team trap; it is an invention, and inventing a confound would overstate
#: the detector's fragility exactly as surely as dropping one would understate it.
TRAPS: dict[str, TrapSpec] = {
    "elections-1": TrapSpec(
        trap_id="elections-1",
        project="elections",
        document_section="1. Small precincts produce round percentages honestly",
        summary=(
            "A precinct with 100 registered voters can legitimately report exactly 70.0%. "
            "An integer-percentage test that does not condition on precinct size detects "
            "arithmetic, not fraud."
        ),
    ),
    "elections-2": TrapSpec(
        trap_id="elections-2",
        project="elections",
        document_section="2. Turnout bimodality has honest sources too",
        summary=(
            "Turnout can be bimodal through genuine heterogeneity — urban against rural, "
            "republics with different mobilisation. A second mode alone is not a signature."
        ),
    ),
    "china-2": TrapSpec(
        trap_id="china-2",
        project="china",
        document_section="2. Boundary changes and rebasing create level shifts",
        summary=(
            "Chongqing separated from Sichuan in 1997; economic censuses trigger rebasing and "
            "back-revision. Each creates a level shift that mimics manipulation."
        ),
    ),
    "gosplan-3": TrapSpec(
        trap_id="gosplan-3",
        project="gosplan",
        document_section="3. The index-number problem (Gerschenkron effect)",
        summary=(
            "Soviet growth rates swing enormously with base-year weights. The same physical "
            "quantities produce spectacular or modest growth depending on the base year."
        ),
    ),
    "gosplan-9": TrapSpec(
        trap_id="gosplan-9",
        project="gosplan",
        document_section="9. Transcription error mimics everything",
        summary=(
            "Digit tests on OCR'd tables detect OCR. Only run them on tables whose "
            "inter-transcription error rate is documented and low."
        ),
    ),
}


@dataclass(frozen=True, eq=False)
class TrapSample:
    """Adversarial data and the evidence that it is honest.

    ``eq=False`` because the sample holds numpy arrays: the generated ``__eq__`` would return
    an array and ``bool()`` on it would raise. Identity comparison is what a caller wants
    here anyway — two draws from the same trap are different samples.
    """

    values: np.ndarray
    trap_id: str
    mechanism: str
    honest_because: str
    truth: dict[str, Any] = field(default_factory=dict)
    seed: int | None = None

    def __post_init__(self) -> None:
        if self.trap_id not in TRAPS:
            raise RedTeamError(
                f"unknown trap id {self.trap_id!r}. Every trap must come from a project's "
                f"docs/known_traps.md; known ids are {sorted(TRAPS)}."
            )

    @property
    def spec(self) -> TrapSpec:
        return TRAPS[self.trap_id]

    def __len__(self) -> int:
        return int(np.asarray(self.values).size)


def _rng(seed: int | None) -> np.random.Generator:
    return np.random.default_rng(seed)


def _as_float_1d(x: ArrayLike, name: str) -> np.ndarray:
    arr = np.asarray(x, dtype=float).ravel()
    if arr.size == 0:
        raise RedTeamError(f"{name} is empty")
    if not np.isfinite(arr).all():
        raise RedTeamError(f"{name} contains non-finite values")
    return arr


# ---------------------------------------------------------------- elections-1


def small_units(
    n: int,
    size_distribution: ArrayLike | Callable[[np.random.Generator, int], np.ndarray],
    *,
    p: float = 0.55,
    seed: int | None = None,
) -> tuple[np.ndarray, TrapSample]:
    """Honest percentages from small denominators (trap ``elections-1``).

    Each unit gets a denominator, then a numerator drawn as ``Binomial(denominator, p)``. That
    is the honest data-generating process in full: there is no rounding step, no snapping to
    integers, and nothing that knows what an integer-percentage test measures. The integer
    spike appears anyway, because with a denominator of 100 every possible turnout *is* an
    integer percentage.

    Parameters
    ----------
    size_distribution : array-like or callable
        Candidate denominators sampled with replacement, or ``f(rng, n) -> denominators``.
        Pass small sizes to build the trap and large ones to build its control.
    p : float
        The true rate. Constant across units, so any structure in the percentages comes from
        the denominators alone.

    Returns
    -------
    (percentages, TrapSample)
        ``truth`` carries ``denominators``, ``numerators`` and ``p``, which is everything
        needed to verify the numerators are exactly binomial draws.
    """
    if n <= 0:
        raise RedTeamError("n must be positive")
    if not 0.0 < p < 1.0:
        raise RedTeamError(f"p must be in (0, 1); got {p}")
    rng = _rng(seed)

    if callable(size_distribution):
        denominators = np.asarray(size_distribution(rng, n), dtype=np.int64).ravel()
    else:
        pool = np.asarray(size_distribution, dtype=np.int64).ravel()
        if pool.size == 0:
            raise RedTeamError("size_distribution is empty")
        denominators = rng.choice(pool, size=n, replace=True)

    if denominators.size != n:
        raise RedTeamError(
            f"size_distribution produced {denominators.size} denominators, expected {n}"
        )
    if (denominators <= 0).any():
        raise RedTeamError("denominators must be positive")

    numerators = rng.binomial(denominators, p)
    pct = 100.0 * numerators / denominators
    return pct, TrapSample(
        values=pct,
        trap_id="elections-1",
        mechanism="binomial draw at constant p; no rounding of any kind",
        honest_because=(
            "the numerator is Binomial(denominator, p) exactly. Nothing in the generator "
            "refers to integers, tolerances or percentage bins."
        ),
        truth={
            "denominators": denominators,
            "numerators": numerators,
            "p": float(p),
            "median_denominator": float(np.median(denominators)),
        },
        seed=seed,
    )


# ---------------------------------------------------------------- elections-2


def heterogeneous_mixture(
    groups: Sequence[Mapping[str, Any]],
    *,
    seed: int | None = None,
) -> tuple[np.ndarray, TrapSample]:
    """Honest bimodality from a mixture of populations (trap ``elections-2``).

    Each group is drawn from its own normal and the draws are pooled. Every unit is honest
    within its own group; the second mode is the mixture, not stuffing. Klimek et al.'s
    argument is about the *joint* distribution of turnout and vote share and about a second
    mode sitting near 100%, and a bare second mode is not that.

    Parameters
    ----------
    groups : sequence of mapping
        Each with ``n``, ``mean``, ``sd`` and optionally ``name``.
    """
    if not groups:
        raise RedTeamError("no groups given; a mixture needs at least one component")

    rng = _rng(seed)
    parts: list[np.ndarray] = []
    labels: list[str] = []
    described: list[dict[str, Any]] = []
    for i, g in enumerate(groups):
        missing = {"n", "mean", "sd"} - set(g)
        if missing:
            raise RedTeamError(f"group {i} is missing {sorted(missing)}")
        size = int(g["n"])
        if size <= 0:
            raise RedTeamError(f"group {i} has n={size}")
        sd = float(g["sd"])
        if sd <= 0:
            raise RedTeamError(f"group {i} has sd={sd}; a component with no spread is a point")
        name = str(g.get("name", f"group{i}"))
        parts.append(rng.normal(float(g["mean"]), sd, size=size))
        labels.extend([name] * size)
        described.append({"name": name, "n": size, "mean": float(g["mean"]), "sd": sd})

    values = np.concatenate(parts)
    return values, TrapSample(
        values=values,
        trap_id="elections-2",
        mechanism="pooled draws from independent normals, one per population",
        honest_because=(
            "every unit is a draw from its own group's honest distribution. No unit was "
            "moved, and no mass was placed near any boundary."
        ),
        truth={"groups": described, "group_of_unit": np.array(labels, dtype=object)},
        seed=seed,
    )


# ---------------------------------------------------------------- china-2


def level_shift(
    series: ArrayLike,
    at: int,
    size: float,
    *,
    kind: str = "additive",
) -> tuple[np.ndarray, TrapSample]:
    """A boundary change or a rebasing, not a fraud (trap ``china-2``).

    Chongqing separating from Sichuan in 1997, an economic census triggering back-revision,
    the 1961 rouble redenomination: each puts a discontinuity into a series that no one
    manipulated. A detector looking for a break will find one.

    Parameters
    ----------
    at : int
        First index of the post-shift regime.
    kind : {"additive", "multiplicative"}
        Additive for a boundary change, multiplicative for a rebasing or redenomination.

    Returns
    -------
    (shifted, TrapSample)
        ``truth["series"]`` is the original. Undoing the shift restores it exactly, which is
        the check that nothing else was done to the numbers.
    """
    original = _as_float_1d(series, "series")
    if kind not in ("additive", "multiplicative"):
        raise RedTeamError(f"kind must be 'additive' or 'multiplicative'; got {kind!r}")
    if not 0 < at < original.size:
        raise RedTeamError(
            f"at must fall strictly inside the series (1..{original.size - 1}); got {at}. A "
            "shift at the first or last index is not a break, it is a different series."
        )
    if kind == "multiplicative" and size <= 0:
        raise RedTeamError("a multiplicative shift must be positive")

    out = original.copy()
    if kind == "additive":
        out[at:] = out[at:] + size
    else:
        out[at:] = out[at:] * size

    return out, TrapSample(
        values=out,
        trap_id="china-2",
        mechanism=f"{kind} level shift of {size} at index {at}",
        honest_because=(
            "the only change is a constant applied to every post-break observation. "
            "Reversing it recovers the input array exactly, so no observation was reordered, "
            "smoothed, rounded or replaced."
        ),
        truth={"series": original, "at": int(at), "size": float(size), "kind": kind},
    )


# ---------------------------------------------------------------- gosplan-3


def reweighting(
    quantities: ArrayLike,
    prices: ArrayLike,
    *,
    base_period: int,
) -> tuple[np.ndarray, TrapSample]:
    """The same real output under different base-year weights (trap ``gosplan-3``).

    The Gerschenkron effect. Early-year prices weight the goods that later expanded most and
    produce spectacular growth; late-year prices produce modest growth. **The physical
    quantities are identical in both cases.** A detector that reads a growth path as padded
    may be reading the base year.

    Parameters
    ----------
    quantities : array-like, shape (n_periods, n_goods)
        Physical output. Never varies with the base period, which is the point.
    prices : array-like, shape (n_periods, n_goods)
        Unit prices per period.
    base_period : int
        Row of ``prices`` supplying the weights.

    Returns
    -------
    (index, TrapSample)
        A Laspeyres volume index, 100 at the base period.
    """
    q = np.asarray(quantities, dtype=float)
    pr = np.asarray(prices, dtype=float)
    if q.ndim != 2 or pr.ndim != 2:
        raise RedTeamError("quantities and prices must both be 2-D (periods x goods)")
    if q.shape != pr.shape:
        raise RedTeamError(f"quantities {q.shape} and prices {pr.shape} must have one shape")
    if not np.isfinite(q).all() or not np.isfinite(pr).all():
        raise RedTeamError("quantities and prices must be finite")
    if (q < 0).any() or (pr <= 0).any():
        raise RedTeamError("quantities must be non-negative and prices strictly positive")
    if not 0 <= base_period < q.shape[0]:
        raise RedTeamError(f"base_period {base_period} is outside 0..{q.shape[0] - 1}")

    weights = pr[base_period]
    valued = q @ weights
    if valued[base_period] <= 0:
        raise RedTeamError("the base period has zero value at its own prices")
    index = 100.0 * valued / valued[base_period]

    return index, TrapSample(
        values=index,
        trap_id="gosplan-3",
        mechanism=f"Laspeyres volume index at period-{base_period} prices",
        honest_because=(
            "the physical quantities are the caller's, unmodified. Only the price vector "
            "used to aggregate them changed, so every difference between two base periods is "
            "an index-number artefact rather than a difference in real output."
        ),
        truth={
            "quantities": q,
            "prices": pr,
            "base_period": int(base_period),
            "weights": weights,
        },
    )


# ---------------------------------------------------------------- gosplan-9


def ocr_noise(
    values: ArrayLike,
    error_rate: float,
    positions: Sequence[int] = (0,),
    *,
    confusion: Mapping[int, int] | None = None,
    seed: int | None = None,
) -> tuple[np.ndarray, TrapSample]:
    """Transcription error in specified digit positions (trap ``gosplan-9``).

    Digit tests on OCR'd tables detect OCR. The corruption is a scanner misreading, not a
    person choosing a number, and a terminal-digit test cannot tell the difference from the
    data alone. This is why the gosplan trap document requires a measured error rate before
    any digit test runs.

    The two modes are not equally dangerous, and the difference is measured in
    ``docs/redteam.md``. A **uniform** misread scatters a digit evenly over the other nine and
    leaves the digit distribution uniform, so a uniformity test does not react to it at any
    rate. A **glyph confusion** — the realistic failure, where a scanner resolves 3, 5, 6 and
    9 all to 8 — piles mass onto one digit, and the terminal-digit test fires on it every
    time from a rate of 0.05 upward. A test that survives the first mode has not been shown
    to survive the second.

    Parameters
    ----------
    values : array-like
        Integer-valued. A transcribed table holds integers; corrupting a digit of a float
        would be a different mechanism.
    error_rate : float
        Probability that any one eligible digit is misread. This is the injector's unit, not
        the unit a transcription comparison measures: under a ``confusion`` table only the
        digits in its keys can change, so the share of digits that differ from the source is
        ``error_rate`` times the share of eligible digits that are keys (about 0.4 for four
        confusable glyphs on uniform digits). :func:`ocr_firing_threshold` works in the
        measured unit and converts.
    positions : sequence of int
        Digit positions eligible to be misread, ``0`` being the last digit.
    confusion : mapping of int to int, optional
        A glyph confusion table: a misread of digit ``d`` resolves to ``confusion[d]`` rather
        than to a uniformly chosen other digit. Digits absent from the mapping are never
        misread, which is what a real confusion matrix looks like — a scanner does not
        struggle with every glyph equally.

    Returns
    -------
    (corrupted, TrapSample)
        ``truth`` carries the originals and the indices changed.
    """
    original = _as_float_1d(values, "values")
    if not np.allclose(original, np.round(original), atol=1e-9):
        raise RedTeamError(
            "values must be integer-valued; a transcribed table holds integers and "
            "corrupting a digit of a float is a different mechanism"
        )
    if not 0.0 <= error_rate <= 1.0:
        raise RedTeamError(f"error_rate must be in [0, 1]; got {error_rate}")
    pos = _digit_positions(positions)

    rng = _rng(seed)
    ints = np.round(np.abs(original)).astype(np.int64)
    sign = np.sign(original)
    out = ints.copy()

    table = None if confusion is None else _confusion_table(confusion)

    n_corrupted = 0
    for p in pos:
        power = 10**p
        eligible = ints >= power  # a digit that does not exist cannot be misread
        hits = eligible & (rng.random(ints.size) < error_rate)
        if not hits.any():
            continue
        current = (out[hits] // power) % 10
        if table is None:
            # a misread produces some *other* digit, uniformly
            offset = rng.integers(1, 10, size=int(hits.sum()))
            replacement = (current + offset) % 10
        else:
            replacement = np.array([table.get(int(d), int(d)) for d in current], dtype=np.int64)
        out[hits] = out[hits] + (replacement - current) * power
        n_corrupted += int((replacement != current).sum())

    corrupted = sign * out.astype(float)
    changed = np.flatnonzero(corrupted != original)
    return corrupted, TrapSample(
        values=corrupted,
        trap_id="gosplan-9",
        mechanism=(
            f"{'glyph confusion' if table else 'uniform'} digit misreads at positions {pos}, "
            f"rate {error_rate}"
        ),
        honest_because=(
            "the underlying table is unchanged; only the reading of it is wrong. Each misread "
            "depends on the glyph alone, never on the value's magnitude, its neighbours or "
            "any target, so the process is a faulty scanner rather than a person choosing "
            "numbers."
        ),
        truth={
            "values": original,
            "positions": pos,
            "error_rate": float(error_rate),
            "confusion": dict(table) if table else None,
            "changed_index": changed,
            "n_digit_misreads": n_corrupted,
        },
        seed=seed,
    )


def _digit_positions(positions: Sequence[int]) -> list[int]:
    if not positions:
        raise RedTeamError("positions is empty; no digit could be misread")
    pos = sorted({int(p) for p in positions})
    if any(p < 0 for p in pos):
        raise RedTeamError("digit positions are non-negative, 0 being the last digit")
    return pos


def _confusion_table(confusion: Mapping[int, int]) -> dict[int, int]:
    table = {int(k): int(v) for k, v in confusion.items()}
    bad = {k: v for k, v in table.items() if not (0 <= k <= 9 and 0 <= v <= 9)}
    if bad:
        raise RedTeamError(f"confusion keys and values must be digits 0-9; got {bad}")
    fixed = {k: v for k, v in table.items() if k == v}
    if fixed:
        raise RedTeamError(
            f"confusion maps {sorted(fixed)} to itself, which is not a misread. Leave a "
            "digit out of the mapping to say the scanner reads it correctly."
        )
    return table


# ---------------------------------------------------------------- running the pass


@dataclass(frozen=True)
class RedTeamResult:
    """What one detector did on one trap. ``fired`` is a false positive by construction."""

    trap_id: str
    detector: str
    fired: bool
    pvalue: float | None
    alpha: float
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def spec(self) -> TrapSpec:
        return TRAPS[self.trap_id]

    def to_dict(self) -> dict[str, Any]:
        return {
            "trap_id": self.trap_id,
            "detector": self.detector,
            "fired": self.fired,
            "pvalue": self.pvalue,
            "alpha": self.alpha,
            "detail": dict(self.detail),
        }


def red_team(
    detectors: Mapping[str, Callable[[TrapSample], Any]],
    samples: Sequence[TrapSample],
    *,
    alpha: float = 0.05,
) -> list[RedTeamResult]:
    """Run every detector against every trap and report every pair.

    Every pair. There is no filtering argument and no way to ask for only the passes: the
    card's forbidden list names quietly dropping a trap that makes a detector look bad, and
    the easiest way to drop one is to have somewhere to drop it.

    Parameters
    ----------
    detectors : mapping
        ``name -> f(sample) -> p-value``. Anything with a ``.pvalue`` attribute (a
        ``TestResult``, or a result object holding one) is unwrapped, so a library test can be
        passed with a thin lambda rather than rewritten.

    Returns
    -------
    list of RedTeamResult
        One per (trap, detector) pair, traps in the order given.
    """
    if not samples:
        raise RedTeamError("no trap samples given; an empty pass proves nothing")
    if not detectors:
        raise RedTeamError("no detectors given")
    if not 0.0 < alpha < 1.0:
        raise RedTeamError(f"alpha must be in (0, 1); got {alpha}")

    results: list[RedTeamResult] = []
    for sample in samples:
        for name, fn in detectors.items():
            detail: dict[str, Any] = {"n": len(sample), "mechanism": sample.mechanism}
            try:
                raw = fn(sample)
            except Exception as exc:
                results.append(
                    RedTeamResult(
                        trap_id=sample.trap_id,
                        detector=name,
                        fired=False,
                        pvalue=None,
                        alpha=alpha,
                        detail={**detail, "error": f"{type(exc).__name__}: {exc}"},
                    )
                )
                continue

            pvalue = _pvalue_of(raw)
            if pvalue is None or not np.isfinite(pvalue):
                results.append(
                    RedTeamResult(
                        trap_id=sample.trap_id,
                        detector=name,
                        fired=False,
                        pvalue=None,
                        alpha=alpha,
                        detail={**detail, "error": "detector produced no usable p-value"},
                    )
                )
                continue

            results.append(
                RedTeamResult(
                    trap_id=sample.trap_id,
                    detector=name,
                    fired=bool(pvalue <= alpha),
                    pvalue=float(pvalue),
                    alpha=alpha,
                    detail=detail,
                )
            )
    return results


def _pvalue_of(raw: Any) -> float | None:
    """Unwrap a p-value from a float, a ``TestResult``, or a result object holding one."""
    if raw is None:
        return None
    if isinstance(raw, (int, float, np.floating)):
        return float(raw)
    for attr in ("pvalue",):
        if hasattr(raw, attr):
            return _pvalue_of(getattr(raw, attr))
    if hasattr(raw, "test"):
        return _pvalue_of(raw.test)
    return None


def casualties(results: Sequence[RedTeamResult]) -> list[RedTeamResult]:
    """The pairs where a detector fired on honest data, most confident first."""
    fired = [r for r in results if r.fired]
    return sorted(fired, key=lambda r: r.pvalue if r.pvalue is not None else 1.0)


def survivors(results: Sequence[RedTeamResult], detector: str) -> list[str]:
    """The trap ids that ``detector`` did not fire on."""
    return [r.trap_id for r in results if r.detector == detector and not r.fired]


# ---------------------------------------------------------------- the OCR gate


def ocr_firing_threshold(
    detector: Callable[[TrapSample], Any],
    honest_table: Callable[[np.random.Generator], ArrayLike],
    *,
    error_rates: Sequence[float],
    confusions: Mapping[int, int] | Sequence[Mapping[int, int]],
    positions: Sequence[int] = (0,),
    alpha: float = 0.05,
    tolerance: float = 0.03,
    n_replicates: int = 1000,
    confidence: float = 0.95,
    seed: int | None = 0,
) -> float | None:
    """The highest transcription error rate tested at which a detector is still calibrated.

    This is what makes the gosplan OCR gate enforceable rather than advisory. Trap
    ``gosplan-9`` says a digit test may not run on transcribed data until the measured
    transcription error rate is known to be below the rate at which the test starts reacting
    to transcription. That number is this one, and :func:`ocr_gate` holds a measured rate to
    it.

    Three things decide it, and each closes a way the gate could open too early.

    **Every corruption mode, minimum taken.** At each rate the detector is run under a uniform
    misread and under every glyph confusion in ``confusions``, and a rate passes only if it
    passes under all of them. A uniformity test cannot see a uniform misread at any rate, so
    that mode alone would pass every rate tested; a Benford test reacts to both, and the
    uniform mode alone can give the higher threshold of the two. The confusion mode is
    therefore required, not optional.

    **Calibration, not majority firing, with room for Monte Carlo error.** A rate passes while
    the detector is shown to fire on at most ``alpha + tolerance`` of honest tables: the
    one-sided Clopper-Pearson upper bound, at ``confidence``, on the share of the
    ``n_replicates`` tables on which it fired must not exceed that. The defaults hold a test
    at alpha 0.05 to 8%. A point estimate held to a band is not enough: walking up the grid,
    the last rate whose estimate lands inside the band is often one whose true firing rate
    lies outside it, admitted by the estimate's own error.

    **The unit a comparison measures.** ``error_rates`` and the returned threshold are both the
    share of digits at ``positions`` that differ from the source table, pooled over those
    positions: the number a transcription checked against its source reports, and the number
    :func:`ocr_gate` takes. Each rate is converted to :func:`ocr_noise`'s injector rate per
    table and mode. For a confusion that is the rate divided by the share of eligible digits
    whose glyph is a key, so a measured 0.02 is an injector rate of about 0.05 when four of
    ten glyphs are confusable.

    Parameters
    ----------
    detector : callable
        ``f(sample) -> p-value``, unwrapped as in :func:`red_team`.
    honest_table : callable
        ``f(rng) -> table``, drawing one fresh honest table like the ones that will be
        transcribed: the same size and the same range of magnitudes. Every replicate draws its
        own. A fixed table is refused, because it is one draw: noise added to it measures how
        that table responds, and a table that happens to sit short of the digit a scanner
        produces absorbs more corruption before the test fires than a fresh one does.
    error_rates : sequence of float
        Transcription error rates to test, in the measured unit above. ``0.0``, the clean
        table, is always tested as well: a test that already misfires on clean tables cannot
        be rescued by an accurate transcription.
    confusions : mapping, or sequence of mappings
        Glyph confusion tables as in :func:`ocr_noise`, at least one. A rate that a
        confusion cannot produce on a table, because too few of its digits are keys, is
        refused rather than tested at a lower rate.
    alpha : float
        The detector fires when its p-value is at or below this.
    tolerance : float
        How far above ``alpha`` the firing rate on honest tables may be.
    n_replicates : int
        Honest tables drawn. The same tables, and the same misread draws, are reused at every
        rate, so a higher rate corrupts a superset of the digits a lower one did. Too few to
        resolve ``tolerance`` is refused: if a test firing at exactly ``alpha`` on them could
        not be shown to be within it, every answer would be ``None``.
    confidence : float
        Of the upper bound on each firing rate.

    Returns
    -------
    float or None
        The highest rate in ``error_rates`` such that the detector passes at it and at every
        lower rate tested, under every mode. When it is calibrated everywhere tested
        this is the highest rate tested: :func:`ocr_gate` admits nothing above it, so the gate
        never opens at a rate nobody measured. ``0.0`` means it misfires already at the lowest
        positive rate tested. ``None`` means it misfires on clean honest tables, and no
        transcription can make it usable. Rates between two tested rates are admitted only
        below the threshold, which assumes more corruption does not make a test fire less.

        A replicate on which the detector raises or returns no usable p-value counts as a
        firing. Under a calibration rule, counting it as a non-firing would let a detector
        that never answers through the gate.
    """
    if not callable(honest_table):
        raise RedTeamError(
            "honest_table must be a function rng -> table that draws a fresh honest table. A "
            "fixed table is one draw: noise added to it measures how that one table responds, "
            "not how often the test fires on honest tables, which is what the gate needs."
        )
    if not error_rates:
        raise RedTeamError("error_rates is empty")
    rates = sorted({float(r) for r in error_rates} | {0.0})
    if any(not 0.0 <= r <= 1.0 for r in rates):
        raise RedTeamError(f"error_rates must lie in [0, 1]; got {sorted(error_rates)}")
    if not 0.0 < alpha < 1.0:
        raise RedTeamError(f"alpha must be in (0, 1); got {alpha}")
    if not 0.0 < tolerance < 1.0 - alpha:
        raise RedTeamError(f"tolerance must be in (0, {1.0 - alpha}); got {tolerance}")
    if not 0.0 < confidence < 1.0:
        raise RedTeamError(f"confidence must be in (0, 1); got {confidence}")
    if n_replicates < 1:
        raise RedTeamError("n_replicates must be at least 1")
    ceiling = alpha + tolerance
    floor = _upper_bound(alpha, n_replicates, confidence)
    if floor > ceiling:
        raise RedTeamError(
            f"{n_replicates} replicates cannot resolve a tolerance of {tolerance}: a test firing "
            f"at exactly alpha = {alpha} on them has an upper bound of {floor:.4f}, above "
            f"{ceiling:.4f}, so no rate could pass. Draw more replicates."
        )
    pos = _digit_positions(positions)

    listed = [confusions] if isinstance(confusions, Mapping) else list(confusions)
    if not listed:
        raise RedTeamError(
            "confusions is empty. The glyph-confusion mode is the realistic OCR failure and "
            "the one a uniformity test can see; a threshold without it is not a threshold."
        )
    modes: list[dict[int, int] | None] = [None]
    for confusion in listed:
        table = _confusion_table(confusion)
        if not table:
            raise RedTeamError("a confusion table with no entries misreads nothing")
        modes.append(table)

    base = np.random.default_rng(seed)
    table_seeds = base.integers(0, 2**31 - 1, size=n_replicates)
    noise_seeds = base.integers(0, 2**31 - 1, size=n_replicates)
    tables = [_honest_draw(honest_table, int(s)) for s in table_seeds]
    changeable = [[_changeable_share(t, pos, mode) for t in tables] for mode in modes]

    def fired_on(rate: float, m: int) -> int:
        fired = 0
        for i, table in enumerate(tables):
            injector = 0.0
            if rate > 0.0:
                share = changeable[m][i]
                if share <= 0.0 or rate > share * (1.0 + 1e-12):
                    raise RedTeamError(
                        f"a transcription error rate of {rate} cannot be produced by confusion "
                        f"{modes[m]} on honest table {i}: at most {share:.4g} of its digits at "
                        f"positions {pos} are keys. Drop the rate from error_rates."
                    )
                injector = min(rate / share, 1.0)
            _, sample = ocr_noise(
                table, injector, pos, confusion=modes[m], seed=int(noise_seeds[i])
            )
            try:
                pvalue = _pvalue_of(detector(sample))
            except Exception:
                pvalue = None
            if pvalue is None or not np.isfinite(pvalue) or pvalue <= alpha:
                fired += 1
        return fired

    passed: float | None = None
    for rate in rates:
        for m in range(len(modes) if rate > 0.0 else 1):
            firing = fired_on(rate, m) / n_replicates
            if _upper_bound(firing, n_replicates, confidence) > ceiling:
                return passed
        passed = rate
    return passed


def _honest_draw(honest_table: Callable[[np.random.Generator], ArrayLike], seed: int) -> np.ndarray:
    table = _as_float_1d(honest_table(np.random.default_rng(seed)), "honest table")
    if not np.allclose(table, np.round(table), atol=1e-9):
        raise RedTeamError("honest_table must return integer-valued tables, as ocr_noise needs")
    return table


def _changeable_share(
    table: np.ndarray, positions: list[int], confusion: dict[int, int] | None
) -> float:
    """The share of existing digits at ``positions`` that a misread in this mode can change."""
    ints = np.round(np.abs(table)).astype(np.int64)
    keys = None if confusion is None else np.array(sorted(confusion), dtype=np.int64)
    eligible = changeable = 0
    for p in positions:
        power = 10**p
        digits = (ints[ints >= power] // power) % 10
        eligible += digits.size
        changeable += digits.size if keys is None else int(np.isin(digits, keys).sum())
    if eligible == 0:
        raise RedTeamError(f"no value in an honest table has a digit at positions {positions}")
    return changeable / eligible


def ocr_gate(
    firing_threshold: float | None,
    measured_error_rate: float,
    *,
    n_compared: int,
    confidence: float = 0.95,
) -> bool:
    """Whether a digit test may be run on a table with this measured error rate.

    ``firing_threshold`` is :func:`ocr_firing_threshold`'s answer, and ``measured_error_rate``
    is in its unit: the share of the ``n_compared`` digits at the tested positions that differ
    from the source. The gate opens only when the one-sided Clopper-Pearson upper bound of
    that rate, at ``confidence``, is at or below the threshold. A point estimate would admit
    a table checked on 50 digits with one error as readily as one checked on 5,000 with 100.

    Comparing two transcriptions with each other rather than one with the source gives a
    disagreement rate of roughly twice either one's error rate while errors are rare, which
    overstates the error and keeps the gate on the safe side. That holds only if the two
    transcriptions are independent: two passes of the same OCR engine make the same
    confusions, agree on them, and understate it.

    ``None`` does not open the gate: the detector misfires on clean honest tables.
    """
    if not 0.0 <= measured_error_rate <= 1.0:
        raise RedTeamError(f"measured_error_rate must be in [0, 1]; got {measured_error_rate}")
    if isinstance(n_compared, bool) or int(n_compared) != n_compared or n_compared < 1:
        raise RedTeamError(f"n_compared must be a positive number of digits; got {n_compared}")
    if not 0.0 < confidence < 1.0:
        raise RedTeamError(f"confidence must be in (0, 1); got {confidence}")
    if firing_threshold is None:
        return False
    if not 0.0 <= firing_threshold <= 1.0:
        raise RedTeamError(f"firing_threshold must be in [0, 1]; got {firing_threshold}")
    return _upper_bound(measured_error_rate, int(n_compared), confidence) <= firing_threshold


def _upper_bound(share: float, n: int, confidence: float) -> float:
    """One-sided Clopper-Pearson upper bound on a proportion observed as ``share`` of ``n``."""
    k = share * n
    if k >= n:
        return 1.0
    return float(stats.beta.ppf(confidence, k + 1.0, n - k))


# ---------------------------------------------------------------- reporting


def format_redteam_table(results: Sequence[RedTeamResult]) -> str:
    """Every pair, one line each, firings called out below. Paste into ``docs/redteam.md``."""
    if not results:
        return "NO RED-TEAM PASS RUN."

    header = f"{'trap':<14} {'detector':<28} {'p':>10} {'fired':>7}"
    lines = [header, "-" * len(header)]
    for r in results:
        p = "-" if r.pvalue is None else f"{r.pvalue:.4g}"
        lines.append(f"{r.trap_id:<14} {r.detector:<28} {p:>10} {r.fired!s:>7}")

    hits = casualties(results)
    lines.append("")
    if not hits:
        lines.append("No detector fired on any trap in this pass.")
    else:
        lines.append(f"{len(hits)} of {len(results)} pairs fired on honest data:")
        for r in hits:
            lines.append(f"  {r.detector} on {r.trap_id} — {r.spec.summary}")
    return "\n".join(lines)
