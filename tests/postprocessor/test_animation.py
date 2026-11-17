from pathlib import Path

import pytest
from PIL import Image

from modules.postprocessor.postprocess_core import (
    build_gifs,
    build_transparent_backgrounds,
)
from modules.postprocessor.postprocess import finalize_render_output


def test_build_gif_contains_every_rendered_frame(tmp_path: Path) -> None:
    frame_dir = tmp_path / "frames" / "PILE_U_MAG"
    frame_dir.mkdir(parents=True)
    colors = ((255, 0, 0), (0, 255, 0), (0, 0, 255))
    for index, color in enumerate(colors):
        Image.new("RGB", (24, 16), color).save(frame_dir / f"{index:04d}.png")

    counts = build_gifs(tmp_path, fps=5)

    target = tmp_path / "animations" / "PILE_U_MAG.gif"
    assert counts == {"PILE_U_MAG": 3}
    with Image.open(target) as animation:
        assert animation.n_frames == 3
        assert animation.info["duration"] == 200


@pytest.mark.parametrize(("fps", "duration", "expected"), [
    (30, None, {10: 330, 41: 1370}),
    (60, None, {10: 170, 41: 680}),
    (25, 4.0, {10: 4000, 41: 4000}),
    (25, 1.125, {10: 1130, 41: 1130}),
])
def test_gif_loop_timing_and_retained_frames(tmp_path, fps, duration, expected):
    for count in expected:
        frames = tmp_path / "frames" / str(count)
        frames.mkdir(parents=True)
        for index in range(count):
            Image.new("RGB", (8, 8), (index, 0, 0)).save(frames / f"{index:04}.png")
    manifest = finalize_render_output(tmp_path, fps, duration_seconds=duration, export_transparent_background_png=False)
    timing = manifest["animation_timing"]
    assert timing["mode"] == ("fps" if duration is None else "duration")
    for count, total_ms in expected.items():
        with Image.open(tmp_path / "animations" / f"{count}.gif") as gif:
            assert gif.n_frames == count
            delays = []
            for index in range(count):
                gif.seek(index)
                assert gif.convert("RGB").getpixel((0, 0)) == (index, 0, 0)
                delays.append(gif.info["duration"])
            assert sum(delays) == total_ms and min(delays) >= 10
            assert max(delays) - min(delays) <= 10
        assert timing["fields"][str(count)]["seconds"] == total_ms / 1000


def test_duplicate_frames_preserve_time_and_infeasible_target_preserves_last_gif(tmp_path):
    frames = tmp_path / "frames" / "MISES"
    frames.mkdir(parents=True)
    for index, color in enumerate(("red", "red", "blue")):
        Image.new("RGB", (8, 8), color).save(frames / f"{index}.png")
    build_gifs(tmp_path, duration_seconds=1.23)
    target = tmp_path / "animations" / "MISES.gif"
    before = target.read_bytes()
    with Image.open(target) as gif:
        assert gif.n_frames == 2
        assert gif.info["duration"] == 820
        gif.seek(1)
        assert gif.info["duration"] == 410
    with pytest.raises(ValueError, match="MISES.*3 个源帧.*0.03"):
        build_gifs(tmp_path, duration_seconds=0.02)
    assert target.read_bytes() == before


def test_transparent_copy_does_not_modify_original_png(tmp_path: Path) -> None:
    source_path = tmp_path / "contours" / "PILE_U_MAG_LAST.png"
    source_path.parent.mkdir(parents=True)
    source = Image.new("RGB", (12, 8), (255, 255, 255))
    for x in range(4, 8):
        for y in range(2, 6):
            source.putpixel((x, y), (180, 20, 20))
    source.save(source_path)
    original_bytes = source_path.read_bytes()

    assert build_transparent_backgrounds(tmp_path) == 1

    assert source_path.read_bytes() == original_bytes
    target = tmp_path / "contours_transparent" / source_path.name
    with Image.open(target) as transparent:
        rgba = transparent.convert("RGBA")
        assert rgba.getpixel((0, 0))[3] == 0
        assert rgba.getpixel((5, 4))[3] == 255


def test_finalize_render_output_can_export_only_transparent_pngs(
    tmp_path: Path,
) -> None:
    frame = tmp_path / "frames" / "PILE_U_MAG" / "0000.png"
    contour = tmp_path / "contours" / "PILE_U_MAG_LAST.png"
    frame.parent.mkdir(parents=True)
    contour.parent.mkdir(parents=True)
    Image.new("RGB", (12, 8), "white").save(frame)
    Image.new("RGB", (12, 8), "white").save(contour)

    manifest = finalize_render_output(
        tmp_path,
        export_white_background_png=False,
        export_transparent_background_png=True,
    )

    assert not (tmp_path / "frames").exists()
    assert not (tmp_path / "contours").exists()
    assert (tmp_path / "frames_transparent" / "PILE_U_MAG" / "0000.png").is_file()
    assert (tmp_path / "contours_transparent" / "PILE_U_MAG_LAST.png").is_file()
    assert (tmp_path / "animations" / "PILE_U_MAG.gif").is_file()
    assert manifest["original_pngs_preserved"] is False
    assert manifest["white_png_count"] == 0
    assert manifest["transparent_png_count"] == 2


def test_finalize_render_output_can_export_only_white_pngs(tmp_path: Path) -> None:
    frame = tmp_path / "frames" / "PILE_U_MAG" / "0000.png"
    contour = tmp_path / "contours" / "PILE_U_MAG_LAST.png"
    frame.parent.mkdir(parents=True)
    contour.parent.mkdir(parents=True)
    Image.new("RGB", (12, 8), "white").save(frame)
    Image.new("RGB", (12, 8), "white").save(contour)

    manifest = finalize_render_output(
        tmp_path,
        export_white_background_png=True,
        export_transparent_background_png=False,
    )

    assert frame.is_file()
    assert contour.is_file()
    assert not (tmp_path / "frames_transparent").exists()
    assert not (tmp_path / "contours_transparent").exists()
    assert manifest["original_pngs_preserved"] is True
    assert manifest["white_png_count"] == 2
    assert manifest["transparent_png_count"] == 0
