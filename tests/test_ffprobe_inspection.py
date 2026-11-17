from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from app.audio.probe import parse_ffprobe_json
from app.core.exceptions import MediaError


@pytest.fixture
def media(real_ffmpeg, tmp_path):
    clip = tmp_path / "clip.mp4"
    music = tmp_path / "music.mp3"
    subprocess.run(
        [str(real_ffmpeg.require()), "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=s=320x240:r=25:d=1", "-pix_fmt", "yuv420p", str(clip)],
        check=True, capture_output=True,
    )
    subprocess.run(
        [str(real_ffmpeg.require()), "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=500:duration=2", "-ac", "2", str(music)],
        check=True, capture_output=True,
    )
    return tmp_path


def test_parse_ffprobe_json_preserves_container_and_stream_timing_fields():
    payload = {
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "start_time": "0.000000", "duration": "1.000000"},
        "streams": [
            {
                "index": 0, "codec_type": "video", "codec_name": "h264",
                "start_time": "0.000000", "duration": "1.000000",
                "time_base": "1/12800", "avg_frame_rate": "25/1", "r_frame_rate": "25/1",
                "width": 320, "height": 240, "nb_read_frames": "25",
            },
            {
                "index": 1, "codec_type": "audio", "codec_name": "aac",
                "start_time": "0.021333", "duration": "0.978667",
                "time_base": "1/48000", "sample_rate": "48000", "channels": 2,
            },
        ],
    }

    info = parse_ffprobe_json(json.dumps(payload))

    assert info.format_name == "mov,mp4,m4a,3gp,3g2,mj2"
    assert info.format_duration_s == pytest.approx(1.0)
    assert info.format_start_time_s == pytest.approx(0.0)
    assert len(info.streams) == 2
    video, audio = info.streams
    assert (video.codec_type, video.codec_name) == ("video", "h264")
    assert (video.width, video.height) == (320, 240)
    assert video.decoded_frame_count == 25
    assert video.time_base == "1/12800"
    assert video.avg_frame_rate == "25/1" and video.real_frame_rate == "25/1"
    assert audio.start_time_s == pytest.approx(0.021333)
    assert audio.duration_s == pytest.approx(0.978667)
    assert (audio.sample_rate, audio.channels) == (48000, 2)


def test_parse_ffprobe_json_keeps_missing_or_unavailable_values_as_none():
    info = parse_ffprobe_json(
        '{"streams":[{"index":"N/A","codec_type":"audio","duration":"N/A",'
        '"start_time":null,"sample_rate":"N/A","channels":2,"nb_read_frames":"N/A"}]}'
    )

    stream = info.streams[0]
    assert stream.index is None
    assert stream.duration_s is None
    assert stream.start_time_s is None
    assert stream.sample_rate is None
    assert stream.channels == 2
    assert stream.decoded_frame_count is None
    assert info.format_duration_s is None


@pytest.mark.parametrize("payload", ["", "not-json", "[]", '{"streams":{}}', '{"streams":[null]}', '{"format":[]}'])
def test_parse_ffprobe_json_rejects_malformed_documents(payload):
    with pytest.raises(MediaError):
        parse_ffprobe_json(payload)


def test_real_ffprobe_inspection_exposes_stream_metadata(real_ffmpeg, media):
    info = real_ffmpeg.probe_structured(media / "clip.mp4")

    assert info.format_duration_s == pytest.approx(1.0, abs=0.1)
    video = next(stream for stream in info.streams if stream.codec_type == "video")
    assert video.codec_name == "h264"
    assert (video.width, video.height) == (320, 240)
    assert video.time_base
    assert video.avg_frame_rate


def test_real_ffprobe_can_count_decoded_video_frames(real_ffmpeg, media):
    info = real_ffmpeg.probe_structured(media / "clip.mp4", count_frames=True)

    video = next(stream for stream in info.streams if stream.codec_type == "video")
    assert video.decoded_frame_count == 25


def test_real_ffprobe_inspection_exposes_audio_metadata(real_ffmpeg, media):
    info = real_ffmpeg.probe_structured(media / "music.mp3")

    audio = next(stream for stream in info.streams if stream.codec_type == "audio")
    assert audio.codec_name == "mp3"
    assert audio.sample_rate
    assert audio.channels


def test_structured_probe_reports_clear_error_when_ffprobe_is_missing(real_ffmpeg, media, monkeypatch):
    def missing():
        raise MediaError("FFprobe is required for structured media inspection but was not found.")

    monkeypatch.setattr(real_ffmpeg, "_find_ffprobe", missing)
    with pytest.raises(MediaError, match="FFprobe is required"):
        real_ffmpeg.probe_structured(media / "clip.mp4")


def test_structured_probe_rejects_missing_media_before_ffprobe_lookup(real_ffmpeg, tmp_path, monkeypatch):
    def should_not_run():
        pytest.fail("FFprobe lookup should not run for a missing input file")

    monkeypatch.setattr(real_ffmpeg, "_find_ffprobe", should_not_run)
    with pytest.raises(MediaError, match="File not found"):
        real_ffmpeg.probe_structured(tmp_path / "missing.mp4")
