# views/gui_app.py
import tkinter as tk
from tkinter import ttk
from queue import Queue, Empty
import pyaudiowpatch

from views.subtitle_overlay import SubtitleOverlay
from models.config import TranscriptionConfig
from controllers.app_controller import AppController

LANGUAGES = [
    ("English",    "en"),
    ("German",     "de"),
    ("French",     "fr"),
    ("Portuguese", "pt"),
    ("Spanish",    "es"),
    ("Italian",    "it"),
    ("Dutch",      "nl"),
    ("Polish",     "pl"),
    ("Turkish",    "tr"),
    ("Russian",    "ru"),
    ("Japanese",   "ja"),
    ("Korean",     "ko"),
    ("Chinese",    "zh"),
]

# Model descriptions for tooltips
MODEL_INFO = {
    "tiny":     "Fastest, least accurate (~1 GB VRAM, ~150 MB RAM)",
    "base":     "Fast, decent accuracy (~1 GB VRAM, ~300 MB RAM)",
    "small":    "Balanced speed/accuracy (~2 GB VRAM, ~500 MB RAM)",
    "medium":   "Slower, high accuracy (~5 GB VRAM, ~1.5 GB RAM)",
    "large-v2": "Very slow, highest accuracy (~10 GB VRAM, ~3 GB RAM)",
    "large-v3": "Newest large model (~10 GB VRAM, ~3 GB RAM)",
    "turbo":    "Fast large model, good balance (~6 GB VRAM, ~1.5 GB RAM)",
}


def list_loopback_devices():
    """Returns list of (device_index, name) — WASAPI loopback only."""
    devices = []
    p = pyaudiowpatch.PyAudio()
    try:
        host_api_count = p.get_host_api_count()
        wasapi_index   = None
        for i in range(host_api_count):
            api = p.get_host_api_info_by_index(i)
            if "WASAPI" in api.get("name", ""):
                wasapi_index = i
                break
        if wasapi_index is None:
            return devices
        api_info     = p.get_host_api_info_by_index(wasapi_index)
        device_count = api_info["deviceCount"]
        for n in range(device_count):
            di = p.get_device_info_by_host_api_device_index(wasapi_index, n)
            if di.get("isLoopbackDevice", False):
                devices.append((di["index"], di["name"]))
    finally:
        p.terminate()
    return devices


