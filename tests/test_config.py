from __future__ import annotations

from pathlib import Path

from app.core.config import AppConfig


def test_directories_are_path_objects(tmp_path):
    config = AppConfig(root_dir=tmp_path)
    assert isinstance(config.projects_dir, Path)
    assert isinstance(config.output_dir, Path)
    assert isinstance(config.cache_dir, Path)
    assert isinstance(config.temp_dir, Path)
    assert isinstance(config.logs_dir, Path)


def test_ensure_directories_creates_them(tmp_path):
    config = AppConfig(root_dir=tmp_path)
    config.ensure_directories()
    for directory in config.required_directories():
        assert directory.exists()
        assert directory.is_dir()


def test_defaults_are_valid(tmp_path):
    config = AppConfig(root_dir=tmp_path)
    assert config.default_language == "en"
    assert config.default_theme in ("dark", "light")
    assert config.app_name
    assert config.app_version