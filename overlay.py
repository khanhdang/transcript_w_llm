"""A movable, borderless subtitle window for presentations."""
import tkinter as tk
from tkinter import font as tkfont
from captions import caption_pages, split_sentences, wrap_lines


class SubtitleOverlay:
    def __init__(self, root):
        self.root = root
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        if root.tk.call("tk", "windowingsystem") == "aqua":
            try:
                self.window.tk.call("::tk::unsupported::MacWindowStyle", "style",
                                    self.window._w, "floating", "noActivates doesNotHide")
            except tk.TclError:
                pass
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.configure(background="#141414")
        self.font = tkfont.Font(root=root, family="Arial", size=28, weight="bold")
        self.preferred_size = 28
        self.label = tk.Label(self.window, text="", font=self.font, fg="white",
                              bg="#141414", padx=24, pady=14, justify="center")
        self.label.pack(fill="both", expand=True)
        self.width = min(1100, int(root.winfo_screenwidth() * 0.85))
        self.bottom = root.winfo_screenheight() - 70
        self.x = (root.winfo_screenwidth() - self.width) // 2
        self.visible = False
        self.text = ""
        self.timer = None
        self.pages = []
        self.page = 0
        self.drag_origin = None
        self.label.bind("<ButtonPress-1>", self.begin_drag)
        self.label.bind("<B1-Motion>", self.drag)
        self.window.bind("<Escape>", lambda event: self.hide())

    def begin_drag(self, event):
        self.drag_origin = (event.x_root, event.y_root, self.x, self.bottom)

    def drag(self, event):
        if self.drag_origin:
            start_x, start_y, x, bottom = self.drag_origin
            self.x = x + event.x_root - start_x
            self.bottom = bottom + event.y_root - start_y
            self.layout()

    def layout(self):
        height = int(self.font.metrics("linespace") * 3 + 28)
        y = self.bottom - height
        # Signed offsets also support monitors positioned left of the main display.
        self.window.geometry("{}x{}+{}+{}".format(self.width, height, self.x, y))

    def configure(self, size, opacity):
        self.preferred_size = int(size)
        try:
            self.window.attributes("-alpha", float(opacity))
        except tk.TclError:
            pass  # Some Linux window managers do not support window opacity.
        self.set_text(self.text)

    def reset_position(self):
        self.x = (self.root.winfo_screenwidth() - self.width) // 2
        self.bottom = self.root.winfo_screenheight() - 70
        self.layout()

    def show(self):
        self.visible = True
        self.layout()
        self.window.deiconify()
        self.window.attributes("-topmost", True)
        self.window.lift()
        if not self.text:
            self.label.configure(text="Translated speech will appear here")

    def hide(self):
        self.visible = False
        self.window.withdraw()

    def cancel_timer(self):
        if self.timer is not None:
            self.window.after_cancel(self.timer)
            self.timer = None

    def set_text(self, text):
        self.cancel_timer()
        self.text = text
        sentences = split_sentences(text)
        # Fit complete sentences into three lines before resorting to pagination.
        size = self.preferred_size
        self.font.configure(size=size)
        while size > 16 and any(len(wrap_lines(sentence, self.font.measure, self.width - 48)) > 3
                                for sentence in sentences):
            size -= 1
            self.font.configure(size=size)
        self.pages = caption_pages(text, self.font.measure, self.width - 48)
        self.page = 0
        self.layout()
        self.display_page()

    def display_page(self):
        self.timer = None
        self.label.configure(text=self.pages[self.page] if self.pages else "")
        if self.page + 1 < len(self.pages):
            # Give a longer caption more time to read, including CJK subtitles.
            duration = max(6000, min(20000, len(self.pages[self.page]) * 80))
            self.timer = self.window.after(duration, self.next_page)

    def next_page(self):
        self.page += 1
        self.display_page()

    def clear(self):
        self.set_text("")
