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
    "error": "#ff6b6b",
    "success": "#4cd97b",
    "field_bg": "#12131a",
}

LIGHT = {
    "bg": "#f5f6f8",
    "bg_alt": "#ffffff",
    "sidebar_bg": "#e9eaee",
    "fg": "#1c1d21",
    "fg_muted": "#5b5d68",
    "accent": "#3f5fdb",
    "border": "#d7d8de",
    "error": "#c62828",
    "success": "#1e8e3e",
    "field_bg": "#ffffff",
}

_PALETTES = {"dark": DARK, "light": LIGHT}


def get_palette(theme: Theme) -> dict:
    return _PALETTES.get(theme, DARK)


def apply_theme(style: ttk.Style, theme: Theme) -> dict:
    """Configure every ttk style used by the shell. Returns the palette so
    callers can use raw colors for things ttk styles can't reach (root
    window background, plain tk.Text widgets, etc.)."""
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

    # Labels
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
    style.configure("Error.TLabel", background=palette["bg"], foreground=palette["error"],
                     font=("Segoe UI", 9, "bold"))
    style.configure("Success.TLabel", background=palette["bg"], foreground=palette["success"],
                     font=("Segoe UI", 9, "bold"))
    style.configure("SectionTitle.TLabel", background=palette["bg"], foreground=palette["fg"],
                     font=("Segoe UI", 11, "bold"))

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

    style.configure("Secondary.TButton", background=palette["bg_alt"], foreground=palette["fg"],
                     padding=(10, 6), font=("Segoe UI", 9))
    style.map("Secondary.TButton", background=[("active", palette["border"])])

    # Treeview (voice list)
    style.configure(
        "Voice.Treeview",
        background=palette["field_bg"],
        fieldbackground=palette["field_bg"],
        foreground=palette["fg"],
        borderwidth=0,
        rowheight=26,
        font=("Segoe UI", 9),
    )
    style.map("Voice.Treeview", background=[("selected", palette["accent"])],
              foreground=[("selected", "#ffffff")])
    style.configure(
        "Voice.Treeview.Heading",
        background=palette["bg_alt"],
        foreground=palette["fg_muted"],
        font=("Segoe UI", 9, "bold"),
        borderwidth=0,
    )

    # Combobox
    style.configure("App.TCombobox", fieldbackground=palette["field_bg"],
                     background=palette["field_bg"], foreground=palette["fg"])

    # Progressbar
    style.configure("App.Horizontal.TProgressbar", background=palette["accent"],
                     troughcolor=palette["bg_alt"], borderwidth=0)

    return palette