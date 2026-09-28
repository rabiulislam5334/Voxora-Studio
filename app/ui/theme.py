from __future__ import annotations

from tkinter import ttk
from typing import Literal

Theme = Literal["dark", "light"]

DARK = {
    "bg": "#1e1f26",
    "bg_alt": "#262834",
    "sidebar_bg": "#181920",
    "fg": "#e8e8ec",
    "fg_muted": "#9a9ba6",
    "accent": "#6c8cff",
    "border": "#33343f",
}

LIGHT = {
    "bg": "#f5f6f8",
    "bg_alt": "#ffffff",
    "sidebar_bg": "#e9eaee",
    "fg": "#1c1d21",
    "fg_muted": "#5b5d68",
    "accent": "#3f5fdb",
    "border": "#d7d8de",
}

_PALETTES = {"dark": DARK, "light": LIGHT}


def get_palette(theme: Theme) -> dict:
    return _PALETTES.get(theme, DARK)


def apply_theme(style: ttk.Style, theme: Theme) -> dict:
    """Configure every ttk style used by the shell. Returns the palette so
    callers (main_window) can use raw colors for things ttk styles can't
    reach (e.g. root window background)."""
    palette = get_palette(theme)
    style.theme_use("clam")  # 'clam' honors background/border overrides reliably

    # Frames
    style.configure("App.TFrame", background=palette["bg"])
    style.configure("Sidebar.TFrame", background=palette["sidebar_bg"])
    style.configure("TopBar.TFrame", background=palette["bg_alt"])
    style.configure("StatusBar.TFrame", background=palette["bg_alt"])
    style.configure(
        "Card.TFrame",
        background=palette["bg_alt"],
        relief="flat",
        borderwidth=1,
    )

    # Labels — one style per background context so text never mismatches its frame
    style.configure("App.TLabel", background=palette["bg"], foreground=palette["fg"],
                     font=("Segoe UI", 10))
    style.configure("PageTitle.TLabel", background=palette["bg"], foreground=palette["fg"],
                     font=("Segoe UI", 16, "bold"))
    style.configure("Muted.TLabel", background=palette["bg"], foreground=palette["fg_muted"],
                     font=("Segoe UI", 9))
    style.configure("TopBarTitle.TLabel", background=palette["bg_alt"], foreground=palette["fg"],
                     font=("Segoe UI", 13, "bold"))
    style.configure("TopBarMuted.TLabel", background=palette["bg_alt"], foreground=palette["fg_muted"],
                     font=("Segoe UI", 9))
    style.configure("SidebarMuted.TLabel", background=palette["sidebar_bg"], foreground=palette["fg_muted"],
                     font=("Segoe UI", 9, "bold"))
    style.configure("Status.TLabel", background=palette["bg_alt"], foreground=palette["fg_muted"],
                     font=("Segoe UI", 9))

    # Buttons
    style.configure("Nav.TButton", background=palette["sidebar_bg"], foreground=palette["fg"],
                     borderwidth=0, anchor="w", padding=(14, 10), font=("Segoe UI", 10))
    style.map("Nav.TButton", background=[("active", palette["bg_alt"])])

    style.configure("NavActive.TButton", background=palette["accent"], foreground="#ffffff",
                     borderwidth=0, anchor="w", padding=(14, 10), font=("Segoe UI", 10, "bold"))
    style.map("NavActive.TButton", background=[("active", palette["accent"])])

    style.configure("Primary.TButton", background=palette["accent"], foreground="#ffffff",
                     padding=(12, 8), font=("Segoe UI", 10, "bold"))
    style.map("Primary.TButton", background=[("active", palette["accent"])])

    return palette














































































































    