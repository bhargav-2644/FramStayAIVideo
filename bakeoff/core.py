"""Bake-off pack: prepare photos, write shot prompts, build and read the score sheet."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import yaml
from PIL import Image, ImageOps

TARGET_SIZE = (1920, 1080)
MIN_WIDTH = 1920
ATTEMPTS = 2
SCORE_FIELDS = ("building", "landscape", "camera", "artifacts")
SHEET_FIELDS = (
    "property", "shot", "move", "model", "attempt", "seconds", "clip_file",
    *SCORE_FIELDS, "sendable", "notes",
)

MOVES = {
    "rise_reveal": "slow rise-and-reveal drone shot",
    "push_in": "slow forward push-in drone shot",
    "orbit": "gentle partial orbit drone shot",
    "lateral_glide": "slow lateral glide drone shot",
    "pull_back": "slow pull-back drone shot rising away",
    "interior_glide": "slow smooth gimbal glide",
}

NEGATIVE = (
    "people, animals, text, signs, logos, new buildings, changed rooflines, "
    "warped walls, melting objects, flicker, fast or shaky camera"
)


@dataclass
class Shot:
    property_id: str
    number: int
    photo: Path
    move: str
    subject: str
    end_photo: Path | None = None

    @property
    def key(self) -> str:
        return f"{self.number}-{self.move}"


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_shots(properties_file: Path) -> list[Shot]:
    """Read properties.yaml and return every shot, with photo paths resolved."""
    base = properties_file.parent
    data = load_yaml(properties_file)
    shots: list[Shot] = []
    seen: set[str] = set()
    for prop in data.get("properties") or []:
        pid = prop["id"]
        if pid in seen:
            raise ValueError(f"duplicate property id: {pid}")
        seen.add(pid)
        if not prop.get("shots"):
            raise ValueError(f"{pid}: no shots listed")
        for n, s in enumerate(prop["shots"], start=1):
            if s["move"] not in MOVES:
                raise ValueError(f"{pid} shot {n}: unknown move {s['move']!r}")
            end = s.get("end_photo")
            shots.append(Shot(
                property_id=pid,
                number=n,
                photo=base / s["photo"],
                move=s["move"],
                subject=s["subject"].strip(),
                end_photo=base / end if end else None,
            ))
    if not shots:
        raise ValueError(f"{properties_file}: no properties listed")
    return shots


def load_models(models_file: Path) -> tuple[list[dict], float]:
    data = load_yaml(models_file)
    return data["models"], float(data.get("usd_to_inr", 88))


def crop_16x9(img: Image.Image) -> Image.Image:
    """Centre-crop to 16:9, then shrink to 1920x1080. Never upscales."""
    w, h = img.size
    tw, th = TARGET_SIZE
    if w * th > h * tw:
        new_w = h * tw // th
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = w * th // tw
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))
    if img.width > tw:
        img = img.resize(TARGET_SIZE, Image.LANCZOS)
    return img


def prepare_photo(src: Path, dest: Path) -> list[str]:
    """Write a 16:9 copy of src to dest and return any warnings about it."""
    warnings = []
    with Image.open(src) as raw:
        img = ImageOps.exif_transpose(raw).convert("RGB")
    if img.width < MIN_WIDTH:
        warnings.append(f"{src.name} is only {img.width}px wide (want {MIN_WIDTH}+)")
    out = crop_16x9(img)
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.save(dest, "JPEG", quality=92)
    return warnings


def prepared_path(out_dir: Path, shot: Shot, end: bool = False) -> Path:
    suffix = "-end" if end else ""
    return out_dir / "photos" / shot.property_id / f"{shot.key}{suffix}.jpg"


def prompt_for(shot: Shot) -> str:
    move = MOVES[shot.move]
    if shot.move == "interior_glide":
        return (
            f"Cinematic interior shot, {move} through {shot.subject}.\n"
            "Soft natural window light, stable smooth camera, 24fps look.\n"
            "Keep the furniture, walls, windows and layout exactly as in the photo.\n"
            "No people, no text, no new objects, no sudden movement."
        )
    return (
        f"Cinematic aerial {move} over {shot.subject}.\n"
        "Golden-hour light, soft shadows, stable smooth camera, 24fps look.\n"
        "Keep the building, pool shape, roofline and landscape exactly as in the photo.\n"
        "No people, no text, no new structures, no sudden movement."
    )


def write_prompts(shots: list[Shot], models: list[dict], out_dir: Path) -> Path:
    """Write prompts.md: one block per shot to paste into every model."""
    lines = [
        "# Bake-off prompts",
        "",
        "Use the same photo, prompt and negative prompt for every model. "
        "Generate without audio. Save each clip as "
        "`clips/<model>/<property>/<shot>-a<attempt>.mp4`.",
        "",
        "Models: " + ", ".join(f"`{m['id']}` ({m['name']})" for m in models),
        "",
        f"Negative prompt for every shot: `{NEGATIVE}`",
        "",
    ]
    current = None
    for shot in shots:
        if shot.property_id != current:
            current = shot.property_id
            lines += [f"## {current}", ""]
        lines += [
            f"### Shot {shot.key}",
            "",
            f"- Photo: `{prepared_path(out_dir, shot).relative_to(out_dir)}`",
        ]
        if shot.end_photo:
            lines.append(
                f"- Last frame (models that support it): "
                f"`{prepared_path(out_dir, shot, end=True).relative_to(out_dir)}`"
            )
        lines += ["", "```text", prompt_for(shot), "```", ""]
    path = out_dir / "prompts.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_sheet(shots: list[Shot], models: list[dict], out_dir: Path) -> Path:
    """Write an empty score sheet: one row per shot, model and attempt."""
    path = out_dir / "scores.csv"
    if path.exists():
        raise FileExistsError(f"{path} already exists; delete it to start over")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SHEET_FIELDS)
        w.writeheader()
        for shot in shots:
            for m in models:
                for attempt in range(1, ATTEMPTS + 1):
                    w.writerow({
                        "property": shot.property_id,
                        "shot": shot.key,
                        "move": shot.move,
                        "model": m["id"],
                        "attempt": attempt,
                        "seconds": m.get("clip_seconds", 5),
                        "clip_file": f"clips/{m['id']}/{shot.property_id}/{shot.key}-a{attempt}.mp4",
                    })
    return path


@dataclass
class ModelResult:
    model: str
    name: str
    clips: int
    shots: int
    sendable_shots: int
    first_try_sendable: int
    avg_score: float
    cost_inr: float

    @property
    def cost_per_sendable(self) -> float | None:
        return self.cost_inr / self.sendable_shots if self.sendable_shots else None


def _score(row: dict, field: str) -> int:
    value = int(row[field])
    if not 1 <= value <= 5:
        raise ValueError(f"{row['model']} {row['property']} {row['shot']}: {field}={value}, want 1 to 5")
    return value


def summarise(sheet: Path, models: list[dict], usd_to_inr: float) -> list[ModelResult]:
    """Score each model from the filled-in sheet, best first.

    A row counts as run once its building score is filled in. A shot is
    sendable if any attempt at it is marked sendable.
    """
    by_id = {m["id"]: m for m in models}
    with open(sheet, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("building", "").strip()]

    results = []
    for mid, m in by_id.items():
        mine = [r for r in rows if r["model"] == mid]
        if not mine:
            continue
        shots: dict[tuple[str, str], bool] = {}
        first_try = 0
        totals = []
        cost_usd = 0.0
        for r in mine:
            totals.append(sum(_score(r, f) for f in SCORE_FIELDS) / len(SCORE_FIELDS))
            ok = r.get("sendable", "").strip().lower() in ("y", "yes", "1", "true")
            key = (r["property"], r["shot"])
            shots[key] = shots.get(key, False) or ok
            if ok and r["attempt"] == "1":
                first_try += 1
            cost_usd += float(r["seconds"]) * m["usd_per_second"]
        results.append(ModelResult(
            model=mid,
            name=m["name"],
            clips=len(mine),
            shots=len(shots),
            sendable_shots=sum(shots.values()),
            first_try_sendable=first_try,
            avg_score=sum(totals) / len(totals),
            cost_inr=cost_usd * usd_to_inr,
        ))
    results.sort(key=lambda r: (-r.sendable_shots / r.shots, -r.avg_score, r.cost_inr))
    return results


def report_markdown(results: list[ModelResult]) -> str:
    lines = [
        "| Rank | Model | Sendable shots | Sendable first try | Avg score (1-5) | Clips run | Spend | Cost per sendable shot |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(results, start=1):
        per = f"Rs {r.cost_per_sendable:,.0f}" if r.cost_per_sendable is not None else "none sendable"
        lines.append(
            f"| {i} | {r.name} | {r.sendable_shots} of {r.shots} | {r.first_try_sendable} "
            f"| {r.avg_score:.2f} | {r.clips} | Rs {r.cost_inr:,.0f} | {per} |"
        )
    return "\n".join(lines)
