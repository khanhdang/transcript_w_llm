"""Microphone → faster-whisper → Ollama → desktop text display."""
import io
import os
import queue
import sys
import threading
import time
import wave

if sys.platform == "darwin":
    os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from backend import AudioBuffer, OllamaClient
from overlay import SubtitleOverlay
from captions import SentenceBuffer
from presentation import load_presentation, recognition_hint, translation_context, prepared_translation

LANGUAGES = {"Auto detect": None, "English": "en", "Vietnamese": "vi",
             "Japanese": "ja", "Chinese": "zh", "Korean": "ko", "French": "fr",
             "German": "de", "Spanish": "es", "Portuguese": "pt", "Russian": "ru",
             "Arabic": "ar", "Hindi": "hi", "Thai": "th", "Indonesian": "id"}


class App:
    def __init__(self, root):
        self.root = root
        root.title("Local Speech Translator")
        root.geometry("1050x720")
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.running = False
        self.recognizer = None
        self.recognizer_name = None
        self.sentence_buffer = SentenceBuffer()
        self.presentation = None
        self.context_snapshot = None
        self.active_context = None
        self.devices = {"System default": None}
        self.fields = {}
        self.overlay = SubtitleOverlay(root)
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Local Speech Translator", font=("Arial", 22, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Speak into your microphone. Your transcript and translation appear below.").pack(anchor="w", pady=(4, 12))
        settings = ttk.Frame(frame)
        settings.pack(fill="x")
        definitions = [
            ("Microphone", "System default", ["System default"]),
            ("Spoken language", "Auto detect", list(LANGUAGES)),
            ("Translate to", "English", [x for x in LANGUAGES if x != "Auto detect"]),
            ("Speech model", "base", ["tiny", "base", "small", "medium", "large-v3"]),
            ("Ollama model", "", []),
            ("Ollama address", "http://localhost:11434", None),
            ("Chunk seconds", "3", ["1", "2", "3", "5", "8", "10"]),
        ]
        self.inputs = []
        for row, (label, default, choices) in enumerate(definitions):
            ttk.Label(settings, text=label).grid(row=row, column=0, sticky="w", pady=3)
            var = tk.StringVar(value=default)
            self.fields[label] = var
            widget = ttk.Entry(settings, textvariable=var) if choices is None else ttk.Combobox(
                settings, textvariable=var, values=choices,
                state="normal" if label in ("Ollama model", "Translate to") else "readonly")
            widget.grid(row=row, column=1, sticky="ew", padx=12, pady=3)
            self.inputs.append(widget)
        settings.columnconfigure(1, weight=1)
        context_panel = ttk.Labelframe(frame, text="Presentation context", padding=6)
        context_panel.pack(fill="x", pady=(8, 0))
        self.load_context_button = ttk.Button(context_panel, text="Load slides / context", command=self.load_context)
        self.load_context_button.pack(side="left")
        self.clear_context_button = ttk.Button(context_panel, text="Remove", command=self.remove_context)
        self.clear_context_button.pack(side="left", padx=4)
        self.slide_var = tk.StringVar()
        self.slide_selector = ttk.Combobox(context_panel, textvariable=self.slide_var, state="readonly", width=32)
        self.slide_selector.pack(side="left", padx=4)
        self.slide_selector.bind("<<ComboboxSelected>>", self.select_slide)
        ttk.Button(context_panel, text="Previous", command=lambda: self.move_slide(-1)).pack(side="left")
        ttk.Button(context_panel, text="Next", command=lambda: self.move_slide(1)).pack(side="left", padx=4)
        self.context_label = tk.StringVar(value="No presentation loaded")
        ttk.Label(context_panel, textvariable=self.context_label).pack(side="left", padx=4)
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=12)
        self.start_button = ttk.Button(controls, text="Start listening", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(controls, text="Stop", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=6)
        self.refresh_button = ttk.Button(controls, text="Refresh microphones / models", command=self.refresh)
        self.refresh_button.pack(side="left", padx=6)
        ttk.Button(controls, text="Save text", command=self.save).pack(side="right")
        ttk.Button(controls, text="Clear", command=self.clear).pack(side="right", padx=6)
        overlay_controls = ttk.Frame(frame)
        overlay_controls.pack(fill="x", pady=(0, 10))
        self.overlay_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(overlay_controls, text="Show slide subtitles", variable=self.overlay_enabled,
                        command=self.toggle_overlay).pack(side="left")
        ttk.Label(overlay_controls, text="Text size").pack(side="left", padx=(12, 4))
        self.subtitle_size = tk.IntVar(value=28)
        ttk.Spinbox(overlay_controls, from_=16, to=60, width=4,
                    textvariable=self.subtitle_size, state="readonly",
                    command=self.configure_overlay).pack(side="left")
        ttk.Label(overlay_controls, text="Opacity").pack(side="left", padx=(12, 4))
        self.subtitle_opacity = tk.DoubleVar(value=0.9)
        ttk.Scale(overlay_controls, from_=0.35, to=1.0, length=90,
                  variable=self.subtitle_opacity, command=lambda value: self.configure_overlay()).pack(side="left")
        ttk.Button(overlay_controls, text="Preview subtitles", command=self.preview_overlay).pack(side="left", padx=8)
        ttk.Button(overlay_controls, text="Reset position", command=self.overlay.reset_position).pack(side="left")
        self.configure_overlay()
        panes = ttk.Panedwindow(frame, orient="horizontal")
        panes.pack(fill="both", expand=True)
        self.texts = []
        for title in ("Transcript", "Translation"):
            panel = ttk.Labelframe(panes, text=title, padding=8)
            text = scrolledtext.ScrolledText(panel, wrap="word", font=("Arial", 15), width=35, state="disabled")
            text.pack(fill="both", expand=True)
            panes.add(panel, weight=1)
            self.texts.append(text)
        self.status = tk.StringVar(value="Ready. Refresh to select an installed Ollama model.")
        ttk.Label(frame, textvariable=self.status, wraplength=980).pack(anchor="w", pady=(10, 0))
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)
        self.refresh()

    def load_context(self):
        path = filedialog.askopenfilename(filetypes=[("Presentation context", "*.json *.pptx *.txt *.md *.markdown"),
                                                   ("Markdown slides", "*.md *.markdown")])
        if not path:
            return
        try:
            data = load_presentation(path)
        except Exception as exc:
            messagebox.showerror("Presentation load failed", str(exc))
            return
        self.presentation = data
        self.slide_selector.configure(values=[str(i + 1) + ": " + (s.get("title") or s.get("text", "").split("\n")[0] or "Slide")[:45]
                                              for i, s in enumerate(data["slides"])])
        self.slide_selector.current(0)
        self.select_slide()
        self.context_label.set(str(len(data["slides"])) + " slides loaded")

    def remove_context(self):
        self.presentation = None
        self.context_snapshot = None
        self.slide_selector.configure(values=[])
        self.slide_var.set("")
        self.context_label.set("No presentation loaded")

    def select_slide(self, event=None):
        if self.presentation is not None:
            self.context_snapshot = (self.presentation, self.slide_selector.current())

    def move_slide(self, step):
        if self.presentation is not None:
            index = max(0, min(len(self.presentation["slides"]) - 1, self.slide_selector.current() + step))
            self.slide_selector.current(index)
            self.select_slide()

    def refresh(self):
        url = self.fields["Ollama address"].get()
        self.refresh_button.configure(state="disabled")
        def work():
            try:
                import sounddevice as sd
                devices = {"System default": None}
                for i, device in enumerate(sd.query_devices()):
                    if device["max_input_channels"] > 0:
                        devices[str(i) + ": " + device["name"]] = i
                self.events.put(("devices", devices))
            except Exception as exc:
                self.events.put(("status", "Microphone discovery failed: " + str(exc)))
            try:
                self.events.put(("models", OllamaClient(url).models()))
            except Exception as exc:
                self.events.put(("status", str(exc)))
            finally:
                self.events.put(("refreshed", None))
        threading.Thread(target=work, daemon=True).start()

    def start(self):
        if self.running:
            return
        config = {key: value.get().strip() for key, value in self.fields.items()}
        try:
            client = OllamaClient(config["Ollama address"])
            if not config["Ollama model"] or not config["Translate to"]:
                raise ValueError("Select an installed Ollama model and a target language.")
            seconds = float(config["Chunk seconds"])
            if not 1 <= seconds <= 15:
                raise ValueError("Chunk duration must be between 1 and 15 seconds.")
        except ValueError as exc:
            messagebox.showerror("Settings", str(exc))
            return
        self.running = True
        self.sentence_buffer = SentenceBuffer()
        self.active_context = self.context_snapshot
        self.stop_event.clear()
        self.set_controls(True)
        device = self.devices.get(config["Microphone"])
        threading.Thread(target=self.listen, args=(config, client, seconds, device), daemon=True).start()

    def listen(self, config, client, seconds, device):
        try:
            import sounddevice as sd
            from faster_whisper import WhisperModel
            self.events.put(("status", "Checking Ollama…"))
            if config["Ollama model"] not in client.models():
                raise RuntimeError("Model is not installed. Run ollama pull MODEL, then refresh.")
            name = config["Speech model"]
            if self.recognizer_name != name:
                self.events.put(("status", "Loading speech model (first use downloads model files)…"))
                self.recognizer = WhisperModel(name, device="cpu", compute_type="int8")
                self.recognizer_name = name
            if self.stop_event.is_set():
                return
            rate = int(sd.query_devices(device, "input")["default_samplerate"])
            buffer = AudioBuffer(int(rate * 2 * max(30, seconds * 2)))
            def callback(data, frames, timing, status):
                buffer.add(bytes(data))
                if status:
                    self.events.put(("status", "Microphone warning: " + str(status)))
            with sd.RawInputStream(device=device, samplerate=rate, channels=1,
                                   dtype="int16", callback=callback):
                next_chunk = time.monotonic() + seconds
                while not self.stop_event.is_set():
                    self.events.put(("status", "Listening…"))
                    # Capture continues during processing. Only wait for the
                    # remainder of the interval, not another full interval.
                    self.stop_event.wait(max(0, next_chunk - time.monotonic()))
                    audio, dropped = buffer.take()
                    next_chunk = time.monotonic() + seconds
                    if dropped:
                        self.events.put(("status", "Processing is slower than recording; older audio was dropped. Try a smaller model or longer chunks."))
                    if len(audio) < rate // 2:
                        continue
                    self.process(audio, rate, config, client)
                audio, dropped = buffer.take()
                if len(audio) >= rate // 2:
                    self.process(audio, rate, config, client)
            remaining = self.sentence_buffer.flush()
            if remaining:
                self.translate_caption(remaining, time.strftime("%H:%M:%S"), config, client, self.active_context)
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            self.events.put(("finished", None))

    def process(self, audio, rate, config, client):
        context = self.context_snapshot
        if context != self.active_context:
            remaining = self.sentence_buffer.flush()
            if remaining:
                self.translate_caption(remaining, time.strftime("%H:%M:%S"), config, client, self.active_context)
            self.active_context = context
        self.events.put(("status", "Transcribing…"))
        wav = io.BytesIO()
        with wave.open(wav, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(rate)
            output.writeframes(audio)
        wav.seek(0)
        segments, info = self.recognizer.transcribe(
            wav, language=LANGUAGES[config["Spoken language"]], vad_filter=True,
            beam_size=1, condition_on_previous_text=False,
            initial_prompt=recognition_hint(*context) if context else None)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        stamp = time.strftime("%H:%M:%S")
        if text:
            self.events.put(("transcript", "[" + stamp + "] " + text + "\n\n"))
        ready = self.sentence_buffer.feed(text)
        if ready:
            self.translate_caption(ready, stamp, config, client, context)

    def translate_caption(self, text, stamp, config, client, context=None):
        self.events.put(("status", "Translating to " + config["Translate to"] + "…"))
        try:
            translated = prepared_translation(*context, text, config["Translate to"]) if context else None
            if translated is None:
                reference = translation_context(*context, config["Translate to"]) if context else None
                translated = client.translate(text, config["Translate to"], config["Ollama model"], context=reference)
            self.events.put(("subtitle", translated))
        except Exception as exc:
            translated = "[Translation failed: " + str(exc) + "]"
        self.events.put(("translation", "[" + stamp + "] " + translated + "\n\n"))

    def set_controls(self, running):
        self.load_context_button.configure(state="disabled" if running else "normal")
        self.clear_context_button.configure(state="disabled" if running else "normal")
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        self.refresh_button.configure(state="disabled" if running else "normal")
        for widget in self.inputs:
            widget.configure(state="disabled" if running else (
                "readonly" if isinstance(widget, ttk.Combobox) and widget not in (self.inputs[2], self.inputs[4]) else "normal"))

    def stop(self):
        self.stop_event.set()
        self.stop_button.configure(state="disabled")
        self.status.set("Stopping after current processing and final audio…")

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind in ("transcript", "translation"):
                    text = self.texts[0 if kind == "transcript" else 1]
                    text.configure(state="normal")
                    text.insert("end", value)
                    text.see("end")
                    text.configure(state="disabled")
                elif kind == "devices":
                    self.devices = value
                    self.inputs[0].configure(values=list(value))
                elif kind == "subtitle":
                    self.overlay.set_text(value)
                elif kind == "models":
                    self.inputs[4].configure(values=value)
                    if value and not self.fields["Ollama model"].get():
                        self.fields["Ollama model"].set(value[0])
                    if not value:
                        self.status.set("No Ollama models installed. Run ollama pull MODEL, then refresh.")
                elif kind == "refreshed":
                    if not self.running:
                        self.refresh_button.configure(state="normal")
                elif kind == "finished":
                    self.running = False
                    self.set_controls(False)
                    if not self.status.get().startswith("Error:"):
                        self.status.set("Stopped.")
                elif kind == "error":
                    self.status.set("Error: " + value)
                    messagebox.showerror("Unable to listen", value)
                else:
                    self.status.set(value)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def toggle_overlay(self):
        if self.overlay_enabled.get():
            self.overlay.show()
        else:
            self.overlay.hide()

    def configure_overlay(self):
        self.overlay.configure(self.subtitle_size.get(), self.subtitle_opacity.get())

    def preview_overlay(self):
        self.overlay_enabled.set(True)
        self.overlay.set_text("Your translated speech appears here while you present your slides.")
        self.overlay.show()

    def clear(self):
        self.overlay.clear()
        for text in self.texts:
            text.configure(state="normal")
            text.delete("1.0", "end")
            text.configure(state="disabled")

    def save(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if path:
            try:
                with open(path, "w", encoding="utf-8") as output:
                    output.write("TRANSCRIPT\n" + self.texts[0].get("1.0", "end") +
                                 "\nTRANSLATION\n" + self.texts[1].get("1.0", "end"))
            except OSError as exc:
                messagebox.showerror("Save failed", str(exc))

    def close(self):
        self.stop_event.set()
        self.root.destroy()


if __name__ == "__main__":
    if sys.platform == "darwin" and tk.TkVersion < 8.6:
        raise SystemExit(
            "This Python uses Apple's obsolete Tk 8.5, which can display a blank window.\n"
            "Use Python 3.12 with modern Tk. See the macOS setup instructions in README.md.")
    root = tk.Tk()
    App(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        # Treat terminal Ctrl+C like closing the application window.
        try:
            root.destroy()
        except tk.TclError:
            pass
