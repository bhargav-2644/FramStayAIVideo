import csv
from pathlib import Path

import pytest
from PIL import Image

from bakeoff import core
from bakeoff.__main__ import main

MODELS = [
    {"id": "cheap", "name": "Cheap", "usd_per_second": 0.10, "clip_seconds": 5},
    {"id": "dear", "name": "Dear", "usd_per_second": 0.40, "clip_seconds": 5},
]


def make_photo(path: Path, size=(4000, 3000)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "green").save(path)


def write_properties(tmp_path: Path, shots: str) -> Path:
    f = tmp_path / "properties.yaml"
    f.write_text(f"properties:\n  - id: p1\n    name: P1\n    shots:\n{shots}", encoding="utf-8")
    return f


TWO_SHOTS = """\
      - photo: a.jpg
        move: rise_reveal
        subject: a villa
      - photo: b.jpg
        move: interior_glide
        subject: a living room
        end_photo: c.jpg
"""


@pytest.mark.parametrize("size", [(4000, 3000), (1000, 3000), (3840, 2160)])
def test_crop_is_16x9_and_never_upscales(size):
    out = core.crop_16x9(Image.new("RGB", size))
    assert abs(out.width / out.height - 16 / 9) < 0.01
    assert out.width <= max(size[0], 1920)
    assert out.width <= 1920


def test_small_photo_warns(tmp_path):
    make_photo(tmp_path / "small.jpg", (1200, 800))
    warnings = core.prepare_photo(tmp_path / "small.jpg", tmp_path / "out.jpg")
    assert warnings and "1200px" in warnings[0]


def test_unknown_move_rejected(tmp_path):
    f = write_properties(tmp_path, "      - photo: a.jpg\n        move: spin\n        subject: x\n")
    with pytest.raises(ValueError, match="unknown move"):
        core.load_shots(f)


def test_interior_prompt_differs():
    exterior = core.Shot("p", 1, Path("a"), "orbit", "a cottage")
    interior = core.Shot("p", 2, Path("b"), "interior_glide", "a bedroom")
    assert "aerial" in core.prompt_for(exterior)
    assert "aerial" not in core.prompt_for(interior)
    assert "a bedroom" in core.prompt_for(interior)


def test_prep_writes_photos_prompts_and_sheet(tmp_path):
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        make_photo(tmp_path / name)
    props = write_properties(tmp_path, TWO_SHOTS)
    models = tmp_path / "models.yaml"
    models.write_text("models:\n  - {id: m1, name: M1, usd_per_second: 0.1}\n", encoding="utf-8")
    out = tmp_path / "run"

    assert main(["--models", str(models), "--out", str(out), "prep", str(props)]) == 0

    assert (out / "photos/p1/1-rise_reveal.jpg").exists()
    assert (out / "photos/p1/2-interior_glide-end.jpg").exists()
    assert "Last frame" in (out / "prompts.md").read_text()
    rows = list(csv.DictReader(open(out / "scores.csv")))
    assert len(rows) == 2 * 1 * core.ATTEMPTS
    # Running prep twice must not wipe scores already entered.
    assert main(["--models", str(models), "--out", str(out), "prep", str(props)]) == 1


def test_prep_reports_missing_photo(tmp_path, capsys):
    props = write_properties(tmp_path, TWO_SHOTS)
    assert main(["--out", str(tmp_path / "run"), "prep", str(props)]) == 1
    assert "missing photo" in capsys.readouterr().err


def write_scores(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=core.SHEET_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({"seconds": 5, "notes": "", "clip_file": "", "move": "orbit", **r})


def row(model, shot, attempt, score, sendable):
    s = str(score) if score else ""
    return {"property": "p1", "shot": shot, "model": model, "attempt": attempt,
            "building": s, "landscape": s, "camera": s, "artifacts": s, "sendable": sendable}


def test_summarise_ranks_by_sendable_rate_and_costs(tmp_path):
    sheet = tmp_path / "scores.csv"
    write_scores(sheet, [
        # cheap: shot 1 fails then passes on retry, shot 2 passes first time
        row("cheap", "1", 1, 2, "n"), row("cheap", "1", 2, 4, "y"),
        row("cheap", "2", 1, 4, "y"), row("cheap", "2", 2, None, ""),
        # dear: one of two shots sendable, higher scores
        row("dear", "1", 1, 5, "y"), row("dear", "2", 1, 3, "n"),
    ])
    results = core.summarise(sheet, MODELS, usd_to_inr=88)
    assert [r.model for r in results] == ["cheap", "dear"]
    cheap, dear = results
    assert cheap.clips == 3  # the unscored retry row is ignored
    assert (cheap.sendable_shots, cheap.shots, cheap.first_try_sendable) == (2, 2, 1)
    assert cheap.cost_inr == pytest.approx(3 * 5 * 0.10 * 88)
    assert cheap.cost_per_sendable == pytest.approx(cheap.cost_inr / 2)
    assert dear.cost_per_sendable == pytest.approx(2 * 5 * 0.40 * 88)
    assert "Rs" in core.report_markdown(results)


def test_summarise_rejects_out_of_range_score(tmp_path):
    sheet = tmp_path / "scores.csv"
    write_scores(sheet, [row("cheap", "1", 1, 7, "y")])
    with pytest.raises(ValueError, match="want 1 to 5"):
        core.summarise(sheet, MODELS, usd_to_inr=88)
