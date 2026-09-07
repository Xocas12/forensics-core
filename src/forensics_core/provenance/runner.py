"""The registry-driven acquisition runner shared by every project in the programme.

Each project exposes ``python -m <project>.acquire``; that entry point is a thin shim around
:func:`main` here, so all four projects behave identically: same flags, same output, same
exit codes, same refusal to invent anything.

Behaviour, which is the whole point of this module:

* **Nothing is fetched that is not in the registry.** The work list comes from
  ``data/SOURCES.yaml``, never from the code.
* **Fail loudly and continue.** A source that cannot be acquired prints a reason and the run
  moves to the next one. One unreachable host does not abort the other twenty.
* **Blocked, paywalled, registration-gated and archive-only sources are skipped by design**,
  with the registry's own reason echoed, because a machine cannot resolve them. They are
  reported as `needs a human`, not as failures.
* **Missing acquirers are reported, not silently ignored.** A registry entry that is
  reachable but has no code to fetch it is a gap in the pipeline and says so.
* **The contact string is checked once, up front**, so the run fails immediately with an
  actionable message rather than after twenty rate-limited requests.

Exit codes: ``0`` when every attempted source succeeded, ``1`` when any attempt failed. A
run consisting only of gated sources exits ``0``: nothing failed, there was simply nothing a
machine could do.
"""

from __future__ import annotations

import argparse
import inspect
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from forensics_core.config import ContactNotConfigured, require_contact
from forensics_core.provenance.manifest import Source, load_sources

#: Access tiers a machine cannot resolve on its own. Each needs a person.
NEEDS_HUMAN = {"registration", "paywalled", "archive_visit", "manual_transcription"}

#: Reachability states worth attempting. "blocked" and "unverified" are not.
ATTEMPTABLE_STATUS = {"verified", "partial"}


def _fmt(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _accepts_force(fn: Callable[..., Any]) -> bool:
    """True if ``fn`` takes a ``force`` keyword (directly or via ``**kwargs``)."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):  # builtins and C callables have no signature
        return False
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return True
    return "force" in params


def plan(
    sources: Sequence[Source],
    acquirers: Mapping[str, Callable[..., Any]],
    only: Sequence[str] | None = None,
) -> tuple[list[Source], list[tuple[Source, str]]]:
    """Split the registry into what will be attempted and what will be skipped.

    Returns ``(attempt, skipped)`` where each skipped entry carries the reason. Selection by
    ``only`` overrides the status filter but not the missing-acquirer check: if a user asks
    for a specific id explicitly, they get a real attempt or a clear explanation.
    """
    attempt: list[Source] = []
    skipped: list[tuple[Source, str]] = []
    wanted = set(only) if only else None

    for s in sources:
        if wanted is not None and s.id not in wanted:
            continue
        if s.id not in acquirers:
            if s.access in NEEDS_HUMAN:
                reason = f"access={s.access}: needs a human, see data/ACCESS_NOTES.md"
            elif s.status == "blocked":
                reason = f"blocked: {s.blocked_reason or 'no reason recorded'}"
            elif s.status == "unverified":
                reason = "unverified: existence was never confirmed; nothing to fetch"
            else:
                reason = "no acquirer implemented for this id"
            skipped.append((s, reason))
            continue
        if wanted is None:
            if s.status == "blocked":
                skipped.append((s, f"blocked: {s.blocked_reason or 'no reason recorded'}"))
                continue
            if s.status not in ATTEMPTABLE_STATUS:
                skipped.append((s, f"status={s.status}: not attemptable"))
                continue
            if s.access in NEEDS_HUMAN:
                skipped.append((s, f"access={s.access}: needs a human"))
                continue
        attempt.append(s)

    return attempt, skipped


def main(
    *,
    project: str,
    data_dir: Path,
    acquirers: Mapping[str, Callable[..., Any]],
    argv: Sequence[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog=f"python -m {project}.acquire",
        description=f"Acquire the sources registered in projects/{project}/data/SOURCES.yaml.",
    )
    parser.add_argument("ids", nargs="*", help="source ids to acquire; omit with --all")
    parser.add_argument("--all", action="store_true", help="acquire every attemptable source")
    parser.add_argument("--list", action="store_true", help="print the registry and exit")
    parser.add_argument(
        "--force", action="store_true", help="re-download even if the file is already held"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="show what would be attempted, fetch nothing"
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    registry = data_dir / "SOURCES.yaml"
    if not registry.exists():
        print(f"ERROR: no registry at {registry}")
        return 1
    sources = load_sources(registry)

    if args.list:
        width = max((len(s.id) for s in sources), default=4)
        print(f"{project}: {_fmt(len(sources), 'source')} in {registry}")
        for s in sorted(sources, key=lambda x: (x.status, x.id)):
            mark = "*" if s.id in acquirers else " "
            print(f"  {mark} {s.id:<{width}}  {s.status:<10} {s.access:<22} {s.name[:60]}")
        print("\n  * = an acquirer is implemented for this source")
        return 0

    if not args.all and not args.ids:
        parser.error("give one or more source ids, or --all")

    attempt, skipped = plan(sources, acquirers, None if args.all else args.ids)

    if args.ids:
        known = {s.id for s in sources}
        for missing in [i for i in args.ids if i not in known]:
            print(f"ERROR: {missing!r} is not in {registry}")
            return 1

    print(f"=== {project}: {_fmt(len(attempt), 'source')} to attempt, {len(skipped)} skipped ===")

    if attempt and not args.dry_run:
        try:
            cfg = require_contact()
        except ContactNotConfigured as exc:
            print(f"\nREFUSING TO FETCH.\n{exc}")
            return 1
        print(f"    contact: {cfg.contact}")

    failures: list[str] = []
    for s in attempt:
        if args.dry_run:
            print(f"[dry] {s.id}: would fetch {s.url}")
            continue
        fn = acquirers[s.id]
        # Decide from the signature whether the acquirer accepts `force`, rather than calling
        # and catching TypeError: that would swallow a genuine TypeError raised *inside* the
        # acquirer and silently re-run it.
        kwargs = {"force": args.force} if _accepts_force(fn) else {}
        try:
            result = fn(s, data_dir, **kwargs)
        except Exception as exc:  # a bad source must not kill the run
            print(f"[FAIL] {s.id}: {type(exc).__name__}: {exc}")
            failures.append(s.id)
            continue
        print(f"  {result}")
        if not getattr(result, "ok", False):
            failures.append(s.id)

    if skipped:
        print(f"\n--- skipped ({len(skipped)}) ---")
        for s, reason in skipped:
            print(f"  [skip] {s.id}: {reason}")

    needs_human = [s.id for s, _ in skipped if s.access in NEEDS_HUMAN]
    if needs_human:
        print(
            f"\n{_fmt(len(needs_human), 'source')} need a human "
            f"(registration, purchase or an archive visit): {', '.join(sorted(needs_human))}"
            f"\nSee projects/{project}/data/ACCESS_NOTES.md for what to do."
        )

    if failures:
        print(f"\nFAILED: {_fmt(len(failures), 'source')}: {', '.join(failures)}")
        print("Every attempt above is recorded in data/fetch_log.jsonl.")
        return 1

    print("\nAll attempted sources acquired." if attempt else "\nNothing to attempt.")
    return 0
