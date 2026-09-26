"""The published power atlas: a frozen format, a loader, and the queries a card asks.

WO-100 measured power as a function of sample size, WO-101 measured what aggregation costs, and
WO-109 put the four method families on one effect-size axis. All three left the result in memory
as a DataFrame. A curve that lives only in the session that produced it cannot answer the
question gosplan and china actually have -- *is this detectable at my sample size* -- and cannot
be cited: a later reader has no way to tell which library release, which estimator settings or
which seed produced the number. This module freezes the on-disk format, loads it, and answers
the two queries, refusing anything the stored atlas does not cover.

The format
----------
A published atlas is a parquet file in the layout
:func:`forensics_core.power.atlas.save_atlas` writes: one row per ``(n, effect_size)`` carrying
:data:`~forensics_core.power.atlas.ATLAS_COLUMNS`, with the record of how it was measured in the
``_spec`` column. Two keys are required in that record's ``settings``:

``library_version``
    ``forensics_core.__version__`` at the moment of publication. The estimator code is not
    frozen when the atlas is, so two releases are two different atlases and a number whose
    release cannot be named is not citable.
``aggregation``
    The rung the curve was measured at. ``"unit"`` is a plain
    :func:`~forensics_core.power.atlas.power_curve`; any other value is a ladder level name,
    extracted from a :func:`~forensics_core.power.aggregation.aggregation_ladder` frame.

:func:`publish_atlas` writes both, and refuses a ladder frame that would put two atlases in one
file. :func:`power_lookup` refuses an atlas carrying no version, because the version is the part
of the citation that makes the number checkable.

Keeping two atlases apart
-------------------------
Two atlases that differ in library version, seed or estimator settings are different atlases,
and the loader keeps them apart: they are distinct entries in a :class:`PowerLookup`, and a
query that matches more than one raises rather than choosing. Answering from the wrong atlas is
the same failure as answering by extrapolation, one step further from view.

Refusing to extrapolate
-----------------------
For a sample size the stored atlas never measured, nothing here interpolates. The refusal is
the one WO-100 wrote, applied to the loaded frame: an atlas that does not cover ``n`` raises,
an atlas whose measured effects never reach the target power raises, and an atlas whose
false-positive rate is too far above nominal at that ``n`` raises rather than lending its power
column to a claim it cannot support.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from forensics_core import __version__
from forensics_core.power.atlas import (
    ATLAS_COLUMNS,
    AtlasError,
    PowerSpec,
    detectable,
    load_atlas,
    minimum_detectable_effect,
    save_atlas,
)

__all__ = [
    "RUNG_KEY",
    "UNIT_RUNG",
    "VERSION_KEY",
    "PowerAtlas",
    "PowerLookup",
    "power_lookup",
    "publish_atlas",
]

#: The rung name for a curve measured on units, before any aggregation.
UNIT_RUNG = "unit"

#: The settings key carrying the library release that produced a stored atlas.
VERSION_KEY = "library_version"

#: The settings key carrying the rung an atlas was measured at.
RUNG_KEY = "aggregation"


@dataclass(frozen=True, eq=False)
class PowerAtlas:
    """One stored atlas, with the record a citation needs.

    Attributes
    ----------
    frame : pandas.DataFrame
        The measured rows, with :data:`ATLAS_COLUMNS` and the spec in ``.attrs``.
    method : str
        The method the curve was measured for.
    aggregation : str
        The rung it was measured at: :data:`UNIT_RUNG`, or a ladder level name.
    library_version : str
        The ``forensics_core`` release that produced the numbers.
    seed : int or None
        The seed the measurement was reproducible from; ``None`` is recorded rather than
        omitted, so "measured once, unrepeatable" cannot be mistaken for "seed forgotten".
    settings : dict
        Every estimator setting recorded beside the numbers, including the rung and the
        version. Two atlases whose settings differ are different atlases.
    path : pathlib.Path or None
        Where it was loaded from, when it came off disk.

    ``eq`` is off because ``frame`` is a DataFrame, whose ``==`` returns a frame rather than a
    bool; identity is by :attr:`fingerprint`.
    """

    frame: pd.DataFrame
    method: str
    aggregation: str
    library_version: str
    seed: int | None
    settings: dict[str, Any]
    path: Path | None = None

    @property
    def fingerprint(self) -> str:
        """Everything that makes this atlas the atlas it is, as one stable string."""
        return json.dumps(
            {
                "method": self.method,
                "aggregation": self.aggregation,
                "library_version": self.library_version,
                "seed": self.seed,
                "settings": self.settings,
            },
            sort_keys=True,
            default=str,
        )

    @property
    def sample_sizes(self) -> tuple[int, ...]:
        """The sample sizes the atlas measured, ascending."""
        return tuple(sorted(int(n) for n in self.frame["n"].unique()))

    @property
    def effect_sizes(self) -> tuple[float, ...]:
        """The effect sizes the atlas measured, ascending. Zero is among them."""
        return tuple(sorted(float(e) for e in self.frame["effect_size"].unique()))

    def cite(self) -> str:
        """The provenance line a card quoting a number from this atlas must carry.

        Every part of it is a recorded fact rather than a convention: the method, the rung,
        the library release, the seed, and the settings that make this atlas distinguishable
        from another curve for the same method.
        """
        seed = "unseeded" if self.seed is None else f"seed={self.seed}"
        return (
            f"{self.method} at {self.aggregation}, forensics-core {self.library_version}, "
            f"{seed}, settings={json.dumps(self.settings, sort_keys=True, default=str)}"
        )


class PowerLookup:
    """A set of stored atlases, queried by method and rung.

    Built by :func:`power_lookup`. Holds every distinct atlas it was given, keyed by
    :attr:`PowerAtlas.fingerprint` rather than by path, so the same atlas loaded twice is one
    entry and two atlases that differ in any recorded setting are two.
    """

    def __init__(self, atlases: Iterable[PowerAtlas] = ()) -> None:
        self._by_fingerprint: dict[str, PowerAtlas] = {}
        for atlas in atlases:
            self._by_fingerprint.setdefault(atlas.fingerprint, atlas)

    def __len__(self) -> int:
        return len(self._by_fingerprint)

    def __iter__(self) -> Iterator[PowerAtlas]:
        return iter(self._by_fingerprint.values())

    def methods(self) -> tuple[str, ...]:
        """The methods the lookup holds an atlas for."""
        return tuple(sorted({atlas.method for atlas in self}))

    def rungs(self, method: str | None = None) -> tuple[str, ...]:
        """The rungs held, for one method or for every method."""
        return tuple(
            sorted(
                {atlas.aggregation for atlas in self if method is None or atlas.method == method}
            )
        )

    def select(self, method: str, *, aggregation: str = UNIT_RUNG) -> PowerAtlas:
        """The one stored atlas for ``(method, aggregation)``.

        Raises
        ------
        AtlasError
            If the lookup holds no atlas for that pair, or holds more than one. More than one
            means they differ in library version, seed or estimator settings: they are
            different atlases, and the answer to "which is it" is not the loader's to invent.
        """
        matches = [
            atlas for atlas in self if atlas.method == method and atlas.aggregation == aggregation
        ]
        if not matches:
            held = ", ".join(f"{a.method!r} at {a.aggregation!r}" for a in self) or "nothing"
            raise AtlasError(
                f"the lookup holds no atlas for method {method!r} at rung {aggregation!r}; it "
                f"holds {held}. It will not answer from a different method or a different rung."
            )
        if len(matches) > 1:
            raise AtlasError(
                f"{len(matches)} stored atlases match method {method!r} at rung "
                f"{aggregation!r}. They are different atlases -- library version, seed or "
                "estimator settings differ -- and the loader keeps them apart rather than "
                "choosing one. Load the one you mean:\n  "
                + "\n  ".join(atlas.cite() for atlas in matches)
            )
        return matches[0]

    def minimum_detectable_effect(
        self, method: str, n: int, *, aggregation: str = UNIT_RUNG, power: float = 0.8
    ) -> float:
        """The smallest measured effect reaching ``power`` at sample size ``n``.

        For a unit atlas ``n`` is the number of units drawn. For an atlas published from an
        aggregation ladder it is the number of *aggregate* units at that rung, and the
        recorded ``settings["mean_group_size"]`` says how many units each one covers.

        Raises
        ------
        AtlasError
            If the lookup holds no atlas for ``(method, aggregation)``, or the atlas does not
            cover ``n``, or its measured effects never reach ``power`` there, or its
            false-positive rate at ``n`` is too far above nominal for the power to be read.
        """
        atlas = self.select(method, aggregation=aggregation)
        return float(minimum_detectable_effect(atlas.frame, n, target_power=power))

    def detectable(
        self, method: str, n: int, effect: float, *, aggregation: str = UNIT_RUNG
    ) -> bool:
        """Whether an effect of that size is detectable at that sample size.

        ``False`` rather than an exception when the atlas does not cover ``n``, matching
        :func:`forensics_core.power.atlas.detectable`: an atlas that cannot show the effect is
        detectable has not shown it. A method or rung the lookup holds no atlas for at all is
        a different failure -- there is no curve to read -- and raises.
        """
        atlas = self.select(method, aggregation=aggregation)
        return bool(detectable(atlas.frame, n, effect))

    def describe(self) -> str:
        """A citable table of what the lookup holds, one line per stored atlas."""
        if not self._by_fingerprint:
            return "NO STORED ATLAS."
        header = f"{'method':<26} {'rung':<14} {'n':>24} {'forensics-core':<16} {'seed':>8}"
        lines = [header, "-" * len(header)]
        for atlas in sorted(self, key=lambda a: (a.method, a.aggregation, a.fingerprint)):
            seed = "-" if atlas.seed is None else str(atlas.seed)
            lines.append(
                f"{atlas.method:<26} {atlas.aggregation:<14} "
                f"{_summarise_sizes(atlas.sample_sizes):>24} "
                f"{atlas.library_version:<16} {seed:>8}"
            )
        return "\n".join(lines)


def power_lookup(source: str | Path | Iterable[str | Path]) -> PowerLookup:
    """Load every stored atlas at ``source`` into a queryable :class:`PowerLookup`.

    Parameters
    ----------
    source : path or iterable of paths
        A published parquet file, a directory of them (``*.parquet``, not recursive), or an
        iterable mixing the two.

    Raises
    ------
    AtlasError
        If a path does not exist, a directory holds no atlas, or a file is not a published
        atlas -- one without the ``library_version`` record has no citation and is refused
        rather than loaded with a blank where the release should be.
    """
    return PowerLookup(_read_one(path) for path in _resolve_paths(source))


def publish_atlas(
    frame: pd.DataFrame,
    path: str | Path,
    *,
    method: str | None = None,
    aggregation: str = UNIT_RUNG,
    semantics: str | None = None,
    seed: int | None = None,
    settings: Mapping[str, Any] | None = None,
) -> PowerAtlas:
    """Write ``frame`` as a published atlas, stamping the record a citation needs.

    Parameters
    ----------
    frame : pandas.DataFrame
        A :func:`~forensics_core.power.atlas.power_curve` frame, or an
        :func:`~forensics_core.power.aggregation.aggregation_ladder` frame. A ladder frame is
        reduced to one rung here, because one stored file is one atlas: ``n`` becomes the
        number of aggregate units at that rung and ``mean_group_size`` moves into the settings.
    method : str, optional
        Required for a ladder frame, which carries no method column. When the frame already
        names a method this must agree with it; relabelling a measurement is refused.
    aggregation : str
        The rung to publish. :data:`UNIT_RUNG` (the default) is the unaggregated curve, either
        a plain power curve or the identity rung of a ladder, which
        :func:`aggregation_ladder` requires to come first.
    semantics : str, optional
        Which aggregation semantics to publish when a ladder rung carries both and they
        disagree. Required in that case, because the two are two different atlases.
    seed : int, optional
        Overrides the seed recorded in the frame's spec; a ladder frame has no spec and must
        be told, or published as ``None`` ("measured once, unrepeatable").
    settings : mapping, optional
        Further estimator settings to record. They are part of the atlas: two atlases that
        differ here are different atlases.

    Returns
    -------
    PowerAtlas
        The published atlas, also written to ``path``. Every validation runs before anything
        is written, so a refused publication leaves no partial file.
    """
    spec = frame.attrs.get("spec")
    merged: dict[str, Any] = dict(getattr(spec, "settings", None) or {})
    merged.update(dict(settings or {}))

    column_method = _column_method(frame)
    if method is not None and column_method and method != column_method:
        raise AtlasError(
            f"the frame was measured for method {column_method!r} but method={method!r} was "
            "given; publishing it under another name would misattribute the measurement"
        )
    resolved = method or column_method or getattr(spec, "method", "")
    if not resolved:
        raise AtlasError(
            "no method name is available: a ladder frame has no method column, so pass "
            "method=... when publishing one"
        )

    if "level" in frame.columns and "n_units" in frame.columns:
        stored, rung, rung_settings = _from_ladder(frame, aggregation, semantics, resolved)
        merged.update(rung_settings)
    else:
        if aggregation != UNIT_RUNG:
            raise AtlasError(
                f"aggregation={aggregation!r} was asked of a frame with no 'level' column. A "
                "frame with no ladder is a unit-level curve and can only be published at "
                f"{UNIT_RUNG!r}."
            )
        _require_columns(frame, ATLAS_COLUMNS, "a unit-level atlas")
        stored = frame[ATLAS_COLUMNS].copy()
        stored["method"] = resolved
        rung = UNIT_RUNG

    merged[RUNG_KEY] = rung
    merged[VERSION_KEY] = __version__
    published_spec = PowerSpec(
        method=resolved,
        alpha=float(getattr(spec, "alpha", None) or _single_number(stored, "alpha", 0.05)),
        n_replicates=int(
            getattr(spec, "n_replicates", None) or _single_number(stored, "n_replicates", 0)
        ),
        seed=seed if seed is not None else getattr(spec, "seed", None),
        settings=merged,
    )
    stored.attrs["spec"] = published_spec
    save_atlas(stored, path)
    return PowerAtlas(
        frame=stored,
        method=resolved,
        aggregation=rung,
        library_version=__version__,
        seed=published_spec.seed,
        settings=merged,
        path=Path(path),
    )


def _from_ladder(
    frame: pd.DataFrame, aggregation: str, semantics: str | None, method: str
) -> tuple[pd.DataFrame, str, dict[str, Any]]:
    """Reduce a ladder frame to the one rung being published.

    Returns ``(frame_with_n, rung, settings)`` where ``frame_with_n`` already carries
    :data:`ATLAS_COLUMNS`.
    """
    levels = list(dict.fromkeys(str(level) for level in frame["level"]))
    if not levels:
        raise AtlasError("the ladder frame has no levels")
    # A ladder's first level is its identity rung, and at that rung the two semantics coincide
    # exactly -- aggregate() returns before semantics matters -- so UNIT_RUNG needs no
    # disambiguation there.
    level = levels[0] if aggregation == UNIT_RUNG else aggregation
    subset = frame[frame["level"] == level]
    if subset.empty:
        raise AtlasError(
            f"the ladder has no rung {aggregation!r}; it measured {levels}. It will not publish "
            "a rung it never measured."
        )

    available = sorted({str(s) for s in subset["semantics"]})
    if not available:
        raise AtlasError(f"rung {level!r} carries no aggregation semantics to publish")
    if semantics is not None and semantics not in available:
        raise AtlasError(f"rung {level!r} has no semantics {semantics!r}; it measured {available}")
    if semantics is None:
        if len(available) > 1:
            by_semantics = {
                s: subset[subset["semantics"] == s].sort_values("effect_size") for s in available
            }
            first, second = (by_semantics[s] for s in available[:2])
            if not np.allclose(first["power"].to_numpy(), second["power"].to_numpy()):
                raise AtlasError(
                    f"rung {level!r} carries both semantics {available} and they disagree: they "
                    "are two different atlases and one stored file cannot hold both. Pass "
                    "semantics= to say which is being published."
                )
        semantics = available[0]

    subset = subset[subset["semantics"] == semantics]
    group_sizes = subset["mean_group_size"].dropna().unique()
    rung_settings: dict[str, Any] = {
        "semantics": semantics,
        "mean_group_size": float(group_sizes[0]) if group_sizes.size == 1 else None,
    }
    stored = subset.rename(columns={"n_units": "n"}).copy()
    stored["method"] = method
    # the rung is recorded under its canonical name, so a ladder published at its identity
    # rung is queryable as "unit" whatever the ladder happened to call that level
    return stored[ATLAS_COLUMNS].copy(), aggregation, rung_settings


def _read_one(path: Path) -> PowerAtlas:
    """Load one published atlas, refusing anything that is not one."""
    frame = load_atlas(path)
    _require_columns(frame, ATLAS_COLUMNS, f"the atlas at {path}")
    spec = frame.attrs.get("spec")
    if spec is None:
        raise AtlasError(
            f"{path} carries no measurement record. A published atlas is written by "
            "publish_atlas, which stamps the library version, the estimator settings and the "
            "seed beside the numbers."
        )
    settings = dict(spec.settings)
    if VERSION_KEY not in settings:
        raise AtlasError(
            f"{path} records no library version, so a reader cannot tell which release produced "
            "it. A number whose source release cannot be named is not citable; publish the "
            "atlas with publish_atlas rather than save_atlas."
        )
    method = spec.method or _column_method(frame)
    if not method:
        raise AtlasError(f"{path} records no method, so no query can be aimed at it")
    return PowerAtlas(
        frame=frame,
        method=method,
        aggregation=str(settings.get(RUNG_KEY, UNIT_RUNG)),
        library_version=str(settings[VERSION_KEY]),
        seed=spec.seed,
        settings=settings,
        path=path,
    )


def _resolve_paths(source: str | Path | Iterable[str | Path]) -> list[Path]:
    """Expand a file, a directory of files, or an iterable of either into atlas paths."""
    raw = [source] if isinstance(source, (str, Path)) else list(source)
    if not raw:
        raise AtlasError("no atlas path given")
    paths: list[Path] = []
    for item in raw:
        path = Path(item)
        if path.is_dir():
            found = sorted(path.glob("*.parquet"))
            if not found:
                raise AtlasError(
                    f"{path} holds no *.parquet atlas. A published atlas is a parquet file "
                    "written by publish_atlas; see data/atlas/README.md for the format."
                )
            paths.extend(found)
        elif path.exists():
            paths.append(path)
        else:
            raise AtlasError(f"{path} does not exist")
    return paths


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], what: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise AtlasError(
            f"{what} is missing the column(s) {missing}; a published atlas carries {ATLAS_COLUMNS}"
        )


def _column_method(frame: pd.DataFrame) -> str:
    if "method" not in frame.columns:
        return ""
    values = sorted({str(v) for v in frame["method"].dropna().unique()})
    if len(values) > 1:
        raise AtlasError(
            f"the frame carries more than one method {values}; one stored atlas records one "
            "measurement, so split the frame before publishing it"
        )
    return values[0] if values else ""


def _single_number(frame: pd.DataFrame, column: str, default: Any) -> Any:
    if column not in frame.columns:
        return default
    values = frame[column].dropna().unique()
    if values.size == 0:
        return default
    if values.size > 1:
        raise AtlasError(
            f"the frame carries more than one {column} ({sorted(values)}); one stored atlas "
            "records one measurement, so split the frame before publishing it"
        )
    return values[0]


def _summarise_sizes(sizes: Sequence[int]) -> str:
    if not sizes:
        return "-"
    if len(sizes) <= 3:
        return ", ".join(str(size) for size in sizes)
    return f"{sizes[0]}..{sizes[-1]} ({len(sizes)} points)"
