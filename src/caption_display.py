import time
import tkinter as tk
import tkinter.font as tkfont
from queue import Empty

from caption_stream import CaptionStream, WordPacer

FONT = ("Helvetica Neue", 32, "bold")
TEXT_COLOR = "white"
PLACEHOLDER_COLOR = "#666666"
VISIBLE_LINES = 3
HISTORY_LINES = 12
PAD_X = 40
PAD_Y = 20
POLL_MS = 100

# A new word ramps from dark grey to white.
FADE_COLORS = ("#3a3a3a", "#6e6e6e", "#a2a2a2", "#d6d6d6")
FADE_STEP_MS = 35

# Rows glide up instead of jumping.
SCROLL_DURATION_MS = 200
SCROLL_STEPS = 8


def _now_ms():
    return time.monotonic() * 1000


class CaptionDisplay:
    """A borderless, always-on-top subtitle overlay with rolling lines."""

    def __init__(self, translator):
        self.translator = translator
        self.stream = CaptionStream()
        self.pacer = WordPacer()
        self.jobs = set()
        self.closed = False
        self.has_words = False
        self.reveal_job = None
        self.last_reveal_ms = None
        self.fade_count = 0
        self.top_line = 0
        self.scroll_job = None
        self.scroll_steps = []
        self.drag_x = 0
        self.drag_y = 0

        self.root = tk.Tk()
        self.root.title("Live Translation")
        self.root.configure(bg="black")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        font = tkfont.Font(root=self.root, font=FONT)
        self.line_height = font.metrics("linespace")

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = min(1_200, screen_width - 80)
        height = self.line_height * VISIBLE_LINES + 2 * PAD_Y
        x = (screen_width - width) // 2
        y = screen_height - height - 70
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        self.text = tk.Text(
            self.root,
            font=font,
            fg=TEXT_COLOR,
            bg="black",
            height=VISIBLE_LINES,
            wrap="word",
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            insertwidth=0,
            cursor="arrow",
            takefocus=False,
        )
        self.text.tag_configure("placeholder", foreground=PLACEHOLDER_COLOR)
        self.text.insert("end", "Listening…", "placeholder")
        self.text.configure(state="disabled")
        self.text.pack(fill="x", padx=PAD_X, pady=PAD_Y)

        # A borderless window can be dragged from anywhere. Escape or q exits.
        for widget in (self.root, self.text):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)
        # Scrolling is driven by the overlay itself; user scrolls would put
        # it out of step, so the wheel and middle-button scan are ignored.
        for sequence in (
            "<MouseWheel>",
            "<Shift-MouseWheel>",
            "<Button-2>",
            "<B2-Motion>",
            "<Button-3>",
            "<B3-Motion>",
            "<Button-4>",
            "<Button-5>",
        ):
            self.text.bind(sequence, lambda _event: "break")
        self.root.bind("<Escape>", self.close)
        self.root.bind("q", self.close)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self._after(POLL_MS, self.update_text)

    def _after(self, delay_ms, callback, *args):
        """Schedule callback and track it so close() can cancel it."""

        def run():
            self.jobs.discard(job)
            if not self.closed:
                callback(*args)

        job = self.root.after(delay_ms, run)
        self.jobs.add(job)
        return job

    def _cancel(self, job):
        if job is not None:
            self.jobs.discard(job)
            self.root.after_cancel(job)

    def _start_drag(self, event):
        self.drag_x = event.x_root - self.root.winfo_x()
        self.drag_y = event.y_root - self.root.winfo_y()
        # Stop the Text widget from starting a selection.
        return "break"

    def _drag(self, event):
        x = event.x_root - self.drag_x
        y = event.y_root - self.drag_y
        self.root.geometry(f"+{x}+{y}")
        return "break"

    def update_text(self):
        while True:
            try:
                caption = self.translator.text_queue.get_nowait()
            except Empty:
                break
            self.pacer.push(self.stream.push(caption["translated"]), _now_ms())

        if len(self.pacer) and self.reveal_job is None:
            # Keep the rhythm if the previous word appeared moments ago.
            delay = 0
            if self.last_reveal_ms is not None:
                elapsed = _now_ms() - self.last_reveal_ms
                delay = max(0, int(self.pacer.next_interval() - elapsed))
            self.reveal_job = self._after(delay, self._reveal_word)

        self._after(POLL_MS, self.update_text)

    def _reveal_word(self):
        self.reveal_job = None
        word = self.pacer.pop()
        if word is None:
            return

        self.text.configure(state="normal")
        if not self.has_words:
            self.text.delete("1.0", "end")
            self.has_words = True
            prefix = ""
        else:
            prefix = " "
        self.fade_count += 1
        tag = f"fade{self.fade_count}"
        self.text.insert("end", prefix + word, tag)
        self.text.configure(state="disabled")
        self.last_reveal_ms = _now_ms()

        self._fade(tag, 0)
        self._scroll_to_bottom()

        if len(self.pacer):
            self.reveal_job = self._after(self.pacer.next_interval(), self._reveal_word)

    def _fade(self, tag, step):
        if step < len(FADE_COLORS):
            self.text.tag_configure(tag, foreground=FADE_COLORS[step])
            self._after(FADE_STEP_MS, self._fade, tag, step + 1)
        else:
            self.text.tag_delete(tag)

    def _display_lines(self):
        count = self.text.count("1.0", "end", "update", "displaylines")
        if isinstance(count, tuple):
            count = count[0]
        return count or 0

    def _scroll_to_bottom(self):
        # Line wrapping is meaningless until the widget has its real width.
        if not self.text.winfo_ismapped():
            return
        if self._display_lines() - VISIBLE_LINES <= self.top_line:
            return

        # Finishing may trim history, so measure the target afterwards.
        self._finish_scroll()
        target = max(0, self._display_lines() - VISIBLE_LINES)
        if target <= self.top_line:
            return
        distance = (target - self.top_line) * self.line_height
        self.top_line = target
        # Integer pixel steps that add up exactly to the distance.
        marks = [round(distance * i / SCROLL_STEPS) for i in range(SCROLL_STEPS + 1)]
        self.scroll_steps = [b - a for a, b in zip(marks, marks[1:])]
        self._scroll_step()

    def _scroll_step(self):
        self.scroll_job = None
        if not self.scroll_steps:
            self._trim_history()
            return
        pixels = self.scroll_steps.pop(0)
        if pixels:
            self.text.yview_scroll(pixels, "pixels")
        self.scroll_job = self._after(
            SCROLL_DURATION_MS // SCROLL_STEPS, self._scroll_step
        )

    def _finish_scroll(self):
        """Jump to the end of a running scroll so a new one starts cleanly."""
        self._cancel(self.scroll_job)
        self.scroll_job = None
        remaining = sum(self.scroll_steps)
        self.scroll_steps = []
        if remaining:
            self.text.yview_scroll(remaining, "pixels")
        self._trim_history()

    def _trim_history(self):
        """Drop the lines above the view once the history gets long."""
        if self.top_line + VISIBLE_LINES <= HISTORY_LINES:
            return
        self.text.configure(state="normal")
        self.text.delete(
            "1.0", f"1.0 + {self.top_line} display lines display linestart"
        )
        self.text.configure(state="disabled")
        self.top_line = 0
        self.text.yview_moveto(0)

    def close(self, _event=None):
        if self.closed:
            return
        self.closed = True
        for job in list(self.jobs):
            self.root.after_cancel(job)
        self.jobs.clear()
        self.root.destroy()

    def run(self):
        self.translator.start()
        try:
            self.root.mainloop()
        finally:
            self.translator.stop()
