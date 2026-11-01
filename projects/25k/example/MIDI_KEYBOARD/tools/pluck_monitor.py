#!/usr/bin/env python3
"""Linux input monitor; explicit emitter arming is limited to the temporary probe."""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import asdict, dataclass, replace
import fcntl
import json
import os
from pathlib import Path
import struct
import tempfile
import threading
import time

from panel_display import PanelError, UsbTransport
from screen_control import GET_PLUCK, GET_PLUCK_NOISE, GET_STATUS, SET_PLUCK_EMITTERS, SET_PLUCK_THRESHOLDS, decode_frame, encode_request


class UnsupportedFirmware(PanelError):
    pass


@dataclass(frozen=True)
class NoiseSnapshot:
    sample_count: int
    flags: int
    floors: tuple[int, ...]
    on_levels: tuple[int, ...]
    off_levels: tuple[int, ...]
    current_vpp: tuple[int, ...]
    calibration_done: int
    calibration_length: int

    @classmethod
    def decode(cls, words: list[int]) -> "NoiseSnapshot":
        if len(words) != 16 or words[0] != 0x314F4E50:
            raise ValueError("Unsupported noise snapshot format; expected PNO1")
        data = struct.pack("<16I", *words)
        return cls(words[1], words[2], struct.unpack_from("<5H", data, 12),
                   struct.unpack_from("<5H", data, 24), struct.unpack_from("<5H", data, 36),
                   struct.unpack_from("<5H", data, 48), words[15] & 65535, words[15] >> 16)

    @property
    def valid_channels(self) -> int:
        return (self.flags >> 8) & 31

    @property
    def carrier_reference(self) -> bool:
        return bool(self.flags & 8)


@dataclass(frozen=True)
class Snapshot:
    flags: int
    sample_count: int
    raw: tuple[int, ...]
    amplitudes: tuple[int, ...]
    trigger_count: int
    on_threshold: int
    off_threshold: int
    sample_hz: int
    channel: int
    transpose: int
    trigger_counts: tuple[int, ...]
    overruns: int
    window_samples: int = 0
    noise: NoiseSnapshot | None = None

    @classmethod
    def decode(cls, words: list[int]) -> "Snapshot":
        if len(words) != 16 or words[0] != 0x314B4C50:
            raise ValueError("Unsupported pluck snapshot format; expected PLK1")
        data = struct.pack("<16I", *words)
        transpose = (words[11] >> 8) & 255
        return cls(words[1], words[2], struct.unpack_from("<6h", data, 12),
                   struct.unpack_from("<5H", data, 24), words[9], words[10] & 65535,
                   words[10] >> 16, words[11] >> 16, words[11] & 15,
                   transpose - 256 if transpose & 128 else transpose,
                   struct.unpack_from("<5H", data, 48), words[15] & 65535, words[15] >> 16)

    @property
    def ready(self) -> bool:
        return self.flags & 3 == 3

    @property
    def gates(self) -> int:
        return (self.flags >> 8) & 31

    @property
    def detailed(self) -> bool:
        return bool(self.flags & 32)

    @property
    def diagnostic_only(self) -> bool:
        return bool(self.flags & 64)

    @property
    def emitters_on(self) -> bool:
        return bool(self.flags & 128)

    @property
    def peak_to_peak(self) -> bool:
        return bool(self.flags & 8192)

    @property
    def adaptive_noise(self) -> bool:
        return bool(self.flags & 16384)

    @property
    def carrier_mode(self) -> bool:
        return bool(self.flags & 32768)

    @property
    def timeouts(self) -> int:
        return self.flags >> 16


