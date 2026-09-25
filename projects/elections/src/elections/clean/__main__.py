"""``python -m elections.clean`` - build the tidy Parquet from the acquired raw files.

Reads only ``data/raw``; writes only the one Parquet file. It refuses nothing and invents
nothing: if a raw file is missing it says which one and how to get it, and if the loaded data
disagrees with a published total it stops rather than writing a file that would be analysed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from elections.clean.checks import IntegrityError
from elections.clean.loader import DATA_DIR, RawFileMissing, write_tidy_parquet
from elections.clean.schema import ELECTIONS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m elections.clean",
        description="Build projects/elections/data/processed/precincts.parquet.",
    )
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR, help="project data directory")
    parser.add_argument("--out", type=Path, default=None, help="output Parquet path")
    parser.add_argument(
        "--election",
        action="append",
        choices=list(ELECTIONS),
        help="build only this election; repeatable",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="skip the acceptance checks (for inspecting a file that already failed them)",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    try:
        path = write_tidy_parquet(
            args.data_dir,
            out_path=args.out,
            elections=args.election,
            validate=not args.no_validate,
        )
    except RawFileMissing as exc:
        print(f"MISSING RAW DATA\n{exc}")
        return 1
    except IntegrityError as exc:
        print(f"INTEGRITY CHECK FAILED, nothing written\n{exc}")
        return 1

    print(f"wrote {path} ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
