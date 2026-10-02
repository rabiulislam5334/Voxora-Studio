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

    # Labels -- typography hierarchy: app title > section heading > normal
    # content > secondary/muted label > status messages (distinct colors).
    style.configure("App.TLabel", background=palette["bg"], foreground=palette["fg"],
                     font=("Segoe UI", 10))
    style.configure("PageTitle.TLabel", background=palette["bg"], foreground=palette["fg"],
                     font=("Segoe UI", 17, "bold"))
    style.configure("Muted.TLabel", background=palette["bg"], foreground=palette["fg_muted"],
                     font=("Segoe UI", 9))
    style.configure("TopBarTitle.TLabel", background=palette["bg_alt"], foreground=palette["fg"],
                     font=("Segoe UI", 14, "bold"))
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
                     font=("Segoe UI", 12, "bold"))
    # Playback status: "Playing" gets the accent color so it's immediately
    # distinguishable at a glance; Paused/Stopped/Ready stay neutral --
    # deliberately just the one existing accent hue, not a new color.
    style.configure("PlaybackActive.TLabel", background=palette["bg"], foreground=palette["accent"],
                     font=("Segoe UI", 9, "bold"))

    # Buttons -- primary (Generate / Preview / Play) vs secondary
    # (Stop / Save As / Regenerate / Refresh) visual weight.
    style.configure("Nav.TButton", background=palette["sidebar_bg"], foreground=palette["fg"],
                     borderwidth=0, anchor="w", padding=(14, 10), font=("Segoe UI", 10))
    style.map("Nav.TButton", background=[("active", palette["bg_alt"])])

    style.configure("NavActive.TButton", background=palette["accent"], foreground="#ffffff",
                     borderwidth=0, anchor="w", padding=(14, 10), font=("Segoe UI", 10, "bold"))
    style.map("NavActive.TButton", background=[("active", palette["accent"])])

    style.configure("Primary.TButton", background=palette["accent"], foreground="#ffffff",
                     padding=(12, 8), font=("Segoe UI", 10, "bold"), borderwidth=0)
    style.map(
        "Primary.TButton",
        background=[("disabled", palette["border"]), ("active", palette["accent"])],
        foreground=[("disabled", palette["fg_muted"])],
    )

    style.configure("Secondary.TButton", background=palette["bg_alt"], foreground=palette["fg"],
                     padding=(10, 6), font=("Segoe UI", 9), borderwidth=1,
                     bordercolor=palette["border"])
    style.map(
        "Secondary.TButton",
        background=[("disabled", palette["bg_alt"]), ("active", palette["border"])],
        foreground=[("disabled", palette["fg_muted"])],
    )

    # Treeview (voice list)
        # Treeview (voice list, scene list -- same look, shared loop so the
    # styling logic lives in exactly one place).
    for prefix in ("Voice", "Scene"):
        style.configure(
            f"{prefix}.Treeview",
            background=palette["field_bg"],
            fieldbackground=palette["field_bg"],
            foreground=palette["fg"],
            borderwidth=1,
            bordercolor=palette["border"],
            relief="solid",
            rowheight=28,
            font=("Segoe UI", 9),
        )
        style.map(f"{prefix}.Treeview", background=[("selected", palette["accent"])],
                  foreground=[("selected", "#ffffff")])
        style.configure(
            f"{prefix}.Treeview.Heading",
            background=palette["bg_alt"],
            foreground=palette["fg_muted"],
            font=("Segoe UI", 9, "bold"),
            borderwidth=1,
            relief="flat",
        )
        style.map(f"{prefix}.Treeview.Heading", background=[("active", palette["bg_alt"])])



    # Combobox -- the readonly/disabled states in ttk's built-in "clam"
    # theme carry their OWN hardcoded field/foreground colors that silently
    # override a plain style.configure(); every one of our comboboxes is
    # state="readonly", so without these explicit style.map() overrides the
    # field renders in clam's stock light-gray-on-light-gray regardless of
    # the palette, which is exactly the low-contrast bug this fixes.
    style.configure(
        "App.TCombobox",
        fieldbackground=palette["field_bg"],
        background=palette["field_bg"],
        foreground=palette["fg"],
        arrowcolor=palette["fg"],
        bordercolor=palette["border"],
        lightcolor=palette["field_bg"],
        darkcolor=palette["field_bg"],
        padding=(8, 4),
    )
    style.map(
        "App.TCombobox",
        fieldbackground=[("readonly", palette["field_bg"]), ("disabled", palette["bg_alt"])],
        foreground=[("readonly", palette["fg"]), ("disabled", palette["fg_muted"])],
        background=[("readonly", palette["field_bg"]), ("disabled", palette["bg_alt"])],
        arrowcolor=[("disabled", palette["fg_muted"])],
        selectbackground=[("readonly", palette["field_bg"])],
        selectforeground=[("readonly", palette["fg"])],
    )

    # Progressbar
    style.configure("App.Horizontal.TProgressbar", background=palette["accent"],
                     troughcolor=palette["bg_alt"], borderwidth=0, thickness=8)

    # Scale (seek bar, volume) -- trough uses field_bg (the darkest/most
    # distinct surface in the palette) so the seek bar visibly stands out
    # from the page background behind it, per the "timeline should be
    # visually distinguishable" requirement.
    style.configure("Horizontal.TScale", background=palette["bg"], troughcolor=palette["field_bg"])

    return palette


def style_combobox_dropdown(combobox: ttk.Combobox, palette: dict) -> None:
    """Color the Combobox's popup listbox.

    This is the OTHER half of the dropdown-visibility fix: the popup list
    shown when a Combobox is clicked is an internal plain Tk Listbox
    (ttk::combobox::PopdownWindow), not a ttk-styled widget -- style.map()
    above only reaches the field itself, never this popup. It has to be
    colored directly, and must be re-applied whenever the palette changes
    since an already-created popup keeps whatever colors it was last given.
    Defensive: if a future Tk version changes this internal widget path,
    this silently no-ops instead of crashing the app.
    """
    try:
        popdown = combobox.tk.eval(f"ttk::combobox::PopdownWindow {combobox}")
        listbox = f"{popdown}.f.l"
        combobox.tk.call(
            listbox, "configure",
            "-background", palette["field_bg"],
            "-foreground", palette["fg"],
            "-selectbackground", palette["accent"],
            "-selectforeground", "#ffffff",
            "-borderwidth", 0,
            "-highlightthickness", 1,
            "-highlightbackground", palette["border"],
            "-highlightcolor", palette["accent"],
            "-font", "{Segoe UI} 9",
        )
    except Exception:
        pass  # cosmetic only -- never let popup styling break the app