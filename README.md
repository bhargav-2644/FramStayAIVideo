# FramStayAIVideo

Give it a city. It finds villas and farm stays around it on Google Maps,
finds each owner's email on their website, makes a short "AI preview" video
from the listing photos, and emails it to them with an offer to make the real
thing. Follow-ups go out on their own, and the sequence stops when someone
replies.

```sh
uv run python -m villa_agent run Hyderabad
```

## How it works

| Step | Command | What it does | Lead moves to |
|---|---|---|---|
| 1 | `discover <city>` | Searches the Places API with the queries in `config.yaml` ("farm stay near Hyderabad", ...). Keeps name, rating, reviews, website, phone, Maps link. Skips closed places and ones already found. | `discovered` |
| 2 | `qualify` | Opens the property's own website (home, contact and about pages) for a published email and Instagram. Scores the lead; rejects it with a reason if it has no website, no email, rating under 4.0, fewer than 20 reviews or fewer than 3 photos. | `qualified` or `rejected` |
| 3 | `videos` | Fetches the listing photos (business-credited ones first, then the widest), turns 3 of them into clips, and stitches a 15 s teaser with cross-dissolves, a title card with the property name and an "AI preview" watermark. Photos are deleted after each video. Stops at `max_spend_usd`. | `video_ready` or `failed` |
| 4 | `approve` | Shows each video, email address and where the address came from; you approve or reject. | `approved` |
| 5 | `send` | Emails approved leads with the video attached, then follow-ups on day 4 and day 9, up to `daily_send_limit` a day. | `emailed`, later `no_reply` |
| 6 | `replies` | Reads the inbox. A reply stops the sequence and is printed for you; "stop" or "not interested" opts the address out for good. | `replied` or `opted_out` |

`run <city>` does steps 1, 2, 3 and 5 in one go; `status` counts leads at
each step. Everything lives in `data/leads.db` (SQLite), with a log of every
change in its `events` table.

## Setup

1. Install Python 3.11+, [uv](https://docs.astral.sh/uv/) and ffmpeg, then
   `uv sync`.
2. `cp config.example.yaml config.yaml` and fill in your sender details, mail
   server and price.
3. `cp .env.example .env` and add:
   - `GOOGLE_MAPS_API_KEY`: a Google Cloud key with **Places API (New)**
     enabled, billing on, a budget alert, and the key restricted to that API.
   - `MAIL_PASSWORD`: for the sending mailbox (only needed once `dry_run` is off).
   - `FAL_KEY`: only when `video.provider` is `fal`.
4. Do a dry run: `uv run python -m villa_agent run Hyderabad --limit 3`, then
   `approve` and `send`. With `dry_run: true`, emails are written to
   `data/outbox/` instead of sent, so you can open them and check.

## Video generators

- `kenburns` (default): free, made locally with ffmpeg as a slow zoom or pan
  over each photo. Use it to test the whole flow without spending anything.
- `fal`: an AI image-to-video model on fal.ai, for the real drone-style look.
  Set `fal_endpoint` to the model the [bake-off](bakeoff/README.md) picks and
  `usd_per_second` to its price so the spend cap works. Check the endpoint's
  input fields on fal.ai and add any extras under `fal_extra_args`.

## Guardrails built in

- `pause: true` in `config.yaml` stops anything that spends money or sends email.
- Nothing is emailed until you approve its video (`require_approval`).
- Email only to addresses the business publishes on its own website, with
  where each one came from stored. Every email has your real identity, an
  opt-out line and a `List-Unsubscribe` header. Opt-outs are permanent.
- Each video is watermarked "AI preview" and the email says it is made from
  photos, not real drone footage.
- Photos come only through the official Places API, never scraped, and are
  deleted after each video. **Google's terms restrict using Maps content
  outside Google's services, and guest photos belong to their
  photographers.** Business-credited photos are used first to reduce that
  risk; get a lawyer's view before scaling up.
- No WhatsApp, SMS or calls are sent automatically. The email can carry a
  click-to-chat link so owners message you first.

## Also in this repo

- [`docs/research/video-models.md`](docs/research/video-models.md): which
  image-to-video models to consider, with prices (October 2026).
- [`bakeoff/`](bakeoff/README.md): a pack for comparing those models by hand
  on a few properties.

Run the tests with `uv run --group dev pytest`.
