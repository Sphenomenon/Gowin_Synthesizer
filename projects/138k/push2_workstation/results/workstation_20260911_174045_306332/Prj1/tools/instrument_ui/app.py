"""Tk main thread: widgets and musical intent. Serial I/O belongs to ControlWorker."""
from dataclasses import dataclass, field, replace
import argparse
from pathlib import Path
import queue
import sys
import time
import tkinter as tk
from tkinter import filedialog, ttk

from instrument_backend import ControlWorker, DEFAULT_SAMPLE_RATE, VOICE_COUNT, gain_word, balance_word, list_ports, phase_step
from instrument_backend.protocol import OUTPUT_OPCODES
from .presets import FACTORY, WAVE_NAMES, VoicePatch, factory_preset, load_preset, save_preset
from .voice_model import VoiceAllocator
from .widgets import COLORS, EnvelopeCanvas, PianoKeyboard, StatusPill, setup_theme
from .latency import LatencyWindow

KEYS = dict(zip("awsedftgyhujkolp;']", range(60, 79)))
NOTE_NAMES = ("C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B")
KEY_ALIASES = {"semicolon": ";", "colon": ";", "apostrophe": "'", "quotedbl": "'",
               "bracketright": "]", "braceright": "]", ":": ";", '"': "'", "}": "]"}


def configure_display():
    """Keep Windows from bitmap-scaling the entire Tk window on high-DPI screens."""
    if sys.platform == "win32":
        import ctypes
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()


def note_name(note):
    n = int(round(float(note)))
    return f"{NOTE_NAMES[n % 12]}{n // 12 - 1}"


@dataclass
class _PatchRequest:
    voice: int
    patch: VoicePatch
    remaining: set[int] = field(default_factory=lambda: {5, 4, 6, 7, 8, 9})


