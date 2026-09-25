"""A declarative catalogue of incentive discontinuities.

The programme's unifying hypothesis is that distortion concentrates at discontinuities in the
incentive function. Every project has one: the 100 per cent plan-fulfilment bonus, the round
vote share, the analyst consensus, the provincial growth target. Today that claim lives in four
project READMEs as prose, which means it is four separate stories rather than one hypothesis.

A catalogue makes it one experiment. Each project writes ``notches.yaml``; :func:`scan_all`
runs the same estimator over all of them and returns one table; and the hypothesis becomes
something that can be confirmed or refuted rather than illustrated.

The two fields that keep this honest
------------------------------------
``incentive`` and ``evidence`` are mandatory, and that is the whole design.

A notch is a place where somebody gained something by reporting a number on one side of a line.
If nobody can say what they gained, it is a **round number**, not a notch, and it belongs in the
digit tests instead. Without that distinction the catalogue becomes a fishing expedition: scan
enough thresholds and something always looks like a spike.

So an entry must state what is discontinuous, for whom, and where that is documented. Entries
whose institutional basis is inferred rather than sourced must say so with ``status:
unverified``. Recording a weak entry honestly is fine; dressing a round number up as a
documented incentive is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml

from forensics_core.bunching.notch import Kink, Notch

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

#: Values ``kind`` may take.
KINDS = ("notch", "kink")

#: Values ``side`` may take. Ignored for a kink, which has no rewarded side.
SIDES = ("above", "below")

#: Values ``status`` may take. ``verified`` means the incentive is documented in a source the
#: project records; ``unverified`` means it is inferred, and the entry says what was tried.
STATUSES = ("verified", "unverified")

#: Columns :func:`scan_all` returns, in order.
SCAN_ALL_COLUMNS = [
    "id",
    "variable",
    "threshold",
    "kind",
    "side",
    "status",
    "excess_mass",
    "missing_mass",
    "normalized_excess",
    "n_in_window",
    "n_confounds",
]


class NotchCatalogueError(ValueError):
    """A catalogue entry is malformed, or claims an incentive it cannot support."""


@dataclass(frozen=True)
class NotchEntry:
    """One incentive discontinuity, as a project records it.

    Attributes
    ----------
    id : str
        Stable slug, unique within the file.
    variable : str
        The column the threshold applies to. Named rather than assumed, because a threshold is
        meaningless without the quantity it is a threshold on.
    threshold : float
        Where the payoff jumps (a notch) or changes slope (a kink).
    kind : {"notch", "kink"}
        A notch is a discontinuous payoff, a kink a discontinuous slope. They imply different
        estimators and different predicted shapes.
    side : {"above", "below"}
        Where the reward lies, so which side mass should pile on. Meaningless for a kink and
        ignored there.
    incentive : str
        **Required.** What is discontinuous, and for whom. If this cannot be written, the entry
        is a round number rather than a notch and does not belong here.
    evidence : str
        **Required.** Where the incentive is documented, or what was tried if it is not.
    confounds : list of str
        Trap identifiers from the project's ``known_traps.md`` that produce bunching here
        without anyone misreporting. An empty list is allowed but is itself a claim.
    status : {"verified", "unverified"}
        Whether the incentive is documented or inferred.
    notes : str
        Anything else worth carrying.
    """

    id: str
    variable: str
    threshold: float
    incentive: str
    evidence: str
    kind: Literal["notch", "kink"] = "notch"
    side: Literal["above", "below"] = "above"
    confounds: list[str] = field(default_factory=list)
    status: Literal["verified", "unverified"] = "unverified"
    notes: str = ""

    def to_notch(self) -> Notch | Kink:
        """Build the object :mod:`forensics_core.bunching.notch` estimators accept."""
        if self.kind == "kink":
            return Kink(threshold=self.threshold, label=self.id)
        return Notch(threshold=self.threshold, side=self.side, label=self.id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "variable": self.variable,
            "threshold": self.threshold,
            "kind": self.kind,
            "side": self.side,
            "incentive": self.incentive,
            "evidence": self.evidence,
            "confounds": list(self.confounds),
            "status": self.status,
            "notes": self.notes,
        }


def _require_text(raw: dict, key: str, entry_id: str, why: str) -> str:
    value = str(raw.get(key, "") or "").strip()
    if not value:
        raise NotchCatalogueError(f"notch {entry_id!r}: {key} is required. {why}")
    return value


def parse_entry(raw: dict, *, index: int = 0) -> NotchEntry:
    """Build one :class:`NotchEntry`, rejecting anything that cannot support a claim."""
    if not isinstance(raw, dict):
        raise NotchCatalogueError(f"entry {index} is not a mapping; got {type(raw).__name__}")

    entry_id = str(raw.get("id", "") or "").strip()
    if not entry_id:
        raise NotchCatalogueError(f"entry {index} has no id")

    variable = _require_text(
        raw, "variable", entry_id, "A threshold is meaningless without the column it applies to."
    )
    incentive = _require_text(
        raw,
        "incentive",
        entry_id,
        "A notch is a place where someone gained something by reporting on one side of a line. "
        "If that cannot be stated, this is a round number and belongs in the digit tests.",
    )
    evidence = _require_text(
        raw,
        "evidence",
        entry_id,
        "Say where the incentive is documented, or what was tried and failed. An unsourced "
        "institutional claim is exactly what this programme exists not to make.",
    )

    kind = str(raw.get("kind", "notch"))
    if kind not in KINDS:
        raise NotchCatalogueError(f"notch {entry_id!r}: kind must be one of {KINDS}; got {kind!r}")
    side = str(raw.get("side", "above"))
    if side not in SIDES:
        raise NotchCatalogueError(f"notch {entry_id!r}: side must be one of {SIDES}; got {side!r}")
    status = str(raw.get("status", "unverified"))
    if status not in STATUSES:
        raise NotchCatalogueError(
            f"notch {entry_id!r}: status must be one of {STATUSES}; got {status!r}"
        )

    try:
        threshold = float(raw["threshold"])
    except (KeyError, TypeError, ValueError) as exc:
        raise NotchCatalogueError(f"notch {entry_id!r}: threshold must be a number") from exc

    confounds = raw.get("confounds") or []
    if not isinstance(confounds, list):
        raise NotchCatalogueError(f"notch {entry_id!r}: confounds must be a list")

    return NotchEntry(
        id=entry_id,
        variable=variable,
        threshold=threshold,
        incentive=incentive,
        evidence=evidence,
        kind=kind,  # type: ignore[arg-type]
        side=side,  # type: ignore[arg-type]
        confounds=[str(c) for c in confounds],
        status=status,  # type: ignore[arg-type]
        notes=str(raw.get("notes", "") or ""),
    )


def load_notches(path: str | Path) -> list[NotchEntry]:
    """Read and validate a project's ``notches.yaml``.

    Raises
    ------
    NotchCatalogueError
        On a malformed file, a duplicate id, or an entry that cannot support a claim.
    """
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise NotchCatalogueError(f"{path}: the catalogue must be a list of entries")

    entries = [parse_entry(item, index=i) for i, item in enumerate(raw)]
    seen: set[str] = set()
    for e in entries:
        if e.id in seen:
            raise NotchCatalogueError(f"{path}: duplicate notch id {e.id!r}")
        seen.add(e.id)
    return entries


def validate_notches(path: str | Path) -> list[str]:
    """Return human-readable problems, empty when the catalogue is sound.

    Unlike :func:`load_notches` this does not raise, so a project can report every problem at
    once rather than one per run.
    """
    problems: list[str] = []
    path = Path(path)
    if not path.is_file():
        return [f"{path}: no such file"]
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [f"{path}: not valid YAML: {exc}"]
    if raw is None:
        return []
    if not isinstance(raw, list):
        return [f"{path}: the catalogue must be a list of entries"]

    seen: set[str] = set()
    for i, item in enumerate(raw):
        try:
            entry = parse_entry(item, index=i)
        except NotchCatalogueError as exc:
            problems.append(str(exc))
            continue
        if entry.id in seen:
            problems.append(f"duplicate notch id {entry.id!r}")
        seen.add(entry.id)
        if not entry.confounds:
            problems.append(
                f"notch {entry.id!r}: no confounds listed. Bunching at a threshold almost "
                "always has an innocent explanation; if none is known, say so in notes."
            )
    return problems


def in_range(entry: NotchEntry, values: Any) -> bool:
    """Whether the threshold falls inside the observed range of ``values``.

    A threshold outside the data cannot be tested, and scanning it produces a meaningless row
    rather than an error, so callers should check.
    """
    import numpy as np

    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return False
    return bool(arr.min() <= entry.threshold <= arr.max())


def scan_all(
    frame: pd.DataFrame,
    catalogue: list[NotchEntry],
    *,
    bin_width: float,
    exclude_below: float,
    exclude_above: float,
    poly_degree: int = 7,
    skip_out_of_range: bool = True,
    **kw: Any,
) -> pd.DataFrame:
    """Estimate excess mass at every catalogued notch, as one table.

    This is what turns the unifying hypothesis into a single experiment: one call, one table,
    every project's notches scored by the same estimator with the same settings.

    Entries whose ``variable`` is not a column of ``frame`` are skipped, as are thresholds
    outside the observed range when ``skip_out_of_range`` is true, because a threshold the data
    never reaches yields a number that looks like a result and is not one.

    Returns a frame with :data:`SCAN_ALL_COLUMNS`, sorted by ``normalized_excess`` descending.
    """
    import pandas as pd

    from forensics_core.bunching.density import bunching_estimator

    rows: list[dict[str, Any]] = []
    for entry in catalogue:
        if entry.variable not in frame.columns:
            continue
        values = frame[entry.variable].to_numpy(dtype=float)
        if skip_out_of_range and not in_range(entry, values):
            continue
        # The side must be passed through, and getting it wrong silently inverts the answer.
        # `excess_mass` is summed over the excluded bins on the BUNCHING side, so an estimator
        # told to look below a threshold where the mass actually piles above reports a large
        # NEGATIVE excess. The programme's flagship notch, the 100 per cent plan-fulfilment
        # bonus, rewards being above, so a scan that did not pass the side would rank it last
        # rather than first. A kink has no rewarded side; it is scanned as "below", which is
        # the estimator's own default, and its `side` column is reported as recorded.
        result = bunching_estimator(
            values,
            entry.threshold,
            bin_width=bin_width,
            exclude_below=exclude_below,
            exclude_above=exclude_above,
            poly_degree=poly_degree,
            bunching_side="below" if entry.kind == "kink" else entry.side,
            **kw,
        )
        rows.append(
            {
                "id": entry.id,
                "variable": entry.variable,
                "threshold": entry.threshold,
                "kind": entry.kind,
                "side": entry.side,
                "status": entry.status,
                "excess_mass": float(result.excess_mass),
                "missing_mass": float(result.missing_mass),
                "normalized_excess": float(result.normalized_excess),
                "n_in_window": float(result.settings.get("n_in_window", float("nan"))),
                "n_confounds": len(entry.confounds),
            }
        )

    out = pd.DataFrame(rows, columns=SCAN_ALL_COLUMNS)
    if not out.empty:
        out = out.sort_values("normalized_excess", ascending=False).reset_index(drop=True)
    return out