class ControlClient:
    def __init__(self, transport: UsbTransport):
        self.transport = transport
        self.sequence = 0
        self.pending = bytearray()

    def query(self, opcode: int, word: int = 0) -> int:
        self.sequence = (self.sequence + 1) & 65535
        self.transport.write(encode_request(opcode, self.sequence, word))
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            if len(self.pending) < 16:
                self.pending.extend(self.transport.read())
                continue
            frame = decode_frame(bytes(self.pending[:16]))
            del self.pending[:16]
            if frame.opcode != (opcode | 128) or frame.sequence != self.sequence:
                raise PanelError("Unexpected MK reply; close other screen/control clients")
            if frame.arg0 == 1 and opcode == GET_PLUCK:
                raise UnsupportedFirmware("当前位流不支持弹拨诊断；MIDI 仍可监视，需验证并授权加载弹拨候选")
            if frame.arg0:
                raise PanelError(f"MK command {opcode:#x} rejected: status {frame.arg0}")
            return frame.arg1
        raise PanelError("MK response deadline exceeded")

    def snapshot(self, between_words=None) -> Snapshot:
        words = []
        for word in range(16):
            words.append(self.query(GET_PLUCK, word))
            if between_words is not None:
                between_words()
        snapshot = Snapshot.decode(words)
        if snapshot.adaptive_noise or snapshot.carrier_mode:
            words = []
            for word in range(16):
                words.append(self.query(GET_PLUCK_NOISE, word))
                if between_words is not None:
                    between_words()
            snapshot = replace(snapshot, noise=NoiseSnapshot.decode(words))
            if snapshot.carrier_mode != snapshot.noise.carrier_reference:
                raise PanelError("PLK1/PNO1 carrier capability mismatch; refusing to label reference data as noise")
        return snapshot


class MidiParser:
    def __init__(self):
        self.status = 0
        self.data: list[int] = []
        self.sysex = False

    def feed(self, data: bytes) -> list[tuple[int, ...]]:
        messages = []
        for value in data:
            if value >= 0xF8:
                continue
            if value & 128:
                self.data.clear()
                if value == 0xF0:
                    self.sysex = True
                    self.status = 0
                elif value >= 0xF0:
                    self.sysex = False
                    self.status = value if value in (0xF1, 0xF2, 0xF3) else 0
                else:
                    self.sysex = False
                    self.status = value
                continue
            if self.sysex or not self.status:
                continue
            self.data.append(value)
            length = 1 if self.status >> 4 in (12, 13) or self.status in (0xF1, 0xF3) else 2
            if len(self.data) == length:
                messages.append((self.status, *self.data))
                self.data.clear()
                if self.status >= 0xF0:
                    self.status = 0
        return messages


def note_name(note: int) -> str:
    return f"{('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')[note % 12]}{note // 12 - 1}"


def describe_midi(message: tuple[int, ...]) -> str:
    status = message[0]
    channel = (status & 15) + 1
    kind = status >> 4
    if kind in (8, 9):
        action = "On " if kind == 9 and message[2] else "Off"
        return f"CH{channel:02} Note {action} {message[1]:3} {note_name(message[1]):3} vel={message[2]}"
    if kind == 11:
        return f"CH{channel:02} CC {message[1]} = {message[2]}"
    if kind == 12:
        return f"CH{channel:02} Program {message[1]}"
    if kind == 14:
        return f"CH{channel:02} Pitch Bend {message[1] | message[2] << 7}"
    return " ".join(f"{value:02X}" for value in message)


def discover_device(root: Path = Path("/sys/bus/usb/devices")) -> dict:
    matches = []
    for path in root.iterdir():
        try:
            if ((path / "idVendor").read_text().strip(), (path / "idProduct").read_text().strip()) == ("fb9a", "fb9b"):
                matches.append(path)
        except (FileNotFoundError, NotADirectoryError):
            continue
    if len(matches) != 1:
        raise PanelError(f"需要唯一一块 fb9a:fb9b 设备；当前找到 {len(matches)} 块")
    path = matches[0]
    midi = list(path.glob("*/sound/card*/midiC*D*"))
    if len(midi) != 1:
        raise PanelError("未找到此 USB 设备的唯一 ALSA MIDI 节点")
    return {"path": path.name, "speed_mbps": (path / "speed").read_text().strip(),
            "serial": (path / "serial").read_text().strip(), "midi": "/dev/snd/" + midi[0].name}


