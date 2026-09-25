"""The power atlas as a query: is this effect detectable at this sample size.

The gosplan and china cards need one call that answers "can this method see an effect this
size at the sample I have", and they need the answer to be citable. :mod:`.atlas` measures the
numbers and stores them; this module is the read side that other repositories call.

Refusing to extrapolate is the point
------------------------------------
A query below the smallest or above the largest sample size an atlas measured raises
:class:`~forensics_core.power.atlas.AtlasError` naming the range the atlas does cover. It does
not return a number. A power number invented outside the measured points is not a
measurement, and here it would go straight into a claim about the historical record.

The same applies to effect sizes: :func:`detectable` answers ``False`` for an effect no bigger
than the largest one measured when nothing measured reached the target power, and refuses for
a larger effect, because whether *that* would be detected was never measured.

What is not settled yet
-----------------------
Three parts of the query are open questions filed as ambiguity reports, and each raises
``NotImplementedError`` naming its report rather than choosing a default:

- ``atlas=None``: where stored atlases live and which one answers when several cover the same
  method (``workorders/AMBIGUITY-WO-111-1.md``). Pass an atlas, or a path to one, explicitly.
- A sample size inside the measured range that was not itself measured, such as ``n = 200`` in
  an atlas measured at 100 and 300 (``AMBIGUITY-WO-111-2.md``).
- Any ``aggregation`` other than ``"unit"`` (``AMBIGUITY-WO-111-3.md``).

The format is the one :func:`~forensics_core.power.atlas.save_atlas` writes; see
``data/atlas/README.md`` and ``docs/power_atlas.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from forensics_core.power import atlas as _atlas
from forensics_core.power.atlas import AtlasError

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

__all__ = [
    "AGGREGATIONS",
    "detectable",
    "minimum_detectable_effect",
]

#: The aggregation levels a query may name. ``"unit"`` is what
#: :func:`~forensics_core.power.atlas.power_curve` measures: no aggregation at all.
AGGREGATIONS: tuple[str, ...] = ("unit",)


def _resolve(
    atlas: pd.DataFrame | str | Path | None, method: str, aggregation: str
) -> pd.DataFrame:
    """The atlas rows for ``method``, or a refusal saying why there are none."""
    if aggregation not in AGGREGATIONS:
        raise NotImplementedError(
            f"aggregation={aggregation!r} is not answered yet: the atlas format has no "
            "aggregation dimension, and how one is added is open "
            "(workorders/AMBIGUITY-WO-111-3.md). Only 'unit' is answered."
        )
    if atlas is None:
        raise NotImplementedError(
            "no atlas was given, and where stored atlases live and which one answers when "
            "several cover a method is open (workorders/AMBIGUITY-WO-111-1.md). Pass the atlas, "
            "or a path to one, as atlas=..."
        )
    frame = _atlas.load_atlas(atlas) if isinstance(atlas, (str, Path)) else atlas

    missing = [c for c in _atlas.ATLAS_COLUMNS if c not in frame.columns]
    if missing:
        raise AtlasError(f"not an atlas: missing columns {missing}")
    rows = frame[frame["method"] == method]
    if rows.empty:
        known = sorted(frame["method"].unique())
        raise AtlasError(f"the atlas has no rows for method {method!r}; it measured {known}")
    return rows


def _check_covered(rows: pd.DataFrame, method: str, n: int) -> None:
    """Refuse an ``n`` outside the measured range, and an unmeasured ``n`` inside it."""
    measured = sorted(int(x) for x in rows["n"].unique())
    if n < measured[0] or n > measured[-1]:
        raise AtlasError(
            f"the atlas does not cover n={n} for {method!r}: it measured n from {measured[0]} "
            f"to {measured[-1]} ({measured}). It will not extrapolate; a power number outside "
            "the measured range is not a measurement."
        )
    if n not in measured:
        raise NotImplementedError(
            f"n={n} lies inside the measured range {measured} but was not itself measured, and "
            "how such a query is answered is open (workorders/AMBIGUITY-WO-111-2.md)."
        )


def minimum_detectable_effect(
    method: str,
    n: int,
    *,
    aggregation: str = "unit",
    power: float = 0.8,
    atlas: pd.DataFrame | str | Path | None = None,
) -> float:
    """The smallest measured effect that ``method`` detects with ``power`` at sample size ``n``.

    Parameters
    ----------
    method : str
        The ``method`` recorded in the atlas rows.
    n : int
        The sample size the caller has.
    aggregation : str
        Only ``"unit"``; see :data:`AGGREGATIONS`.
    power : float
        Target power.
    atlas : DataFrame, path, or None
        An atlas as :func:`~forensics_core.power.atlas.power_curve` returns it, or a path that
        :func:`~forensics_core.power.atlas.load_atlas` reads. ``None`` is not answered yet.

    Raises
    ------
    AtlasError
        If the atlas has no rows for ``method``, ``n`` is outside the measured range, no
        measured effect reaches ``power`` at ``n``, or the false-positive rate at ``n`` is too
        far above nominal for the power to be read.
    NotImplementedError
        For the open questions listed in the module docstring.
    """
    n = int(n)
    rows = _resolve(atlas, method, aggregation)
    _check_covered(rows, method, n)
    return _atlas.minimum_detectable_effect(rows, n, target_power=power, method=method)


def detectable(
    method: str,
    n: int,
    effect: float,
    *,
    aggregation: str = "unit",
    power: float = 0.8,
    atlas: pd.DataFrame | str | Path | None = None,
) -> bool:
    """Whether ``method`` detects an effect of size ``effect`` with ``power`` at sample size ``n``.

    ``True`` when ``effect`` is at least the :func:`minimum_detectable_effect`. ``False`` when it
    is smaller, or when no measured effect reached ``power`` and ``effect`` is no larger than the
    largest one measured.

    Raises
    ------
    AtlasError
        If ``n`` is outside the measured range, the false-positive rate at ``n`` is too far
        above nominal, or no measured effect reached ``power`` and ``effect`` exceeds every
        measured effect, so whether it would be detected was never measured.
    NotImplementedError
        For the open questions listed in the module docstring.
    """
    n = int(n)
    rows = _resolve(atlas, method, aggregation)
    _check_covered(rows, method, n)

    at_n = rows[rows["n"] == n]
    fpr = float(at_n["false_positive_rate"].iloc[0])
    alpha = float(at_n["alpha"].iloc[0])
    if fpr > _atlas.FPR_TOLERANCE * alpha:
        raise AtlasError(
            f"at n={n} the false-positive rate is {fpr:.3f} against a nominal {alpha:.3f}, so "
            "the power column cannot be read and detectability cannot be answered either way."
        )
    reaching = at_n[(at_n["effect_size"] > 0) & (at_n["power"] >= power)]
    if reaching.empty:
        largest = float(at_n["effect_size"].max())
        if float(effect) > largest:
            raise AtlasError(
                f"no measured effect reaches power {power} at n={n}, and effect={effect} is "
                f"larger than the largest measured ({largest}). Whether it would be detected "
                "was never measured, and the atlas will not extrapolate."
            )
        return False
    return float(effect) >= minimum_detectable_effect(
        method, n, aggregation=aggregation, power=power, atlas=rows
    )
