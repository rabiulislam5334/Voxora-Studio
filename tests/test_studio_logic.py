from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.audio.mixer import build_mix_args
from app.audio.probe import parse_probe_output
from app.cache.video_cache import VideoCache
from app.core.exceptions import MediaError, ProductionError
from app.models.scene import Scene
from app.projects.manager import ProjectManager
from app.projects.serializer import project_from_dict, project_to_dict
from app.studio.models import (
    AudioSettings, MusicTrack, SceneVideo, StudioState, VideoSettings, output_size,
)
from app.studio.timing import SceneTimingInput, compute_timeline
from app.studio.validation import ERROR, WARNING, has_errors, validate_production
from app.video.render import (
    FILTER_SCRIPT_OPTIONS, SegmentSpec, build_concat_list, build_segment_args, build_xfade_join_args,
    build_xfade_script, is_unknown_option_error,
)


# ---------------- sizes ----------------

def test_output_sizes_for_aspects_and_resolutions():
    assert output_size("16:9", "1080p") == (1920, 1080)
    assert output_size("16:9", "720p") == (1280, 720)
    assert output_size("9:16", "1080p") == (1080, 1920)
    assert output_size("9:16", "720p") == (720, 1280)
    assert output_size("16:9", "360p (draft)") == (640, 360)
    assert output_size("nonsense", "nonsense") == (1280, 720)


# ---------------- model persistence ----------------

def test_studio_state_roundtrips_through_project_file(tmp_path):
    manager = ProjectManager()
    project = manager.current_project
    scene = project.add_scene(Scene(title="One", text="Hello"))
    state = StudioState()
    state.audio.narration_volume_percent = 90
    state.audio.tracks.append(MusicTrack(path="C:/music/ক.mp3", volume_percent=12, trim_start_s=3, trim_end_s=40))
    state.video.aspect, state.video.resolution, state.video.transition = "9:16", "1080p", "crossfade"
    state.video.set_scene(scene.id, SceneVideo(media_path="C:/img/ছবি 1.png", duration_s=7.5, motion="pan_left", fit="fit"))
    state.write_to(project.settings)

    path = manager.save(tmp_path / "প্রজেক্ট.voxora")
    reopened = ProjectManager().open(path)
    loaded = StudioState.from_project_settings(reopened.settings)
    assert loaded.to_dict() == state.to_dict()
    assert loaded.video.scene(scene.id).media_path == "C:/img/ছবি 1.png"


def test_old_project_without_studio_settings_opens_with_defaults():
    legacy = {"schema_version": 1, "id": "x", "name": "Old", "language": "en", "settings": {"theme": "dark"},
              "scenes": [{"id": "s1", "title": "A", "text": "hi", "order": 0}]}
    project = project_from_dict(legacy)
    assert "studio" not in project.settings
    state = StudioState.from_project_settings(project.settings)
    assert state.video.resolution == "720p" and state.audio.tracks == []
    # unrelated settings survive a save round trip
    assert project_from_dict(json.loads(json.dumps(project_to_dict(project)))).settings == {"theme": "dark"}


def test_corrupt_studio_settings_fall_back_to_safe_defaults():
    garbage = {"studio": {"audio": {"tracks": ["x", 5, {"path": ""}, {"path": "a.mp3", "volume_percent": "loud",
                                                                      "trim_start_s": 10, "trim_end_s": 2}]},
                          "video": {"aspect": "4:3", "fps": 9999, "transition_s": -3,
                                    "scenes": {"s": {"duration_s": "abc", "motion": "spin"}, 7: {}}}}}
    state = StudioState.from_project_settings(garbage)
    assert [t.path for t in state.audio.tracks] == ["a.mp3"]
    assert state.audio.tracks[0].volume_percent == 15 and state.audio.tracks[0].trim_end_s is None
    assert state.video.aspect == "16:9" and state.video.fps == 60 and state.video.transition_s == 0.1
    assert state.video.scenes == {}
    assert StudioState.from_project_settings(None).video.aspect == "16:9"


