# views/subtitle_overlay.py
"""
Borderless, always-on-top subtitle bar with centered word-wrap.

Hover  → quick definition card.
Click  → pinned detail window with COMPLETE info (pronunciation, meanings, forms, examples).
"""

import tkinter as tk
from queue import Queue, Empty

from services.definition_service import (
    LANG_NAMES, SKIP_TAGS,
    pick_pronunciations, pick_forms, is_inflection_definition,
)


class SubtitleOverlay:
    # ── layout constants ─────────────────────────────────────────────
    MARGIN_X    = 24
    MARGIN_Y    = 10
    WORD_PAD_X  = 6
    LINE_HEIGHT = 38

    # ── visual constants (IMPROVED) ──────────────────────────────────
    BG              = "#0f0f1a"      # Darker, more modern
    FG              = "#e5e7eb"      # Softer white
    HOVER_FG        = "#60a5fa"      # Brighter blue
    
    # Card styling (modern, clean)
    CARD_BG         = "#1a1b26"      # Dark blue-gray
    CARD_BORDER     = "#414868"      # Subtle border
    CARD_TITLE_FG   = "#bb9af7"      # Purple accent
    CARD_DEF_FG     = "#c0caf5"      # Light blue-white
    CARD_GRAM_FG    = "#9aa5ce"      # Muted blue
    CARD_PRON_FG    = "#7aa2f7"      # Bright blue
    CARD_EXAMPLE_FG = "#7dcfff"      # Cyan
    CARD_SYN_FG     = "#9ece6a"      # Green
    CARD_ANT_FG     = "#f7768e"      # Red
    CARD_ERR_FG     = "#f7768e"      # Red for errors
    CARD_SECTION_FG = "#565f89"      # Section headers
    
    # Fonts (improved hierarchy)
    FONT_WORD       = ("Segoe UI", 22, "bold")
    FONT_CARD_TITLE = ("Segoe UI", 16, "bold")      # Larger title
    FONT_CARD_PRON  = ("Segoe UI", 12)              # Pronunciation
    FONT_CARD_POS   = ("Segoe UI", 11, "italic")    # Part of speech
    FONT_CARD_BODY  = ("Segoe UI", 11)
    FONT_CARD_EXAMPLE = ("Segoe UI", 10, "italic")
    FONT_CARD_META  = ("Segoe UI", 9)               # Small metadata

    # Translation line (dual subtitle)
    FONT_TRANSLATION  = ("Segoe UI", 18)
    TRANSLATION_FG    = "#9ca3af"       # Muted gray — visually secondary
    TRANSLATION_PAD_Y = 6

    MAX_SENSES = 4

    def __init__(self, master: tk.Tk,
                 controller,
                 get_source_lang=None,
                 get_target_lang=None):
        self.master        = master
        self._controller   = controller
        self._get_src_lang = get_source_lang or (lambda: "en")
        self._get_tgt_lang = get_target_lang or (lambda: "en")

        self.queue: Queue = Queue()
        self._screen_w = master.winfo_screenwidth()

        # ── main overlay window ──────────────────────────────────────
        self.win = tk.Toplevel(master)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.95)
        self.win.configure(bg=self.BG)

        self._word_labels: list[tk.Label] = []
        self._card: tk.Toplevel | None   = None
        self._card_after_id: str | None  = None
        self._pinned_card: tk.Toplevel | None = None
        self._words: list = []

        # Translation line (dual subtitle)
        self._translation_label: tk.Label | None = None
        self._translation_text: str = ""
        self._translation_visible: bool = False

        # Pinned word (Word model holds definition data)
        self._pinned_word = None
        self._anki_btn: tk.Button | None = None

        self._measure_label = tk.Label(self.win, font=self.FONT_WORD)
        self._measure_label.place(x=-9999, y=-9999)

        self.win.bind("<Escape>", lambda e: self.hide())
        self.master.after(30, self._drain_queue)

    # ── public ───────────────────────────────────────────────────────
    def show(self):
        self.win.deiconify()
        self._reposition()

    def hide(self):
        self._hide_card()
        self.win.withdraw()

    def clear(self):
        self._hide_card(immediate=True)
        self._words.clear()
        self._translation_text = ""
        self._rebuild_labels()

    def set_translation_visible(self, visible: bool):
        self._translation_visible = visible
        if not visible:
            self._translation_text = ""
            if self._translation_label:
                self._translation_label.destroy()
                self._translation_label = None
            self._rebuild_labels()

    # ── queue polling ────────────────────────────────────────────────
    def _drain_queue(self):
        rebuild = False
        try:
            while True:
                item = self.queue.get_nowait()
                if isinstance(item, tuple):
                    if item[0] == "WORDS":
                        self._words = item[1]
                        rebuild = True
                    elif item[0] == "TRANSLATION":
                        self._translation_text = item[1]
                        rebuild = True
        except Empty:
            pass
        if rebuild:
            self._rebuild_labels()
        self.master.after(30, self._drain_queue)

    # ── measuring ────────────────────────────────────────────────────
    def _measure_word(self, text: str) -> int:
        self._measure_label.config(text=text)
        self._measure_label.update_idletasks()
        return self._measure_label.winfo_width()

    # ── flow layout + label rebuild ──────────────────────────────────
    def _rebuild_labels(self):
        for lbl in self._word_labels:
            lbl.destroy()
        self._word_labels.clear()
        if self._translation_label:
            self._translation_label.destroy()
            self._translation_label = None

        if not self._words:
            self.win.geometry(f"{self._screen_w}x0+0+0")
            return

        max_line_width = self._screen_w - 2 * self.MARGIN_X
        word_pad       = self.WORD_PAD_X * 2

        lines: list[list[tuple]] = []
        current_line: list[tuple] = []
        current_x = 0

        for word_obj in self._words:
            w_px = self._measure_word(word_obj.text) + word_pad
            if current_line and (current_x + w_px) > max_line_width:
                lines.append(current_line)
                current_line = []
                current_x    = 0

            current_line.append((word_obj, w_px))
            current_x += w_px

        if current_line:
            lines.append(current_line)

        num_lines = len(lines)
        words_bottom = num_lines * self.LINE_HEIGHT + self.MARGIN_Y

        for line_idx, line in enumerate(lines):
            line_total_w = sum(w for _, w in line)
            x = (self._screen_w - line_total_w) // 2
            y = self.MARGIN_Y + line_idx * self.LINE_HEIGHT

            for word_obj, w_px in line:
                lbl = tk.Label(
                    self.win,
                    text=word_obj.text,
                    font=self.FONT_WORD,
                    fg=self.FG,
                    bg=self.BG,
                    padx=self.WORD_PAD_X,
                    pady=2,
                    cursor="hand2",
                )
                lbl.place(x=x, y=y, width=w_px, height=self.LINE_HEIGHT)
                lbl.bind("<Enter>",   lambda e, wo=word_obj, lb=lbl: self._on_word_enter(e, wo, lb))
                lbl.bind("<Leave>",   lambda e: self._on_word_leave(e))
                lbl.bind("<Button-1>", lambda e, wo=word_obj: self._on_word_click(wo))
                self._word_labels.append(lbl)
                x += w_px

        # ── translation line (dual subtitle) ──────────────────────
        if self._translation_visible and self._translation_text:
            trans_y = words_bottom + self.TRANSLATION_PAD_Y
            self._translation_label = tk.Label(
                self.win,
                text=self._translation_text,
                font=self.FONT_TRANSLATION,
                fg=self.TRANSLATION_FG,
                bg=self.BG,
                anchor="center",
                wraplength=self._screen_w - 2 * self.MARGIN_X,
            )
            self._translation_label.update_idletasks()
            trans_h = self._translation_label.winfo_reqheight()
            trans_w = self._translation_label.winfo_reqwidth()
            trans_x = (self._screen_w - trans_w) // 2
            self._translation_label.place(x=trans_x, y=trans_y, height=trans_h)
            overlay_h = trans_y + trans_h + self.MARGIN_Y
        else:
            overlay_h = words_bottom + self.MARGIN_Y

        self.win.geometry(f"{self._screen_w}x{overlay_h}+0+0")

    def _reposition(self):
        if self._words:
            self._rebuild_labels()
        else:
            self.win.geometry(f"{self._screen_w}x0+0+0")

    # ── hover ────────────────────────────────────────────────────────
    def _on_word_enter(self, event, word_obj, label: tk.Label):
        label.config(fg=self.HOVER_FG)
        if self._card_after_id:
            self.master.after_cancel(self._card_after_id)
            self._card_after_id = None

        self._show_hover_card(word_obj, label)

        self._controller.fetch_hover_definition(
            word_obj, self._get_src_lang(), self._get_tgt_lang(),
            on_ready=lambda w: self.master.after(0, self._apply_hover_definition, w),
        )

    def _on_word_leave(self, event):
        for lbl in self._word_labels:
            lbl.config(fg=self.FG)
        self._card_after_id = self.master.after(120, self._hide_card)

    # ── hover card (QUICK PREVIEW) ───────────────────────────────────
    def _show_hover_card(self, word_obj, label: tk.Label):
        self._hide_card(immediate=True)

        card = tk.Toplevel(self.master)
        card.overrideredirect(True)
        card.attributes("-topmost", True)
        card.attributes("-alpha", 0.97)
        card.configure(bg=self.CARD_BORDER)

        inner = tk.Frame(card, bg=self.CARD_BG, padx=16, pady=12)
        inner.pack(padx=2, pady=2)

        # Title
        tk.Label(
            inner, 
            text=word_obj.text, 
            font=self.FONT_CARD_TITLE,
            fg=self.CARD_TITLE_FG, 
            bg=self.CARD_BG
        ).pack(anchor="w")

        # Source language
        src_name = LANG_NAMES.get(self._get_src_lang(), self._get_src_lang())
        tk.Label(
            inner, 
            text=f"from {src_name}",
            font=self.FONT_CARD_META, 
            fg=self.CARD_GRAM_FG, 
            bg=self.CARD_BG
        ).pack(anchor="w", pady=(0, 6))

        tk.Frame(inner, bg=self.CARD_BORDER, height=1).pack(fill="x", pady=(0, 8))

        self._card_def_label = tk.Label(
            inner, text="Loading…", font=self.FONT_CARD_BODY,
            fg=self.CARD_DEF_FG, bg=self.CARD_BG, justify="left", wraplength=320
        )
        self._card_def_label.pack(anchor="w")

        self._card_gram_label = tk.Label(
            inner, text="", font=self.FONT_CARD_POS,
            fg=self.CARD_GRAM_FG, bg=self.CARD_BG, justify="left"
        )
        self._card_gram_label.pack(anchor="w", pady=(6, 0))

        self._card_err_label = tk.Label(
            inner, text="", font=self.FONT_CARD_META,
            fg=self.CARD_ERR_FG, bg=self.CARD_BG, justify="left"
        )
        self._card_err_label.pack(anchor="w", pady=(4, 0))

        # Position below word
        label.update_idletasks()
        x = label.winfo_rootx()
        y = label.winfo_rooty() + label.winfo_height() + 8
        
        card.update_idletasks()
        card_w = card.winfo_reqwidth()
        screen_w = self.master.winfo_screenwidth()
        if x + card_w > screen_w:
            x = screen_w - card_w - 10
        
        card.geometry(f"+{x}+{y}")

        self._card = card

        def cancel_hide(e):
            if self._card_after_id:
                self.master.after_cancel(self._card_after_id)
                self._card_after_id = None

        def schedule_hide(e):
            self._card_after_id = self.master.after(120, self._hide_card)

        card.bind("<Enter>", cancel_hide)
        card.bind("<Leave>", schedule_hide)

    def _hide_card(self, immediate=False):
        if self._card_after_id:
            self.master.after_cancel(self._card_after_id)
            self._card_after_id = None
        if self._card is not None:
            try:
                self._card.destroy()
            except tk.TclError:
                pass
            self._card = None

    # ── hover apply ─────────────────────────────────────────────────
    def _apply_hover_definition(self, word):
        if self._card is None:
            return

        result = word.simple_result or {}

        if result.get("error"):
            self._card_def_label.config(text="")
            self._card_gram_label.config(text="")
            self._card_err_label.config(text=f"⚠️ {result['error']}")
            return

        self._card_def_label.config(text=word.definition or "No definition found.")
        if word.grammar:
            self._card_gram_label.config(text=f"• {word.grammar}")
        else:
            self._card_gram_label.config(text="")
        self._card_err_label.config(text="")
        self._card.update_idletasks()

    # ── click (FULL DETAILS) ─────────────────────────────────────────
    def _on_word_click(self, word_obj):
        self._show_pinned_card(word_obj)

        self._controller.fetch_full_definition(
            word_obj, self._get_src_lang(), self._get_tgt_lang(),
            on_ready=lambda w: self.master.after(0, self._apply_pinned_details, w),
        )

    # ── pinned detail card (IMPROVED) ────────────────────────────────
    def _show_pinned_card(self, word_obj):
        if self._pinned_card is not None:
            try:
                self._pinned_card.destroy()
            except tk.TclError:
                pass
            self._pinned_card = None

        card = tk.Toplevel(self.master)
        card.title("Word Details")
        card.attributes("-topmost", True)
        card.configure(bg=self.CARD_BORDER)
        card.protocol("WM_DELETE_WINDOW", lambda: self._close_pinned_card())
        card.resizable(False, False)

        # Main container with scrolling
        canvas = tk.Canvas(card, bg=self.CARD_BG, highlightthickness=0, width=480, height=600)
        scrollbar = tk.Scrollbar(card, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.CARD_BG)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=2, pady=2)
        scrollbar.pack(side="right", fill="y")

        inner = tk.Frame(scrollable_frame, bg=self.CARD_BG, padx=20, pady=16)
        inner.pack(fill="both", expand=True)

        # Word title (larger, more prominent)
        tk.Label(
            inner, 
            text=word_obj.text, 
            font=self.FONT_CARD_TITLE,
            fg=self.CARD_TITLE_FG, 
            bg=self.CARD_BG
        ).pack(anchor="w")

        # Source language
        src_name = LANG_NAMES.get(self._get_src_lang(), self._get_src_lang())
        tk.Label(
            inner, 
            text=f"from {src_name}",
            font=self.FONT_CARD_META, 
            fg=self.CARD_GRAM_FG, 
            bg=self.CARD_BG
        ).pack(anchor="w", pady=(0, 12))

        tk.Frame(inner, bg=self.CARD_BORDER, height=2).pack(fill="x", pady=(0, 12))

        # Content area (will be filled by _apply_pinned_details)
        content_frame = tk.Frame(inner, bg=self.CARD_BG)
        content_frame.pack(fill="both", expand=True)

        self._pinned_content_frame = content_frame
        self._pinned_word = word_obj

        self._pinned_loading_label = tk.Label(
            content_frame,
            text="Loading…",
            font=self.FONT_CARD_BODY,
            fg=self.CARD_DEF_FG,
            bg=self.CARD_BG
        )
        self._pinned_loading_label.pack(anchor="w")

        # Buttons row
        btn_frame = tk.Frame(inner, bg=self.CARD_BG)
        btn_frame.pack(fill="x", pady=(16, 0))

        self._anki_btn = tk.Button(
            btn_frame,
            text="+ Anki",
            command=self._save_to_anki,
            bg="#2d4a2d",
            fg=self.CARD_SYN_FG,
            font=self.FONT_CARD_BODY,
            relief="flat",
            padx=20,
            pady=6,
            cursor="hand2",
            state="disabled",
        )
        self._anki_btn.pack(side="left")

        close_btn = tk.Button(
            btn_frame,
            text="✕ Close",
            command=self._close_pinned_card,
            bg=self.CARD_BORDER,
            fg=self.CARD_DEF_FG,
            font=self.FONT_CARD_BODY,
            relief="flat",
            padx=20,
            pady=6,
            cursor="hand2"
        )
        close_btn.pack(side="right")

        self._pinned_card = card
        card.update_idletasks()
        
        # Center on screen
        screen_w = self.master.winfo_screenwidth()
        screen_h = self.master.winfo_screenheight()
        card_w = 520
        card_h = min(650, screen_h - 100)
        x = (screen_w - card_w) // 2
        y = (screen_h - card_h) // 2
        card.geometry(f"{card_w}x{card_h}+{x}+{y}")

    def _close_pinned_card(self):
        if self._pinned_card is not None:
            try:
                self._pinned_card.destroy()
            except tk.TclError:
                pass
            self._pinned_card = None

    # ── pinned apply (COMPLETE INFO) ─────────────────────────────────
    def _apply_pinned_details(self, word):
        if self._pinned_card is None:
            return

        simple_result = word.simple_result or {}
        detail_result = word.detail_result or {}

        # Clear loading message
        for widget in self._pinned_content_frame.winfo_children():
            widget.destroy()

        content = self._pinned_content_frame

        # Handle errors
        if simple_result.get("error") and detail_result.get("error"):
            tk.Label(
                content,
                text=f"⚠️ Error: {simple_result['error']}",
                font=self.FONT_CARD_BODY,
                fg=self.CARD_ERR_FG,
                bg=self.CARD_BG
            ).pack(anchor="w")
            return

        d = word.details

        # PART OF SPEECH (prominent)
        pos = d.get("partOfSpeech", word.grammar)
        if pos:
            tk.Label(
                content, 
                text=f"• {pos}", 
                font=self.FONT_CARD_POS,
                fg=self.CARD_GRAM_FG, 
                bg=self.CARD_BG
            ).pack(anchor="w", pady=(0, 12))

        # PRONUNCIATION (from detail data)
        prons = pick_pronunciations(d.get("pronunciations", []), self._get_src_lang())
        if prons:
            self._add_section_header(content, "Pronunciation")
            for p in prons:
                txt  = p.get("text", "")
                tags = p.get("tags", [])
                tag_str = f" ({', '.join(tags)})" if tags else ""
                tk.Label(
                    content, 
                    text=f"  {txt}{tag_str}", 
                    font=self.FONT_CARD_PRON,
                    fg=self.CARD_PRON_FG, 
                    bg=self.CARD_BG
                ).pack(anchor="w", pady=(2, 0))
            self._add_spacer(content)

        # MEANINGS (include simple definition at top)
        self._add_section_header(content, "Meanings")
        
        # First show the simple/hover definition (always clear and concise)
        simple_def = word.definition
        if simple_def and simple_def != "No definition found.":
            tk.Label(
                content, 
                text=f"• {simple_def}", 
                font=self.FONT_CARD_BODY,
                fg=self.CARD_DEF_FG, 
                bg=self.CARD_BG,
                wraplength=440,
                justify="left"
            ).pack(anchor="w", pady=(4, 8))

        # Then show detailed senses (filtered)
        senses = d.get("senses", [])
        if senses:
            filtered = [s for s in senses if not (set(s.get("tags", [])) & SKIP_TAGS)]
            real = [s for s in filtered if not is_inflection_definition(s.get("definition", ""))]
            infl = [s for s in filtered if is_inflection_definition(s.get("definition", ""))]
            
            chosen = (real or infl)[:self.MAX_SENSES]
            
            for i, s in enumerate(chosen, start=1):
                defi = s.get("definition", "")
                tags = s.get("tags", [])
                
                # Skip if it's the same as simple definition
                if defi == simple_def:
                    continue
                
                # Definition number + text
                def_frame = tk.Frame(content, bg=self.CARD_BG)
                def_frame.pack(anchor="w", fill="x", pady=(4, 2))
                
                tk.Label(
                    def_frame, 
                    text=f"{i}.", 
                    font=self.FONT_CARD_BODY,
                    fg=self.CARD_TITLE_FG, 
                    bg=self.CARD_BG
                ).pack(side="left", anchor="nw")
                
                tag_str = f" [{', '.join(tags)}]" if tags else ""
                tk.Label(
                    def_frame, 
                    text=f" {defi}{tag_str}", 
                    font=self.FONT_CARD_BODY,
                    fg=self.CARD_DEF_FG, 
                    bg=self.CARD_BG,
                    wraplength=400,
                    justify="left"
                ).pack(side="left", anchor="nw", fill="x", expand=True)

                # Examples
                examples = s.get("examples", [])
                if examples:
                    tk.Label(
                        content, 
                        text=f"    e.g. {examples[0]}", 
                        font=self.FONT_CARD_EXAMPLE,
                        fg=self.CARD_EXAMPLE_FG, 
                        bg=self.CARD_BG,
                        wraplength=420,
                        justify="left"
                    ).pack(anchor="w", pady=(2, 0))

                # Synonyms
                synonyms = s.get("synonyms", [])
                if synonyms:
                    tk.Label(
                        content, 
                        text=f"    ≈ {', '.join(synonyms[:6])}", 
                        font=self.FONT_CARD_META,
                        fg=self.CARD_SYN_FG, 
                        bg=self.CARD_BG,
                        wraplength=420,
                        justify="left"
                    ).pack(anchor="w", pady=(2, 0))

                # Antonyms
                antonyms = s.get("antonyms", [])
                if antonyms:
                    tk.Label(
                        content, 
                        text=f"    ≠ {', '.join(antonyms[:6])}", 
                        font=self.FONT_CARD_META,
                        fg=self.CARD_ANT_FG, 
                        bg=self.CARD_BG,
                        wraplength=420,
                        justify="left"
                    ).pack(anchor="w", pady=(2, 6))

        self._add_spacer(content)

        # KEY FORMS
        forms = pick_forms(d.get("forms", []))
        if forms:
            self._add_section_header(content, "Key Forms")
            for f in forms:
                w = f.get("word", "")
                tags = f.get("tags", [])
                tag_str = f" — {', '.join(tags)}" if tags else ""
                tk.Label(
                    content,
                    text=f"  • {w}{tag_str}",
                    font=self.FONT_CARD_BODY,
                    fg=self.CARD_DEF_FG,
                    bg=self.CARD_BG
                ).pack(anchor="w", pady=(2, 0))

        # Enable Anki button now that data is loaded
        if self._anki_btn:
            self._anki_btn.config(state="normal")

        self._pinned_card.update_idletasks()

    def _add_section_header(self, parent, text):
        """Add a section header with visual separator."""
        tk.Label(
            parent, 
            text=text.upper(), 
            font=("Segoe UI", 10, "bold"),
            fg=self.CARD_SECTION_FG, 
            bg=self.CARD_BG
        ).pack(anchor="w", pady=(12, 4))

    def _add_spacer(self, parent, height=8):
        """Add vertical spacing."""
        tk.Frame(parent, bg=self.CARD_BG, height=height).pack(fill="x")

    # ── Anki export ───────────────────────────────────────────────────
    def _save_to_anki(self):
        if not self._pinned_word or not self._pinned_word.is_definition_loaded:
            return
        self._show_deck_picker()

    def _show_deck_picker(self):
        from views.deck_picker import DeckPickerDialog

        def on_saved():
            if self._anki_btn:
                self._anki_btn.config(text="Saved", state="disabled", bg=self.CARD_BORDER)

        DeckPickerDialog(
            master=self.master,
            controller=self._controller,
            word=self._pinned_word,
            src_lang=self._get_src_lang(),
            on_saved=on_saved,
            anchor_window=self._pinned_card,
        )