class Monitor(threading.Thread):
    def __init__(self, telemetry_file: Path | None = None):
        super().__init__(daemon=True)
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.status = "等待设备…"
        self.snapshot: Snapshot | None = None
        self.updated = 0.0
        self.notes: set[tuple[int, int]] = set()
        self.events: deque = deque(maxlen=300)
        self.event_count = 0
        self.emitter_request: bool | None = None
        self.threshold_request: tuple[int, int] | None = None
        self.telemetry_file = telemetry_file

    def write_telemetry(self):
        if self.telemetry_file is None:
            return
        with self.lock:
            snapshot = self.snapshot
            result = {"timestamp": time.time(), "status": self.status,
                      "age_seconds": time.monotonic() - self.updated if self.updated else None,
                      "snapshot": asdict(snapshot) if snapshot else None,
                      "peak_to_peak": bool(snapshot and snapshot.peak_to_peak),
                      "carrier_mode": bool(snapshot and snapshot.carrier_mode),
                      "event_count": self.event_count, "notes": sorted(self.notes),
                      "events": list(self.events)[-20:]}
        self.telemetry_file.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.telemetry_file.parent,
                                         prefix=self.telemetry_file.name + ".", delete=False) as output:
            temporary = Path(output.name)
            try:
                json.dump(result, output, ensure_ascii=False)
                output.write("\n")
                output.flush()
                os.replace(temporary, self.telemetry_file)
            finally:
                temporary.unlink(missing_ok=True)

    def read_midi(self, descriptor: int, parser: MidiParser):
        for attempt in range(32):
            try:
                data = os.read(descriptor, 4096)
            except BlockingIOError:
                return
            if not data:
                raise PanelError("MIDI device disconnected")
            for message in parser.feed(data):
                with self.lock:
                    self.event_count += 1
                    self.events.append((self.event_count, time.strftime("%H:%M:%S"), describe_midi(message)))
                    kind = message[0] >> 4
                    channel = message[0] & 15
                    if kind in (8, 9):
                        note = (channel, message[1])
                        if kind == 9 and message[2]:
                            self.notes.add(note)
                        else:
                            self.notes.discard(note)
                    elif kind == 11 and message[1] in (120, 123):
                        self.notes = {note for note in self.notes if note[0] != channel}

    def run(self):
        while not self.stop_event.is_set():
            try:
                lock_path = Path(tempfile.gettempdir()) / f"gw25k-pluck-monitor-{os.getuid()}.lock"
                with lock_path.open("a") as lease:
                    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    identity = discover_device()
                    descriptor = os.open(identity["midi"], os.O_RDONLY | os.O_NONBLOCK)
                    try:
                        self.session(identity, descriptor)
                    finally:
                        os.close(descriptor)
            except Exception as error:
                with self.lock:
                    self.status = f"连接中断 / 不可用：{error}；1 秒后重试"
                    self.snapshot = None
                    self.updated = 0
                    self.notes.clear()
                    self.emitter_request = None
                    self.threshold_request = None
                self.write_telemetry()
                self.stop_event.wait(1)

    def session(self, identity: dict, descriptor: int):
        transport = None
        parser = MidiParser()
        supported = True
        next_connect = 0.0
        last_count = None
        last_progress = time.monotonic()
        emitter_wanted = False
        next_arm_refresh = 0.0
        try:
            while not self.stop_event.is_set():
                if not (Path("/sys/bus/usb/devices") / identity["path"]).exists():
                    raise PanelError("USB device disconnected")
                self.read_midi(descriptor, parser)
                if transport is None and time.monotonic() >= next_connect:
                    try:
                        transport = UsbTransport(timeout_ms=200).__enter__()
                        client = ControlClient(transport)
                        supported = True
                    except PanelError as error:
                        with self.lock:
                            self.status = f"USB {identity['speed_mbps']} Mbps · MIDI 可读；ADC 诊断不可用（检查 USB 访问权限）：{error}"
                        next_connect = time.monotonic() + 2
                if transport is not None and supported:
                    try:
                        with self.lock:
                            requested = self.emitter_request
                            self.emitter_request = None
                            diagnostic_only = bool(self.snapshot and self.snapshot.diagnostic_only)
                            thresholds = self.threshold_request
                            self.threshold_request = None
                            vpp_control = bool(self.snapshot and self.snapshot.diagnostic_only and self.snapshot.peak_to_peak)
                        if thresholds is not None and vpp_control:
                            client.query(SET_PLUCK_THRESHOLDS, (thresholds[1] << 16) | thresholds[0])
                        if requested is not None and diagnostic_only:
                            emitter_wanted = requested
                            next_arm_refresh = 0
                            if not requested:
                                client.query(SET_PLUCK_EMITTERS, 0)
                        if emitter_wanted and time.monotonic() >= next_arm_refresh:
                            client.query(SET_PLUCK_EMITTERS, 1)
                            next_arm_refresh = time.monotonic() + 0.5
                        snapshot = client.snapshot(lambda: self.read_midi(descriptor, parser))
                        if emitter_wanted and not snapshot.flags & 1:
                            emitter_wanted = False
                            client.query(SET_PLUCK_EMITTERS, 0)
                        now = time.monotonic()
                        if snapshot.sample_count != last_count:
                            last_progress = now
                            last_count = snapshot.sample_count
                        health = "ADC 正在采样" if snapshot.ready else "ADC 未就绪 / 校准中"
                        if (snapshot.adaptive_noise or snapshot.carrier_mode) and snapshot.emitters_on and not snapshot.ready:
                            health = "无遮挡载波参考校准中，请移开双手" if snapshot.carrier_mode else "逐路静态噪声校准中，请移开双手、不要弹拨"
                        if snapshot.diagnostic_only and not snapshot.emitters_on:
                            health = "临时诊断 · 发射灯关闭，仅观察 ADC / 滑杆"
                        if now - last_progress > 0.5:
                            health = "ADC 采样计数停滞，勿视为有效演奏"
                        with self.lock:
                            self.snapshot = snapshot
                            self.updated = now
                            self.status = f"USB {identity['speed_mbps']} Mbps · {health} · {identity['serial']}"
                    except UnsupportedFirmware as error:
                        supported = False
                        with self.lock:
                            self.status = str(error)
                self.write_telemetry()
                self.stop_event.wait(0.05 if transport is not None and supported else 0.02)
        finally:
            if transport is not None:
                if emitter_wanted:
                    try:
                        client.query(SET_PLUCK_EMITTERS, 0)
                    except Exception:
                        pass
                transport.close()


