# views/deck_picker.py
"""
Modal dialog for choosing an Anki deck and saving a note.
"""

import tkinter as tk
from tkinter import ttk


# ── theme tokens (match subtitle_overlay) ─────────────────────────────
_BG         = "#1a1b26"
_BORDER     = "#414868"
_FG         = "#c0caf5"
_MUTED      = "#9aa5ce"
_GREEN      = "#9ece6a"
_BLUE       = "#7aa2f7"
_RED        = "#f7768e"
_GREEN_BG   = "#2d4a2d"
_FONT_BODY  = ("Segoe UI", 11)
_FONT_META  = ("Segoe UI", 9)


class DeckPickerDialog:
    """Show a deck picker, create decks, and save an Anki note."""

    def __init__(
        self,
        master: tk.Tk,
        controller,
        word,
        src_lang: str,
        on_saved=None,
        anchor_window: tk.Toplevel | None = None,
    ):
        self._master = master
        self._controller = controller
        self._word = word
        self._src_lang = src_lang
        self._on_saved = on_saved

        self._dialog = dlg = tk.Toplevel(master)
        dlg.title("Save to Anki")
        dlg.attributes("-topmost", True)
        dlg.configure(bg=_BG)
        dlg.resizable(False, False)
        dlg.grab_set()

        frame = tk.Frame(dlg, bg=_BG, padx=20, pady=16)
        frame.pack()

        tk.Label(frame, text="Choose deck:", font=_FONT_BODY,
                 fg=_FG, bg=_BG).pack(anchor="w", pady=(0, 8))

        # ── deck combo ────────────────────────────────────────────────
        self._combo = ttk.Combobox(frame, values=[], width=30, font=_FONT_BODY)
        self._combo.set("Loading…")
        self._combo.config(state="disabled")
        self._combo.pack(fill="x", pady=(0, 4))

        # ── new-deck row ──────────────────────────────────────────────
        row = tk.Frame(frame, bg=_BG)
        row.pack(fill="x", pady=(2, 4))

        self._new_entry = tk.Entry(
            row, font=_FONT_META, bg=_BORDER, fg=_FG,
            insertbackground=_FG, relief="flat",
        )

        self._new_btn = tk.Button(
            row, text="+ New Deck", command=self._show_new_entry,
            bg=_BG, fg=_BLUE, font=_FONT_META, relief="flat",
            cursor="hand2", padx=0, pady=0,
        )
        self._new_btn.pack(anchor="w")

        self._create_btn = tk.Button(
            row, text="Create", command=self._do_create_deck,
            bg=_GREEN_BG, fg=_GREEN, font=_FONT_META, relief="flat",
            padx=8, pady=2, cursor="hand2",
        )
        self._new_entry.bind("<Return>", lambda e: self._do_create_deck())

        # ── status ────────────────────────────────────────────────────
        self._status = tk.Label(
            frame, text="Starting Anki…", font=_FONT_META,
            fg=_MUTED, bg=_BG,
        )
        self._status.pack(anchor="w", pady=(4, 8))

        # ── save / cancel ─────────────────────────────────────────────
        btn_row = tk.Frame(frame, bg=_BG)
        btn_row.pack(fill="x")

        self._save_btn = tk.Button(
            btn_row, text="Save", command=self._on_save,
            bg=_GREEN_BG, fg=_GREEN, font=_FONT_BODY, relief="flat",
            padx=20, pady=6, cursor="hand2",
        )
        self._save_btn.pack(side="left")

        tk.Button(
            btn_row, text="Cancel", command=dlg.destroy,
            bg=_BORDER, fg=_FG, font=_FONT_BODY, relief="flat",
            padx=20, pady=6, cursor="hand2",
        ).pack(side="right")

        # ── position & launch background connect ──────────────────────
        self._controller.ensure_anki_ready(
            on_ready=lambda ok, decks: self._master.after(
                0, self._on_decks_loaded, ok, decks
            ),
        )

        dlg.update_idletasks()
        if anchor_window:
            px, py = anchor_window.winfo_x(), anchor_window.winfo_y()
            pw, ph = anchor_window.winfo_width(), anchor_window.winfo_height()
            dw, dh = dlg.winfo_reqwidth(), dlg.winfo_reqheight()
            dlg.geometry(f"+{px + (pw - dw) // 2}+{py + (ph - dh) // 2}")

    # ── new-deck helpers ──────────────────────────────────────────────
    def _show_new_entry(self):
        self._new_btn.pack_forget()
        self._new_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._create_btn.pack(side="right")
        self._new_entry.focus_set()

    def _do_create_deck(self):
        name = self._new_entry.get().strip()
        if not name:
            return
        self._create_btn.config(state="disabled", text="…")

        def on_created(result):
            self._master.after(0, lambda: self._apply_create_result(result, name))

        self._controller.create_anki_deck(name, on_ready=on_created)

    def _apply_create_result(self, result, name):
        if result["success"]:
            vals = list(self._combo["values"]) + [name]
            self._combo["values"] = vals
            self._combo.set(name)
            self._new_entry.delete(0, "end")
            self._new_entry.pack_forget()
            self._create_btn.pack_forget()
            self._new_btn.pack(anchor="w")
            self._status.config(text=f'Deck "{name}" created.', fg=_GREEN)
        else:
            self._status.config(text=result["error"], fg=_RED)
        self._create_btn.config(state="normal", text="Create")

    # ── connect to Anki ───────────────────────────────────────────────
    def _on_decks_loaded(self, anki_ok, decks):
        self._combo.config(state="normal")
        if decks:
            self._combo["values"] = decks
            self._combo.set(decks[0])
            self._status.config(text="", fg=_MUTED)
        elif anki_ok:
            self._combo.set("Default")
            self._status.config(text="No decks found — type a name to create one.", fg=_MUTED)
        else:
            self._combo.set("Default")
            self._status.config(
                text="Could not start Anki. Is it installed with AnkiConnect?",
                fg=_RED,
            )

    # ── save ──────────────────────────────────────────────────────────
    def _on_save(self):
        deck_name = self._combo.get().strip()
        if not deck_name:
            self._status.config(text="Enter a deck name.", fg=_RED)
            return

        self._save_btn.config(state="disabled", text="Saving…")

        def on_result(result):
            self._master.after(0, lambda: self._apply_save_result(result))

        self._controller.save_to_anki(
            self._word, deck_name, self._src_lang, on_ready=on_result,
        )

    def _apply_save_result(self, result):
        if result["success"]:
            self._status.config(text="Saved!", fg=_GREEN)
            if self._on_saved:
                self._on_saved()
            self._dialog.after(800, self._dialog.destroy)
        else:
            self._status.config(text=result["error"], fg=_RED)
            self._save_btn.config(state="normal", text="Save")
