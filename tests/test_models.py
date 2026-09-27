from __future__ import annotations

from pathlib import Path

from app.models.audio import AudioInfo
from app.models.project import Project
from app.models.scene import Scene
from app.models.voice import Voice


def test_project_creation_defaults():
    project = Project()
    assert project.id
    assert project.name == "Untitled Project"
    assert project.scenes == []
    assert project.language == "en"


def test_project_add_scene_updates_timestamp():
    project = Project()
    original_updated = project.updated_at
    scene = Scene(title="Introduction", text="Hello world")
    project.add_scene(scene)
    assert project.scenes[0] is scene
    assert project.updated_at >= original_updated


def test_scene_creation_defaults():
    scene = Scene()
    assert scene.id
    assert scene.speed == 1.0
    assert scene.audio_path is None


def test_voice_creation():
    voice = Voice(id="bn-BD-NabanitaNeural", name="Nabanita", provider="edge", language="bn-BD")
    assert voice.gender is None
    assert voice.metadata == {}


def test_audio_info_creation():
    info = AudioInfo(path=Path("output/example.mp3"), format="mp3")
    assert info.duration_seconds is None
    assert info.sample_rate is None