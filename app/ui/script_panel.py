from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from app.core.config import AppConfig
from app.core.constants import APP_NAME
from app.core.exceptions import ProjectError
from app.core.logger import get_logger
from app.models.project import Project
from app.models.scene import Scene
from app.projects.manager import PROJECT_EXTENSION, ProjectManager
from app.text.importer import import_txt_file, split_into_scenes
from app.text.wordcount import count_characters, count_words, estimate_duration_seconds, format_duration

logger = get_logger("ui.script_panel")


class ScriptPanel(ttk.Frame):
    """Script Editor & Scene Management (Phase 3).

    Owns a ProjectManager (its own Project model + file I/O); the editor
    widgets are a *view* onto whichever scene is currently selected. The
    model is treated as the continuous source of truth: every keystroke
    flushes into the selected Scene object immediately (see
    _flush_editor_to_scene), so there is no separate "did we remember to
    save before switching" bookkeeping anywhere else in this file -- the
    model simply never goes stale relative to the widgets.
    """

    def __init__(
        self,
        master: tk.Widget,
        config: AppConfig,
        palette: dict,
        on_status: Optional[callable] = None,
    ) -> None:
        super().__init__(master, style="App.TFrame")
        self._config = config
        self._palette = palette
        self._on_status = on_status or (lambda text: None)

        self._project_manager = ProjectManager()
        self._selected_scene_id: Optional[str] = None

        self._build_layout()
        self._bind_shortcuts()
        self._rebuild_tree_rows()
        self._refresh_status_bar()
        self._refresh_scene_buttons_state()

    @property
    def _project(self) -> Project:
        return self._project_manager.current_project

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        ttk.Label(self, text="Script", style="PageTitle.TLabel").grid(
            row=0, column=0, sticky="w", padx=24, pady=(24, 4)
        )

        self._build_toolbar()
        self._build_body()
        self._build_status_bar()

    def _build_toolbar(self) -> None:
        toolbar = ttk.Frame(self, style="App.TFrame")
        toolbar.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 12))

        buttons = [
            ("New Project", self._on_new_project),
            ("Open Project", self._on_open_project),
            ("Save", self._on_save_project),
            ("Save As...", self._on_save_as_project),
        ]
        for text, command in buttons:
            ttk.Button(toolbar, text=text, style="Secondary.TButton", command=command).pack(
                side="left", padx=(0, 8)
            )

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)

        ttk.Button(
            toolbar, text="Add Scene", style="Secondary.TButton", command=self._on_add_scene
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            toolbar, text="Import Script...", style="Secondary.TButton", command=self._on_import_script
        ).pack(side="left")

    def _build_body(self) -> None:
        body = ttk.Frame(self, style="App.TFrame")
        body.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 8))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        self._build_scene_library(body)
        self._build_editor(body)

    def _build_scene_library(self, parent: ttk.Frame) -> None:
        library = ttk.Frame(parent, style="App.TFrame")
        library.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        library.rowconfigure(1, weight=1)
        library.columnconfigure(0, weight=1)

        ttk.Label(library, text="Scenes", style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )

        tree_frame = ttk.Frame(library, style="App.TFrame")
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        columns = ("num", "title", "words", "duration")
        self._tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", style="Scene.Treeview", selectmode="browse"
        )
        self._tree.heading("num", text="#")
        self._tree.heading("title", text="Title")
        self._tree.heading("words", text="Words")
        self._tree.heading("duration", text="Est. Duration")
        self._tree.column("num", width=32, anchor="center")
        self._tree.column("title", width=160)
        self._tree.column("words", width=60, anchor="center")
        self._tree.column("duration", width=90, anchor="center")
        self._tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        self._tree.bind("<<TreeviewSelect>>", self._on_scene_select)

        scene_buttons = ttk.Frame(library, style="App.TFrame")
        scene_buttons.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        self._rename_btn = ttk.Button(
            scene_buttons, text="Rename", style="Secondary.TButton", command=self._on_rename_scene
        )
        self._duplicate_btn = ttk.Button(
            scene_buttons, text="Duplicate", style="Secondary.TButton", command=self._on_duplicate_scene
        )
        self._delete_btn = ttk.Button(
            scene_buttons, text="Delete", style="Secondary.TButton", command=self._on_delete_scene
        )
        self._move_up_btn = ttk.Button(
            scene_buttons, text="\u2191", style="Secondary.TButton", width=3, command=self._on_move_up
        )
        self._move_down_btn = ttk.Button(
            scene_buttons, text="\u2193", style="Secondary.TButton", width=3, command=self._on_move_down
        )
        for btn in (self._rename_btn, self._duplicate_btn, self._delete_btn):
            btn.pack(side="left", padx=(0, 6))
        self._move_up_btn.pack(side="left", padx=(0, 4))
        self._move_down_btn.pack(side="left")

    def _build_editor(self, parent: ttk.Frame) -> None:
        editor = ttk.Frame(parent, style="App.TFrame")
        editor.grid(row=0, column=1, sticky="nsew")
        editor.columnconfigure(0, weight=1)
        editor.rowconfigure(2, weight=1)

        ttk.Label(editor, text="Scene Editor", style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )

        edit_toolbar = ttk.Frame(editor, style="App.TFrame")
        edit_toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        edit_buttons = [
            ("Copy", self._on_copy),
            ("Cut", self._on_cut),
            ("Paste", self._on_paste),
            ("Select All", self._on_select_all),
            ("Undo", self._on_undo),
            ("Redo", self._on_redo),
            ("Clear Scene Text", self._on_clear_scene_text),
        ]
        for text, command in edit_buttons:
            ttk.Button(edit_toolbar, text=text, style="Secondary.TButton", command=command).pack(
                side="left", padx=(0, 6)
            )

        self._text_widget = tk.Text(
            editor, wrap="word", font=("Segoe UI", 10), undo=True, autoseparators=True, maxundo=-1,
            background=self._palette["field_bg"], foreground=self._palette["fg"],
            insertbackground=self._palette["fg"], relief="flat", padx=8, pady=8,
            highlightthickness=1, highlightbackground=self._palette["border"],
            highlightcolor=self._palette["accent"],
        )
        self._text_widget.grid(row=2, column=0, sticky="nsew", pady=(0, 6))
        self._text_widget.bind("<KeyRelease>", self._on_text_changed)

        self._word_count_label = ttk.Label(editor, text="", style="Muted.TLabel")
        self._word_count_label.grid(row=3, column=0, sticky="w", pady=(0, 10))

        meta_frame = ttk.Frame(editor, style="App.TFrame")
        meta_frame.grid(row=4, column=0, sticky="ew")
        meta_frame.columnconfigure(1, weight=1)

        ttk.Label(meta_frame, text="Notes:", style="Muted.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
        self._notes_var = tk.StringVar()
        notes_entry = ttk.Entry(meta_frame, textvariable=self._notes_var)
        notes_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 4))
        notes_entry.bind("<KeyRelease>", self._on_text_changed)

        ttk.Label(meta_frame, text="Visual Prompt:", style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        self._visual_prompt_var = tk.StringVar()
        prompt_entry = ttk.Entry(meta_frame, textvariable=self._visual_prompt_var)
        prompt_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0))
        prompt_entry.bind("<KeyRelease>", self._on_text_changed)

    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self, style="Card.TFrame", padding=10)
        bar.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 16))

        self._status_name_label = ttk.Label(bar, text="", style="App.TLabel")
        self._status_name_label.pack(side="left", padx=(0, 20))
        self._status_scenes_label = ttk.Label(bar, text="", style="Muted.TLabel")
        self._status_scenes_label.pack(side="left", padx=(0, 20))
        self._status_words_label = ttk.Label(bar, text="", style="Muted.TLabel")
        self._status_words_label.pack(side="left", padx=(0, 20))
        self._status_duration_label = ttk.Label(bar, text="", style="Muted.TLabel")
        self._status_duration_label.pack(side="left", padx=(0, 20))
        self._status_unsaved_label = ttk.Label(bar, text="", style="Muted.TLabel")
        self._status_unsaved_label.pack(side="right")

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def apply_theme(self, palette: dict) -> None:
        self._palette = palette
        self._text_widget.configure(
            background=palette["field_bg"], foreground=palette["fg"], insertbackground=palette["fg"],
            highlightbackground=palette["border"], highlightcolor=palette["accent"],
        )

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------

    def _bind_shortcuts(self) -> None:
        self.winfo_toplevel().bind("<Control-s>", self._on_shortcut_save, add="+")
        self._text_widget.bind("<Control-a>", self._on_select_all)
        self._text_widget.bind("<Control-z>", self._on_shortcut_undo)
        self._text_widget.bind("<Control-y>", self._on_shortcut_redo)

    def _on_shortcut_save(self, _event=None) -> None:
        if self.winfo_viewable():
            self._on_save_project()

    def _on_shortcut_undo(self, _event=None) -> str:
        self._on_undo()
        return "break"

    def _on_shortcut_redo(self, _event=None) -> str:
        self._on_redo()
        return "break"

    # ------------------------------------------------------------------
    # Editor <-> model sync
    # ------------------------------------------------------------------

    def _flush_editor_to_scene(self) -> None:
        if self._selected_scene_id is None:
            return
        scene = self._project.get_scene(self._selected_scene_id)
        if scene is None:
            return
        scene.text = self._text_widget.get("1.0", "end-1c")
        scene.notes = self._notes_var.get()
        scene.visual_prompt = self._visual_prompt_var.get()

    def _load_scene_into_editor(self, scene: Scene) -> None:
        self._text_widget.delete("1.0", "end")
        self._text_widget.insert("1.0", scene.text)
        self._text_widget.edit_reset()
        self._notes_var.set(scene.notes)
        self._visual_prompt_var.set(scene.visual_prompt)
        self._update_word_char_counts()

    def _clear_editor(self) -> None:
        self._text_widget.delete("1.0", "end")
        self._text_widget.edit_reset()
        self._notes_var.set("")
        self._visual_prompt_var.set("")
        self._update_word_char_counts()

    def _update_word_char_counts(self) -> None:
        content = self._text_widget.get("1.0", "end-1c")
        words = count_words(content)
        chars = count_characters(content)
        duration = format_duration(estimate_duration_seconds(words))
        self._word_count_label.configure(text=f"Words: {words}    Characters: {chars}    Est: {duration}")

    def _on_text_changed(self, _event=None) -> None:
        self._flush_editor_to_scene()
        self._mark_dirty()
        self._update_word_char_counts()
        if self._selected_scene_id and self._tree.exists(self._selected_scene_id):
            scene = self._project.get_scene(self._selected_scene_id)
            if scene:
                words = count_words(scene.text)
                duration = format_duration(estimate_duration_seconds(words))
                self._tree.item(
                    self._selected_scene_id, values=(scene.order + 1, scene.title, words, duration)
                )
        self._refresh_status_bar()

    # ------------------------------------------------------------------
    # Scene selection
    # ------------------------------------------------------------------

    def _activate_scene(self, scene_id: Optional[str]) -> None:
        """Synchronously make scene_id the active scene: flush whatever
        was previously loaded, load the new one, refresh button states.

        This used to happen only inside the <<TreeviewSelect>> handler,
        which Tk fires as a QUEUED virtual event -- not immediately when
        .selection_set() is called. That meant every programmatic
        selection (add/duplicate/delete/move/open/new) left
        self._selected_scene_id stale until the next event-loop tick, a
        real bug caught by the automated smoke test (see Phase 3 report).
        Centralizing the synchronous state change here, called directly
        by both the user-click handler and the programmatic selector,
        fixes that at the source instead of working around it.
        """
        if scene_id == self._selected_scene_id:
            return
        self._flush_editor_to_scene()
        self._selected_scene_id = scene_id
        if scene_id:
            scene = self._project.get_scene(scene_id)
            if scene:
                self._load_scene_into_editor(scene)
        else:
            self._clear_editor()
        self._refresh_scene_buttons_state()

    def _on_scene_select(self, _event=None) -> None:
        """User clicked a row in the tree directly."""
        selection = self._tree.selection()
        new_id = selection[0] if selection else None
        self._activate_scene(new_id)

    def _select_scene_in_tree(self, scene_id: Optional[str]) -> None:
        """Programmatic selection (from our own button handlers): updates
        the Treeview's visual row AND synchronously activates the scene,
        without waiting for the async <<TreeviewSelect>> event."""
        if scene_id and self._tree.exists(scene_id):
            self._tree.selection_set(scene_id)
            self._tree.focus(scene_id)
        else:
            self._tree.selection_remove(*self._tree.selection())
        self._activate_scene(scene_id)
        self._refresh_scene_buttons_state()

    def _rebuild_tree_rows(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for scene in sorted(self._project.scenes, key=lambda s: s.order):
            words = count_words(scene.text)
            duration = format_duration(estimate_duration_seconds(words))
            self._tree.insert(
                "", "end", iid=scene.id, values=(scene.order + 1, scene.title, words, duration)
            )

    # ------------------------------------------------------------------
    # Scene management actions
    # ------------------------------------------------------------------

    def _on_add_scene(self) -> None:
        self._flush_editor_to_scene()
        scene = self._project.add_scene()
        self._mark_dirty()
        self._rebuild_tree_rows()
        self._selected_scene_id = None
        self._select_scene_in_tree(scene.id)
        self._refresh_status_bar()
        self._on_status(f"Added {scene.title}.")

    def _on_rename_scene(self) -> None:
        if not self._selected_scene_id:
            return
        scene = self._project.get_scene(self._selected_scene_id)
        if not scene:
            return
        from tkinter import simpledialog

        new_title = simpledialog.askstring("Rename Scene", "Scene title:", initialvalue=scene.title, parent=self)
        if not new_title or not new_title.strip():
            return
        self._project.rename_scene(scene.id, new_title.strip())
        self._mark_dirty()
        self._rebuild_tree_rows()
        self._select_scene_in_tree(scene.id)
        self._refresh_status_bar()

    def _on_duplicate_scene(self) -> None:
        if not self._selected_scene_id:
            return
        self._flush_editor_to_scene()
        copy = self._project.duplicate_scene(self._selected_scene_id)
        self._mark_dirty()
        self._rebuild_tree_rows()
        self._selected_scene_id = None
        self._select_scene_in_tree(copy.id)
        self._refresh_status_bar()
        self._on_status(f"Duplicated scene as '{copy.title}'.")

    def _on_delete_scene(self) -> None:
        if not self._selected_scene_id:
            return
        scene = self._project.get_scene(self._selected_scene_id)
        if not scene:
            return
        if not messagebox.askyesno("Delete Scene", f"Delete '{scene.title}'? This cannot be undone."):
            return

        deleted_index = scene.order
        self._project.delete_scene(scene.id)
        self._mark_dirty()
        self._rebuild_tree_rows()

        remaining = sorted(self._project.scenes, key=lambda s: s.order)
        next_id = None
        if remaining:
            next_index = min(deleted_index, len(remaining) - 1)
            next_id = remaining[next_index].id

        self._selected_scene_id = None
        self._select_scene_in_tree(next_id)
        self._refresh_status_bar()
        self._on_status("Scene deleted.")

    def _on_move_up(self) -> None:
        if not self._selected_scene_id:
            return
        self._project.move_scene_up(self._selected_scene_id)
        self._mark_dirty()
        self._rebuild_tree_rows()
        self._select_scene_in_tree(self._selected_scene_id)

    def _on_move_down(self) -> None:
        if not self._selected_scene_id:
            return
        self._project.move_scene_down(self._selected_scene_id)
        self._mark_dirty()
        self._rebuild_tree_rows()
        self._select_scene_in_tree(self._selected_scene_id)

    def _refresh_scene_buttons_state(self) -> None:
        has_selection = self._selected_scene_id is not None
        scenes_sorted = sorted(self._project.scenes, key=lambda s: s.order)
        idx = next((i for i, s in enumerate(scenes_sorted) if s.id == self._selected_scene_id), -1)

        state = "normal" if has_selection else "disabled"
        self._rename_btn.configure(state=state)
        self._duplicate_btn.configure(state=state)
        self._delete_btn.configure(state=state)
        self._move_up_btn.configure(state="normal" if has_selection and idx > 0 else "disabled")
        self._move_down_btn.configure(
            state="normal" if has_selection and 0 <= idx < len(scenes_sorted) - 1 else "disabled"
        )

    # ------------------------------------------------------------------
    # Text editing actions
    # ------------------------------------------------------------------

    def _on_copy(self) -> None:
        self._text_widget.event_generate("<<Copy>>")

    def _on_cut(self) -> None:
        self._text_widget.event_generate("<<Cut>>")
        self._on_text_changed()

    def _on_paste(self) -> None:
        self._text_widget.event_generate("<<Paste>>")
        self._on_text_changed()

    def _on_select_all(self, _event=None) -> str:
        self._text_widget.tag_add("sel", "1.0", "end-1c")
        return "break"

    def _on_undo(self) -> None:
        try:
            self._text_widget.edit_undo()
        except tk.TclError:
            pass
        self._on_text_changed()

    def _on_redo(self) -> None:
        try:
            self._text_widget.edit_redo()
        except tk.TclError:
            pass
        self._on_text_changed()

    def _on_clear_scene_text(self) -> None:
        if not self._selected_scene_id:
            return
        if not messagebox.askyesno("Clear Scene Text", "Clear all text in this scene?"):
            return
        self._text_widget.delete("1.0", "end")
        self._on_text_changed()

    # ------------------------------------------------------------------
    # Project actions
    # ------------------------------------------------------------------

    def _confirm_discard_if_dirty(self) -> bool:
        if self._project_manager.dirty:
            return messagebox.askyesno(
                "Unsaved Changes", "This project has unsaved changes. Continue and discard them?"
            )
        return True

    def _on_new_project(self) -> None:
        self._flush_editor_to_scene()
        if not self._confirm_discard_if_dirty():
            return
        self._project_manager.new_project()
        self._selected_scene_id = None
        self._rebuild_tree_rows()
        self._clear_editor()
        self._refresh_status_bar()
        self._refresh_scene_buttons_state()
        self._on_status("New project created.")

    def _on_open_project(self) -> None:
        self._flush_editor_to_scene()
        if not self._confirm_discard_if_dirty():
            return
        path = filedialog.askopenfilename(
            title="Open Project", filetypes=[("Voxora Project", f"*{PROJECT_EXTENSION}"), ("All Files", "*.*")]
        )
        if not path:
            return
        try:
            self._project_manager.open(Path(path))
        except ProjectError as exc:
            messagebox.showerror("Open Failed", str(exc))
            logger.error("Failed to open project %s: %s", path, exc)
            return

        self._selected_scene_id = None
        self._rebuild_tree_rows()
        scenes = sorted(self._project.scenes, key=lambda s: s.order)
        self._select_scene_in_tree(scenes[0].id if scenes else None)
        self._refresh_status_bar()
        self._on_status(f"Opened {Path(path).name}")

    def _on_save_project(self) -> None:
        self._flush_editor_to_scene()
        if self._project_manager.current_path is None:
            self._on_save_as_project()
            return
        try:
            path = self._project_manager.save()
        except ProjectError as exc:
            messagebox.showerror("Save Failed", str(exc))
            logger.error("Failed to save project: %s", exc)
            return
        self._refresh_status_bar()
        self._on_status(f"Project saved to {path}")

    def _on_save_as_project(self) -> None:
        self._flush_editor_to_scene()
        dest = filedialog.asksaveasfilename(
            title="Save Project As",
            defaultextension=PROJECT_EXTENSION,
            filetypes=[("Voxora Project", f"*{PROJECT_EXTENSION}")],
            initialfile=f"{self._project.name}{PROJECT_EXTENSION}",
        )
        if not dest:
            return
        try:
            path = self._project_manager.save(Path(dest))
        except ProjectError as exc:
            messagebox.showerror("Save Failed", str(exc))
            logger.error("Failed to save project as %s: %s", dest, exc)
            return
        self._refresh_status_bar()
        self._on_status(f"Project saved to {path}")

    # ------------------------------------------------------------------
    # Script import
    # ------------------------------------------------------------------

    def _on_import_script(self) -> None:
        path = filedialog.askopenfilename(
            title="Import Script", filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if not path:
            return
        try:
            content = import_txt_file(Path(path))
        except ProjectError as exc:
            messagebox.showerror("Import Failed", str(exc))
            logger.error("Failed to import %s: %s", path, exc)
            return

        split_choice = messagebox.askyesnocancel(
            "Import Script",
            "Split the file into multiple scenes using blank lines as separators?\n\n"
            "Yes = Split into scenes\nNo = Import as one single scene\nCancel = Abort import",
        )
        if split_choice is None:
            return

        texts = split_into_scenes(content) if split_choice else [content]
        if not texts:
            messagebox.showwarning("Import", "No content found to import (the file may be empty).")
            return

        if self._project.scenes:
            replace = messagebox.askyesnocancel(
                "Import Script",
                "This project already has scenes.\n\n"
                "Yes = Replace existing scenes\nNo = Append imported scenes\nCancel = Abort import",
            )
            if replace is None:
                return
            if replace:
                self._flush_editor_to_scene()
                self._selected_scene_id = None
                self._project.scenes.clear()

        self._flush_editor_to_scene()
        first_new_id = None
        for text in texts:
            scene = self._project.add_scene(Scene(title=f"Scene {len(self._project.scenes) + 1}", text=text))
            if first_new_id is None:
                first_new_id = scene.id

        self._mark_dirty()
        self._rebuild_tree_rows()
        self._selected_scene_id = None
        self._select_scene_in_tree(first_new_id)
        self._refresh_status_bar()
        self._on_status(f"Imported {len(texts)} scene(s) from {Path(path).name}.")

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _mark_dirty(self) -> None:
        self._project_manager.mark_dirty()
        self._refresh_status_bar()

    def _refresh_status_bar(self) -> None:
        total_scenes = len(self._project.scenes)
        total_words = self._project.total_word_count()
        total_duration = format_duration(estimate_duration_seconds(total_words))

        self._status_name_label.configure(text=f"Project: {self._project.name}")
        self._status_scenes_label.configure(text=f"Scenes: {total_scenes}")
        self._status_words_label.configure(text=f"Words: {total_words}")
        self._status_duration_label.configure(text=f"Est. Duration: {total_duration} (estimate only)")

        if self._project_manager.dirty:
            self._status_unsaved_label.configure(text="\u25cf Unsaved changes", style="Error.TLabel")
        else:
            self._status_unsaved_label.configure(text="\u2713 Saved", style="Success.TLabel")

    # ------------------------------------------------------------------
    # Lifecycle hooks called by MainWindow
    # ------------------------------------------------------------------

    def confirm_close(self) -> bool:
        self._flush_editor_to_scene()
        if self._project_manager.dirty:
            return messagebox.askyesno(
                "Unsaved Project",
                f"'{self._project.name}' has unsaved changes.\n\nClose {APP_NAME} anyway?",
            )
        return True

    def shutdown(self) -> None:
        pass