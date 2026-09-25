"""Maps a ``SOURCES.yaml`` id to the callable that acquires it.

A source with no registered acquirer is not a bug: many entries in the registry are blocked,
paywalled, or reference material that a human must obtain. Those are reported as skipped with
the reason from the registry, which is the honest outcome.
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
    :class:`forensics_core.provenance.manifest.Source` entry and ``data_dir`` is the project's
    ``data/`` directory, and must return an :class:`AcquireResult`.
    """

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        if source_id in ACQUIRERS:
            raise ValueError(f"duplicate acquirer registered for {source_id!r}")
        ACQUIRERS[source_id] = fn
        return fn

    return deco
