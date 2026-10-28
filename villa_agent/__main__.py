"""Command line. Run `python -m villa_agent --help`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from villa_agent import config, pipeline, places
from villa_agent.db import STATUSES, LeadDB


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m villa_agent",
                                description="Find properties, make previews, email the owners.")
    p.add_argument("--config", type=Path, default=Path("config.yaml"))
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="discover, qualify, make videos and send, for one region")
    run.add_argument("region")
    run.add_argument("--limit", type=int, help="most videos to make this run")
    d = sub.add_parser("discover", help="search Google Maps for properties in a region")
    d.add_argument("region")
    q = sub.add_parser("qualify", help="find owner emails on their websites and score leads")
    q.add_argument("region", nargs="?")
    v = sub.add_parser("videos", help="make preview videos for qualified leads")
    v.add_argument("region", nargs="?")
    v.add_argument("--limit", type=int)
    a = sub.add_parser("approve", help="review finished videos before they can be sent")
    a.add_argument("region", nargs="?")
    s = sub.add_parser("send", help="send first emails and due follow-ups")
    s.add_argument("region", nargs="?")
    sub.add_parser("replies", help="check the inbox and stop sequences that got a reply")
    st = sub.add_parser("status", help="count leads at each step")
    st.add_argument("region", nargs="?")

    args = p.parse_args(argv)
    try:
        cfg = config.load(args.config)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    db = LeadDB(cfg.data_dir / "leads.db")
    region = getattr(args, "region", None)
    try:
        api = lambda: places.Places(cfg.secret("GOOGLE_MAPS_API_KEY"))  # noqa: E731
        if args.command in ("discover", "run"):
            pipeline.discover(cfg, db, region, api())
        if args.command in ("qualify", "run"):
            pipeline.qualify(cfg, db, region)
        if args.command in ("videos", "run"):
            pipeline.videos(cfg, db, region, api(), limit=args.limit)
        if args.command == "approve" or (args.command == "run" and not
                                         cfg.section("outreach").get("require_approval", True)):
            pipeline.approve(cfg, db, region)
        if args.command in ("send", "run"):
            sent = pipeline.send(cfg, db, region)
            if args.command == "run" and cfg.section("outreach").get("require_approval", True):
                print(f"{sent} sent. New videos wait for `python -m villa_agent approve`, "
                      "then go out on the next `send` or `run`.")
        if args.command == "replies":
            pipeline.replies(cfg, db)
        if args.command in ("status", "run"):
            counts = db.counts(region)
            print("  ".join(f"{s}: {counts[s]}" for s in STATUSES if counts.get(s)) or "no leads yet")
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
