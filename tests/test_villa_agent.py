import email
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image

from villa_agent import contacts, pipeline, places, video
from villa_agent.config import Config
from villa_agent.db import LeadDB
from villa_agent.outreach import Mailer, build_message, is_stop

OUTREACH = {
    "require_approval": True,
    "daily_send_limit": 20,
    "followup_days": [4, 9],
    "price_from": "10,000",
    "whatsapp_number": "919800000000",
    "sender": {"name": "Asha", "business": "Studio", "city": "Hyderabad",
               "phone": "+91 1", "email": "hi@studio.in"},
}


def make_cfg(tmp_path, **over) -> Config:
    data = {
        "pause": False, "dry_run": True,
        "discover": {"queries": ["farm stay near {region}"], "max_results_per_query": 20},
        "qualify": {"min_rating": 4.0, "min_reviews": 20, "min_photos": 3},
        "video": {"provider": "kenburns", "shots": 3, "clip_seconds": 1, "max_spend_usd": 5},
        "outreach": OUTREACH,
    }
    data.update(over)
    return Config(data, tmp_path / "data")


def place(pid, name, rating=4.6, reviews=120, website="https://greenacres.in", photos=4, **kw):
    return {
        "id": pid, "displayName": {"text": name}, "formattedAddress": "Hyderabad",
        "rating": rating, "userRatingCount": reviews, "websiteUri": website,
        "googleMapsUri": f"https://maps.google.com/?cid={pid}",
        "photos": [{"name": f"places/{pid}/photos/{i}", "widthPx": 4000, "heightPx": 3000,
                    "authorAttributions": [{"displayName": name if i == 0 else "A Guest"}]}
                   for i in range(photos)],
        **kw,
    }


class FakePlaces:
    def __init__(self, results, tmp_path):
        self.results = results
        self.tmp = tmp_path

    def search(self, query, max_results=60):
        return self.results

    def photos(self, place_id):
        return next(p for p in self.results if p["id"] == place_id)["photos"]

    def download_photo(self, name, dest, max_width=4800):
        dest.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (2400, 1600), (40, 120, 60)).save(dest, "JPEG")
        return dest


# contacts

def test_find_emails_skips_images_and_placeholders():
    html = ('<a href="mailto:stay@greenacres.in">x</a> logo@2x.png bookings@gmail.com '
            'you@example.com stay@greenacres.in')
    assert contacts.find_emails(html) == ["stay@greenacres.in", "bookings@gmail.com"]


def test_best_email_prefers_own_domain():
    assert contacts.best_email(["a@gmail.com", "b@greenacres.in"], "https://www.greenacres.in") == "b@greenacres.in"


def test_find_instagram_skips_post_links():
    html = 'instagram.com/p/abc123 and https://instagram.com/greenacres.farm'
    assert contacts.find_instagram(html) == "greenacres.farm"


@pytest.mark.parametrize("lead,reason", [
    ({"email": None}, "no email"),
    ({"email": "a@b.in", "rating": 3.9, "review_count": 50, "photo_count": 5}, "rating"),
    ({"email": "a@b.in", "rating": 4.5, "review_count": 5, "photo_count": 5}, "reviews"),
    ({"email": "a@b.in", "rating": 4.5, "review_count": 50, "photo_count": 1}, "photos"),
])
def test_score_rejects(lead, reason):
    points, why = contacts.score(lead, {})
    assert points == 0 and reason in why


# places

def test_rank_photos_puts_business_photos_first():
    photos = [
        {"name": "guest", "widthPx": 5000, "heightPx": 3000, "authorAttributions": [{"displayName": "Ravi"}]},
        {"name": "portrait", "widthPx": 3000, "heightPx": 4000, "authorAttributions": [{"displayName": "Green Acres"}]},
        {"name": "own", "widthPx": 4000, "heightPx": 3000, "authorAttributions": [{"displayName": "Green Acres Farm Stay"}]},
    ]
    assert [p["name"] for p in places.rank_photos(photos, "Green Acres Farm Stay")] == ["own", "portrait", "guest"]


# outreach

def test_first_email_has_attachment_optout_and_whatsapp(tmp_path):
    clip = tmp_path / "v.mp4"
    clip.write_bytes(b"0" * 100)
    msg = build_message({"name": "Green Acres", "email": "stay@greenacres.in"}, 0, OUTREACH, clip)
    body = msg.get_body(("plain",)).get_content()
    assert "Green Acres" in msg["Subject"]
    assert "not real drone footage" in body
    assert 'Reply "stop"' in body
    assert "wa.me/919800000000" in body
    assert msg["List-Unsubscribe"]
    assert any(p.get_filename() for p in msg.iter_attachments())


def test_followups_have_no_attachment(tmp_path):
    clip = tmp_path / "v.mp4"
    clip.write_bytes(b"0")
    msg = build_message({"name": "G", "email": "a@b.in"}, 1, OUTREACH, clip)
    assert not list(msg.iter_attachments())


@pytest.mark.parametrize("text,stop", [("Please STOP emailing", True), ("Not interested, thanks", True),
                                        ("How much for 2 videos?", False)])
def test_is_stop(text, stop):
    assert is_stop(text) is stop


# full pipeline, dry run, local video