def test_prune_scenes_removes_deleted_scene_settings():
    state = StudioState()
    state.video.set_scene("keep", SceneVideo(media_path="a.png"))
    state.video.set_scene("gone", SceneVideo(media_path="b.png"))
    assert state.prune_scenes(["keep"]) is True
    assert list(state.video.scenes) == ["keep"]
    assert state.prune_scenes(["keep"]) is False


def test_empty_scene_video_is_not_stored():
    video = VideoSettings()
    video.set_scene("s", SceneVideo())
    assert video.scenes == {}


# ---------------- timing ----------------

def test_timeline_uses_narration_length_and_pause():
    t = compute_timeline(
        [SceneTimingInput("a", 4.0, None, 1.0), SceneTimingInput("b", 2.0, None, 1.0)],
        transition="cut", transition_s=0.5, default_duration_s=5.0,
    )
    assert [s.slot_s for s in t.slots] == [5.0, 3.0]        # last scene: narration + 1.0 pause
    assert [s.start_s for s in t.slots] == [0.0, 5.0]
    assert t.total_s == 8.0 and t.transition_s == 0


def test_narration_is_never_truncated_by_a_short_configured_duration():
    t = compute_timeline([SceneTimingInput("a", 9.0, 3.0, 0.5), SceneTimingInput("b", 1.0, 20.0, 0.5)],
                         transition="cut", transition_s=0.5, default_duration_s=5.0)
    assert t.slots[0].slot_s == 9.5 and t.slots[0].extended is True
    assert t.slots[1].slot_s == 20.0 and t.slots[1].extended is False   # longer configured duration wins


def test_scenes_without_narration_use_configured_or_default_duration():
    t = compute_timeline([SceneTimingInput("a", None, 2.0), SceneTimingInput("b", None, None)],
                         transition="cut", transition_s=0.5, default_duration_s=6.0)
    assert [s.slot_s for s in t.slots] == [2.0, 6.0]


def test_crossfade_extends_segments_but_not_slots():
    inputs = [SceneTimingInput(x, 3.0, None, 1.0) for x in "abc"]
    t = compute_timeline(inputs, transition="crossfade", transition_s=0.5, default_duration_s=5.0)
    assert t.transition_s == 0.5
    assert [s.slot_s for s in t.slots] == [4.0, 4.0, 4.0]
    assert [s.segment_s for s in t.slots] == [4.5, 4.5, 4.0]
    assert [s.start_s for s in t.slots] == [0.0, 4.0, 8.0] and t.total_s == 12.0


def test_crossfade_is_limited_by_short_scenes_and_ignored_for_one_scene():
    short = compute_timeline([SceneTimingInput("a", None, 0.6), SceneTimingInput("b", None, 4.0)],
                             transition="crossfade", transition_s=2.0, default_duration_s=5.0)
    assert short.transition_s == pytest.approx(0.3)
    single = compute_timeline([SceneTimingInput("a", 2.0, None, 0.0)], transition="crossfade",
                              transition_s=1.0, default_duration_s=5.0)
    assert single.transition_s == 0 and single.slots[0].segment_s == single.slots[0].slot_s


def test_empty_timeline():
    t = compute_timeline([], transition="cut", transition_s=0.5, default_duration_s=5.0)
    assert t.slots == [] and t.total_s == 0


# ---------------- validation ----------------

class FakeScene:
    def __init__(self, id, title, text):
        self.id, self.title, self.text = id, title, text


def test_validation_reports_missing_media_music_voice_and_ffmpeg(tmp_path):
    scenes = [FakeScene("s1", "Intro", "hello"), FakeScene("s2", "Body", "world"), FakeScene("s3", "End", "bye")]
    studio = StudioState()
    studio.video.set_scene("s1", SceneVideo(media_path=str(tmp_path / "missing.png")))
    (tmp_path / "doc.txt").write_text("x")
    studio.video.set_scene("s2", SceneVideo(media_path=str(tmp_path / "doc.txt")))
    studio.audio.tracks.append(MusicTrack(path=str(tmp_path / "nope.mp3")))
    issues = validate_production(scenes, studio, ffmpeg_ready=False, voice_selected=False,
                                 render_video=True, export_audio=False)
    errors = [i.message for i in issues if i.severity == ERROR]
    assert any("FFmpeg" in m for m in errors)
    assert any("No voice" in m for m in errors)
    assert any("Music file is missing" in m for m in errors)
    assert any("Intro" in m and "missing" in m for m in errors)
    assert any("Body" in m and "unsupported" in m for m in errors)
    assert any(i.severity == WARNING and "End" in i.message for i in issues)  # no media -> black screen warning
    assert has_errors(issues)


def test_validation_passes_for_a_complete_project(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    scenes = [FakeScene("s1", "Only", "text")]
    studio = StudioState()
    studio.video.set_scene("s1", SceneVideo(media_path=str(img)))
    issues = validate_production(scenes, studio, ffmpeg_ready=True, voice_selected=True,
                                 render_video=True, export_audio=True)
    assert not has_errors(issues) and issues == []


def test_validation_requires_an_output_and_some_text():
    issues = validate_production([FakeScene("s", "Blank", "  ")], StudioState(), ffmpeg_ready=True,
                                 voice_selected=True, render_video=False, export_audio=False)
    messages = " ".join(i.message for i in issues)
    assert "No scene has any text" in messages and "at least one output" in messages


# ---------------- cache keys ----------------

def _spec(media, **kw):
    base = dict(kind="image", media=str(media), length_s=4.0, width=640, height=360, fps=30, motion="zoom_in", fit="fill")
    base.update(kw)
    return SegmentSpec(**base)


def test_segment_key_changes_only_with_visual_inputs(tmp_path):
    cache = VideoCache(tmp_path / "v")
    img = tmp_path / "a.png"
    img.write_bytes(b"one")
    base = cache.segment_key(_spec(img))
    assert base == cache.segment_key(_spec(img))
    for change in (dict(length_s=4.5), dict(width=1280), dict(fps=25), dict(motion="pan_left"), dict(fit="fit")):
        assert cache.segment_key(_spec(img, **change)) != base, change
    img.write_bytes(b"two-two")            # replaced/edited media -> new identity
    assert cache.segment_key(_spec(img)) != base


def test_segment_commit_and_prune(tmp_path):
    import os, time
    cache = VideoCache(tmp_path / "v")
    for i in range(3):
        part = cache.part_path(f"k{i}")
        part.write_bytes(b"x" * 1000)
        cache.commit_segment(part, f"k{i}")
        os.utime(cache.segment_path(f"k{i}"), (time.time() + i, time.time() + i))
    cache.prune(max_bytes=1500)
    assert [p.name for p in cache.segments_dir.glob("*.mp4")] == ["k2.mp4"]
    empty = cache.part_path("z")
    empty.write_bytes(b"")
    with pytest.raises(OSError):
        cache.commit_segment(empty, "z")


# ---------------- command builders (pure) ----------------

def test_concat_list_escapes_quotes_and_uses_forward_slashes(tmp_path):
    odd = tmp_path / "it's a ছবি.mp4"
    odd.write_bytes(b"x")
    text = build_concat_list([odd])
    assert "'\\''" in text and "\\" not in text.replace("'\\''", "")


def test_xfade_script_offsets_follow_scene_starts():
    script = build_xfade_script([0.0, 4.0, 8.0], 0.5)
    assert "offset=4.000" in script and "offset=8.000" in script and script.endswith("[vout]")
    assert build_xfade_script([0.0], 0.5) == "[0:v]format=yuv420p[vout]"


def test_segment_commands_never_use_shell_strings(tmp_path):
    exe = Path("ffmpeg")
    for spec in (_spec("a b.png"), _spec("c.mp4", kind="video"), _spec(None, kind="blank"), _spec("a.png", motion="none")):
        args = build_segment_args(exe, spec, tmp_path / "o.mp4")
        assert isinstance(args, list) and all(isinstance(a, str) for a in args)
    zoom = build_segment_args(exe, _spec("a.png", motion="zoom_in"), tmp_path / "o.mp4")
    assert any("zoompan" in a for a in zoom) and "-frames:v" in zoom


def test_mix_args_validate_inputs(tmp_path):
    audio = AudioSettings(tracks=[MusicTrack(path="m.mp3")])
    with pytest.raises(ProductionError):   # duration of the track unknown (could not be read)
        build_mix_args(Path("ffmpeg"), Path("n.wav"), 10.0, audio, {}, tmp_path / "o.wav", fmt="wav", sample_rate=44100)
    audio.tracks[0].offset_s = 20
    with pytest.raises(ProductionError):   # music starts after the narration ends
        build_mix_args(Path("ffmpeg"), Path("n.wav"), 10.0, audio, {audio.tracks[0].id: 30.0}, tmp_path / "o.wav",
                       fmt="wav", sample_rate=44100)
    with pytest.raises(ProductionError):
        build_mix_args(Path("ffmpeg"), Path("n.wav"), 10.0, AudioSettings(), {}, tmp_path / "o.xyz", fmt="xyz", sample_rate=44100)


def test_disabled_tracks_are_ignored_by_the_mixer(tmp_path):
    audio = AudioSettings(tracks=[MusicTrack(path="m.mp3", enabled=False)])
    args = build_mix_args(Path("ffmpeg"), Path("n.wav"), 10.0, audio, {}, tmp_path / "o.wav", fmt="wav", sample_rate=44100)
    assert args.count("-i") == 1


# ---------------- probe parsing ----------------

def test_probe_parser_for_video_image_audio_and_errors():
    video = parse_probe_output("Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'c.mp4':\n  Duration: 00:00:02.04, start: 0.0\n"
                               "  Stream #0:0[0x1](und): Video: h264 (High), yuv420p, 320x240 [SAR 1:1], 25 fps\n")
    assert video.kind == "video" and video.duration_s == pytest.approx(2.04) and (video.width, video.height) == (320, 240)
    image = parse_probe_output("Input #0, png_pipe, from 'a.png':\n  Duration: N/A, bitrate: N/A\n"
                               "  Stream #0:0: Video: png, rgb24(pc), 640x480, 25 fps\n")
    assert image.kind == "image" and image.duration_s is None
    audio = parse_probe_output("Input #0, mp3, from 'm.mp3':\n  Duration: 00:03:10.50, start: 0.025\n"
                               "  Stream #0:0: Audio: mp3, 44100 Hz, stereo\n"
                               "  Stream #0:1: Video: mjpeg, yuvj420p, 500x500 (attached pic)\n")
    assert audio.kind == "audio" and audio.duration_s == pytest.approx(190.5) and not audio.has_video
    with pytest.raises(MediaError):
        parse_probe_output("x.png: No such file or directory\n")
    with pytest.raises(MediaError):
        parse_probe_output("bad.bin: Invalid data found when processing input\n")


def test_xfade_join_uses_the_requested_filter_script_option(tmp_path):
    segs = [tmp_path / "a.mp4", tmp_path / "b.mp4"]
    for option in FILTER_SCRIPT_OPTIONS:
        args = build_xfade_join_args(Path("ffmpeg"), segs, tmp_path / "g.txt", 30, tmp_path / "o.mp4", option)
        assert option in args and args[args.index(option) + 1] == str(tmp_path / "g.txt")
        other = [o for o in FILTER_SCRIPT_OPTIONS if o != option][0]
        assert other not in args
    # newest spelling is tried first; the legacy one is only a fallback
    assert FILTER_SCRIPT_OPTIONS == ("-/filter_complex", "-filter_complex_script")


def test_unknown_option_errors_are_recognised_but_other_errors_are_not():
    assert is_unknown_option_error("FFmpeg failed (exit code 1): Error splitting the argument list: Option not found")
    assert is_unknown_option_error("Unrecognized option 'filter_complex_script'.")
    assert not is_unknown_option_error("FFmpeg failed (exit code 1): No space left on device")