class ToolTip:
    """Simple tooltip for tkinter widgets."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        widget.bind("<Enter>", self.show_tip)
        widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font=("Segoe UI", 9))
        label.pack(ipadx=4, ipady=2)

    def hide_tip(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class TranscriberGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Live Transcriber — GPU Optimized")
        self.root.geometry("600x660")

        self._textbox_queue: Queue = Queue()
        self.controller = AppController()

        self.overlay = SubtitleOverlay(
            self.root,
            controller=self.controller,
            get_source_lang=self._get_transcription_lang,
            get_target_lang=lambda: "en",
        )

        self.is_running    = False
        self.model_loaded  = False

        self._subtitle_buffer: list = []
        self._max_words = 10

        # Try importing psutil for RAM monitoring (optional dependency)
        try:
            import psutil
            self._psutil = psutil
            self._process = psutil.Process()
            self._has_psutil = True
        except ImportError:
            self._has_psutil = False

        self._build_ui()
        self._refresh_devices()
        self.root.after(50, self._drain_textbox_queue)
        if self._has_psutil:
            self.root.after(2000, self._update_ram_label)

    def run(self):
        self.root.mainloop()

    def _get_transcription_lang(self) -> str:
        text = self.lang_combo.get()
        if not text:
            return "en"
        return text.split("(")[-1].replace(")", "").strip()

    # ── UI ───────────────────────────────────────────────────────────
    def _build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")

        # row 0: device
        ttk.Label(top, text="Loopback device:").grid(row=0, column=0, sticky="w")
        self.device_var   = tk.StringVar()
        self.device_combo = ttk.Combobox(top, textvariable=self.device_var,
                                         state="readonly", width=60)
        self.device_combo.grid(row=0, column=1, padx=8, sticky="we")
        refresh_btn = ttk.Button(top, text="↻", command=self._refresh_devices, width=3)
        refresh_btn.grid(row=0, column=2, padx=4)
        ToolTip(refresh_btn, "Re-scan audio devices\n(use if you plug in new hardware)")

        # row 1: model + transcription language
        ttk.Label(top, text="Model:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.model_var   = tk.StringVar(value="small")  # default to small for balance
        self.model_combo = ttk.Combobox(top, textvariable=self.model_var, state="readonly",
                                        values=list(MODEL_INFO.keys()), width=12)
        self.model_combo.grid(row=1, column=1, sticky="w", padx=8, pady=(8, 0))
        self.model_combo.bind("<<ComboboxSelected>>", self._on_model_select)

        self.model_info_label = ttk.Label(top, text=MODEL_INFO["small"],
                                          font=("Segoe UI", 8), foreground="gray")
        self.model_info_label.grid(row=2, column=1, sticky="w", padx=8)

        ttk.Label(top, text="Language:").grid(row=1, column=1, sticky="e", pady=(8, 0))
        lang_display    = [f"{name} ({code})" for name, code in LANGUAGES]
        self.lang_combo = ttk.Combobox(top, state="readonly", values=lang_display, width=18)
        self.lang_combo.grid(row=1, column=2, sticky="w", pady=(8, 0))
        self.lang_combo.current(0)

        # row 3: GPU + WAV save + load
        self.gpu_var = tk.BooleanVar(value=True)  # default ON for RTX 4070
        gpu_check = ttk.Checkbutton(top, text="Use GPU (CUDA)", variable=self.gpu_var)
        gpu_check.grid(row=3, column=0, sticky="w", padx=8, pady=(8, 0), columnspan=2)
        ToolTip(gpu_check, "Recommended: ON for RTX 4070\nUses float16 (optimal)")

        self.save_wav_var = tk.BooleanVar(value=False)  # default OFF (saves disk I/O)
        wav_check = ttk.Checkbutton(top, text="Save recording to WAV", variable=self.save_wav_var)
        wav_check.grid(row=3, column=1, sticky="e", pady=(8, 0))
        ToolTip(wav_check, "Save last 5 min of audio to disk after stopping\n(buffer is capped, no RAM impact)")

        self.load_btn = ttk.Button(top, text="Load Model", command=self._load_model)
        self.load_btn.grid(row=3, column=2, sticky="w", pady=(8, 0))

        # row 4: mode selection
        ttk.Label(top, text="Mode:").grid(row=4, column=0, sticky="w", pady=(8, 0))
        self.mode_combo = ttk.Combobox(top, state="readonly", values=[
            "Fast (300ms, quick response)",
            "VAD (pause detection, highest accuracy)",
            "Accurate (700ms, continuous speech)",
        ], width=40)
        self.mode_combo.grid(row=4, column=1, sticky="w", padx=8, pady=(8, 0))
        self.mode_combo.current(1)  # default to VAD

        self.translate_var = tk.BooleanVar(value=False)
        translate_check = ttk.Checkbutton(
            top, text="Translate → EN",
            variable=self.translate_var,
            command=self._on_translate_toggle,
        )
        translate_check.grid(row=4, column=2, sticky="w", pady=(8, 0))
        ToolTip(translate_check, "Translate foreign speech to English subtitles\n(uses Whisper's built-in translation)")

        # row 5: dual subtitle toggle
        self.dual_sub_var = tk.BooleanVar(value=False)
        dual_sub_check = ttk.Checkbutton(
            top, text="Show Translation (EN)",
            variable=self.dual_sub_var,
            command=self._on_dual_subtitle_toggle,
        )
        dual_sub_check.grid(row=5, column=1, sticky="w", padx=8, pady=(4, 0))
        ToolTip(dual_sub_check,
                "Show English translation below the original subtitles\n"
                "(uses Google Translate — requires internet)")

        # buttons
        btns = ttk.Frame(self.root, padding=10)
        btns.pack(fill="x")
        self.start_btn = ttk.Button(btns, text="Start", command=self._start, state="disabled")
        self.start_btn.pack(side="left")
        self.stop_btn  = ttk.Button(btns, text="Stop",  command=self._stop,  state="disabled")
        self.stop_btn.pack(side="left", padx=8)
        
        clear_btn = ttk.Button(btns, text="Clear", command=self._clear)
        clear_btn.pack(side="left", padx=8)
        ToolTip(clear_btn, "Clear transcript text and subtitle overlay")
        
        self.unload_btn = ttk.Button(btns, text="Unload Model", command=self._unload_model, state="disabled")
        self.unload_btn.pack(side="left", padx=8)
        ToolTip(self.unload_btn, "Free VRAM/RAM by unloading Whisper model\n(must reload before starting again)")
        
        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(btns, textvariable=self.status_var).pack(side="left", padx=12)
        
        # RAM monitor (if psutil available)
        if self._has_psutil:
            self.ram_var = tk.StringVar(value="RAM: — MB")
            ttk.Label(btns, textvariable=self.ram_var, font=("Segoe UI", 9),
                      foreground="blue").pack(side="right")
        else:
            ttk.Label(btns, text="(install psutil for RAM monitor)", 
                     font=("Segoe UI", 8), foreground="gray").pack(side="right")

        # transcript text box
        mid = ttk.Frame(self.root, padding=10)
        mid.pack(fill="both", expand=True)
        self.text = tk.Text(mid, wrap="word", height=20)
        self.text.pack(fill="both", expand=True)

        # info footer
        footer = ttk.Label(self.root, 
                          text="💡 Audio buffer capped at 5 min (~65 MB RAM) — safe for long recordings",
                          font=("Segoe UI", 8), foreground="green")
        footer.pack(pady=4)

        top.columnconfigure(1, weight=1)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_translate_toggle(self):
        """Toggle translate mode on the controller (works mid-session)."""
        enabled = self.translate_var.get()
        if enabled:
            # Mutually exclusive with dual subtitle
            self.dual_sub_var.set(False)
            self.controller.set_dual_subtitle(False)
            self.overlay.set_translation_visible(False)
        self.controller.set_translate(enabled)

    def _on_dual_subtitle_toggle(self):
        """Toggle dual subtitle (original + English translation)."""
        enabled = self.dual_sub_var.get()
        if enabled:
            # Mutually exclusive with Whisper translate
            self.translate_var.set(False)
            self.controller.set_translate(False)
        self.controller.set_dual_subtitle(enabled)
        self.overlay.set_translation_visible(enabled)

    def _on_model_select(self, event):
        """Update model info label when model is selected."""
        model = self.model_var.get()
        self.model_info_label.config(text=MODEL_INFO.get(model, ""))

    # ── device ───────────────────────────────────────────────────────
    def _refresh_devices(self):
        devices       = list_loopback_devices()
        self._devices = devices
        display       = [f"[{idx}] {name}" for idx, name in devices]
        self.device_combo["values"] = display
        if display:
            self.device_combo.current(0)
        else:
            self.device_combo.set("No WASAPI loopback devices found")

    # ── RAM monitor ──────────────────────────────────────────────────
    def _update_ram_label(self):
        if not self._has_psutil:
            return
        try:
            mem_mb = self._process.memory_info().rss / 1024 / 1024
            self.ram_var.set(f"RAM: {mem_mb:.0f} MB")
        except Exception:
            self.ram_var.set("RAM: —")
        self.root.after(2000, self._update_ram_label)

    # ── start / stop ─────────────────────────────────────────────────
    def _start(self):
        if not self.model_loaded or not self.controller.is_transcription_loaded:
            self.status_var.set("Load model first")
            return
        if self.is_running:
            return

        self.is_running = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.unload_btn.config(state="disabled")
        self.status_var.set("Recording…")
        self.overlay.show()

        mode = self.mode_combo.get()

        if mode.startswith("Fast"):
            self.controller.start_live_background(
                on_words_callback=self._on_words,
                mode="fast",
            )
        elif mode.startswith("VAD"):
            self.controller.start_live_background(
                on_words_callback=self._on_words,
                mode="vad",
            )
        else:  # Accurate
            self.controller.start_live_background(
                on_words_callback=self._on_words,
                mode="accurate",
            )

    def _stop(self):
        if not self.is_running:
            return
        self.status_var.set("Stopping…")
        self.root.update_idletasks()
        if self.controller.is_transcription_loaded:
            save_wav = self.save_wav_var.get()
            self.controller.stop_live_background(save_wav=save_wav)
        self.is_running = False
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.unload_btn.config(state="normal")
        self.status_var.set("Idle")
        self.overlay.hide()

    # ── unload model ────────────────────────────────────────────────
    def _unload_model(self):
        if not self.model_loaded:
            return
        if self.is_running:
            self.status_var.set("Stop transcription first")
            return
        
        self.controller.unload_transcription()
        self.model_loaded = False
        self.start_btn.config(state="disabled")
        self.unload_btn.config(state="disabled")
        self.load_btn.config(state="normal")
        self.status_var.set("Model unloaded — VRAM freed")
        
        # Force garbage collection to release VRAM faster
        import gc
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    # ── callback (background thread) ─────────────────────────────────
    def _on_words(self, words):
        new_words = [w for w in words if w.text.strip()]
        if not new_words:
            return

        self._subtitle_buffer.extend(new_words)
        self._subtitle_buffer = self._subtitle_buffer[-self._max_words:]

        self.overlay.queue.put(("WORDS", list(self._subtitle_buffer)))
        self._textbox_queue.put(" ".join(w.text for w in new_words))

        # Dual subtitle: translate the current buffer sentence
        if self.controller.is_dual_subtitle_enabled:
            sentence = " ".join(w.text for w in self._subtitle_buffer)
            src_lang = self._get_transcription_lang()
            self.controller.translate_subtitle(
                sentence, src_lang,
                callback=lambda translated: self.overlay.queue.put(
                    ("TRANSLATION", translated)
                ),
            )

    # ── textbox drain (Tk thread) ────────────────────────────────────
    def _drain_textbox_queue(self):
        try:
            while True:
                text = self._textbox_queue.get_nowait()
                self.text.insert("end", text + " ")
                self.text.see("end")
        except Empty:
            pass
        self.root.after(50, self._drain_textbox_queue)

    # ── helpers ──────────────────────────────────────────────────────
    def _clear(self):
        self.text.delete("1.0", "end")
        self._subtitle_buffer.clear()
        self.overlay.clear()

    def _on_close(self):
        try:
            self._stop()
        finally:
            self.root.destroy()

    def _load_model(self):
        if self.model_loaded:
            self.status_var.set("Model already loaded ✓")
            return

        selected  = self.device_combo.get()
        if not selected or "No WASAPI" in selected:
            self.status_var.set("Select a valid audio device first")
            return
            
        device_id = int(selected.split("]")[0].replace("[", ""))
        lang_code = self._get_transcription_lang()

        config = TranscriptionConfig(
            model_size=self.model_var.get(),
            device_id=device_id,
            use_gpu=self.gpu_var.get(),
            language=lang_code,
        )

        self.status_var.set("Loading model…")
        self.root.update_idletasks()

        try:
            self.controller.load_transcription(config)
            self.model_loaded = True
            self.status_var.set("Model loaded ✓  Ready")
            self.start_btn.config(state="normal")
            self.unload_btn.config(state="normal")
        except Exception as e:
            self.status_var.set(f"Error loading model: {e}")
            self.model_loaded = False