class InstrumentApp:
    def __init__(self, root, port=None, offline=False, auto_connect=False):
        self.root = root
        self.window_system = root.tk.call("tk", "windowingsystem")
        self.worker = ControlWorker()
        self.allocator = VoiceAllocator()
        self.patches = factory_preset(next(iter(FACTORY)))
        self.connected = False
        self.connecting = False
        self.closing = False
        self.active_mask = 0
        self.voice_count = VOICE_COUNT
        self.connection_id = None
        self.last_sound_ack = None
        self.latency_window = None
        self.selected = 0
        self.port_items = []
        self.release_jobs = {}
        self.physical_keys = {}
        self.note_vars, self.wave_vars, self.gain_vars, self.voice_pills = [], [], [], []
        self.last_parameters = {}
        self.patch_requests = {}
        self.request_id = 0
        self.output_jobs = {}
        self.output_intents = {}
        self.output_pending = {}
        self.output_confirmed = {}
        self.output_supported = {}
        self.output_failed = set()
        self.root.title("Mega Synth · FPGA 串口控制台")
        scale = float(root.tk.call("tk", "scaling")) / (96 / 72)
        height = min(int(960*scale), root.winfo_screenheight() - int(100*scale))
        self.root.geometry(f"{int(1260*scale)}x{height}")
        self.root.minsize(int(1100*scale), min(height, int(940*scale)))
        setup_theme(root)
        ttk.Style(root).configure("Card.TLabel", background=COLORS["panel"])
        ttk.Style(root).configure("Voice.TButton", padding=(6, 2))
        ttk.Style(root).configure("TNotebook.Tab", padding=(8, 5))
        self.root.configure(bg=COLORS["bg"])
        self._build()
        self.refresh_ports(port)
        self.offline_var.set(offline)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<KeyPress>", self._key_down)
        self.root.bind("<KeyRelease>", self._key_up)
        self.root.bind("<FocusOut>", lambda event: self.root.after(60, self._focus_check))
        self.root.bind("<Escape>", lambda event: self.panic())
        self.root.after(25, self._drain_events)
        self._load_editor(0)
        if auto_connect or offline:
            self.root.after(150, self.toggle_connection)

    def _build(self):
        outer = ttk.Frame(self.root, padding=(24, 11))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)
        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(header, text="MEGA  /  SYNTH", font=("Cascadia Code", 23, "bold")).pack(side="left")
        ttk.Label(header, text="FPGA 实时合成 · 32 声部演奏台", foreground=COLORS["muted"]).pack(side="left", padx=24)
        self.connection_pill = StatusPill(header, text="未连接", tone="muted")
        self.connection_pill.pack(side="right")

        connection = ttk.Frame(outer, padding=8, style="Card.TFrame")
        connection.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(connection, text="串口", style="Card.TLabel").pack(side="left", padx=(0, 8))
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(connection, textvariable=self.port_var, state="readonly", width=37)
        self.port_combo.pack(side="left")
        self.refresh_button = ttk.Button(connection, text="刷新", command=self.refresh_ports, width=6)
        self.refresh_button.pack(side="left", padx=8)
        ttk.Label(connection, text="115200 · 8N1", style="Card.TLabel", foreground=COLORS["muted"]).pack(side="left", padx=8)
        self.offline_var = tk.BooleanVar(value=False)
        self.offline_check = ttk.Checkbutton(connection, text="离线预览", variable=self.offline_var)
        self.offline_check.pack(side="left", padx=14)
        self.connect_button = ttk.Button(connection, text="连接设备", command=self.toggle_connection, style="Accent.TButton")
        self.connect_button.pack(side="right")

        output = ttk.Frame(outer, padding=(12, 7), style="Card.TFrame")
        output.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        output.columnconfigure(1, weight=1)
        output.columnconfigure(5, weight=1)
        ttk.Label(output, text="总音量", style="Card.TLabel").grid(row=0, column=0, padx=(0, 10))
        self.master_volume_var = tk.DoubleVar(value=100)
        self.balance_var = tk.DoubleVar(value=0)
        self.master_scale = ttk.Scale(output, from_=0, to=100, variable=self.master_volume_var,
                                      command=lambda value: self.change_output(16))
        self.master_scale.grid(row=0, column=1, sticky="ew")
        self.master_value = ttk.Label(output, text="100%", style="Card.TLabel", width=5)
        self.master_value.grid(row=0, column=2, padx=(8, 22))
        ttk.Label(output, text="L / R 平衡", style="Card.TLabel").grid(row=0, column=3, padx=(0, 10))
        ttk.Label(output, text="L", style="Card.TLabel").grid(row=0, column=4, padx=(0, 6))
        self.balance_scale = ttk.Scale(output, from_=-100, to=100, variable=self.balance_var,
                                       command=lambda value: self.change_output(17))
        self.balance_scale.grid(row=0, column=5, sticky="ew")
        ttk.Label(output, text="R", style="Card.TLabel").grid(row=0, column=6, padx=(6, 0))
        self.balance_value = ttk.Label(output, text="居中", style="Card.TLabel", width=7)
        self.balance_value.grid(row=0, column=7, padx=8)
        self.balance_center_button = ttk.Button(output, text="居中", command=self.center_balance, style="Voice.TButton")
        self.balance_center_button.grid(row=0, column=8)
        self.output_status_var = tk.StringVar(value="输出设置将在连接时同步")
        ttk.Label(output, textvariable=self.output_status_var, style="Card.TLabel",
                  foreground=COLORS["muted"]).grid(row=1, column=0, columnspan=9, sticky="w", pady=(3, 0))

        body = ttk.Frame(outer)
        body.grid(row=3, column=0, sticky="nsew")
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        right = ttk.Frame(body, padding=12, style="Card.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        title = ttk.Frame(left)
        title.pack(fill="x", pady=(0, 8))
        ttk.Label(title, text="独立声部", font=("Microsoft YaHei UI", 13, "bold")).pack(side="left")
        self.active_label = ttk.Label(title, text="已确认活动 0 / 32", foreground=COLORS["muted"])
        self.active_label.pack(side="right")
        matrix = ttk.Frame(left)
        matrix.pack(fill="x", pady=(0, 7))
        self.voice_tiles = []
        for voice in range(VOICE_COUNT):
            tile = tk.Button(matrix, text=f"{voice+1:02d}", relief="flat", bd=0,
                             background=COLORS["panel_alt"], foreground=COLORS["muted"],
                             activebackground=COLORS["accent"], width=2, takefocus=False,
                             command=lambda v=voice: self.select_voice(v))
            tile.grid(row=voice // 16, column=voice % 16, padx=1, pady=1, sticky="ew")
            matrix.columnconfigure(voice % 16, weight=1)
            self.voice_tiles.append(tile)
        self.voice_pages = ttk.Notebook(left)
        self.voice_pages.pack(fill="both", expand=True)
        for first in range(0, VOICE_COUNT, 4):
            page = ttk.Frame(self.voice_pages)
            self.voice_pages.add(page, text=f"{first+1}–{first+4}")
            for voice in range(first, first+4):
                self._voice_card(page, voice)
        help_text = "自动分配 32 个槽；第 33 个同时按键忽略。\n上方 01–32 显示全部活动；点击编号编辑。Esc 全部清音。"
        ttk.Label(left, text=help_text, foreground=COLORS["muted"], justify="left").pack(anchor="w", pady=(8, 0))

        ttk.Label(right, text="音色预设", style="Card.TLabel", font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w")
        presets = ttk.Frame(right, style="Card.TFrame")
        presets.pack(fill="x", pady=(6, 6))
        self.preset_var = tk.StringVar(value=next(iter(FACTORY)))
        ttk.Combobox(presets, textvariable=self.preset_var, values=list(FACTORY), state="readonly", width=23).pack(side="left", fill="x", expand=True)
        ttk.Button(presets, text="载入", width=5, command=self.load_factory).pack(side="right", padx=(8, 0))
        preset_actions = ttk.Frame(right, style="Card.TFrame")
        preset_actions.pack(fill="x", pady=(0, 8))
        ttk.Button(preset_actions, text="导入 JSON", command=self.import_preset).pack(side="left")
        ttk.Button(preset_actions, text="保存预设", command=self.export_preset).pack(side="left", padx=8)
        self.apply_all_button = ttk.Button(preset_actions, text="应用到 32 声部", command=self.apply_all)
        self.apply_all_button.pack(side="right")
        ttk.Separator(right).pack(fill="x", pady=(0, 8))
        editor_title = ttk.Frame(right, style="Card.TFrame")
        editor_title.pack(fill="x")
        self.editor_title = ttk.Label(editor_title, text="声部 1 · ADSR", style="Card.TLabel", font=("Microsoft YaHei UI", 11, "bold"))
        self.editor_title.pack(side="left")
        ttk.Button(editor_title, text="应用参数", command=self.apply_selected).pack(side="right")
        self.env_vars = {name: tk.StringVar() for name in ("attack_ms", "decay_ms", "sustain", "release_ms")}
        grid = ttk.Frame(right, style="Card.TFrame")
        grid.pack(fill="x", pady=(7, 3))
        for index, (name, label, unit) in enumerate((("attack_ms", "起音 A", "ms"), ("decay_ms", "衰减 D", "ms"), ("sustain", "保持 S", "%"), ("release_ms", "满幅 R", "ms"))):
            ttk.Label(grid, text=label, style="Card.TLabel").grid(row=index//2, column=(index%2)*3, padx=(0, 5), pady=5, sticky="w")
            box = ttk.Entry(grid, textvariable=self.env_vars[name], width=7)
            box.grid(row=index//2, column=(index%2)*3+1, padx=3, pady=5)
            box.bind("<FocusOut>", lambda event: self._preview_envelope())
            box.bind("<Return>", lambda event: self.apply_selected())
            ttk.Label(grid, text=unit, style="Card.TLabel", foreground=COLORS["muted"]).grid(row=index//2, column=(index%2)*3+2, padx=(2, 14))
        self.envelope = EnvelopeCanvas(right, height=110)
        self.envelope.pack(fill="both", expand=True, pady=(5, 5))
        ttk.Label(right, text="32 声部需要新版位流；曲线为参数示意。\nFs 48,828.125 Hz · 音频由 FPGA 生成。", style="Card.TLabel", foreground=COLORS["muted"], justify="left").pack(anchor="w")

        piano_header = ttk.Frame(outer)
        piano_header.grid(row=4, column=0, sticky="ew", pady=(14, 6))
        ttk.Label(piano_header, text="演奏键盘   C4 — C6", font=("Microsoft YaHei UI", 12, "bold")).pack(side="left")
        ttk.Label(piano_header, text="离开窗口自动清音 · 尾音来自声部状态快照", foreground=COLORS["muted"]).pack(side="left", padx=20)
        self.patch_ready_var = tk.StringVar(value="音色未准备")
        ttk.Label(piano_header, textvariable=self.patch_ready_var, foreground=COLORS["muted"]).pack(side="left")
        ttk.Button(piano_header, text="■  全部清音  Esc", style="Danger.TButton", command=self.panic).pack(side="right")
        self.piano = PianoKeyboard(outer, height=110, on_note_on=lambda n: self.note_on(f"mouse:{n}", n), on_note_off=lambda n: self.note_off(f"mouse:{n}"), key_labels={n: k.upper() for k, n in KEYS.items()})
        self.piano.grid(row=5, column=0, sticky="ew")
        self.piano.set_enabled(False)

        footer = ttk.Frame(outer)
        footer.grid(row=6, column=0, sticky="ew", pady=(12, 6))
        self.message_var = tk.StringVar(value="选择串口后连接。此机器上次验证成功的端口为 COM26。")
        ttk.Label(footer, textvariable=self.message_var, foreground=COLORS["muted"]).pack(side="left")
        self.rtt_var = tk.StringVar(value="ACK — ms")
        ttk.Label(footer, textvariable=self.rtt_var, font=("Cascadia Code", 10)).pack(side="right")
        ttk.Button(footer, text="延迟检测", command=self.open_latency, style="Voice.TButton").pack(side="right", padx=12)
        self.log = tk.Text(outer, height=2, bg=COLORS["panel"], fg=COLORS["muted"], insertbackground=COLORS["text"], relief="flat", font=("Cascadia Code", 9), padx=10, pady=4, state="disabled", takefocus=False)
        self.log.grid(row=7, column=0, sticky="ew")

    def _voice_card(self, parent, voice):
        card = ttk.Frame(parent, padding=(10, 4), style="Card.TFrame")
        card.pack(fill="x", pady=2)
        card.columnconfigure(4, weight=1)
        ttk.Button(card, text=f"{voice+1:02d}", command=lambda: self.select_voice(voice), width=3, style="Voice.TButton").grid(row=0, column=0, rowspan=2, padx=(0, 10))
        note = tk.StringVar(value=str((60, 64, 67, 72)[voice % 4]))
        wave = tk.StringVar(value=WAVE_NAMES[self.patches[voice].waveform])
        gain = tk.DoubleVar(value=20)
        self.note_vars.append(note); self.wave_vars.append(wave); self.gain_vars.append(gain)
        ttk.Label(card, text="音高 MIDI", style="Card.TLabel", foreground=COLORS["muted"]).grid(row=0, column=1, sticky="w")
        spin = ttk.Spinbox(card, from_=0, to=127, increment=.5, textvariable=note, width=6, command=lambda: self.change_pitch(voice))
        spin.grid(row=1, column=1, padx=(0, 10))
        spin.bind("<Return>", lambda event: self.change_pitch(voice))
        combo = ttk.Combobox(card, values=WAVE_NAMES, state="readonly", textvariable=wave, width=7)
        combo.grid(row=0, column=2, rowspan=2, padx=(0, 10))
        combo.bind("<<ComboboxSelected>>", lambda event: self.change_wave(voice))
        ttk.Label(card, text="力度", style="Card.TLabel", foreground=COLORS["muted"]).grid(row=0, column=3, sticky="w")
        scale = ttk.Scale(card, from_=0, to=100, variable=gain, command=lambda value: self.change_gain(voice))
        scale.grid(row=1, column=3, columnspan=2, sticky="ew", padx=(0, 10))
        self.gain_value = getattr(self, "gain_value", [])
        gain_text = ttk.Label(card, text="20%", style="Card.TLabel", width=5)
        gain_text.grid(row=0, column=4, sticky="e", padx=(0, 10)); self.gain_value.append(gain_text)
        pill = StatusPill(card, text="静音", tone="muted", height=24)
        pill.grid(row=0, column=5, padx=(0, 8)); self.voice_pills.append(pill)
        buttons = ttk.Frame(card, style="Card.TFrame")
        buttons.grid(row=1, column=5)
        ttk.Button(buttons, text="起音", width=4, command=lambda: self.manual_on(voice), style="Voice.TButton").pack(side="left")
        ttk.Button(buttons, text="松键", width=4, command=lambda: self.manual_off(voice), style="Voice.TButton").pack(side="left", padx=(4, 0))

    def _notice(self, message, error=False):
        self.message_var.set(str(message)[:120])
        self.log.configure(state="normal")
        self.log.insert("end", f"{time.strftime('%H:%M:%S')}  {'! ' if error else ''}{message}\n")
        if int(self.log.index("end-1c").split('.')[0]) > 160:
            self.log.delete("1.0", "40.0")
        self.log.see("end"); self.log.configure(state="disabled")

    def refresh_ports(self, preferred=None):
        if self.connected or self.connecting: return
        try:
            self.port_items = list_ports()
            values = [p["display"] for p in self.port_items]
            self.port_combo.configure(values=values)
            desired = preferred or "COM26"
            found = next((p["display"] for p in self.port_items if p["device"] == desired), None)
            self.port_var.set(found or (values[0] if values else "无串口，可选择离线预览"))
        except Exception as exc:
            self._notice(f"串口枚举失败：{exc}", True)

    def toggle_connection(self):
        if self.connected or self.connecting:
            self.allocator.clear(); self.piano.release_all(); self.worker.disconnect()
            self.connect_button.configure(state="disabled")
            return
        simulated = self.offline_var.get()
        port = next((p["device"] for p in self.port_items if p["display"] == self.port_var.get()), None)
        if not simulated and not port:
            self._notice("请选择可用串口，或勾选离线预览。", True); return
        self.connecting = True
        self.connection_pill.set_status("正在连接", "warning")
        self.connect_button.configure(text="取消连接")
        self.offline_check.configure(state="disabled")
        self.port_combo.configure(state="disabled")
        self._update_output_status()
        self.worker.connect(port or "离线", simulated=simulated,
                            output_controls=tuple(self._output_word(opcode) for opcode in OUTPUT_OPCODES))

    def _output_word(self, opcode):
        percent = round((self.master_volume_var if opcode == 16 else self.balance_var).get())
        return gain_word(percent / 100) if opcode == 16 else balance_word(percent / 100)

    def _update_output_status(self):
        for opcode, widget in ((16, self.master_scale), (17, self.balance_scale),
                               (17, self.balance_center_button)):
            widget.configure(state="disabled" if self.connecting or (
                self.connected and self.output_supported.get(opcode) is False) else "normal")
        if self.connecting:
            text = "正在清音并同步输出设置…"
        elif not self.connected:
            text = "输出设置将在连接时同步"
        else:
            states = []
            for opcode, name in ((16, "总音量"), (17, "LR")):
                if self.output_supported.get(opcode) is False:
                    states.append(f"{name}：旧位流不支持")
                elif opcode in self.output_failed:
                    states.append(f"{name}：未应用")
                elif (opcode in self.output_jobs or opcode in self.output_pending
                        or self.output_confirmed.get(opcode) != self._output_word(opcode)):
                    states.append(f"{name}：待确认")
                else:
                    states.append(f"{name}：已确认")
            text = " · ".join(states)
            if self.offline_var.get():
                text += "（离线控制模拟）"
        self.output_status_var.set(text)

    def change_output(self, opcode):
        submitted_at = time.perf_counter()
        master = round(self.master_volume_var.get())
        balance = round(self.balance_var.get())
        self.master_value.configure(text=f"{master}%")
        self.balance_value.configure(text="居中" if balance == 0 else f"{'L' if balance < 0 else 'R'} {abs(balance)}%")
        if self.connected and not self.connecting and self.output_supported.get(opcode) is not False:
            self.output_intents[opcode] = submitted_at
            # Limit Tk slider traffic without postponing notes/releases. The
            # worker separately replaces each control's latest unsent value.
            if opcode not in self.output_jobs:
                self.output_jobs[opcode] = self.root.after(20, lambda: self._send_output(opcode))
        self._update_output_status()

    def _send_output(self, opcode):
        job = self.output_jobs.pop(opcode, None)
        if job is not None:
            self.root.after_cancel(job)
        submitted_at = self.output_intents.pop(opcode, None)
        if not self.connected or self.output_supported.get(opcode) is False:
            return
        word = self._output_word(opcode)
        # An older command may still be in flight, even when the desired value
        # has returned to the previous confirmed setting; send that return too.
        if opcode not in self.output_pending and self.output_confirmed.get(opcode) == word:
            self._update_output_status()
            return
        self.request_id += 1
        tag = f"output:{opcode}:{self.request_id}"
        if self._submit([(opcode, 255, word)], tag, f"output:{opcode}", submitted_at=submitted_at):
            self.output_pending[opcode] = (tag, word)
            self.output_failed.discard(opcode)
        else:
            self.output_failed.add(opcode)
        self._update_output_status()

    def center_balance(self):
        self.balance_var.set(0)
        self.change_output(17)
        self._send_output(17)

    def _confirm_output_ack(self, event):
        if not self.connected or event.get("connection_id") != self.connection_id:
            return
        opcode = event.get("opcode")
        pending = self.output_pending.get(opcode)
        if pending is None or pending[0] != event.get("tag"):
            return
        self.output_pending.pop(opcode)
        if event.get("status") == 0:
            self.output_confirmed[opcode] = pending[1]
            self.output_supported[opcode] = True
            self.output_failed.discard(opcode)
        else:
            self.output_failed.add(opcode)
        self._update_output_status()

    def _cancel_output_jobs(self):
        for job in self.output_jobs.values():
            self.root.after_cancel(job)
        self.output_jobs.clear()
        self.output_intents.clear()

    def _read_editor(self):
        return replace(self.patches[self.selected], **{
            name: float(var.get()) / (100 if name == "sustain" else 1)
            for name, var in self.env_vars.items()
        }).validate()

    def _load_editor(self, voice):
        self.selected = voice
        self.editor_title.configure(text=f"声部 {voice+1} · ADSR")
        patch = self.patches[voice]
        for name, var in self.env_vars.items():
            var.set(f"{getattr(patch,name)*(100 if name=='sustain' else 1):g}")
        self.envelope.set_envelope(patch.attack_ms, patch.decay_ms, patch.sustain, patch.release_ms)

    def _preview_envelope(self):
        try:
            patch = self._read_editor()
            self.envelope.set_envelope(patch.attack_ms, patch.decay_ms, patch.sustain, patch.release_ms)
        except ValueError:
            pass

    def select_voice(self, voice):
        try: self.patches[self.selected] = self._read_editor()
        except ValueError as exc: self._notice(str(exc), True); return
        self._load_editor(voice)
        self.voice_pages.select(voice // 4)

    def _submit(self, commands, tag, coalesce_key=None, submitted_at=None, background=False):
        if not self.connected:
            self._notice("请先连接设备或进入离线预览。", True); return False
        if any(opcode in range(1, 10) and voice >= self.voice_count for opcode, voice, value in commands):
            self._notice(f"当前旧位流仅支持前 {self.voice_count} 声部，请下载 32 声部位流。", True)
            return False
        return self.worker.submit(commands, tag=tag, coalesce_key=coalesce_key,
                                  submitted_at=submitted_at, background=background)

    def _invalidate_parameters(self, voice, pending_only=False):
        # Remove old tags as well: an ACK already queued in Tk must not restore
        # a cache after a newer edit or cancellation. Tags are never reused.
        if not pending_only:
            self.last_parameters.pop(voice, None)
        self.patch_requests = {tag: request for tag, request in self.patch_requests.items()
                               if request.voice != voice}
        self._update_patch_readiness()

    def _update_patch_readiness(self):
        if not self.connected:
            self.patch_ready_var.set("音色未准备")
            return
        ready = sum(self.last_parameters.get(voice) == self.patches[voice] for voice in range(self.voice_count))
        if ready == self.voice_count:
            self.patch_ready_var.set(f"音色就绪 {ready}/{self.voice_count}")
        else:
            state = "正在准备音色" if self.patch_requests else "已准备音色"
            self.patch_ready_var.set(f"{state} {ready}/{self.voice_count} · 未就绪声部起音时配置")

    def _confirm_patch_ack(self, event):
        if not self.connected or event.get("connection_id") != self.connection_id:
            return
        key = (event.get("tag", ""), event.get("voice"))
        request = self.patch_requests.get(key)
        if request is None or event.get("opcode") not in request.remaining:
            return
        if event.get("status") != 0:
            self.patch_requests.pop(key)
            return
        request.remaining.remove(event["opcode"])
        if not request.remaining:
            # Every parameter was acknowledged, not merely the final release
            # setting. Lost, cancelled or superseded batches stay unconfirmed.
            self.last_parameters[request.voice] = request.patch
            self.patch_requests.pop(key)

    def note_on(self, token, note, preferred=None):
        submitted_at = time.perf_counter()
        if not self.connected: return
        for opcode in list(self.output_jobs):
            self._send_output(opcode)
        try:
            step = phase_step(float(note))
            self.patches[self.selected] = self._read_editor()
            old_owners = dict(self.allocator.owners)
            old_cursor = self.allocator.next_voice
            if preferred is not None:
                self.allocator.release(token)
            voice = self.allocator.press(token, float(note), preferred, active_mask=self.active_mask)
            if voice is None: return
            self.request_id += 1
            tag = f"note_on:{voice}:{self.request_id}"
            patch = replace(self.patches[voice])
            needs_patch = self.last_parameters.get(voice) != patch
            commands = (patch.commands(voice) if needs_patch else []) + [(1, voice, step)]
            if needs_patch: self._invalidate_parameters(voice)
            if not self._submit(commands, tag, submitted_at=submitted_at):
                self.allocator.owners = old_owners
                self.allocator.next_voice = old_cursor
                return
            if needs_patch: self.patch_requests[(tag, voice)] = _PatchRequest(voice, patch)
            self._update_patch_readiness()
            self.note_vars[voice].set(f"{float(note):g}")
            self.piano.set_active_notes(self.allocator.notes)
            self._notice(f"声部 {voice+1} · {note_name(note)} · 起音已排队")
        except (ValueError, OverflowError) as exc:
            self._notice(f"无效参数：{exc}", True)

    def note_off(self, token, submitted_at=None):
        submitted_at = time.perf_counter() if submitted_at is None else submitted_at
        assignment = self.allocator.release(token)
        if assignment and self.connected:
            self._invalidate_parameters(assignment[0], pending_only=True)
            self.worker.submit([(2, assignment[0], 0)], tag=f"note_off:{assignment[0]}", submitted_at=submitted_at)
        self.piano.set_active_notes(self.allocator.notes)

    def manual_on(self, voice):
        # Repeated manual clicks intentionally retrigger this explicit voice slot.
        self.note_on(f"manual:{voice}", self.note_vars[voice].get(), preferred=voice)

    def manual_off(self, voice):
        submitted_at = time.perf_counter()
        self.allocator.release_voice(voice)
        self._invalidate_parameters(voice, pending_only=True)
        if self.connected: self.worker.submit([(2, voice, 0)], tag=f"note_off:{voice}", submitted_at=submitted_at)
        self.piano.set_active_notes(self.allocator.notes)

    def change_pitch(self, voice):
        try:
            value = float(self.note_vars[voice].get())
            step = phase_step(value)
            if self.connected and self.allocator.note_for_voice(voice) is not None:
                if self._submit([(3, voice, step)], f"pitch:{voice}", f"pitch:{voice}"):
                    self._invalidate_parameters(voice, pending_only=True)
                    self.allocator.set_note(voice, value)
                    self.piano.set_active_notes(self.allocator.notes)
        except (ValueError, OverflowError) as exc: self._notice(f"音高无效：{exc}", True)

    def change_wave(self, voice):
        self.patches[voice].waveform = WAVE_NAMES.index(self.wave_vars[voice].get())
        self._invalidate_parameters(voice)
        if self.connected:
            self._submit([(5, voice, self.patches[voice].waveform)], f"wave:{voice}", f"wave:{voice}")

    def change_gain(self, voice):
        value = self.gain_vars[voice].get()/100
        self.patches[voice].velocity = value
        self._invalidate_parameters(voice)
        self.gain_value[voice].configure(text=f"{value:.0%}")
        if self.connected:
            self._submit([(4, voice, gain_word(value))], f"gain:{voice}", f"gain:{voice}")

    def apply_selected(self):
        try:
            self.patches[self.selected] = self._read_editor()
            self._invalidate_parameters(self.selected)
            self._preview_envelope()
            if self.connected:
                voice = self.selected
                patch = replace(self.patches[voice])
                self.request_id += 1
                tag = f"patch:{voice}:{self.request_id}"
                if self._submit(patch.commands(voice), tag, f"patch:{voice}"):
                    self.patch_requests[(tag, voice)] = _PatchRequest(voice, patch)
                    self._update_patch_readiness()
            else: self._notice("参数已保存在界面，下一次起音时下发。")
        except ValueError as exc: self._notice(f"参数未应用：{exc}", True)

    def apply_all(self):
        try:
            self.patches[self.selected] = self._read_editor()
            patches = [replace(patch) for patch in self.patches[:self.voice_count]]
            commands = [command for v, patch in enumerate(patches) for command in patch.commands(v)]
            self.last_parameters.clear(); self.patch_requests.clear()
            self.request_id += 1
            tag = f"preload:all:{self.request_id}"
            if self._submit(commands, tag, "patch:all", background=True):
                self.patch_requests.update({(tag, voice): _PatchRequest(voice, patch)
                                            for voice, patch in enumerate(patches)})
            self._update_patch_readiness()
        except ValueError as exc: self._notice(str(exc), True)

    def _show_patches(self, name, patches):
        self.patches = patches
        self.preset_var.set(name)
        for v, patch in enumerate(patches):
            self.wave_vars[v].set(WAVE_NAMES[patch.waveform])
            self.gain_vars[v].set(patch.velocity*100)
            self.gain_value[v].configure(text=f"{patch.velocity:.0%}")
        self._load_editor(self.selected)
        self._update_patch_readiness()
        self._notice(f"已载入「{name}」；点击应用，或在下次起音时写入。")

    def load_factory(self):
        name = self.preset_var.get()
        if name in FACTORY: self._show_patches(name, factory_preset(name))

    def import_preset(self):
        self.panic(quiet=True)
        path = filedialog.askopenfilename(parent=self.root, title="导入音色预设", filetypes=[("JSON 预设", "*.json")])
        if not path: return
        try: self._show_patches(*load_preset(path))
        except (ValueError, OSError, TypeError) as exc: self._notice(f"导入失败：{exc}", True)

    def export_preset(self):
        try: self.patches[self.selected] = self._read_editor()
        except ValueError as exc: self._notice(str(exc), True); return
        self.panic(quiet=True)
        path = filedialog.asksaveasfilename(parent=self.root, title="保存音色预设", defaultextension=".json", initialfile="my_preset.json", filetypes=[("JSON 预设", "*.json")])
        if not path: return
        try:
            save_preset(path, Path(path).stem[:80], self.patches)
            self._notice(f"预设已保存：{path}")
        except (ValueError, OSError) as exc: self._notice(str(exc), True)

    def panic(self, quiet=False):
        self.last_parameters.clear(); self.patch_requests.clear()
        self._update_patch_readiness()
        self._clear_keys()
        self.allocator.clear()
        self.piano.release_all()
        self.piano.set_active_notes([])
        if self.connected:
            dirty_output = set(self.output_jobs) | set(self.output_pending)
            self._cancel_output_jobs()
            self.worker.panic()
            # PANIC cancels queued slider work as well as notes. Reassert only
            # unfinished settings after its fence; acknowledged gains persist.
            for opcode in dirty_output:
                self.output_confirmed.pop(opcode, None)
                self.output_pending.pop(opcode, None)
                self._send_output(opcode)
        if not quiet: self._notice("已请求全部清音；等待 FPGA 确认。" if self.connected else "未连接，无需清音。")

    def _typing(self, event):
        return isinstance(event.widget, (tk.Entry, ttk.Entry, ttk.Spinbox, ttk.Combobox, tk.Text))

    def _clear_keys(self):
        for job in self.release_jobs.values():
            self.root.after_cancel(job)
        self.release_jobs.clear()
        self.physical_keys.clear()

    @staticmethod
    def _event_key(event):
        symbol = event.keysym.lower()
        return KEY_ALIASES.get(symbol, symbol)

    def _key_down(self, event):
        physical = getattr(event, "keycode", None)
        key = self.physical_keys.get(physical, self._event_key(event))
        if key not in KEYS or self._typing(event): return
        if physical is not None: self.physical_keys[physical] = key
        if key in self.release_jobs:
            self.root.after_cancel(self.release_jobs.pop(key))
        self.note_on(f"key:{key}", KEYS[key])

    def _key_up(self, event):
        submitted_at = time.perf_counter()
        physical = getattr(event, "keycode", None)
        key = self.physical_keys.get(physical, self._event_key(event))
        if key not in KEYS: return
        def release():
            self.release_jobs.pop(key, None)
            self.physical_keys.pop(physical, None)
            self.note_off(f"key:{key}", submitted_at=submitted_at)
        if self.window_system == "x11":
            # X11 autorepeat sends a release/press pair. The following press
            # cancels this idle callback; a real release has no fixed timer.
            if key not in self.release_jobs: self.release_jobs[key] = self.root.after_idle(release)
        else:
            release()

    def _focus_check(self):
        if self.closing: return
        if self.root.focus_displayof() is None and self.allocator.owners:
            self.panic()

    def open_latency(self):
        if self.latency_window is None:
            self.latency_window = LatencyWindow(self)
        else:
            self.latency_window.root.lift()

    def _drain_events(self):
        voice_status_dirty = False
        host_timing_dirty = False
        try:
            for _ in range(100):
                event = self.worker.events.get_nowait()
                kind = event.get("type")
                if kind == "connected":
                    self.connected = True; self.connecting = False
                    self.connection_id = event.get("connection_id")
                    self._cancel_output_jobs()
                    self.output_pending.clear(); self.output_failed.clear()
                    self.output_supported = dict(event.get("output_controls_supported", {}))
                    self.output_confirmed = dict(event.get("output_values", {}))
                    self._update_output_status()
                    self.last_sound_ack = None
                    if self.latency_window is not None: self.latency_window.refresh_host()
                    self.voice_count = event.get("voice_count", VOICE_COUNT)
                    self.allocator.voice_count = self.voice_count
                    self.apply_all_button.configure(text=f"应用到 {self.voice_count} 声部")
                    self.last_parameters.clear(); self.patch_requests.clear()
                    self.connection_pill.set_status("离线模拟" if event.get("simulated") else f"已连接 {event.get('port')}", "warning" if event.get("simulated") else "success")
                    self.connect_button.configure(text="断开连接", state="normal")
                    self.piano.set_enabled(True)
                    self.apply_all()
                    profile = event.get("transport_profile", {})
                    backend = profile.get("backend", "普通串口")
                    if backend == "ftdi-d2xx":
                        timer = profile.get("latency_ms")
                        backend = f"FTDI D2XX · USB 定时器 {timer} ms" if timer is not None else "FTDI D2XX · USB 定时器未确认"
                    self._notice("离线模拟：不访问硬件，不产生声音。" if event.get("simulated") else f"设备连接成功，已清音；{backend}。")
                    if self.voice_count < VOICE_COUNT:
                        self._notice("旧位流不支持 32 位声部状态，已限制为前 4 声部；请下载 32 声部位流。", True)
                    self._update_voice_status()
                elif kind == "disconnected":
                    self._clear_keys()
                    self.connected = False; self.connecting = False; self.active_mask = 0
                    self.connection_id = None; self.last_sound_ack = None
                    self._cancel_output_jobs()
                    self.output_pending.clear(); self.output_confirmed.clear(); self.output_failed.clear()
                    self.output_supported.clear()
                    self._update_output_status()
                    if self.latency_window is not None: self.latency_window.refresh_host()
                    self.last_parameters.clear(); self.patch_requests.clear()
                    self.allocator.clear(); self.piano.release_all(); self.piano.set_active_notes([]); self.piano.set_enabled(False)
                    self.connection_pill.set_status("未连接", "muted")
                    self.connect_button.configure(text="连接设备", state="normal")
                    self.offline_check.configure(state="normal"); self.port_combo.configure(state="readonly")
                    self._update_voice_status()
                elif kind == "ack":
                    if event.get("active_mask") is not None:
                        self.active_mask = (self.active_mask & ~0xFF) | (event["active_mask"] & 0xFF)
                    if event.get("opcode") == 10 and event.get("status") == 0:
                        self.active_mask = 0
                    tag = event.get("tag", "")
                    self._confirm_patch_ack(event)
                    self._confirm_output_ack(event)
                    self.rtt_var.set(f"ACK {event['rtt_ms']:.1f} ms")
                    if (self.connected and event.get("status") == 0
                            and (1 <= event.get("opcode", 0) <= 10 or event.get("opcode") in OUTPUT_OPCODES)
                            and event.get("connection_id") == self.connection_id):
                        self.last_sound_ack = event
                        if self.latency_window is not None: self.latency_window.observe_sound_ack(event)
                        host_timing_dirty = True
                    voice_status_dirty = True
                    if event.get("tag", "").startswith(("note_on", "patch")):
                        self.message_var.set(f"FPGA 已确认 · {event.get('tag')} · 最近活动位图 0x{self.active_mask:08X}")
                elif kind == "voice_status":
                    self.active_mask = event["active_mask"] & 0xFFFFFFFF
                    voice_status_dirty = True
                elif kind == "patch_preload_cancelled":
                    self.patch_requests.pop((event.get("tag"), event.get("voice")), None)
                elif kind == "output_control_unsupported":
                    if self.connected and event.get("connection_id") == self.connection_id:
                        opcode = event["opcode"]
                        self.output_supported[opcode] = False
                        self.output_pending.pop(opcode, None)
                        self.output_intents.pop(opcode, None)
                        job = self.output_jobs.pop(opcode, None)
                        if job is not None: self.root.after_cancel(job)
                        self._update_output_status()
                        self._notice("当前位流不支持此输出控制；请下载新版位流。演奏连接继续可用。", True)
                elif kind in ("latency_status", "latency_unsupported", "latency_status_aborted",
                              "voice_onset_status", "voice_onset_unsupported", "voice_onset_aborted"):
                    if self.latency_window is not None: self.latency_window.receive(event)
                elif kind == "error":
                    self._notice(event.get("message", "通信失败"), True)
                elif kind == "log":
                    self._notice(event.get("message", ""))
        except queue.Empty:
            pass
        # One paint per GUI batch keeps 192-parameter applies and 64-byte
        # diagnostics from redrawing every voice for every individual ACK.
        if voice_status_dirty:
            self._update_voice_status()
        self._update_patch_readiness()
        if host_timing_dirty and self.latency_window is not None:
            self.latency_window.refresh_host()
        if not self.closing: self.root.after(25, self._drain_events)

    def _update_voice_status(self):
        self.active_label.configure(text=f"已确认活动 {self.active_mask.bit_count()} / {self.voice_count}")
        for v, pill in enumerate(self.voice_pills):
            active = bool(self.active_mask & (1 << v))
            held = self.allocator.note_for_voice(v) is not None
            available = v < self.voice_count
            pill.set_status("不可用" if not available else "演奏" if active and held else "尾音" if active else "静音", "success" if active else "muted")
            self.voice_tiles[v].configure(background=COLORS["accent"] if active and held else COLORS["amber"] if active else COLORS["panel_alt"],
                                          foreground=COLORS["bg"] if active else COLORS["muted"])

    def close(self):
        if self.closing: return
        self.closing = True
        self._cancel_output_jobs()
        if self.latency_window is not None: self.latency_window.close()
        self._clear_keys()
        self.piano.set_enabled(False)
        self.worker.close()
        self.message_var.set("正在清音并关闭串口…")
        def wait_closed():
            if self.worker.is_alive: self.root.after(50, wait_closed)
            else: self.root.destroy()
        wait_closed()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM26", help="select a port; connection still needs the Connect button")
    parser.add_argument("--offline", action="store_true", help="connect the simulated control backend, without audio")
    parser.add_argument("--connect", action="store_true", help="connect the selected serial port at startup")
    args = parser.parse_args()
    configure_display()
    root = tk.Tk()
    InstrumentApp(root, args.port, args.offline, args.connect)
    root.mainloop()
