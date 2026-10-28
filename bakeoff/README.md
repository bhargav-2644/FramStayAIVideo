# Video model bake-off

Five image-to-video models get the same photos, prompts and camera moves.
Each clip gets a score, and the report picks the model that gives the most
sendable shots for the least money. The shortlist and its prices come from
[`docs/research/video-models.md`](../docs/research/video-models.md).

The pack is 3 to 5 properties x 3 shots x 5 models x up to 2 attempts. With
5 properties that is 75 to 150 clips, about $70 to $120 at the prices in
`models.yaml`.

## Steps

1. **Install** (Python 3.11+): `uv sync`
2. **Pick 3 to 5 properties** you would really pitch: different styles (a
   pool villa, a farm stay, a cottage among trees), with good photos the owner
   published themselves. Put the photos under `bakeoff/photos/<property-id>/`
   (git ignores this folder).
3. **Describe them:** copy `properties.example.yaml` to `properties.yaml` and
   list 3 shots per property: the photo, one camera move and a short
   description of what is in the frame. Prefer wide or elevated photos. For
   at least one shot per property, add an `end_photo` taken from further
   along the same move, so models with a last-frame option can use it.
4. **Check prices** for each model on the provider's own page and update
   `models.yaml`.
5. **Prepare:**

   ```sh
   uv run python -m bakeoff prep bakeoff/properties.yaml
   ```

   This writes `bakeoff-run/` (also ignored by git):
   - `photos/`: each photo centre-cropped to 16:9 and capped at 1920x1080.
     It warns about photos narrower than 1920 px; swap those out if you can.
   - `prompts.md`: one prompt per shot, plus the shared negative prompt.
   - `scores.csv`: one row per shot, model and attempt, ready to fill in.
6. **Generate:** for every shot and model, use the prepared photo and the
   prompt exactly as written, 5 seconds, no audio. Save each clip at the path
   in the `clip_file` column. Only run attempt 2 when attempt 1 is not
   sendable, and change nothing between attempts except the seed.
7. **Score** each clip in `scores.csv` (rubric below). If you can, score
   without looking at the model folder name, so the brand doesn't sway you.
8. **Report:**

   ```sh
   uv run python -m bakeoff report
   ```

   This prints the ranking and saves it to `bakeoff-run/report.md`.

## Scoring rubric

Score 1 to 5 in each column; 5 is best.

| Column | 5 | 3 | 1 |
|---|---|---|---|
| `building` | Roofline, walls, windows and pool shape match the photo all the way through | Small drift an owner might not notice | The building warps, melts or changes |
| `landscape` | Trees, water, hills and paths stay put and move naturally | Some shimmer or a soft patch | Ground or trees morph or flicker |
| `camera` | Slow and smooth, and the move matches the one asked for | Slightly fast, or a different move | Jerky, sudden, or a cut |
| `artifacts` | Nothing invented | One small invented object | People, animals, text or new structures appear |

Set `sendable` to `y` if you would put the clip in front of the owner as it is,
and `n` otherwise. Use `notes` for anything worth remembering, such as "pool
changes shape at 3 s".

## How the report ranks

- A row counts once its `building` score is filled in.
- A shot is sendable if any attempt at it is marked `y`.
- Models are ranked by share of shots sendable, then average score, then
  spend.
- Spend is clip seconds times the price per second in `models.yaml`, in
  rupees. Cost per sendable shot is that spend divided by the number of
  sendable shots.

**Pick a winner** that gets at least 3 of 5 properties' shots sendable. Then
check its cost per sendable shot: a 15 second teaser is 3 shots and has to
come in under about Rs 300, so cost per sendable shot should be at most about
Rs 100. If the top model misses that, the runner-up may be the better buy.
