"""``python -m gosplan.transcribe`` -- generate forms, validate them, compare two of them.

Four subcommands, each doing one thing:

``targets``   list the transcription queue with its priorities and its honesty flags
``template``  write blank forms for one target or all of them
``validate``  check a filled form and print every problem with its code
``compare``   report the disagreement rate between two independent transcriptions

Exit codes: ``0`` when everything checked passed, ``1`` when any file had errors. ``compare``
returns ``0`` whatever the disagreement rate is: measuring a rate is not the same as judging
it, and the judgement needs a threshold that a person has to choose (see
:func:`gosplan.transcribe.compare.digit_tests_permitted`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from gosplan.transcribe.compare import compare_files
from gosplan.transcribe.targets import TARGETS, target_by_id
from gosplan.transcribe.templates import DEFAULT_BLANK_ROWS, write_all_templates, write_template
from gosplan.transcribe.validate import validate_file


def _cmd_targets(_: argparse.Namespace) -> int:
    print(f"{len(TARGETS)} transcription targets, in priority order:\n")
    for t in sorted(TARGETS, key=lambda x: (x.priority, x.target_id)):
        seen = "table seen" if t.confirmed_present else "NOT YET LOCATED"
        cross = f"; cross-check: {t.cross_check_source_id}" if t.cross_check_source_id else ""
        print(f"  {t.priority}. {t.target_id}  [{seen}]")
        print(f"     source: {t.source_id}{cross}")
        print(f"     {t.title_translit}")
        print(f"     {t.locator}\n")
    return 0


def _cmd_template(args: argparse.Namespace) -> int:
    out = Path(args.out)
    if args.target:
        paths = list(
            write_template(
                target_by_id(args.target),
                out,
                blank_rows=args.rows,
                transcriber=args.transcriber,
            )
        )
    else:
        paths = write_all_templates(out, blank_rows=args.rows, transcriber=args.transcriber)
    for p in paths:
        print(f"wrote {p}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    failed = 0
    for name in args.paths:
        path = Path(name)
        if not path.is_file():
            print(f"ERROR: no such file: {path}")
            failed += 1
            continue
        report = validate_file(path)
        print(report.summary())
        for issue in report.issues:
            print(f"  {issue}")
        if args.json:
            print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        failed += 0 if report.ok else 1
    return 1 if failed else 0


def _cmd_compare(args: argparse.Namespace) -> int:
    missing = [p for p in (Path(args.a), Path(args.b)) if not p.is_file()]
    if missing:
        for path in missing:
            print(f"ERROR: no such file: {path}")
        return 1
    report = compare_files(Path(args.a), Path(args.b), align=args.align)
    print(report.summary())
    if report.identity_differences:
        print("  the two files describe different tables:")
        for name, va, vb in report.identity_differences:
            print(f"    {name}: {va!r} vs {vb!r}")
    for stats in report.by_position:
        print(
            f"  digit position {stats.position}: "
            f"{stats.n_disagreements}/{stats.n_compared} ({stats.rate:.3%})"
        )
    for d in report.disagreements:
        print(f"  {d}")
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m gosplan.transcribe",
        description="Generate, validate and cross-check transcriptions of printed Soviet tables.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_targets = sub.add_parser("targets", help="list the transcription queue")
    p_targets.set_defaults(func=_cmd_targets)

    p_template = sub.add_parser("template", help="write blank transcription forms")
    p_template.add_argument("--out", required=True, help="directory to write into")
    p_template.add_argument("--target", help="one target id; omit for all targets")
    p_template.add_argument(
        "--rows", type=int, default=DEFAULT_BLANK_ROWS, help="blank rows to leave"
    )
    p_template.add_argument("--transcriber", default="", help="pre-fill the transcriber column")
    p_template.set_defaults(func=_cmd_template)

    p_validate = sub.add_parser("validate", help="check filled forms")
    p_validate.add_argument("paths", nargs="+")
    p_validate.add_argument("--json", action="store_true", help="also print the report as JSON")
    p_validate.set_defaults(func=_cmd_validate)

    p_compare = sub.add_parser("compare", help="compare two independent transcriptions")
    p_compare.add_argument("a")
    p_compare.add_argument("b")
    p_compare.add_argument("--align", choices=("leading", "trailing"), default="leading")
    p_compare.add_argument("--json", action="store_true", help="also print the report as JSON")
    p_compare.set_defaults(func=_cmd_compare)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
