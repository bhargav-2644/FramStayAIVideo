"""Make the preview: pick photos, turn each into a clip, stitch with a title card and watermark."""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

from bakeoff.core import NEGATIVE, Shot, crop_16x9, prompt_for

SIZE = (1280, 720)
FPS = 24
FADE = 0.6
CARD_SECONDS = 3.0
# One move per shot position: open on a reveal, move in, close pulling away.
MOVES = ("rise_reveal", "push_in", "lateral_glide", "pull_back")
FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)


def font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_PATHS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


def run(cmd: list[str]) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {res.stderr.strip()[-800:]}")


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def prepare(src: Path, dest: Path) -> Path:
    with Image.open(src) as raw:
        img = ImageOps.exif_transpose(raw).convert("RGB")
    crop_16x9(img).save(dest, "JPEG", quality=92)
    return dest


def shot_for(photo: Path, move: str, n: int) -> Shot:
    return Shot("lead", n, photo, move, "the property in the photo, its buildings and grounds")


# Clip generators. Each takes a prepared 16:9 photo and a shot, writes an mp4.

class KenBurns:
    """Free local clips: a slow zoom or pan over the still photo."""

    usd_per_second = 0.0

    def __init__(self, seconds: float = 5):
        self.seconds = seconds

    def clip(self, photo: Path, shot: Shot, dest: Path) -> Path:
        n = int(self.seconds * FPS)
        center_x, center_y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        motion = {
            "push_in": (f"1+0.15*on/{n}", center_x, center_y),
            "pull_back": (f"1.15-0.15*on/{n}", center_x, center_y),
            "rise_reveal": ("1.15", center_x, f"(ih-ih/zoom)*(1-on/{n})"),
            "lateral_glide": ("1.15", f"(iw-iw/zoom)*on/{n}", center_y),
        }.get(shot.move, (f"1+0.1*on/{n}", center_x, center_y))
        z, x, y = motion
        vf = (
            f"scale=3840:-2,zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={SIZE[0]}x{SIZE[1]}:fps={FPS},"
            "format=yuv420p"
        )
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(photo), "-vf", vf,
             "-frames:v", str(n), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(dest)])
        return dest


class Fal:
    """An image-to-video model on fal.ai's queue API."""

    def __init__(self, api_key: str, endpoint: str, usd_per_second: float,
                 seconds: float = 5, extra_args: dict | None = None,
                 session: requests.Session | None = None, poll_seconds: float = 5):
        self.key = api_key
        self.endpoint = endpoint
        self.usd_per_second = usd_per_second
        self.seconds = seconds
        self.extra = extra_args or {}
        self.http = session or requests.Session()
        self.poll = poll_seconds

    def clip(self, photo: Path, shot: Shot, dest: Path) -> Path:
        headers = {"Authorization": f"Key {self.key}"}
        image = "data:image/jpeg;base64," + base64.b64encode(photo.read_bytes()).decode()
        body = {"prompt": prompt_for(shot), "negative_prompt": NEGATIVE,
                "image_url": image, **self.extra}
        r = self.http.post(f"https://queue.fal.run/{self.endpoint}", json=body,
                           headers=headers, timeout=60)
        r.raise_for_status()
        job = r.json()
        deadline = time.time() + 15 * 60
        while True:
            s = self.http.get(job["status_url"], headers=headers, timeout=30)
            s.raise_for_status()
            status = s.json().get("status")
            if status == "COMPLETED":
                break
            if status not in ("IN_QUEUE", "IN_PROGRESS"):
                raise RuntimeError(f"fal job {job.get('request_id')} ended as {status}")
            if time.time() > deadline:
                raise RuntimeError(f"fal job {job.get('request_id')} timed out")
            time.sleep(self.poll)
        res = self.http.get(job["response_url"], headers=headers, timeout=30)
        res.raise_for_status()
        url = res.json()["video"]["url"]
        video = self.http.get(url, timeout=120)
        video.raise_for_status()
        dest.write_bytes(video.content)
        return dest


def title_card(name: str, dest: Path) -> Path:
    img = Image.new("RGB", SIZE, (18, 22, 20))
    d = ImageDraw.Draw(img)
    size = 64
    while size > 28 and d.textlength(name, font=font(size)) > SIZE[0] - 120:
        size -= 4  # long property names shrink to fit
    big, small = font(size), font(28)
    for text, f, y in ((name, big, SIZE[1] // 2 - 60),
                       ("A cinematic preview, made from your listing photos", small, SIZE[1] // 2 + 30)):
        w = d.textlength(text, font=f)
        d.text(((SIZE[0] - w) / 2, y), text, font=f, fill=(240, 236, 228))
    img.save(dest)
    return dest


def watermark(dest: Path) -> Path:
    text = "AI preview"
    f = font(26)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    w = int(probe.textlength(text, font=f)) + 28
    img = Image.new("RGBA", (w, 46), (0, 0, 0, 110))
    ImageDraw.Draw(img).text((14, 8), text, font=f, fill=(255, 255, 255, 220))
    img.save(dest)
    return dest


def stitch(clips: list[Path], card: Path, mark: Path, dest: Path, music: Path | None = None) -> Path:
    """Cross-dissolve the clips, end on the title card, watermark everything."""
    work = dest.parent
    card_clip = work / "card.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(card), "-t", str(CARD_SECONDS),
         "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", str(card_clip)])
    parts = [*clips, card_clip]
    inputs: list[str] = []
    for p in parts:
        inputs += ["-i", str(p)]
    inputs += ["-i", str(mark)]
    norm = "".join(
        f"[{i}:v]scale={SIZE[0]}:{SIZE[1]}:force_original_aspect_ratio=increase,"
        f"crop={SIZE[0]}:{SIZE[1]},fps={FPS},format=yuv420p,setsar=1,settb=AVTB[n{i}];"
        for i in range(len(parts))
    )
    chain, last, offset = "", "n0", 0.0
    for i in range(1, len(parts)):
        offset += duration(parts[i - 1]) - FADE
        chain += f"[{last}][n{i}]xfade=transition=fade:duration={FADE}:offset={offset:.3f}[x{i}];"
        last = f"x{i}"
    total = offset + duration(parts[-1])
    graph = norm + chain + f"[{last}][{len(parts)}:v]overlay=W-w-24:H-h-24[out]"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs]
    audio_map: list[str] = []
    if music:
        cmd += ["-i", str(music)]
        graph += f";[{len(parts) + 1}:a]afade=t=out:st={max(total - 2, 0):.2f}:d=2[aout]"
        audio_map = ["-map", "[aout]", "-c:a", "aac", "-b:a", "128k"]
    cmd += ["-filter_complex", graph, "-map", "[out]", *audio_map, "-t", f"{total:.2f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(dest)]
    run(cmd)
    return dest


def make_preview(name: str, photos: list[Path], generator, dest: Path,
                 music: Path | None = None) -> tuple[Path, float]:
    """Build one property's teaser from its photos. Returns the path and the spend in USD."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    spent = 0.0
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        clips = []
        for i, src in enumerate(photos):
            prepared = prepare(src, work / f"photo{i}.jpg")
            shot = shot_for(prepared, MOVES[i % len(MOVES)], i + 1)
            clips.append(generator.clip(prepared, shot, work / f"clip{i}.mp4"))
            spent += getattr(generator, "seconds", 5) * generator.usd_per_second
        out = stitch(clips, title_card(name, work / "card.png"), watermark(work / "mark.png"),
                     work / "preview.mp4", music)
        shutil.move(out, dest)
    return dest, spent
