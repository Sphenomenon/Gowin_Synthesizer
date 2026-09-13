"""Reusable Tk controls; this module has no serial or instrument dependencies."""
from __future__ import annotations

import math
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Callable, Iterable, Mapping


COLORS = {
    "bg": "#0e141c",
    "panel": "#171f2a",
    "panel_alt": "#1d2835",
    "border": "#2c3949",
    "text": "#ecf2f7",
    "muted": "#91a1b6",
    "accent": "#49d8b5",
    "accent_hover": "#79e7cb",
    "amber": "#f5be68",
    "danger": "#ff858b",
}
FONT_UI = "Microsoft YaHei UI"
FONT_MONO = "Cascadia Code"


def setup_theme(root: tk.Misc) -> dict[str, str]:
    """Install shared dark ttk styles and return the palette used by canvases."""
    root.configure(background=COLORS["bg"])
    root.option_add("*Font", (FONT_UI, 10))
    root.option_add("*TCombobox*Listbox.background", COLORS["panel_alt"])
    root.option_add("*TCombobox*Listbox.foreground", COLORS["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", COLORS["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", COLORS["bg"])
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=(FONT_UI, 10), background=COLORS["bg"],
                    foreground=COLORS["text"], bordercolor=COLORS["border"],
                    darkcolor=COLORS["border"], lightcolor=COLORS["border"],
                    troughcolor=COLORS["panel_alt"], selectbackground=COLORS["accent"],
                    selectforeground=COLORS["bg"])
    style.configure("TFrame", background=COLORS["bg"])
    for name in ("Panel", "Card"):
        style.configure(f"{name}.TFrame", background=COLORS["panel"])
        style.configure(f"{name}.TLabel", background=COLORS["panel"])
    style.configure("Alt.TFrame", background=COLORS["panel_alt"])
    style.configure("TLabel", background=COLORS["bg"])
    style.configure("Muted.TLabel", foreground=COLORS["muted"])
    style.configure("Muted.Panel.TLabel", background=COLORS["panel"], foreground=COLORS["muted"])
    style.configure("Title.TLabel", font=(FONT_UI, 22, "bold"))
    style.configure("Subtitle.TLabel", font=(FONT_UI, 10), foreground=COLORS["muted"])
    style.configure("Section.TLabel", font=(FONT_UI, 12, "bold"), background=COLORS["panel"])
    style.configure("Accent.TLabel", foreground=COLORS["accent"])
    style.configure("Mono.TLabel", font=(FONT_MONO, 10))
    style.configure("TButton", background=COLORS["panel_alt"], foreground=COLORS["text"],
                    borderwidth=1, padding=(12, 8), focusthickness=0)
    style.map("TButton", background=[("active", "#2b3b4e"), ("pressed", "#34495d")],
              foreground=[("disabled", "#617287")], bordercolor=[("focus", COLORS["accent"])])
    style.configure("Accent.TButton", background=COLORS["accent"], foreground=COLORS["bg"],
                    font=(FONT_UI, 10, "bold"), bordercolor=COLORS["accent"])
    style.map("Accent.TButton", background=[("disabled", "#244b45"),
              ("active", COLORS["accent_hover"]), ("pressed", "#30b796")],
              foreground=[("disabled", "#82a19c")])
    style.configure("Danger.TButton", background="#472b35", foreground="#ffb3b7", bordercolor="#69404a")
    style.map("Danger.TButton", background=[("active", "#623541"), ("pressed", "#733c4a")])
    style.configure("TEntry", fieldbackground=COLORS["panel_alt"], foreground=COLORS["text"],
                    insertcolor=COLORS["accent"], borderwidth=1, padding=(8, 6))
    style.map("TEntry", bordercolor=[("focus", COLORS["accent"]), ("disabled", COLORS["border"])])
    for name in ("TCombobox", "TSpinbox"):
        style.configure(name, fieldbackground=COLORS["panel_alt"], background=COLORS["panel_alt"],
                        foreground=COLORS["text"], arrowcolor=COLORS["muted"],
                        insertcolor=COLORS["accent"], borderwidth=1, padding=(8, 6))
        style.map(name, fieldbackground=[("readonly", COLORS["panel_alt"]),
                  ("disabled", COLORS["panel"])], foreground=[("readonly", COLORS["text"]),
                  ("disabled", "#617287")], background=[("active", "#2b3b4e")],
                  bordercolor=[("focus", COLORS["accent"])])
    style.configure("Horizontal.TScale", background=COLORS["panel"],
                    troughcolor=COLORS["border"], borderwidth=0, sliderlength=16)
    style.map("Horizontal.TScale", background=[("active", COLORS["accent"])])
    style.configure("TCheckbutton", background=COLORS["panel"], indicatorbackground=COLORS["panel_alt"])
    style.map("TCheckbutton", background=[("active", COLORS["panel"])],
              indicatorbackground=[("selected", COLORS["accent"])])
    style.configure("TSeparator", background=COLORS["border"])
    style.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", padding=(14, 8), background=COLORS["panel_alt"])
    style.map("TNotebook.Tab", background=[("selected", COLORS["panel"])],
              foreground=[("selected", COLORS["accent"])])
    style.configure("Vertical.TScrollbar", background=COLORS["border"],
                    troughcolor=COLORS["panel"], borderwidth=0, arrowcolor=COLORS["muted"])
    return dict(COLORS)


class StatusPill(tk.Canvas):
    """Compact status indicator with text so status never relies on color alone."""

    TONES = {
        "muted": ("#253140", COLORS["muted"]),
        "success": ("#193c35", COLORS["accent"]),
        "warning": ("#433726", COLORS["amber"]),
        "error": ("#482b36", COLORS["danger"]),
    }

    def __init__(self, master: tk.Misc, text: str = "", tone: str = "muted", **kwargs):
        kwargs.setdefault("background", COLORS["panel"])
        kwargs.setdefault("height", 28)
        kwargs.setdefault("highlightthickness", 0)
        super().__init__(master, **kwargs)
        self._font = tkfont.Font(self, family=FONT_UI, size=9)
        self._text = ""
        self._tone = "muted"
        self.bind("<Configure>", self._draw)
        self.set_status(text, tone)

    def set_status(self, text: str, tone: str = "muted") -> None:
        self._text, self._tone = str(text), tone
        self.configure(width=max(44, self._font.measure(self._text) + 38))
        self._draw()

    def _draw(self, _event=None) -> None:
        self.delete("all")
        width = max(self.winfo_width(), int(self.cget("width")))
        height = max(14, self.winfo_height() if self.winfo_height() > 1 else int(self.cget("height")))
        fill, foreground = self.TONES.get(self._tone, self.TONES["muted"])
        radius = min(height / 2 - 1, width / 2)
        self.create_rectangle(radius, 1, width - radius, height - 1, fill=fill, outline=fill)
        self.create_oval(1, 1, 2 * radius, height - 1, fill=fill, outline=fill)
        self.create_oval(width - 2 * radius, 1, width - 1, height - 1, fill=fill, outline=fill)
        self.create_oval(11, height / 2 - 3, 17, height / 2 + 3, fill=foreground, outline="")
        self.create_text(25, height / 2, anchor="w", text=self._text, font=self._font, fill=foreground)


class PianoKeyboard(tk.Canvas):
    """C4–C6 piano with independent pointer and controller note highlights.

    A local pointer grab delivers button release even outside the canvas. Moving
    outside its keys releases the current pointer note; dragging onto another
    key performs note-off followed by note-on. Callbacks never run in response
    to ``set_active_notes``. The application owns computer-keyboard bindings.
    """

    FIRST_NOTE, LAST_NOTE = 60, 84
    BLACK_CLASSES = frozenset((1, 3, 6, 8, 10))
    DEFAULT_KEY_LABELS = dict(zip(range(60, 79),
                                 ("A", "W", "S", "E", "D", "F", "T", "G", "Y", "H",
                                  "U", "J", "K", "O", "L", "P", ";", "'", "]")))

    def __init__(self, master: tk.Misc,
                 on_note_on: Callable[[int], None] | None = None,
                 on_note_off: Callable[[int], None] | None = None,
                 key_labels: Mapping[int, str] | None = None, **kwargs):
        kwargs.setdefault("background", COLORS["panel"])
        kwargs.setdefault("height", 178)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("cursor", "hand2")
        kwargs.setdefault("takefocus", False)
        super().__init__(master, **kwargs)
        self.on_note_on, self.on_note_off = on_note_on, on_note_off
        self._key_labels = dict(self.DEFAULT_KEY_LABELS if key_labels is None else key_labels)
        self._active_notes: set[int] = set()
        self._enabled = True
        self._pointer_down = False
        self._pointer_note: int | None = None
        self._white_keys: list[tuple[int, tuple[float, float, float, float]]] = []
        self._black_keys: list[tuple[int, tuple[float, float, float, float]]] = []
        self.bind("<Configure>", self._draw)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Leave>", self._leave)
        self.bind("<Destroy>", self._destroyed, add=True)

    def set_active_notes(self, notes: Iterable[int]) -> None:
        self._active_notes = {int(note) for note in notes}
        self._draw()

    def set_key_labels(self, key_labels: Mapping[int, str]) -> None:
        self._key_labels = dict(key_labels)
        self._draw()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        if not self._enabled:
            self.release_all()
        self.configure(cursor="hand2" if self._enabled else "arrow")
        self._draw()

    def release_all(self) -> None:
        """Release the pointer's note and local grab, including during panic."""
        self._pointer_down = False
        try:
            self._change_pointer_note(None)
        finally:
            try:
                if self.grab_current() == self:
                    self.grab_release()
            except tk.TclError:
                pass

    def _destroyed(self, event) -> None:
        if event.widget is self:
            # Do not redraw a canvas whose Tcl command has already disappeared.
            note, self._pointer_note = self._pointer_note, None
            self._pointer_down = False
            if note is not None and self.on_note_off is not None:
                self.on_note_off(note)

    def _change_pointer_note(self, note: int | None) -> None:
        if note == self._pointer_note:
            return
        previous, self._pointer_note = self._pointer_note, note
        if previous is not None and self.on_note_off is not None:
            self.on_note_off(previous)
        if note is not None and self.on_note_on is not None:
            self.on_note_on(note)
        self._draw()

    def _hit_test(self, x: float, y: float) -> int | None:
        for note, (left, top, right, bottom) in self._black_keys + self._white_keys:
            if left <= x < right and top <= y < bottom:
                return note
        return None

    def _press(self, event) -> str:
        if not self._enabled:
            return "break"
        note = self._hit_test(event.x, event.y)
        if note is not None:
            self._pointer_down = True
            self.grab_set()
            self._change_pointer_note(note)
        return "break"

    def _motion(self, event) -> str:
        if self._pointer_down:
            self._change_pointer_note(self._hit_test(event.x, event.y))
        return "break"

    def _release(self, _event) -> str:
        self.release_all()
        return "break"

    def _leave(self, _event) -> None:
        if self._pointer_down:
            self._change_pointer_note(None)

    def _draw(self, _event=None) -> None:
        self.delete("all")
        width, height = max(1, self.winfo_width()), max(1, self.winfo_height())
        self._white_keys, self._black_keys = [], []
        if width < 20 or height < 20:
            return
        margin = 3
        top, bottom = 4, height - 4
        white_notes = [note for note in range(self.FIRST_NOTE, self.LAST_NOTE + 1)
                       if note % 12 not in self.BLACK_CLASSES]
        key_width = (width - margin * 2) / len(white_notes)
        active = self._active_notes | ({self._pointer_note} if self._pointer_note is not None else set())
        for index, note in enumerate(white_notes):
            left, right = margin + index * key_width, margin + (index + 1) * key_width
            self._white_keys.append((note, (left, top, right, bottom)))
            selected = note in active
            fill = COLORS["accent"] if selected else ("#dce4ec" if self._enabled else "#7f8c9b")
            self.create_rectangle(left + 1, top, right - 1, bottom, fill=fill, outline="")
            self.create_rectangle(left + 1, bottom - 5, right - 1, bottom,
                                  fill="#2cae90" if selected else "#a7b6c6", outline="")
            if key_width >= 20 and height >= 78:
                key_label = self._key_labels.get(note, "")
                if key_label:
                    self.create_text((left + right) / 2, bottom - 35, text=key_label,
                                     fill="#213546", font=(FONT_MONO, 9, "bold"))
                if note % 12 == 0 or key_width >= 38:
                    name = ("C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B")[note % 12]
                    self.create_text((left + right) / 2, bottom - 17,
                                     text=f"{name}{note // 12 - 1}" if note % 12 == 0 else name,
                                     fill="#516479", font=(FONT_UI, 8))
        black_width = key_width * 0.61
        black_bottom = top + (bottom - top) * 0.61
        for note in range(self.FIRST_NOTE, self.LAST_NOTE + 1):
            if note % 12 not in self.BLACK_CLASSES:
                continue
            white_before = sum(n < note for n in white_notes)
            center = margin + white_before * key_width
            left, right = center - black_width / 2, center + black_width / 2
            self._black_keys.append((note, (left, top, right, black_bottom)))
            selected = note in active
            fill = "#209e83" if selected else ("#263242" if self._enabled else "#414d5e")
            self.create_rectangle(left + 2, top + 2, right + 2, black_bottom + 3,
                                  fill="#718395", outline="")
            self.create_rectangle(left, top, right, black_bottom, fill=fill, outline="#0d1721")
            self.create_line(left + 2, black_bottom - 5, right - 2, black_bottom - 5,
                             fill="#4ce3b8" if selected else "#43536a", width=2)
            label = self._key_labels.get(note, "")
            if label and black_width >= 15 and height >= 78:
                self.create_text(center, black_bottom - 19, text=label,
                                 fill="#e8f4f1" if selected else "#b5c2d0", font=(FONT_MONO, 8))


class EnvelopeCanvas(tk.Canvas):
    """Linear ADSR parameter plot. Sustain's illustrative hold is labelled.

    ``sustain`` normally uses 0–1. Values over one are accepted as 0–255 for
    convenience. Attack and decay are segment times. Release is a full-scale
    slope time, as encoded by the controller, so a steady-state key release
    from sustain to zero takes ``sustain * release_ms``. Releasing during attack
    or decay can start from a different level. All segments share one time scale;
    the held interval is an explicit example because it depends on key release.
    """

    def __init__(self, master: tk.Misc, **kwargs):
        kwargs.setdefault("background", COLORS["panel"])
        kwargs.setdefault("height", 230)
        kwargs.setdefault("highlightthickness", 0)
        super().__init__(master, **kwargs)
        self._envelope = (20.0, 120.0, 0.7, 300.0)
        self.bind("<Configure>", self._draw)

    def set_envelope(self, attack_ms: float, decay_ms: float,
                     sustain: float, release_ms: float) -> None:
        def duration(value: float) -> float:
            value = float(value)
            return max(0.0, value) if math.isfinite(value) else 0.0

        sustain = float(sustain)
        if not math.isfinite(sustain):
            sustain = 0.0
        if sustain > 1:
            sustain /= 255.0
        self._envelope = (duration(attack_ms), duration(decay_ms),
                          min(1.0, max(0.0, sustain)), duration(release_ms))
        self._draw()

    @staticmethod
    def _time_label(milliseconds: float) -> str:
        return f"{milliseconds / 1000:.2g} s" if milliseconds >= 1000 else f"{milliseconds:.0f} ms"

    def _draw(self, _event=None) -> None:
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        if width < 60 or height < 60:
            return
        attack, decay, sustain, release = self._envelope
        compact = width < 390 or height < 190
        left, right = (31 if compact else 42), width - 18
        top, bottom = (30 if compact else 40), height - (52 if compact else 69)
        if bottom <= top:
            return
        actual_release = sustain * release
        hold = max(200.0, (attack + decay + actual_release) * 0.3)
        total = attack + decay + hold + actual_release
        times = (0.0, attack, attack + decay, attack + decay + hold, total)
        levels = (0.0, 1.0, sustain, sustain, 0.0)
        xs = [left + time / total * (right - left) for time in times]
        ys = [bottom - level * (bottom - top) for level in levels]
        self.create_text(left, 12, anchor="w", text="ADSR / 参数示意", fill=COLORS["muted"],
                         font=(FONT_UI, 8))
        if width > 400:
            self.create_text(right, 12, anchor="e", text="线性包络 · 非实时采样", fill=COLORS["muted"],
                             font=(FONT_UI, 8))
        for gain in (0.0, 0.5, 1.0):
            y = bottom - gain * (bottom - top)
            self.create_line(left, y, right, y, fill=COLORS["border"], dash=(2, 4))
            self.create_text(left - 9, y, anchor="e", text=f"{gain:.1f}",
                             fill=COLORS["muted"], font=(FONT_MONO, 8))
        points = [coordinate for point in zip(xs, ys) for coordinate in point]
        self.create_polygon(*points, right, bottom, left, bottom,
                            fill="#236f63", stipple="gray25", outline="")
        self.create_line(*points, fill=COLORS["accent"], width=2.5, joinstyle=tk.ROUND,
                         tags=("envelope_curve",))
        for index, (x, y) in enumerate(zip(xs[1:-1], ys[1:-1]), 1):
            self.create_line(x, y + 4, x, bottom, fill="#34584f", dash=(2, 4))
            color = COLORS["amber"] if index == 3 else COLORS["accent"]
            self.create_oval(x - 3, y - 3, x + 3, y + 3, fill=color, outline=COLORS["panel"])
        if not compact:
            self.create_line(xs[3], top - 4, xs[3], bottom, fill="#756346", dash=(3, 4))
            self.create_text(min(right - 15, max(left + 15, xs[3])), top - 12,
                             text="松键", fill=COLORS["amber"], font=(FONT_UI, 8))
            for index, name in enumerate(("A", "D", "S", "R")):
                if xs[index + 1] - xs[index] > 25:
                    self.create_text((xs[index] + xs[index + 1]) / 2, bottom + 14,
                                     text=name, fill=COLORS["muted"], font=(FONT_MONO, 9, "bold"))
            self.create_text(left, bottom + 35, anchor="w", text="0", fill=COLORS["muted"],
                             font=(FONT_MONO, 8))
            self.create_text(right, bottom + 35, anchor="e", text=self._time_label(total),
                             fill=COLORS["muted"], font=(FONT_MONO, 8))
            self.create_text((left + right) / 2, bottom + 35,
                             text=f"实际 R {self._time_label(actual_release)} = S × 满幅 R",
                             fill=COLORS["amber"], font=(FONT_UI, 8))
            note = f"稳态松键示意 · S 按住 {self._time_label(hold)}，长度仅作示例"
            self.create_text((left + right) / 2, height - 12, text=note,
                             fill=COLORS["muted"], font=(FONT_UI, 8))
        else:
            self.create_text(left, bottom + 18, anchor="w", text="0", fill=COLORS["muted"],
                             font=(FONT_MONO, 8))
            self.create_text(right, bottom + 18, anchor="e", text=self._time_label(total),
                             fill=COLORS["muted"], font=(FONT_MONO, 8))
            if width >= 270:
                self.create_text((left + right) / 2, bottom + 35,
                                 text=f"稳态松键 · 实际 R {self._time_label(actual_release)} = S × 满幅 R",
                                 fill=COLORS["amber"], font=(FONT_UI, 8))
