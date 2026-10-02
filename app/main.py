from __future__ import annotations

import sys
import tkinter as tk
from tkinter import messagebox

from app.core.config import get_config
from app.core.constants import APP_NAME
from app.core.logger import get_logger, setup_logging
from app.ui.main_window import MainWindow


def main() -> int:
    setup_logging()
    logger = get_logger("main")

    try:
        config = get_config()
        config.ensure_directories()
        logger.info("Configuration loaded. Root directory: %s", config.root_dir)
    except Exception:
        logger.exception("Failed to load configuration")
        _show_startup_error(
            "Configuration Error",
            "The application could not load its configuration.\n"
            "Check logs/app.log for details.",
        )
        return 1

    try:
        root = tk.Tk()
        MainWindow(root)
        root.mainloop()
        return 0
    except Exception:
        logger.exception("Unhandled error during application startup")
        _show_startup_error(
            "Startup Error",
            f"{APP_NAME} failed to start.\n"
            "Check logs/app.log for details.",
        )
        return 1


def _show_startup_error(title: str, message: str) -> None:
    try:
        error_root = tk.Tk()
        error_root.withdraw()
        messagebox.showerror(title, message)
        error_root.destroy()
    except Exception:
        print(f"{title}: {message}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())