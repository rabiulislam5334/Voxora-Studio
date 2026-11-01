"""Real-FFmpeg integration tests with tiny synthetic media (360p draft quality)."""
from __future__ import annotations

import asyncio
import re
import subprocess
import threading
from pathlib import Path

import pytest

from app.audio.mixer import build_mix_args
from app.cache.manager import NarrationCache
from app.cache.video_cache import VideoCache
from app.core.exceptions import FFmpegError, GenerationCancelled, MediaError, ProductionError
from app.studio.models import MusicTrack, SceneVideo, StudioState
from app.studio.previews import make_thumbnail, make_waveform, render_mix_preview
from app.workers.cancel import CancelToken
from app.workers.narration import NarrationJob
from app.workers.production import ProductionJob, ProductionOptions, SceneInfo
from tests.helpers import FakeTTS, make_request


def ff(real_ffmpeg, *args):
    exe = str(real_ffmpeg.require())
    proc = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc


def describe(real_ffmpeg, path):
    info = real_ffmpeg.probe(Path(path))
    text = subprocess.run([str(real_ffmpeg.require()), "-hide_banner", "-i", str(path)],
                          capture_output=True, text=True).stderr
    return info, text


@pytest.fixture(scope="module")
def media(real_ffmpeg, tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    ff(real_ffmpeg, "-f", "lavfi", "-i", "testsrc=s=800x600", "-frames:v", "1", str(d / "a.png"))
    ff(real_ffmpeg, "-f", "lavfi", "-i", "color=c=red:s=300x500", "-frames:v", "1", str(d / "b.jpg"))
    ff(real_ffmpeg, "-f", "lavfi", "-i", "testsrc=s=320x240:r=25:d=1", "-pix_fmt", "yuv420p", str(d / "clip.mp4"))
    ff(real_ffmpeg, "-f", "lavfi", "-i", "sine=frequency=500:duration=2", "-ac", "2", str(d / "music.mp3"))
    ff(real_ffmpeg, "-f", "lavfi", "-i", "sine=frequency=300:duration=1", "-af", "volume=3", str(d / "loud.wav"))
    return d


@pytest.fixture
def env(tmp_path, real_ffmpeg, tone_mp3):
    def build(tts=None):
        tts = tts or FakeTTS(tone_mp3)
        ncache = NarrationCache(tmp_path / "chunks", tmp_path / "scenes")
        njob = NarrationJob(tts, real_ffmpeg, ncache, tmp_path / "temp", retry_base_delay=0.0)
        vcache = VideoCache(tmp_path / "video")
        return tts, ProductionJob(njob, real_ffmpeg, vcache, tmp_path / "temp"), vcache
    return build


SCENES = [SceneInfo("s1", "Intro", "One. Two."), SceneInfo("s2", "Middle", "Three."), SceneInfo("s3", "Quiet", "")]


def requests():
    # chunks are 0.5 s each from the fake provider; 300 ms scene pause, no sentence/paragraph pause
    return [make_request("One. Two.", 1, scene_id="s1", title="Intro", sentence_pause_ms=0, scene_pause_ms=300),
            make_request("Three.", 2, scene_id="s2", title="Middle", sentence_pause_ms=0, scene_pause_ms=300)]


def studio_with(media, transition="cut", aspect="16:9", music=False):
    st = StudioState()
    st.video.resolution = "360p (draft)"
    st.video.aspect = aspect
    st.video.fps = 15
    st.video.transition = transition
    st.video.default_duration_s = 1.0
    st.video.set_scene("s1", SceneVideo(media_path=str(media / "a.png"), motion="zoom_in"))
    st.video.set_scene("s2", SceneVideo(media_path=str(media / "clip.mp4")))
    if music:
        st.audio.tracks.append(MusicTrack(path=str(media / "music.mp3"), volume_percent=30))
    return st


def run(job, st, opts, cancel=None, events=None, name="proj", reqs=None, scenes=None):
    return asyncio.run(job.run(reqs or requests(), scenes or SCENES, st, opts, basename=name, cancel=cancel,
                               on_progress=events.append if events is not None else None))


def test_probe_real_files(real_ffmpeg, media):
    assert real_ffmpeg.probe(media / "a.png").kind == "image"
    clip = real_ffmpeg.probe(media / "clip.mp4")
    assert clip.kind == "video" and clip.duration_s == pytest.approx(1.0, abs=0.1) and (clip.width, clip.height) == (320, 240)
    assert real_ffmpeg.probe(media / "music.mp3").kind == "audio"
    with pytest.raises(MediaError):
        real_ffmpeg.probe(media / "nope.png")
    (media / "junk.png").write_bytes(b"not an image at all")
    with pytest.raises(MediaError):
        real_ffmpeg.probe(media / "junk.png")


def test_thumbnail_and_waveform_are_cached_pngs(real_ffmpeg, media, tmp_path):
    cache = VideoCache(tmp_path / "v")
    thumb = make_thumbnail(real_ffmpeg, cache, media / "a.png")
    assert thumb.read_bytes()[:4] == b"\x89PNG" and make_thumbnail(real_ffmpeg, cache, media / "a.png") == thumb
    wave = make_waveform(real_ffmpeg, cache, media / "music.mp3", 400, 80)
    assert wave.read_bytes()[:4] == b"\x89PNG"


def test_mix_never_clips_and_matches_narration_length(real_ffmpeg, media, tmp_path):
    st = StudioState()
    st.audio.narration_volume_percent = 200
    st.audio.tracks.append(MusicTrack(path=str(media / "loud.wav"), volume_percent=200, loop=True))
    out = tmp_path / "mix.wav"
    args = build_mix_args(real_ffmpeg.require(), media / "loud.wav", 3.0, st.audio,
                          {st.audio.tracks[0].id: 1.0}, out, fmt="wav", sample_rate=44100)
    real_ffmpeg.run_args(args)
    info = real_ffmpeg.probe(out)
    assert info.duration_s == pytest.approx(3.0, abs=0.1)
    stats = subprocess.run([str(real_ffmpeg.require()), "-i", str(out), "-af", "volumedetect", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
    peak = float(re.search(r"max_volume: (-?[\d.]+) dB", stats).group(1))
    assert peak <= -0.2, f"clipped: {peak} dB"          # limiter keeps the sum below full scale


def test_mix_preview_is_short_and_matches_final_graph(real_ffmpeg, media, tmp_path):
    st = StudioState()
    st.audio.tracks.append(MusicTrack(path=str(media / "music.mp3")))
    out = render_mix_preview(real_ffmpeg, media / "loud.wav", 1.0, st.audio, tmp_path / "p.wav", seconds=0.5)
    assert real_ffmpeg.probe(out).duration_s == pytest.approx(0.5, abs=0.1)


def test_audio_only_export_mp3_and_wav_with_music(env, media, tmp_path):
    tts, job, _ = env()
    st = studio_with(media, music=True)
    mp3 = tmp_path / "out" / "ফাইনাল audio.mp3"
    result = run(job, st, ProductionOptions(render_video=False, export_audio=True, audio_output=mp3, audio_format="mp3"))
    assert mp3.exists() and result.video_path is None and result.audio_path == mp3
    # scene 1 = one 0.5 s chunk, 0.3 s scene pause, scene 2 = 0.5 s -> 1.3 s (no pause after the last scene)
    assert result.duration_s == pytest.approx(0.5 + 0.3 + 0.5, abs=0.15)
    wav = tmp_path / "out" / "final.wav"
    run(job, st, ProductionOptions(render_video=False, export_audio=True, audio_output=wav, audio_format="wav"))
    assert wav.exists() and not list((tmp_path / "out").glob("*.part"))


def test_full_video_with_cuts_has_h264_aac_and_exact_duration(env, media, tmp_path):
    tts, job, _ = env()
    st = studio_with(media)
    out = tmp_path / "video" / "final.mp4"
    events = []
    result = run(job, st, ProductionOptions(render_video=True, video_output=out), events=events)
    info, text = describe(job._ffmpeg, out)
    assert out.exists() and not list(out.parent.glob("*.part"))
    assert "Video: h264" in text and "Audio: aac" in text and "640x360" in text and "48000 Hz" in text
    assert info.duration_s == pytest.approx(result.duration_s, abs=0.25)
    # slots: scene1 = .5 narration + .3 pause ; scene2 = .5 + .3 pause ; scene3 (no text) = default 1.0
    assert [round(s.slot_s, 2) for s in result.timeline.slots] == [0.8, 0.8, 1.0]
    assert result.segments_rendered == 3 and result.segments_cached == 0
    assert events[-1].fraction == 1.0 and {e.stage for e in events} >= {"Narration", "Video scenes", "Final video"}
    fractions = [e.fraction for e in events]
    assert fractions == sorted(fractions)


def test_crossfade_and_vertical_video(env, media, tmp_path):
    tts, job, _ = env()
    st = studio_with(media, transition="crossfade", aspect="9:16")
    out = tmp_path / "short.mp4"
    result = run(job, st, ProductionOptions(render_video=True, video_output=out))
    info, text = describe(job._ffmpeg, out)
    assert "360x640" in text
    assert result.timeline.transition_s > 0
    assert info.duration_s == pytest.approx(result.duration_s, abs=0.25)


def test_music_change_reuses_narration_and_video_but_media_change_rerenders_one_scene(env, media, tmp_path):
    tts, job, vcache = env()
    st = studio_with(media)
    run(job, st, ProductionOptions(render_video=True, video_output=tmp_path / "a.mp4"), name="a")
    calls = len(tts.calls)

    st.audio.tracks.append(MusicTrack(path=str(media / "music.mp3"), volume_percent=40))   # audio-only change
    second = run(job, st, ProductionOptions(render_video=True, video_output=tmp_path / "b.mp4"), name="b")
    assert len(tts.calls) == calls                                   # narration reused
    assert second.segments_rendered == 0 and second.segments_cached == 3   # video reused

    st.video.set_scene("s1", SceneVideo(media_path=str(media / "a.png"), motion="pan_right"))  # one scene's motion
    third = run(job, st, ProductionOptions(render_video=True, video_output=tmp_path / "c.mp4"), name="c")
    assert (third.segments_rendered, third.segments_cached) == (1, 2)

    (media / "b2.jpg").write_bytes((media / "b.jpg").read_bytes())
    st.video.set_scene("s1", SceneVideo(media_path=str(media / "b2.jpg"), motion="pan_right"))
    run(job, st, ProductionOptions(render_video=True, video_output=tmp_path / "d.mp4"), name="d")
    (media / "b2.jpg").write_bytes(b"")  # now broken -> must not silently reuse stale cache
    with pytest.raises(ProductionError):
        run(job, st, ProductionOptions(render_video=True, video_output=tmp_path / "e.mp4"), name="e")
    assert not (tmp_path / "e.mp4").exists()


def test_narration_longer_than_configured_duration_extends_scene(env, media, tmp_path):
    tts, job, _ = env()
    st = studio_with(media)
    st.video.set_scene("s1", SceneVideo(media_path=str(media / "a.png"), duration_s=0.4))
    result = run(job, st, ProductionOptions(render_video=True, video_output=tmp_path / "x.mp4"))
    assert result.timeline.slots[0].slot_s >= 0.8 and result.timeline.slots[0].extended
    assert any("extended" in w for w in result.warnings)


def test_cancel_leaves_no_output_parts_or_temp_files(env, media, tmp_path, tone_mp3):
    tts, job, vcache = env(FakeTTS(tone_mp3, delay=0.3))
    st = studio_with(media)
    out = tmp_path / "cancelled.mp4"
    token = CancelToken()
    threading.Timer(0.4, token.cancel).start()
    with pytest.raises(GenerationCancelled):
        run(job, st, ProductionOptions(render_video=True, video_output=out), cancel=token)
    assert not out.exists() and not list(tmp_path.rglob("*.part")) or all(p.parent != tmp_path for p in tmp_path.glob("*.part"))
    assert not list((tmp_path / "temp").glob("production_*"))
    assert not list(vcache.segments_dir.glob("*.part"))


def test_cancel_during_video_render_cleans_up(env, media, tmp_path):
    tts, job, vcache = env()
    st = studio_with(media)
    out = tmp_path / "cancel2.mp4"
    token = CancelToken()
    events = []

    def watcher(ev):
        events.append(ev)
        if ev.stage == "Video scenes":
            token.cancel()

    with pytest.raises(GenerationCancelled):
        asyncio.run(job.run(requests(), SCENES, st, ProductionOptions(render_video=True, video_output=out),
                            basename="c", cancel=token, on_progress=watcher))
    assert not out.exists() and not out.with_name(out.name + ".part").exists()
    assert not list((tmp_path / "temp").glob("production_*"))
    assert not list(vcache.segments_dir.glob("*.part"))


def test_missing_media_and_bad_options_raise_clear_errors(env, media, tmp_path):
    tts, job, _ = env()
    st = studio_with(media)
    st.video.set_scene("s1", SceneVideo(media_path=str(media / "deleted.png")))
    with pytest.raises(ProductionError, match="Intro"):
        run(job, st, ProductionOptions(render_video=True, video_output=tmp_path / "m.mp4"))
    with pytest.raises(ProductionError, match="at least one output"):
        run(job, st, ProductionOptions(render_video=False, export_audio=False))
    with pytest.raises(ProductionError, match="MP4 output"):
        run(job, st, ProductionOptions(render_video=True, video_output=None))
    st.video.set_scene("s1", SceneVideo(media_path=str(media / "music.mp3")))   # audio file used as scene media
    with pytest.raises(ProductionError, match="not an image or video"):
        run(job, st, ProductionOptions(render_video=True, video_output=tmp_path / "n.mp4"))


def test_unreadable_music_file_is_reported(env, media, tmp_path):
    tts, job, _ = env()
    st = studio_with(media)
    bad = media / "bad.mp3"
    bad.write_bytes(b"not audio")
    st.audio.tracks.append(MusicTrack(path=str(bad)))
    with pytest.raises(ProductionError, match="bad.mp3"):
        run(job, st, ProductionOptions(render_video=False, export_audio=True, audio_output=tmp_path / "o.mp3"))
    assert not (tmp_path / "o.mp3").exists()


# ---------------------------------------------------------------------------
# Crossfade must work on FFmpeg that spells the filter-script option either way
# (new: -/filter_complex, removed in later releases: -filter_complex_script).
# The real FFmpeg here may support only one of them, so each test emulates a
# policy: calls using an option the emulated FFmpeg "does not know" fail with
# FFmpeg's real error text; accepted calls run on the real FFmpeg using
# whichever spelling it really supports.
# ---------------------------------------------------------------------------

def _real_option(real_ffmpeg, tmp_path):
    graph = tmp_path / "probe_graph.txt"
    graph.write_text("[0:v]format=yuv420p[vout]")
    exe = str(real_ffmpeg.require())
    for option in ("-/filter_complex", "-filter_complex_script"):
        proc = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                               "color=c=black:s=64x64:d=0.2", option, str(graph), "-map", "[vout]",
                               "-f", "null", "-"], capture_output=True)
        if proc.returncode == 0:
            return option
    pytest.skip("This FFmpeg supports neither filter-script option.")


def _emulate(monkeypatch, job, real_ffmpeg, tmp_path, accepted, attempts, fail_other=None):
    real_run = job._ffmpeg.run_with_progress
    real_option = _real_option(real_ffmpeg, tmp_path)

    def fake(args, total, on_progress=None, cancel=None, timeout=0):
        used = [o for o in ("-/filter_complex", "-filter_complex_script") if o in args]
        if not used:
            return real_run(args, total, on_progress, cancel)
        attempts.append(used[0])
        if fail_other:
            raise FFmpegError(fail_other)
        if used[0] not in accepted:
            raise FFmpegError("FFmpeg failed (exit code 1): Error splitting the argument list: Option not found")
        fixed = [real_option if a == used[0] else a for a in args]
        return real_run(fixed, total, on_progress, cancel)

    # monkeypatch undoes this after the test (the FFmpeg object is shared by the whole session)
    monkeypatch.setattr(job._ffmpeg, "run_with_progress", fake)


def test_crossfade_on_new_ffmpeg_uses_the_new_option_first(env, media, tmp_path, real_ffmpeg, monkeypatch):
    tts, job, _ = env()
    attempts = []
    _emulate(monkeypatch, job, real_ffmpeg, tmp_path, {"-/filter_complex"}, attempts)
    out = tmp_path / "new.mp4"
    result = run(job, studio_with(media, transition="crossfade"), ProductionOptions(render_video=True, video_output=out))
    assert out.exists() and result.timeline.transition_s > 0
    assert attempts == ["-/filter_complex"]


def test_crossfade_on_old_ffmpeg_falls_back_and_remembers(env, media, tmp_path, real_ffmpeg, monkeypatch):
    tts, job, _ = env()
    attempts = []
    _emulate(monkeypatch, job, real_ffmpeg, tmp_path, {"-filter_complex_script"}, attempts)
    st = studio_with(media, transition="crossfade")
    run(job, st, ProductionOptions(render_video=True, video_output=tmp_path / "old1.mp4"), name="a")
    assert attempts == ["-/filter_complex", "-filter_complex_script"]        # tried new, then legacy
    st.video.set_scene("s1", SceneVideo(media_path=str(media / "b.jpg"), motion="pan_left"))  # force a new join
    attempts.clear()
    run(job, st, ProductionOptions(render_video=True, video_output=tmp_path / "old2.mp4"), name="b")
    assert attempts == ["-filter_complex_script"]                            # learned: no wasted first try
    assert (tmp_path / "old1.mp4").exists() and (tmp_path / "old2.mp4").exists()


def test_crossfade_reports_clearly_when_no_option_is_supported(env, media, tmp_path, real_ffmpeg, monkeypatch):
    tts, job, _ = env()
    attempts = []
    _emulate(monkeypatch, job, real_ffmpeg, tmp_path, set(), attempts)
    out = tmp_path / "none.mp4"
    with pytest.raises(ProductionError, match="crossfade"):
        run(job, studio_with(media, transition="crossfade"), ProductionOptions(render_video=True, video_output=out))
    assert attempts == ["-/filter_complex", "-filter_complex_script"] and not out.exists()


def test_unrelated_ffmpeg_errors_are_not_mistaken_for_an_option_problem(env, media, tmp_path, real_ffmpeg, monkeypatch):
    tts, job, _ = env()
    attempts = []
    _emulate(monkeypatch, job, real_ffmpeg, tmp_path, {"-/filter_complex"}, attempts, fail_other="FFmpeg failed: No space left on device")
    with pytest.raises(FFmpegError, match="No space"):
        run(job, studio_with(media, transition="crossfade"), ProductionOptions(render_video=True, video_output=tmp_path / "x.mp4"))
    assert attempts == ["-/filter_complex"]                                  # no pointless retry