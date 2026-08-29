import tkinter as tk


class CaptionDisplay:
    """A borderless, always-on-top subtitle overlay."""

    def __init__(self, translator, caption_timeout_ms=7_000):
        self.translator = translator
        self.caption_timeout_ms = caption_timeout_ms
        self.clear_job = None
        self.drag_x = 0
        self.drag_y = 0

        self.root = tk.Tk()
        self.root.title("Live Translation")
        self.root.configure(bg="black")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = min(1_200, screen_width - 80)
        height = 180
        x = (screen_width - width) // 2
        y = screen_height - height - 70
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        self.label = tk.Label(
            self.root,
            text="Listening…",
            font=("Helvetica Neue", 32, "bold"),
            fg="white",
            bg="black",
            wraplength=width - 80,
            justify="center",
        )
        self.label.pack(expand=True, fill="both", padx=40, pady=20)

        # A borderless window can be dragged from anywhere. Escape or q exits.
        for widget in (self.root, self.label):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)
        self.root.bind("<Escape>", self.close)
        self.root.bind("q", self.close)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.root.after(100, self.update_text)

    def _start_drag(self, event):
        self.drag_x = event.x_root - self.root.winfo_x()
        self.drag_y = event.y_root - self.root.winfo_y()

    def _drag(self, event):
        x = event.x_root - self.drag_x
        y = event.y_root - self.drag_y
        self.root.geometry(f"+{x}+{y}")

    def _clear_caption(self):
        self.label.config(text="")
        self.clear_job = None

    def update_text(self):
        latest = None
        while not self.translator.text_queue.empty():
            latest = self.translator.text_queue.get()

        if latest is not None:
            self.label.config(text=latest["translated"])
            if self.clear_job is not None:
                self.root.after_cancel(self.clear_job)
            self.clear_job = self.root.after(
                self.caption_timeout_ms, self._clear_caption
            )

        self.root.after(100, self.update_text)

    def close(self, _event=None):
        self.root.destroy()

    def run(self):
        self.translator.start()
        try:
            self.root.mainloop()
        finally:
            self.translator.stop()