def test_pipeline_end_to_end(tmp_path):
    cfg = make_cfg(tmp_path)
    db = LeadDB(cfg.data_dir / "leads.db")
    results = [
        place("p1", "Green Acres Farm Stay"),
        place("p2", "No Site Villa", website=None),
        place("p3", "Shut Resort", businessStatus="CLOSED_PERMANENTLY"),
        place("p4", "Tiny Cottage", reviews=3),
    ]
    api = FakePlaces(results, tmp_path)
    say = lambda s: None  # noqa: E731

    assert pipeline.discover(cfg, db, "Hyderabad", api, say) == 3
    assert pipeline.discover(cfg, db, "Hyderabad", api, say) == 0  # no duplicates

    scrape = lambda site: {"email": "stay@greenacres.in", "email_source": site, "instagram": "greenacres"}  # noqa: E731
    assert pipeline.qualify(cfg, db, "Hyderabad", scrape, say) == 1
    assert db.get("p2")["status"] == "rejected"
    assert "reviews" in db.get("p4")["reason"]

    assert pipeline.videos(cfg, db, "Hyderabad", api, say=say) == 1
    lead = db.get("p1")
    assert lead["status"] == "video_ready"
    assert video.duration(Path(lead["video_path"])) > 3
    assert "Green Acres Farm Stay" in lead["photo_authors"]

    assert pipeline.send(cfg, db, None, say=say) == 0  # nothing approved yet
    assert pipeline.approve(cfg, db, None, ask=lambda _: "y", say=say) == 1

    assert pipeline.send(cfg, db, None, say=say) == 1
    lead = db.get("p1")
    assert (lead["status"], lead["touches"]) == ("emailed", 1)
    eml = next((cfg.data_dir / "outbox").glob("*.eml"))
    msg = email.message_from_bytes(eml.read_bytes())
    assert msg["To"] == "stay@greenacres.in"

    # Not due yet; then due once four days have passed.
    assert pipeline.send(cfg, db, None, say=say) == 0
    old = (datetime.now(timezone.utc) - timedelta(days=4, minutes=1)).isoformat(timespec="seconds")
    db.update("p1", last_sent_at=old)
    assert pipeline.send(cfg, db, None, say=say) == 1
    assert db.get("p1")["touches"] == 2

    # A reply stops the sequence.
    assert pipeline.replies(cfg, db, fetch=lambda: [("stay@greenacres.in", "Re", "How much?")], say=say) == 1
    assert db.get("p1")["status"] == "replied"


def test_stop_reply_opts_out_for_good(tmp_path):
    cfg = make_cfg(tmp_path)
    db = LeadDB(cfg.data_dir / "leads.db")
    db.add(places.to_lead(place("p1", "Green Acres"), "Hyderabad"))
    db.update("p1", status="emailed", email="stay@greenacres.in", touches=1)
    pipeline.replies(cfg, db, fetch=lambda: [("stay@greenacres.in", "stop", "")], say=lambda s: None)
    assert db.get("p1")["status"] == "opted_out"
    assert db.is_opted_out("Stay@GreenAcres.in")


def test_daily_limit_and_pause(tmp_path):
    cfg = make_cfg(tmp_path, outreach={**OUTREACH, "daily_send_limit": 1})
    db = LeadDB(cfg.data_dir / "leads.db")
    for i in range(3):
        db.add(places.to_lead(place(f"p{i}", f"Stay {i}"), "Hyderabad"))
        db.update(f"p{i}", status="approved", email=f"s{i}@x.in")
    assert pipeline.send(cfg, db, None, say=lambda s: None) == 1
    assert pipeline.send(cfg, db, None, say=lambda s: None) == 0

    paused = make_cfg(tmp_path, pause=True)
    with pytest.raises(RuntimeError, match="pause"):
        pipeline.send(paused, db, None, say=lambda s: None)


def test_spend_cap_stops_videos(tmp_path):
    cfg = make_cfg(tmp_path, video={"shots": 3, "clip_seconds": 5, "max_spend_usd": 1})
    db = LeadDB(cfg.data_dir / "leads.db")
    db.add(places.to_lead(place("p1", "Green Acres"), "Hyderabad"))
    db.update("p1", status="qualified")

    class Pricey(video.KenBurns):
        usd_per_second = 0.2  # 3 x 5 s x $0.20 = $3, over the $1 cap

    assert pipeline.videos(cfg, db, None, FakePlaces([], tmp_path), Pricey(5), say=lambda s: None) == 0
    assert db.get("p1")["status"] == "qualified"


def test_fal_generator_polls_and_downloads(tmp_path):
    calls = []

    class Resp:
        def __init__(self, data=None, content=b""):
            self.data, self.content = data, content

        def raise_for_status(self):
            pass

        def json(self):
            return self.data

    class Session:
        statuses = iter(["IN_QUEUE", "COMPLETED"])

        def post(self, url, json, headers, timeout):
            calls.append(("post", url, json["prompt"]))
            return Resp({"request_id": "r1", "status_url": "S", "response_url": "R"})

        def get(self, url, headers=None, timeout=None):
            calls.append(("get", url))
            if url == "S":
                return Resp({"status": next(self.statuses)})
            if url == "R":
                return Resp({"video": {"url": "V"}})
            return Resp(content=b"mp4")

    photo = tmp_path / "p.jpg"
    Image.new("RGB", (1920, 1080)).save(photo)
    gen = video.Fal("k", "fal-ai/test", 0.1, session=Session(), poll_seconds=0)
    out = gen.clip(photo, video.shot_for(photo, "push_in", 1), tmp_path / "c.mp4")
    assert out.read_bytes() == b"mp4"
    assert calls[0][1] == "https://queue.fal.run/fal-ai/test"
    assert "push-in" in calls[0][2]
