from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict

from app.core.logger import get_logger

logger = get_logger("core.settings")


class SettingsStore:
    """Tiny JSON key/value store for machine-local app settings (currently
    just the FFmpeg path). A missing or corrupt file is treated as empty --
    settings are conveniences, never worth crashing the app over. Writes are
    atomic (temp file in the same folder, then replace)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> Dict[str, Any]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except OSError as exc:
            logger.warning("Could not read settings file %s: %s", self.path, exc)
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Settings file %s is corrupt; ignoring it.", self.path)
            return {}
        return data if isinstance(data, dict) else {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.load().get(key, default)

    def set(self, key: str, value: Any) -> None:
        data = self.load()
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), prefix=".voxora_settings_", suffix=".tmp")
        tmp_path = Path(tmp_name)
        try:
            with open(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            tmp_path.replace(self.path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise