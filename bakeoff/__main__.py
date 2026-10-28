"""Command line for the bake-off pack. Run `python -m bakeoff --help`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bakeoff import core

HERE = Path(__file__).parent


def cmd_prep(args: argparse.Namespace) -> int:
    shots = core.load_shots(args.properties)
    models, _ = core.load_models(args.models)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    missing = [s.photo for s in shots if not s.photo.exists()]
    missing += [s.end_photo for s in shots if s.end_photo and not s.end_photo.exists()]
    if missing:
        for p in missing:
            print(f"missing photo: {p}", file=sys.stderr)
        return 1
    warnings = []
    for s in shots:
        warnings += core.prepare_photo(s.photo, core.prepared_path(out, s))
        if s.end_photo:
            warnings += core.prepare_photo(s.end_photo, core.prepared_path(out, s, end=True))
    prompts = core.write_prompts(shots, models, out)
    sheet = core.write_sheet(shots, models, out)
    for w in warnings:
        print(f"warning: {w}")
    print(f"{len(shots)} shots x {len(models)} models x {core.ATTEMPTS} attempts")
    print(f"photos:  {out / 'photos'}")
    print(f"prompts: {prompts}")
    print(f"scores:  {sheet}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    models, rate = core.load_models(args.models)
    results = core.summarise(args.out / "scores.csv", models, rate)
    if not results:
        print("no scored clips yet: fill in the building column of scores.csv")
        return 1
    table = core.report_markdown(results)
    (args.out / "report.md").write_text("# Bake-off results\n\n" + table + "\n", encoding="utf-8")
    print(table)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m bakeoff")
    p.add_argument("--models", type=Path, default=HERE / "models.yaml")
    p.add_argument("--out", type=Path, default=Path("bakeoff-run"),
                   help="folder for prepared photos, prompts, scores and report")
    sub = p.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prep", help="crop photos, write prompts.md and scores.csv")
    prep.add_argument("properties", type=Path)
    prep.set_defaults(func=cmd_prep)
    report = sub.add_parser("report", help="rank models from the filled-in scores.csv")
    report.set_defaults(func=cmd_report)
    args = p.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, KeyError, FileExistsError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
