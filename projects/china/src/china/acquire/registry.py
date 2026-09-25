"""Maps a ``SOURCES.yaml`` id to the callable that acquires it.

A source with no registered acquirer is not a bug: many entries in the registry are blocked
(the legacy National Bureau of Statistics portal, the China Electricity Council), gated
behind registration (the Earth Observation Group nightlight products), paywalled (CEIC,
Wind, Caixin) or are reference material a human must read. Those are reported as skipped
with the reason from the registry, which is the honest outcome.

This module is a copy of the ``elections`` project's registry, deliberately: all four
projects in the programme expose the same shape so that an acquirer written for one reads
the same as an acquirer written for another.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: source_id -> acquirer callable. Populated by the @register decorator at import time.
ACQUIRERS: dict[str, Callable[..., Any]] = {}


@dataclass(frozen=True)
class AcquireResult:
    """Outcome of one acquirer. ``ok`` False is a normal, reported outcome, not an exception."""

    source_id: str
    ok: bool
    detail: str
    paths: tuple[Path, ...] = ()
    skipped_cached: bool = False

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        mark = "ok " if self.ok else "FAIL"
        cached = " (cached)" if self.skipped_cached else ""
        return f"[{mark}] {self.source_id}{cached}: {self.detail}"


def register(source_id: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register an acquirer for a ``SOURCES.yaml`` id.

    The decorated function is called as ``fn(source, data_dir)`` where ``source`` is the
    :class:`forensics_core.provenance.manifest.Source` entry and ``data_dir`` is the
    project's ``data/`` directory, and must return an :class:`AcquireResult`. An acquirer
    that also accepts ``force`` is passed the ``--force`` flag by the shared runner.

    Parameters
    ----------
    source_id : str
        The id as written in ``data/SOURCES.yaml``.

    Returns
    -------
    Callable
        The decorator, which returns the function unchanged.

    Raises
    ------
    ValueError
        If an acquirer is already registered for ``source_id``. Two acquirers for one id
        would make the run order decide which provenance the registry records.
    """

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        if source_id in ACQUIRERS:
            raise ValueError(f"duplicate acquirer registered for {source_id!r}")
        ACQUIRERS[source_id] = fn
        return fn

    return deco