class Window:
    def __init__(self, root, monitor: Monitor):
        import tkinter as tk
        from tkinter import ttk

        self.root = root
        self.monitor = monitor
        self.last_event = 0
        self.last_sample = None
        self.history: deque = deque(maxlen=160)
        root.title("GW25K · 弹拨板 / 触摸板实时 MIDI")
        root.geometry("1100x850")
        root.minsize(850, 650)
        container = ttk.Frame(root, padding=16)
        container.pack(fill="both", expand=True)
        self.status = tk.StringVar(value="正在连接实际 USB 设备…")
        ttk.Label(container, text="GW25K 实时输入监视", font=("sans", 19, "bold")).pack(anchor="w")
        ttk.Label(container, textvariable=self.status, wraplength=980).pack(anchor="w", pady=(6, 10))
        ttk.Label(container, text="默认只读 / 不烧录 · CHN1–5 暂映射到触摸键 A–E（48–52）；CHN6 仅显示").pack(anchor="w")
        self.carrier_info = tk.StringVar(value="PWM 配置尚未回读；不代表引脚波形已实测。")
        ttk.Label(container, textvariable=self.carrier_info, wraplength=1040).pack(anchor="w", pady=4)
        emitter_controls = ttk.Frame(container)
        emitter_controls.pack(fill="x", pady=4)
        self.arm_button = ttk.Button(emitter_controls, text="电气确认后开启发射灯…", command=self.arm_emitters, state="disabled")
        self.arm_button.pack(side="left")
        ttk.Button(emitter_controls, text="关闭发射灯", command=self.disarm_emitters).pack(side="left", padx=8)
        ttk.Label(emitter_controls, text="仅临时诊断；未确认 LED 电流额定值前不要开启。断联后 2 秒自动关闭。").pack(side="left")
        threshold_controls = ttk.Frame(container)
        threshold_controls.pack(fill="x", pady=4)
        self.on_value = tk.StringVar(value="64")
        self.off_value = tk.StringVar(value="32")
        for label, variable in (("Vpp ON", self.on_value), ("OFF", self.off_value)):
            ttk.Label(threshold_controls, text=label).pack(side="left", padx=(0, 4))
            ttk.Spinbox(threshold_controls, from_=0, to=65535, textvariable=variable, width=7).pack(side="left", padx=(0, 8))
        self.threshold_button = ttk.Button(threshold_controls, text="应用阈值 / 重新校准", command=self.apply_thresholds, state="disabled")
        self.threshold_button.pack(side="left")
        self.threshold_hint = tk.StringVar(value="计数单位；64/32 仅为试验初值，以板端回读为准。")
        ttk.Label(threshold_controls, textvariable=self.threshold_hint).pack(side="left", padx=8)
        columns = ("input", "raw", "amplitude", "noise", "limits", "gate", "triggers", "mapping")
        self.table = ttk.Treeview(container, columns=columns, show="headings", height=6)
        for column, label in zip(columns, ("物理输入", "ADC 有符号原值", "基线差值绝对值", "静态噪声上限", "有效 ON/OFF", "门控", "触发次数", "统一 MIDI 映射")):
            self.table.heading(column, text=label)
            self.table.column(column, width=130, anchor="center")
        for channel in range(6):
            self.table.insert("", "end", iid=str(channel), values=(f"CHN{channel+1}", "—", "—", "—", "—", "—", "—", "待诊断"))
        self.table.pack(fill="x", pady=10)
        self.details = tk.StringVar(value="ADC 尚无有效诊断；‘—’不表示零信号。")
        ttk.Label(container, textvariable=self.details, wraplength=980).pack(anchor="w")
        self.noise_info = tk.StringVar(value="遮挡后不连续补发；请分别观察遮挡瞬间与移开瞬间的触发次数。")
        ttk.Label(container, textvariable=self.noise_info, wraplength=980).pack(anchor="w", pady=4)
        self.plot = tk.Canvas(container, height=180, background="#111827", highlightthickness=0)
        self.plot.pack(fill="x", pady=10)
        self.keys = []
        keyboard = ttk.Frame(container)
        keyboard.pack(fill="x")
        for key_index in range(16):
            label = tk.Label(keyboard, text=f"{chr(65+key_index)}\n{48+key_index}", background="#e5e7eb", width=5, height=2)
            label.pack(side="left", fill="x", expand=True, padx=2)
            self.keys.append(label)
        self.midi_info = tk.StringVar(value="实际收到的 MIDI（含触摸键、弹拨、滑条、编码器），不在电脑合成消息。")
        ttk.Label(container, textvariable=self.midi_info).pack(anchor="w", pady=(8, 4))
        self.log = tk.Text(container, height=9, background="#111827", foreground="#d1fae5", font=("monospace", 10))
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(50, self.refresh)

    def close(self):
        self.monitor.stop_event.set()
        self.root.destroy()

    def arm_emitters(self):
        from tkinter import messagebox
        with self.monitor.lock:
            carrier = bool(self.monitor.snapshot and self.monitor.snapshot.carrier_mode)
        drive = "此候选输出五路50%占空比PWM；峰值电流仍须满足LED额定值。" if carrier else "旧候选可能输出直流；请确认连续电流额定值。"
        if messagebox.askyesno("发射灯电气确认", "网表未注明发射灯型号。3.3V / 120Ω 支路电流上界约 27.5mA（实际随 LED 压降降低）。\n"
                              f"{drive}\n请确认限流电阻、供电和接线已核实，且允许该工作电流。\n"
                              "开启后请移开双手、保持无遮挡静止至少 1.2 秒；不要在此期间弹拨。\n"
                              "未确认请选择否。是否已完成检查并开启？", parent=self.root):
            with self.monitor.lock:
                self.monitor.emitter_request = True

    def disarm_emitters(self):
        with self.monitor.lock:
            self.monitor.emitter_request = False

    def apply_thresholds(self):
        from tkinter import messagebox

        try:
            on_value = int(self.on_value.get())
            off_value = int(self.off_value.get())
            if not 0 <= off_value < on_value <= 65535:
                raise ValueError("需要满足 0 ≤ OFF < ON ≤ 65535")
        except ValueError as error:
            messagebox.showerror("阈值无效", str(error), parent=self.root)
            return
        with self.monitor.lock:
            adaptive = bool(self.monitor.snapshot and self.monitor.snapshot.adaptive_noise)
            carrier = bool(self.monitor.snapshot and self.monitor.snapshot.carrier_mode)
        calibration_text = ("请保持无遮挡至少1.2秒，建立各路载波Vpp参考。\n"
                            "ON/OFF是最小下降计数；同时要求至少下降50%/25%。遮挡降低Vpp才触发。") if carrier else (
                            "请先移开双手，不遮挡、不弹拨。确认后采集约1秒静态噪声；\nON/OFF为每路噪声上限之上的余量。")
        if (adaptive or carrier) and not messagebox.askokcancel("逐路无遮挡校准", calibration_text, parent=self.root):
            return
        with self.monitor.lock:
            self.monitor.threshold_request = (on_value, off_value)

    def refresh(self):
        with self.monitor.lock:
            snapshot = self.monitor.snapshot
            updated = self.monitor.updated
            notes = set(self.monitor.notes)
            events = list(self.monitor.events)
            status = self.monitor.status
            count = self.monitor.event_count
        self.status.set(status)
        stale = not updated or time.monotonic() - updated > 1 or not snapshot or not snapshot.flags & 1
        self.arm_button.configure(state="normal" if snapshot and snapshot.diagnostic_only and not stale else "disabled")
        self.threshold_button.configure(state="normal" if snapshot and snapshot.diagnostic_only and snapshot.peak_to_peak and not stale else "disabled")
        vpp_mode = bool(snapshot and snapshot.peak_to_peak)
        adaptive = bool(snapshot and snapshot.adaptive_noise)
        carrier = bool(snapshot and snapshot.carrier_mode)
        noise = snapshot.noise if snapshot and not stale else None
        self.table.heading("amplitude", text="Vpp / 200 ms 保持" if vpp_mode else "基线差值绝对值")
        self.table.heading("noise", text="无遮挡载波参考" if carrier else "静态噪声上限")
        self.table.heading("limits", text="触发≤ / 恢复≥" if carrier else "有效 ON/OFF")
        self.threshold_hint.set("最小下降量64/32；另有50%/25%迟滞，无遮挡校准。" if carrier else
                                "逐路噪声上限 + ON/OFF余量；校准时请移开双手。" if adaptive else
                                "计数单位；64/32 仅为试验初值，以板端回读为准。")
        self.threshold_button.configure(text="无遮挡校准 / 应用余量" if adaptive or carrier else "应用阈值 / 重新校准")
        self.carrier_info.set("PWM配置 CHN1→5：1.66 / 3.40 / 6.97 / 1.00 / 4.86 kHz，50%占空比；启用标志不代表引脚已实测。" if carrier and not stale else
                              "非载波下降检测候选 / 状态过期；不宣称已输出指定频率。")
        for channel in range(6):
            if snapshot is None or stale:
                values = (f"CHN{channel+1}", "—", "—", "—", "—", "—", "—", "未验证")
            else:
                note = 48 + channel + snapshot.transpose
                mapped = f"CH{snapshot.channel+1} {note} {note_name(note)}" if channel < 5 else "滑杆，仅观察"
                values = (f"CHN{channel+1}", snapshot.raw[channel],
                          snapshot.amplitudes[channel] if channel < 5 and snapshot.detailed else "—",
                          noise.floors[channel] if channel < 5 and noise else "—",
                          f"{noise.on_levels[channel]}/{noise.off_levels[channel]}" if channel < 5 and noise else "—",
                          ("ON" if snapshot.gates & (1 << channel) else "off") if channel < 5 else "—",
                          snapshot.trigger_counts[channel] if channel < 5 and snapshot.detailed else "—", mapped)
            self.table.item(str(channel), values=values)
        if snapshot and not stale:
            window = f" · {snapshot.window_samples} 点/{1000 * snapshot.window_samples / snapshot.sample_hz:g} ms 窗口" if snapshot.peak_to_peak and snapshot.sample_hz else ""
            self.details.set(f"采样 #{snapshot.sample_count} · {snapshot.sample_hz} Hz · BUSY 超时 {snapshot.timeouts} · "
                             f"检测溢出 {snapshot.overruns} · {'最小下降量' if carrier else 'ON/OFF余量' if adaptive else '阈值'} {snapshot.on_threshold}/{snapshot.off_threshold} · 触发总数 {snapshot.trigger_count} · "
                             f"{'完整统计' if snapshot.detailed else '精简统计：差值/分路计数未启用'} · 发射灯 {'开' if snapshot.emitters_on else '关'}{window}")
            if self.last_sample != snapshot.sample_count:
                self.history.append(noise.current_vpp if carrier and noise else snapshot.amplitudes if vpp_mode else snapshot.raw[:5])
                self.last_sample = snapshot.sample_count
        else:
            self.details.set("ADC 诊断不可用 / 已过期；不能据此宣称弹拨识别成功。")
            self.history.clear()
            self.last_sample = None
        if noise:
            invalid = [str(channel + 1) for channel in range(5) if not noise.valid_channels & (1 << channel)]
            progress = f"校准 {noise.calibration_done}/{noise.calibration_length} 窗口"
            warning = f" · 未校准/载波过弱/阈值无效 {','.join(invalid)}，禁止触发" if invalid else " · 五路阈值有效（不代表已实物验收）"
            policy = "先稳定100ms再采1秒参考；低Vpp连续4ms触发一次，恢复≥阈值10ms后重装填。" if carrier else "校准时无遮挡；静止仍误触请提高余量，不据此反转极性。"
            self.noise_info.set(f"{progress}{warning} · 当前窗口Vpp {','.join(map(str, noise.current_vpp))} · {policy}")
        else:
            self.noise_info.set("未取得逐路噪声诊断；遮挡后不连续补发，需分别观察遮挡瞬间与移开瞬间的触发次数。")
        self.plot.delete("all")
        width = max(1, self.plot.winfo_width())
        baseline = 164 if vpp_mode else 94
        scale = max(32, max((abs(value) for sample in self.history for value in sample), default=0))
        self.plot.create_line(0, baseline, width, baseline, fill="#374151")
        self.plot.create_text(width-8, 30, anchor="e", text=f"{'Vpp' if vpp_mode else 'ADC ±'} 满幅 {scale} 计数 · 自动缩放", fill="#e5e7eb")
        for channel, color in enumerate(("#22d3ee", "#fbbf24", "#a78bfa", "#fb7185", "#4ade80")):
            points = []
            for sample_index, raw in enumerate(self.history):
                points.extend((sample_index * width / 159, baseline - raw[channel] * (116 if vpp_mode else 60) / scale))
            if len(points) >= 4:
                self.plot.create_line(*points, fill=color, width=2)
            self.plot.create_text(50 + 100 * channel, 12, text=f"CHN{channel+1}", fill=color)
        selected_channel = snapshot.channel if snapshot else 0
        transpose = snapshot.transpose if snapshot else 0
        for key_index, label in enumerate(self.keys):
            note = 48 + key_index + transpose
            active = (selected_channel, note) in notes if snapshot else any(held_note == note for _, held_note in notes)
            label.configure(text=f"{chr(65+key_index)}\n{note}", background="#34d399" if active else "#e5e7eb")
        new_events = [event for event in events if event[0] > self.last_event]
        if new_events:
            self.log.configure(state="normal")
            if new_events[0][0] > self.last_event + 1:
                self.log.insert("end", "[GUI 日志缓存已覆盖旧记录，不是无损录制]\n")
            for sequence, stamp, text in new_events:
                self.log.insert("end", f"{stamp}  {sequence:7}  {text}\n")
                self.last_event = sequence
            lines = int(self.log.index("end-1c").split(".")[0])
            if lines > 300:
                self.log.delete("1.0", f"{lines-300}.0")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.midi_info.set(f"实际 MIDI 消息 {count} · 当前持音 {len(notes)} · 日志仅保留最近300条 · 图为低速{'最近窗口Vpp' if carrier else 'Vpp保持值' if vpp_mode else '原值'}显示，非全速波形录制")
        self.root.after(50, self.refresh)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true", help="read one real snapshot/status without opening a GUI")
    parser.add_argument("--telemetry-file", type=Path, help="atomically replace a bounded latest-status JSON file; no second USB client needed")
    args = parser.parse_args(argv)
    if args.probe:
        try:
            identity = discover_device()
            with UsbTransport(timeout_ms=200) as transport:
                client = ControlClient(transport)
                result = {"device": identity, "status_flags": client.query(GET_STATUS)}
                try:
                    result["pluck"] = asdict(client.snapshot())
                    result["pluck_supported"] = True
                except UnsupportedFirmware as error:
                    result.update(pluck_supported=False, message=str(error))
        except (PanelError, OSError) as error:
            print(json.dumps({"error": str(error), "pluck_verified": False}, ensure_ascii=False))
            return 2
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    import tkinter as tk

    root = tk.Tk()
    monitor = Monitor(args.telemetry_file)
    Window(root, monitor)
    monitor.start()
    try:
        root.mainloop()
    finally:
        monitor.stop_event.set()
        monitor.join(timeout=2)
        with monitor.lock:
            monitor.status = "GUI 已关闭；发射灯租约停止续期"
            monitor.snapshot = None
            monitor.updated = 0
            monitor.notes.clear()
        monitor.write_telemetry()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
