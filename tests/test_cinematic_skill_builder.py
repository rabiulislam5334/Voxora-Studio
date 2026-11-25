import json
from types import SimpleNamespace

import pytest
from PIL import Image

from app.universal.cinematic_skill_builder import (
    CinematicSkillFilmBuildError,
    CinematicSkillFilmBuilder,
    CinematicSkillShot,
)
from app.universal.cinematic_skill_timing import (
    CinematicLineCue,
    CinematicSkillNarrationDoc,
    CinematicWordCue,
)


class FakeFilm:
    def __init__(self, duration, fps, look):
        self.duration, self.fps, self.look = duration, fps, look
        self.items, self.cam_keys = [], []
        self.auto_cues = self.auto_whoosh = False

    def add(self, item):
        self.items.append(item)
        return item

    def shot(self, t, x, y, zoom, **kwargs):
        self.cam_keys.append((t, x, y, zoom, kwargs))


class FakeItem:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


def fake_engine():
    return SimpleNamespace(
        Film=FakeFilm,
        Card=FakeItem,
        BigText=FakeItem,
        Counter=FakeItem,
        Print=FakeItem,
    )


def make_doc(tmp_path):
    return CinematicSkillNarrationDoc(
        tmp_path,
        [
            CinematicLineCue(
                1, 0.0, 2.0, "The Voyager crossed the heliopause.",
                (
                    CinematicWordCue("The", 0.05, 0.2),
                    CinematicWordCue("Voyager", 0.25, 0.7),
                    CinematicWordCue("crossed", 0.75, 1.0),
                    CinematicWordCue("the", 1.05, 1.2),
                    CinematicWordCue("heliopause.", 1.25, 1.9),
                ),
            ),
            CinematicLineCue(2, 2.0, 4.0, "It entered interstellar space."),
        ],
    )


def test_builds_one_narration_synchronised_card_per_line(tmp_path):
    doc = make_doc(tmp_path)
    film = CinematicSkillFilmBuilder(engine_module=fake_engine()).build(doc)

    assert film.duration == 4.0
    assert film.fps == 30
    assert len(film.cam_keys) == 2
    assert [item.kwargs["title"] for item in film.items] == [
        "KEY IDEA 01", "KEY IDEA 02",
    ]
    assert film.items[0].kwargs["lines"] == ("The Voyager crossed the heliopause.",)
    assert film.items[0].kwargs["t_in"] == 0.0
    assert film.items[0].kwargs["t_out"] == 2.0


def test_explicit_counter_shot_requires_and_uses_integer_value(tmp_path):
    doc = make_doc(tmp_path)
    film = CinematicSkillFilmBuilder(engine_module=fake_engine()).build(
        doc,
        [CinematicSkillShot(1, kind="counter", counter_value=1977)],
    )
    assert film.items[0].kwargs["value"] == 1977
    assert film.items[0].kwargs["t_in"] == 0.0


def test_emphasis_uses_exact_measured_word_timestamp(tmp_path):
    doc = make_doc(tmp_path)
    film = CinematicSkillFilmBuilder(engine_module=fake_engine()).build(
        doc,
        [CinematicSkillShot(1, emphasis_word="Voyager")],
    )
    emphasis = film.items[1]
    assert emphasis.kwargs["text"] == "Voyager"
    assert emphasis.kwargs["t_in"] == 0.25


def test_missing_word_timestamp_is_not_estimated(tmp_path):
    doc = make_doc(tmp_path)
    with pytest.raises(ValueError, match="no measured timestamp"):
        CinematicSkillFilmBuilder(engine_module=fake_engine()).build(
            doc,
            [CinematicSkillShot(1, emphasis_word="NASA")],
        )


def test_long_body_is_rejected_instead_of_silently_truncated(tmp_path):
    doc = make_doc(tmp_path)
    long_line = " ".join(["word"] * 250)
    with pytest.raises(CinematicSkillFilmBuildError, match="Split the narration"):
        CinematicSkillFilmBuilder._wrap_lines(long_line)


def test_invalid_shot_reference_is_rejected(tmp_path):
    doc = make_doc(tmp_path)
    with pytest.raises(CinematicSkillFilmBuildError, match="unknown narration line"):
        CinematicSkillFilmBuilder(engine_module=fake_engine()).build(
            doc, [CinematicSkillShot(99)]
        )


def test_counter_rejects_non_integer_values(tmp_path):
    doc = make_doc(tmp_path)
    with pytest.raises(CinematicSkillFilmBuildError, match="requires an integer"):
        CinematicSkillFilmBuilder(engine_module=fake_engine()).build(
            doc, [CinematicSkillShot(1, kind="counter", counter_value=3.5)]
        )

def test_unsupported_visual_kind_is_rejected(tmp_path):
    doc = make_doc(tmp_path)
    with pytest.raises(CinematicSkillFilmBuildError, match="unsupported visual kind"):
        CinematicSkillFilmBuilder(engine_module=fake_engine()).build(
            doc, [CinematicSkillShot(1, kind="unverified_magic")]
        )



def test_image_shot_stages_local_asset_and_adds_print_item(tmp_path):
    source = tmp_path / "voyager.png"
    Image.new("RGB", (640, 320), (30, 90, 150)).save(source)
    doc = make_doc(tmp_path)

    film = CinematicSkillFilmBuilder(engine_module=fake_engine()).build(
        doc,
        [CinematicSkillShot(
            1, kind="image", title="Voyager", image_path=str(source),
        )],
    )

    item = film.items[0]
    key = item.args[0]
    assert key.startswith("voxora_")
    assert item.kwargs["t_in"] == 0.0
    assert item.kwargs["t_out"] == 2.0
    assert item.kwargs["label"] == "Voyager"
    staged = doc.prep / "photos" / f"{key}.jpg"
    assert staged.is_file()
    metadata = json.loads((doc.prep / "photos" / "meta.json").read_text())
    assert metadata[key] == {"w": 640, "h": 320, "kind": "photo"}
    assert doc.meta[key] == metadata[key]


def test_image_shot_rejects_missing_or_invalid_local_asset(tmp_path):
    doc = make_doc(tmp_path)
    builder = CinematicSkillFilmBuilder(engine_module=fake_engine())
    with pytest.raises(CinematicSkillFilmBuildError, match="image_path"):
        builder.build(doc, [CinematicSkillShot(1, kind="image")])
    with pytest.raises(CinematicSkillFilmBuildError, match="unavailable"):
        builder.build(
            doc,
            [CinematicSkillShot(
                1, kind="image", image_path=str(tmp_path / "missing.png"),
            )],
        )


def test_director_camera_presets_change_camera_zoom_deterministically(tmp_path):
    doc = make_doc(tmp_path)
    shots = [
        CinematicSkillShot(1, camera_preset="evidence_detail"),
        CinematicSkillShot(2, camera_preset="map_wide"),
    ]
    film = CinematicSkillFilmBuilder(engine_module=fake_engine()).build(doc, shots)
    assert [key[3] for key in film.cam_keys] == [1.22, 0.86]
    assert film.cam_keys[0][4] == {"radius": 1350, "strength": 0.56}
    assert film.cam_keys[1][4] == {"radius": 2050, "strength": 0.42}


def test_unknown_camera_preset_is_rejected(tmp_path):
    doc = make_doc(tmp_path)
    with pytest.raises(CinematicSkillFilmBuildError, match="unsupported camera preset"):
        CinematicSkillFilmBuilder(engine_module=fake_engine()).build(
            doc, [CinematicSkillShot(1, camera_preset="arbitrary")],
        )
