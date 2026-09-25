"""A common effect-size scale, and an honest account of where it stops working.

Integer excess is a count, bunching is normalised excess mass, underdispersion is a variance
ratio. Three incomparable tables cannot answer "which method family gives the most detection
power per unit of distortion", which is this programme's stated research question for
elections (ROADMAP.md, WO-109).

The scale
---------
Every mechanism is expressed as

    displacement = share of units touched  x  mean relative displacement of a touched unit

which is natural for all four injectors and reads as a substantive sentence: *about x per cent
of the reported numbers were moved, by about y per cent each*.

Measured against :mod:`forensics_core.inject`, it behaves. It is linear in ``fraction`` for
rounding, linear in ``mass`` for bunching, exactly ``block_share x magnitude`` for padding, and
monotone decreasing in ``retain`` for smoothing. All four land on one axis.

Where it stops working, and it does
-----------------------------------
``displacement`` is a **gross** quantity: it adds up movement without regard to direction. For
two of the four mechanisms that is also the net misreporting, and for two it is not. Measured
as ``net / gross`` (:attr:`CommonEffect.directionality`):

===============  ===============  ==============================================
mechanism        net / gross      what the movement does
===============  ===============  ==============================================
padding          1.000            every touched year inflated; gross *is* net
bunching         1.000            every mover crosses the threshold the same way
rounding         0.016 to 0.023   units round up and down about equally
smoothing        -0.005           deviations shrink around a preserved level
===============  ===============  ==============================================

(Measured over the fixtures in ``tests/test_effect.py``; the full grid is in
``docs/effect_size.md``. The rounding figure varies with the draw because its net displacement
is near zero, which is the point rather than a measurement problem.)

So the sentence "about x per cent of reported output was moved, by about y per cent" is a
**true claim about quantity** for padding and bunching, and a **false one** for rounding and
smoothing, where almost no quantity moves at all. Rounding displaces digits; smoothing
displaces variance. Both leave the total essentially where it was.

This is not a defect in the scale, and forcing the four into one substantive reading would be
worse than saying so. The consequence is a split in what the number may be used for:

- **As a comparison axis for detection power** — all four, without qualification. That is the
  question the power atlas asks, and it only needs the mechanisms ordered on one axis.
- **As a substantive claim about how much output was misreported** — padding and bunching
  only. :func:`as_quantity_claim` refuses the other two rather than letting the sentence be
  written.

The gosplan bound the programme is eventually aiming at ("distortion is at least X in sector S
over years Y") is a padding claim, so it falls in the half where the reading holds.

Never a replacement for native units
------------------------------------
The common scale is an additional reporting column. A published estimator's output is reported
in its own units — Kobak's integer excess as a count, Chetty's excess mass as a normalised
ratio — and the common scale sits beside it. :func:`effect_table` builds exactly that pairing,
and nothing here rescales an estimator's output into the common scale, because a reader
comparing this programme's numbers against the source paper's must find the source paper's.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import ArrayLike

__all__ = [
    "QUANTITY_MECHANISMS",
    "SHAPE_MECHANISMS",
    "CommonEffect",
    "EffectError",
    "as_quantity_claim",
    "effect_table",
    "measure_effect",
]

#: Above this ``|directionality|`` the movement is one-directional enough that gross
#: displacement can be read as net misreporting. Padding and bunching measure 1.000; rounding
#: and smoothing measure under 0.02. Nothing observed so far lands near the boundary, which is
#: why a single cut is adequate; if a mechanism ever does, it needs its own discussion rather
#: than a tie-break.
QUANTITY_DIRECTIONALITY: float = 0.5

#: Mechanisms whose displacement is net misreporting, from the measurements in
#: ``docs/effect_size.md``.
QUANTITY_MECHANISMS: tuple[str, ...] = ("padding", "bunching")

#: Mechanisms that move the shape of the numbers while leaving the total where it was.
SHAPE_MECHANISMS: tuple[str, ...] = ("rounding", "smoothing")


class EffectError(ValueError):
    """A common effect size was computed or read in a way that would misstate it."""


@dataclass(frozen=True)
class CommonEffect:
    """One distortion on the common scale, with the evidence for how it may be read.

    Attributes
    ----------
    displacement : float
        The common scale: ``share_touched * mean_relative_displacement``. Gross.
    share_touched : float
        Share of all units whose value changed.
    mean_relative_displacement : float
        Mean of ``|after - before| / |before|`` over touched units only. Undefined for a
        touched unit whose ``before`` is zero, which is why such units are counted and
        excluded rather than contributing an infinity.
    net_displacement, gross_displacement : float
        Signed and unsigned total movement, each as a share of ``sum(|before|)``.
    directionality : float
        ``net / gross``, in ``[-1, 1]``. One means every unit moved the same way.
    n, n_touched, n_undefined : int
        Sample size, units moved, and touched units dropped for a zero baseline.
    """

    displacement: float
    share_touched: float
    mean_relative_displacement: float
    net_displacement: float
    gross_displacement: float
    directionality: float
    n: int
    n_touched: int
    n_undefined: int = 0

    @property
    def moves_quantity(self) -> bool:
        """Whether gross displacement may be read as net misreporting."""
        return abs(self.directionality) >= QUANTITY_DIRECTIONALITY

    def to_dict(self) -> dict[str, Any]:
        return {
            "displacement": self.displacement,
            "share_touched": self.share_touched,
            "mean_relative_displacement": self.mean_relative_displacement,
            "net_displacement": self.net_displacement,
            "gross_displacement": self.gross_displacement,
            "directionality": self.directionality,
            "moves_quantity": self.moves_quantity,
            "n": self.n,
            "n_touched": self.n_touched,
            "n_undefined": self.n_undefined,
        }


def measure_effect(before: ArrayLike, after: ArrayLike) -> CommonEffect:
    """The common effect size of one distortion, measured from the two series.

    Mechanism-agnostic by construction: it reads only what changed. An injector's own
    parameter is not consulted and does not need to be, which is what makes the four
    comparable — a scale defined per-mechanism would be four scales.

    Parameters
    ----------
    before, after : array-like
        Equal-length finite 1-D arrays, the series before and after the distortion.

    Raises
    ------
    EffectError
        On mismatched lengths, empty input, or non-finite values. A non-finite value is
        refused rather than dropped: dropping one silently changes both the share touched and
        the denominator of every relative displacement.
    """
    b = np.asarray(before, dtype=float).ravel()
    a = np.asarray(after, dtype=float).ravel()
    if b.size != a.size:
        raise EffectError(f"before and after must be the same length; got {b.size} and {a.size}")
    if b.size == 0:
        raise EffectError("before is empty")
    if not np.isfinite(b).all() or not np.isfinite(a).all():
        raise EffectError(
            "before and after must be finite. A non-finite value is refused rather than "
            "dropped: dropping one changes the share touched and the denominator of every "
            "relative displacement at once."
        )

    total = float(np.abs(b).sum())
    if total == 0.0:
        raise EffectError(
            "the baseline series is identically zero, so there is no scale to express a "
            "relative displacement against"
        )

    moved = a != b
    n_touched = int(moved.sum())
    if n_touched == 0:
        return CommonEffect(
            displacement=0.0,
            share_touched=0.0,
            mean_relative_displacement=0.0,
            net_displacement=0.0,
            gross_displacement=0.0,
            directionality=0.0,
            n=int(b.size),
            n_touched=0,
        )

    delta = a[moved] - b[moved]
    base = b[moved]
    usable = base != 0.0
    n_undefined = int((~usable).sum())
    rel = np.abs(delta[usable]) / np.abs(base[usable])
    mean_rel = float(rel.mean()) if rel.size else 0.0

    share = n_touched / b.size
    gross = float(np.abs(delta).sum() / total)
    net = float(delta.sum() / total)
    return CommonEffect(
        displacement=float(share * mean_rel),
        share_touched=float(share),
        mean_relative_displacement=mean_rel,
        net_displacement=net,
        gross_displacement=gross,
        directionality=float(net / gross) if gross > 0 else 0.0,
        n=int(b.size),
        n_touched=n_touched,
        n_undefined=n_undefined,
    )


def as_quantity_claim(effect: CommonEffect, mechanism: str | None = None) -> str:
    """The substantive sentence, or a refusal to write it.

    "About x per cent of the reported numbers were moved, by about y per cent each" is a claim
    about output. It is true for padding and bunching, where every touched unit moves the same
    way, and false for rounding and smoothing, where the movement cancels and the total stays
    where it was. Rounding at ``fraction=1.0`` displaces 0.46% of the numbers gross and 0.008%
    net; a sentence quoting the first as misreporting would overstate it by a factor of 55.

    Raises
    ------
    EffectError
        If the movement is not one-directional enough to support the reading, naming the
        measured directionality and what may be said instead.
    """
    if mechanism is not None and mechanism in SHAPE_MECHANISMS:
        raise EffectError(
            f"{mechanism!r} moves the shape of the numbers, not their quantity (see "
            "docs/effect_size.md). Its displacement is a valid comparison axis for detection "
            "power and is not a statement about how much output was misreported."
        )
    if not effect.moves_quantity:
        raise EffectError(
            f"directionality is {effect.directionality:.3f}, so gross displacement "
            f"({effect.gross_displacement:.5f}) is not net misreporting "
            f"({effect.net_displacement:.5f}): the movement cancels. Report the displacement "
            "as a comparison axis, and do not write it as a share of output."
        )
    return (
        f"about {100 * effect.share_touched:.1f}% of units were moved, by about "
        f"{100 * effect.mean_relative_displacement:.1f}% each "
        f"(net {100 * effect.net_displacement:+.2f}% of the total)"
    )


def effect_table(
    rows: Sequence[tuple[str, str, float, CommonEffect]],
) -> str:
    """Native units and the common scale side by side, never one instead of the other.

    Parameters
    ----------
    rows : sequence of (method, native_unit, native_value, CommonEffect)
        ``native_value`` is the estimator's own output in its own units — Kobak's integer
        excess as a count, Chetty's excess mass as a ratio. It is printed unchanged.
    """
    if not rows:
        return "NO EFFECTS MEASURED."

    header = f"{'method':<22} {'native':>14} {'unit':<20} {'displacement':>13} {'reads as':>10}"
    lines = [header, "-" * len(header)]
    for method, unit, native, eff in rows:
        reads = "quantity" if eff.moves_quantity else "shape"
        lines.append(
            f"{method:<22} {native:>14.6g} {unit:<20} {eff.displacement:>13.6f} {reads:>10}"
        )
    lines.append("")
    lines.append(
        "Native values are the estimators' own and are never rescaled. Displacement is a "
        "comparison axis; only rows reading 'quantity' may be stated as shares of output."
    )
    return "\n".join(lines)
