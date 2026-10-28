"""The steps, in order. Each picks leads at one status, does its work and moves them on."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from villa_agent import contacts, places, video
from villa_agent.config import Config
from villa_agent.db import LeadDB
from villa_agent.outreach import Mailer, build_message, fetch_replies, is_stop

Say = Callable[[str], None]


def _check_pause(cfg: Config) -> None:
    if cfg.paused:
        raise RuntimeError("pause is on in config.yaml; nothing that spends or sends will run")


def discover(cfg: Config, db: LeadDB, region: str, api: places.Places, say: Say = print) -> int:
    rules = cfg.section("discover")
    new = 0
    for q in rules.get("queries") or ["farm stay near {region}"]:
        query = q.format(region=region)
        results = api.search(query, int(rules.get("max_results_per_query", 60)))
        added = sum(db.add(places.to_lead(p, region)) for p in results if places.is_open(p))
        say(f"{query!r}: {len(results)} found, {added} new")
        new += added
    return new


def qualify(cfg: Config, db: LeadDB, region: str | None, scrape=contacts.scrape_contacts,
            say: Say = print) -> int:
    rules = cfg.section("qualify")
    passed = 0
    for row in db.by_status("discovered", region):
        lead = dict(row)
        if not lead.get("website"):
            db.update(lead["place_id"], status="rejected", reason="no website on the listing")
            continue
        lead.update(scrape(lead["website"]))
        if lead.get("email") and db.is_opted_out(lead["email"]):
            db.update(lead["place_id"], status="rejected", reason="opted out earlier")
            continue
        points, reason = contacts.score(lead, rules)
        db.update(
            lead["place_id"], email=lead.get("email"), email_source=lead.get("email_source"),
            instagram=lead.get("instagram"), score=points,
            status="rejected" if reason else "qualified", reason=reason,
        )
        if not reason:
            passed += 1
            say(f"qualified: {lead['name']} <{lead['email']}> score {points}")
    return passed


def make_generator(cfg: Config):
    v = cfg.section("video")
    seconds = float(v.get("clip_seconds", 5))
    if v.get("provider", "kenburns") == "fal":
        return video.Fal(cfg.secret("FAL_KEY"), v["fal_endpoint"], float(v.get("usd_per_second", 0.224)),
                         seconds, v.get("fal_extra_args"))
    return video.KenBurns(seconds)


def videos(cfg: Config, db: LeadDB, region: str | None, api: places.Places, generator=None,
           limit: int | None = None, say: Say = print) -> int:
    """Make a preview for each qualified lead. Photos are deleted after each job."""
    _check_pause(cfg)
    v = cfg.section("video")
    generator = generator or make_generator(cfg)
    budget = float(v.get("max_spend_usd", 25))
    shots = int(v.get("shots", 3))
    music = Path(v["music"]) if v.get("music") else None
    spent, made = 0.0, 0
    for row in db.by_status("qualified", region, limit):
        per_video = shots * float(v.get("clip_seconds", 5)) * generator.usd_per_second
        if spent + per_video > budget:
            say(f"stopping: the next video would take spend past max_spend_usd ${budget:.2f}")
            break
        try:
            photos = places.rank_photos(api.photos(row["place_id"]), row["name"])[:shots]
            if len(photos) < shots:
                raise ValueError(f"only {len(photos)} photos available")
            with tempfile.TemporaryDirectory() as tmp:
                files = [api.download_photo(p["name"], Path(tmp) / f"{i}.jpg") for i, p in enumerate(photos)]
                dest = cfg.data_dir / "videos" / f"{row['place_id']}.mp4"
                _, cost = video.make_preview(row["name"], files, generator, dest, music)
            spent += cost
            db.update(row["place_id"], status="video_ready", video_path=str(dest),
                      photo_authors=places.authors(photos), reason=None)
            made += 1
            say(f"video ready: {row['name']} -> {dest} (${cost:.2f})")
        except Exception as e:  # one bad lead never stops the rest
            db.update(row["place_id"], status="failed", reason=f"video: {e}")
            say(f"failed: {row['name']}: {e}")
    say(f"{made} videos made, about ${spent:.2f} spent")
    return made


def approve(cfg: Config, db: LeadDB, region: str | None, ask: Callable[[str], str] = input,
            say: Say = print) -> int:
    """Show each finished video and its email, and let you approve or reject it."""
    rows = db.by_status("video_ready", region)
    if not cfg.section("outreach").get("require_approval", True):
        for r in rows:
            db.update(r["place_id"], status="approved", reason="auto-approved")
        return len(rows)
    approved = 0
    for r in rows:
        say(f"\n{r['name']} ({r['region']}), rating {r['rating']} from {r['review_count']} reviews")
        say(f"  email: {r['email']} (found on {r['email_source']})")
        say(f"  video: {r['video_path']}")
        say(f"  photo credits: {r['photo_authors'] or 'none listed'}")
        answer = ask("  approve? [y]es / [n]o / [s]kip / [q]uit: ").strip().lower()
        if answer == "q":
            break
        if answer == "y":
            db.update(r["place_id"], status="approved")
            approved += 1
        elif answer == "n":
            db.update(r["place_id"], status="failed", reason="rejected in review")
    return approved


def _days_since(ts: str | None) -> float:
    if not ts:
        return 0.0
    return (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds() / 86400


def send(cfg: Config, db: LeadDB, region: str | None, mailer: Mailer | None = None,
         say: Say = print) -> int:
    """First emails to approved leads, then follow-ups that are due, within the daily limit."""
    _check_pause(cfg)
    o = cfg.section("outreach")
    if mailer is None:
        password = None if cfg.dry_run else cfg.secret("MAIL_PASSWORD")
        mailer = Mailer(cfg.section("smtp"), password, cfg.data_dir / "outbox", cfg.dry_run)
    room = int(o.get("daily_send_limit", 20)) - db.sent_today()
    days = [int(d) for d in o.get("followup_days", [4, 9])]
    gaps = [b - a for a, b in zip([0, *days], days)]

    due = []
    for r in db.by_status("emailed", region):
        touch = r["touches"]
        if touch <= len(gaps) and _days_since(r["last_sent_at"]) >= gaps[touch - 1]:
            due.append((r, touch))
        elif touch > len(gaps) and _days_since(r["last_sent_at"]) >= 5:
            db.update(r["place_id"], status="no_reply", reason="no reply after the last follow-up")
    due += [(r, 0) for r in db.by_status("approved", region)]

    sent = 0
    for r, touch in due:
        if sent >= room:
            say(f"daily send limit reached; {len(due) - sent} left for tomorrow")
            break
        if db.is_opted_out(r["email"]):
            db.update(r["place_id"], status="opted_out", reason="on the opt-out list")
            continue
        msg = build_message(dict(r), touch, o, Path(r["video_path"]) if r["video_path"] else None)
        result = mailer.send(msg, r["name"])
        db.update(r["place_id"], status="emailed", touches=touch + 1,
                  last_sent_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        db.log(r["place_id"], "sent", f"touch {touch}: {result}")
        sent += 1
        say(f"{r['name']}: {result}")
    return sent


def replies(cfg: Config, db: LeadDB, fetch=None, say: Say = print) -> int:
    """Mark leads that replied, so their sequence stops; opt-outs are remembered for good."""
    emailed = {r["email"].lower(): r for r in db.by_status("emailed")}
    if not emailed:
        return 0
    if fetch is None:
        imap = cfg.section("imap")
        since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%d-%b-%Y")
        fetch = lambda: fetch_replies(imap, cfg.secret("MAIL_PASSWORD"), since)  # noqa: E731
    found = 0
    for sender, subject, body in fetch():
        lead = emailed.get(sender)
        if not lead:
            continue
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if is_stop(subject + " " + body):
            db.opt_out(sender)
            db.update(lead["place_id"], status="opted_out", replied_at=ts, reason="asked to stop")
            say(f"opted out: {lead['name']}")
        else:
            db.update(lead["place_id"], status="replied", replied_at=ts, reason=body.strip()[:500])
            say(f"REPLY from {lead['name']} <{sender}>: {body.strip()[:200]}")
        found += 1
    return found
