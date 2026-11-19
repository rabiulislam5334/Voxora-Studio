import json

import pytest

from app.universal.visual_generation_settings import (
    LocalImageGenerationSettings,
    VisualGenerationSettingsError,
    load_local_image_generation_settings,
    save_local_image_generation_settings,
)


def test_missing_settings_returns_safe_defaults(tmp_path):
    settings = load_local_image_generation_settings(tmp_path / "missing.json")
    assert settings == LocalImageGenerationSettings()
    assert settings.threads == 4
    assert settings.steps == 20


def test_settings_round_trip_and_keep_only_local_runtime_fields(tmp_path):
    path = tmp_path / "userdata" / "visual_generation.json"
    expected = LocalImageGenerationSettings(
        executable_path=r"C:\tools\sd-cli.exe",
        model_path=r"D:\models\sd15.safetensors",
        threads=3,
        steps=18,
    )
    save_local_image_generation_settings(path, expected)
    assert load_local_image_generation_settings(path) == expected
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload) == {"version", "executable_path", "model_path", "threads", "steps"}


@pytest.mark.parametrize("kwargs", [
    {"threads": 0}, {"threads": 33}, {"threads": True},
    {"steps": 0}, {"steps": 101}, {"steps": False},
    {"executable_path": None}, {"model_path": 7},
])
def test_settings_reject_invalid_values(kwargs):
    with pytest.raises(VisualGenerationSettingsError):
        LocalImageGenerationSettings(**kwargs)


def test_settings_reject_unknown_version(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"version": 99}), encoding="utf-8")
    with pytest.raises(VisualGenerationSettingsError, match="Unsupported"):
        load_local_image_generation_settings(path)


def test_settings_reject_symlink(tmp_path):
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "settings.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not available on this platform")
    with pytest.raises(VisualGenerationSettingsError, match="symbolic link"):
        load_local_image_generation_settings(link)
