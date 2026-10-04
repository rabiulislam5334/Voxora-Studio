from __future__ import annotations

import json
from pathlib import Path
from typing import List

from app.core.exceptions import ConfigurationError
from app.core.logger import get_logger
from app.models.voice_preset import BUILTIN_PRESETS, VoicePreset, validate_preset

logger = get_logger("tts.preset_store")


class PresetStore:
    """Loads/saves user-defined custom presets as a single flat JSON file.
    Built-in presets are code constants and are never written to this
    file; list_all() always returns built-ins first, then custom presets.
    No database -- this is simple enough that a JSON file is sufficient,
    per the Phase 4 instruction to avoid introducing one.
    """

    def __init__(self, presets_file: Path) -> None:
        self.presets_file = Path(presets_file)
        self._custom: List[VoicePreset] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._custom = self._read_from_disk()
        self._loaded = True

    def _read_from_disk(self) -> List[VoicePreset]:
        if not self.presets_file.exists():
            return []
        try:
            raw = self.presets_file.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read custom presets file (%s) -- starting empty: %s",
                            self.presets_file, exc)
            return []

        if not isinstance(data, list):
            logger.warning("Custom presets file has an unexpected format -- starting empty.")
            return []

        presets = []
        for entry in data:
            try:
                presets.append(VoicePreset.from_dict(entry, is_builtin=False))
            except Exception:
                logger.warning("Skipped an unreadable custom preset entry.")
        return presets

    def _write_to_disk(self) -> None:
        data = [p.to_dict() for p in self._custom]
        try:
            self.presets_file.parent.mkdir(parents=True, exist_ok=True)
            self.presets_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            raise ConfigurationError(f"Could not save custom presets: {exc}") from exc

    def list_builtin(self) -> List[VoicePreset]:
        return list(BUILTIN_PRESETS)

    def list_custom(self) -> List[VoicePreset]:
        self._ensure_loaded()
        return list(self._custom)

    def list_all(self) -> List[VoicePreset]:
        return self.list_builtin() + self.list_custom()

    def get(self, name: str) -> VoicePreset:
        for preset in self.list_all():
            if preset.name == name:
                return preset
        raise ConfigurationError(f"No preset named '{name}'.")

    def save_custom(self, preset: VoicePreset) -> None:
        """Validates, then inserts or overwrites (by name) a custom preset.
        Saving under a name that matches a built-in is rejected -- custom
        presets must not shadow/confuse the built-in list."""
        validate_preset(preset)
        if preset.name in {p.name for p in BUILTIN_PRESETS}:
            raise ConfigurationError(
                f"'{preset.name}' is a built-in preset name and cannot be overwritten. "
                "Please choose a different name for your custom preset."
            )

        self._ensure_loaded()
        preset = preset.copy_with(is_builtin=False)
        self._custom = [p for p in self._custom if p.name != preset.name]
        self._custom.append(preset)
        self._write_to_disk()
        logger.info("Saved custom preset '%s'", preset.name)

    def delete_custom(self, name: str) -> None:
        self._ensure_loaded()
        before = len(self._custom)
        self._custom = [p for p in self._custom if p.name != name]
        if len(self._custom) == before:
            raise ConfigurationError(f"No custom preset named '{name}' to delete.")
        self._write_to_disk()
        logger.info("Deleted custom preset '%s'", name)