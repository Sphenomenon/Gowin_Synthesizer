#!/usr/bin/env python3
"""Focused computer keyboard -> existing 138K 115200 MIDI input.

Independent performance window; does not modify the teammate's GUI or FPGA.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import time
import tkinter as tk

import serial
from midi_serial import DEFAULT_PORT, decode_record, performance, expression

NOTE_KEYS = dict(zip("zsxdcvgbhnjmq2w3er5t6y7ui", range(60, 85)))
PROGRAMS = [(73, "笛"), (40, "弦乐"), (56, "铜管"), (12, "马林巴"), (0, "钢琴")]
SOUND_NAMES = dict(zip(["flute", "strings", "trumpet", "marimba", "piano"], [p[1] for p in PROGRAMS]))
EFFECTS = [(1, "延迟"), (2, "合唱"), (4, "混响")]
WHITE_NOTES = [n for n in range(60, 85) if n % 12 not in (1, 3, 6, 8, 10)]
BG, PANEL, TEXT, MUTED, GREEN = "#0a1420", "#172838", "#edf4fa", "#a5b6c5", "#39d8ac"
REPEAT_DELAY_MS = 300
REPEAT_INTERVAL_MS = 80


class Notes:
    """Own notes by physical keycode, independent of modifiers on release."""

    def __init__(self, send):
        self.send = send
        self.held = {}
        self.pedal = False
        self.velocity = 100

    def press(self, token, note):
        if token in self.held:
            return
        already = note in self.held.values()
        self.held[token] = note
        if not already:
            self.send(bytes((0x90, note, self.velocity)))

    def release(self, token):
        note = self.held.pop(token, None)
        if note is not None and note not in self.held.values():
            self.send(bytes((0x80, note, 0)))

    def retrigger(self, token):
        note = self.held.get(token)
        # CC64 defers Note Off in the shared synth. Preserve pedal hold instead
        # of accumulating unreleased voices while the pedal is down.
        if note is not None and not self.pedal:
            self.send(bytes((0x80, note, 0)))
            self.send(bytes((0x90, note, self.velocity)))

    def sustain(self, down):
        if self.pedal != down:
            self.pedal = down
            self.send(bytes((0xb0, 64, 127 if down else 0)))

    def drain(self):
        packet = b"".join(bytes((0x80, note, 0)) for note in sorted(set(self.held.values())))
        if self.pedal:
            packet += bytes((0xb0, 64, 0))
        self.held.clear()
        self.pedal = False
        return packet

    def discard(self):
        self.held.clear()
        self.pedal = False


class KeyboardWindow:
    def __init__(self, root, port=DEFAULT_PORT, log=None, connect=True):
        self.root, self.port_name, self.log = root, port, log
        self.port = None
        self.ready = False
        self.closed = False
        self.buffer = bytearray()
        self.recovery = b""
        self.cpu_sequence = None
        self.last_state = None
        self.last_expression = None
        self.panic_epoch = None
        self.telemetry_seen = False
        self.requests = {}
        self.scale_timers = {}
        self.bend_owned = False
        self.effect_request = None
        self.notes = Notes(self.send)
        self.pressed = {}
        self.releases = {}
        self.release_times = {}
        self.repeat_timers = {}
        self.repeat_due = {}
        self.status = tk.StringVar(value="尚未连接")
        self.board = tk.StringVar(value="等待板端状态；按键立即发送，不等待每秒回报。")
        self.activity = tk.StringVar(value="切到英文输入法，点击本窗口后演奏。")
        root.title("138K · 电脑键盘演奏")
        root.configure(bg=BG)
        root.geometry("1120x890")
        root.minsize(980, 850)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.build_widgets()
        # Run before button class bindings, so Space only operates the pedal.
        tag = f"PerformanceKeys{root.winfo_id()}"
        root.bind_class(tag, "<KeyPress>", self.key_press)
        root.bind_class(tag, "<KeyRelease>", self.key_release)
        def attach(widget):
            widget.bindtags((tag,) + widget.bindtags())
            for child in widget.winfo_children():
                attach(child)
        attach(root)
        root.bind("<FocusOut>", lambda event: root.after_idle(self.check_focus))
        root.bind("<Unmap>", lambda event: self.release_owned() if event.widget == root else None)
        self.poll_id = root.after(5, self.poll)
        if connect:
            self.connect()

    def label(self, parent, text=None, variable=None, size=11, color=TEXT):
        return tk.Label(parent, text=text, textvariable=variable, bg=BG, fg=color,
                        font=("Noto Sans CJK SC", size), anchor="w")

    def button(self, parent, text, command):
        return tk.Button(parent, text=text, command=command, bg=PANEL, fg=TEXT,
                         activebackground="#2c465d", activeforeground=TEXT,
                         relief="flat", padx=12, pady=7, takefocus=False,
                         font=("Noto Sans CJK SC", 10))

    def build_widgets(self):
        body = tk.Frame(self.root, bg=BG, padx=24, pady=16)
        body.pack(fill="both", expand=True)
        header = tk.Frame(body, bg=BG)
        header.pack(fill="x")
        self.label(header, "138K  键盘演奏", size=22).pack(side="left")
        self.button(header, "重新连接", self.connect).pack(side="right", padx=(8, 0))
        self.button(header, "Esc  全部清音", self.panic).pack(side="right")
        self.status_label = self.label(body, variable=self.status, color=GREEN)
        self.status_label.pack(fill="x", pady=(8, 0))
        self.label(body, variable=self.board, color=MUTED).pack(fill="x")
        self.label(body, "低音区 C4–B4： Z S X D C V G B H N J M     高音区 C5–C6： Q 2 W 3 E R 5 T 6 Y 7 U I").pack(fill="x", pady=(14, 2))
        self.label(body, "短按一次 · 长按 300ms 后每 80ms 连击 · 松开停止      空格：延音（暂停连击）      [ / ]：力度减 / 加", color=MUTED).pack(fill="x")
        self.canvas = tk.Canvas(body, height=205, bg=BG, highlightthickness=0, takefocus=True)
        self.canvas.pack(fill="x", pady=(14, 8))
        self.canvas.bind("<Configure>", lambda event: self.draw_keys())
        self.canvas.bind("<Button-1>", lambda event: self.canvas.focus_set())
        mode_row = tk.Frame(body, bg=BG)
        mode_row.pack(fill="x", pady=(0, 8))
        self.label(mode_row, "合成模式  ").pack(side="left")
        self.mode_buttons = {}
        for mode, title in enumerate(("F1  A · 32×1", "F2  B · 32×4", "F3  C · 4×32")):
            button = self.button(mode_row, title, lambda m=mode: self.set_mode(m))
            button.pack(side="left", padx=(0, 8))
            self.mode_buttons[mode] = button
        sound_row = tk.Frame(body, bg=BG)
        sound_row.pack(fill="x")
        self.label(sound_row, "五种音色  ").pack(side="left")
        self.sound_buttons = {}
        for index, (program, title) in enumerate(PROGRAMS):
            button = self.button(sound_row, f"F{index + 5}  {title}", lambda p=program: self.set_program(p))
            button.pack(side="left", padx=(0, 8))
            self.sound_buttons[index] = button
        effect_row = tk.Frame(body, bg=BG)
        effect_row.pack(fill="x", pady=(8, 0))
        self.label(effect_row, "音效叠加  ").pack(side="left")
        self.effect_buttons = {}
        for index, (bit, title) in enumerate(EFFECTS):
            button = self.button(effect_row, f"F{index + 10}  {title} · 关", lambda b=bit: self.toggle_effect(b))
            button.pack(side="left", padx=(0, 8))
            self.effect_buttons[bit] = button
        self.button(effect_row, "F4  音效全关", lambda: self.set_effects(0)).pack(side="left")
        route_row = tk.Frame(body, bg=BG)
        route_row.pack(fill="x", pady=(8, 0))
        self.label(route_row, "声道路由  ").pack(side="left")
        self.route_buttons = {}
        for route, title in enumerate(("立体声", "仅左", "仅右", "静音")):
            button = self.button(route_row, title, lambda v=route: self.set_route(v))
            button.pack(side="left", padx=(0, 8))
            self.route_buttons[route] = button
        expression_row = tk.Frame(body, bg=BG)
        expression_row.pack(fill="x", pady=(8, 0))
        self.expression_buttons, self.scale_vars, self.scales = {}, {}, {}
        for field, title in (("vibrato", "VIBR 颤音"), ("glide", "GLIDE 过渡")):
            button = self.button(expression_row, title, lambda f=field: self.toggle_expression(f))
            button.pack(side="left", padx=(0, 6))
            self.expression_buttons[field] = button
            variable = tk.IntVar(value=0)
            scale = tk.Scale(expression_row, from_=0, to=127, orient="horizontal", length=180,
                             variable=variable, command=lambda value, f=field: self.queue_scale(f, value),
                             bg=BG, fg=TEXT, highlightthickness=0, troughcolor=PANEL, takefocus=False)
            scale.pack(side="left", padx=(0, 14))
            self.scale_vars[field], self.scales[field] = variable, scale
        bend_row = tk.Frame(body, bg=BG)
        bend_row.pack(fill="x", pady=(4, 0))
        self.label(bend_row, "BEND 弯音  ").pack(side="left")
        self.bend_label = self.label(bend_row, "待回读", color=MUTED)
        self.bend_label.pack(side="left", padx=(0, 8))
        variable = tk.IntVar(value=0)
        scale = tk.Scale(bend_row, from_=-8192, to=8191, resolution=1, orient="horizontal", length=330,
                         variable=variable, command=lambda value: self.queue_scale("bend", value),
                         bg=BG, fg=TEXT, highlightthickness=0, troughcolor=PANEL, takefocus=False)
        scale.pack(side="left", padx=(0, 12))
        self.scale_vars["bend"], self.scales["bend"] = variable, scale
        self.button(bend_row, "弯音归中", lambda: self.set_bend(0)).pack(side="left")
        self.snap_button = self.button(bend_row, "SNAP · PCM快照", self.take_snapshot)
        self.snap_button.pack(side="right")
        self.snapshot_text = tk.StringVar(value="SNAP：等待板端快照能力回读。")
        self.label(body, variable=self.snapshot_text, color=MUTED).pack(fill="x", pady=(4, 0))
        self.label(body, "← / →：按住向下 / 向上弯音，松开归中；Backspace 归中。GLIDE 值越大，弯音过渡越慢。", size=10, color=MUTED).pack(fill="x")
        self.label(body, variable=self.activity, color=GREEN).pack(fill="x", pady=(12, 0))
        self.label(body, "绿键显示本机按住状态；板端回读约每秒更新。失焦 / 关闭窗口会释放本机音符。", size=10, color=MUTED).pack(fill="x")

    def record(self, kind, **data):
        if self.log:
            self.log.write(json.dumps(dict(time=time.time(),kind=kind,**data), ensure_ascii=False) + "\n")
            self.log.flush()

    def connect(self):
        if self.port:
            self.release_owned()
            if self.port:  # A failed release may already have closed the port.
                self.port.close()
        self.port = None
        self.ready = False
        self.buffer.clear()
        self.cpu_sequence = None
        self.last_state = None
        self.telemetry_seen = False
        self.effect_request = None
        self.last_expression = None
        self.panic_epoch = None
        self.requests.clear()
        self.update_controls()
        try:
            self.port = serial.Serial(port=None, baudrate=115200, timeout=0, write_timeout=.1,
                                      exclusive=True if os.name == "posix" else None)
            self.port.dtr = False
            self.port.rts = False
            self.port.port = self.port_name
            self.port.open()
            self.port.reset_input_buffer()
            self.opened = time.monotonic()
            self.status.set("连接中 → 排出 USB 旧缓存，等待 138K 就绪（约 3 秒）")
            self.status_label.configure(fg=MUTED)
            self.record("open", port=self.port_name)
        except (OSError, serial.SerialException) as error:
            self.fail(str(error))

    def send(self, data):
        if not data:
            return
        if not self.ready or self.port is None:
            raise serial.SerialException("138K 尚未就绪")
        try:
            if self.port.write(data) != len(data):
                raise serial.SerialTimeoutException("串口写入不完整")
            self.record("tx", hex=data.hex(" ").upper())
        except (OSError, serial.SerialException):
            # Retain releases even if the port disappears during Note Off.
            if data[0] == 0x90:
                self.recovery += bytes((0x80, data[1], 0))
            elif data[0] == 0xe0:
                self.recovery += bytes((0xe0, 0, 64))
            elif data[0] == 0x80 or data[:2] == bytes((0xb0, 64)):
                self.recovery += data if data[0] == 0x80 else bytes((0xb0, 64, 0))
            raise

    def fail(self, reason):
        self.cancel_repeats()
        self.recovery += self.notes.drain()
        if self.bend_owned:
            self.recovery += bytes((0xe0, 0, 64))
            self.bend_owned = False
        self.requests.clear()
        for timer in self.scale_timers.values():
            self.root.after_cancel(timer)
        self.scale_timers.clear()
        if self.port and self.port.is_open and self.recovery:
            try:
                if self.port.write(self.recovery) == len(self.recovery):
                    self.record("cleanup_tx", hex=self.recovery.hex(" ").upper())
                    self.recovery = b""
            except (OSError, serial.SerialException):
                pass
        if self.port:
            self.port.close()
        self.port, self.ready = None, False
        self.effect_request = None
        self.status.set("未连接 → " + reason)
        self.status_label.configure(fg="#ffb18a")
        self.record("disconnected", reason=reason)
        self.update_controls()
        self.draw_keys()

    def poll(self):
        try:
            if self.port:
                now = time.monotonic()
                chunk = self.port.read(min(self.port.in_waiting, 16384))
                if now - self.opened < 2:
                    self.buffer.clear()
                else:
                    self.buffer.extend(chunk)
                    while b"\n" in self.buffer:
                        line, _, rest = self.buffer.partition(b"\n")
                        self.buffer = bytearray(rest)
                        decoded = decode_record(bytes(line) + b"\n")
                        if decoded:
                            self.receive(*decoded)
                    if len(self.buffer) > 4096:
                        raise ValueError("串口数据格式不匹配")
                # P21/P22 can have a silent U15 return path while V14 input
                # remains usable. After draining old FTDI data, permit notes in
                # an explicit one-way state; any later K138 upgrades it.
                if not self.ready and now - self.opened > 2:
                    self.ready = True
                    self.status.set("单向演奏 · 未收到板端 C350/K138 回报")
                    self.status_label.configure(fg="#edbd68")
                    self.activity.set("可演奏；声音与板端状态需人工确认。")
                    self.record("one_way_ready", reason="no C350/K138 telemetry after FTDI drain")
                if self.telemetry_seen and self.ready and now - self.last_live > 3.5:
                    raise ValueError("板端回报超时，已停止本机演奏")
        except (OSError, serial.SerialException, ValueError) as error:
            self.fail(str(error))
        if not self.closed:
            self.poll_id = self.root.after(5, self.poll)

    def receive(self, kind, words):
        if kind == "C350":
            good = words[4] == 0x43505531 and words[5] == 0x50415353 and words[7] == 0
            self.cpu_sequence = words[0] if good else None
            if self.ready and not good:
                raise ValueError("AE350 未就绪或报告异常")
        elif kind == "K138" and words[0] == self.cpu_sequence:
            state = performance(words)
            if state["pc_input_errors"]:
                raise ValueError("板端串口故障：" + str(state["pc_input_errors"]))
            self.last_live = time.monotonic()
            self.telemetry_seen = True
            self.last_state = state
            if self.effect_request:
                request = self.effect_request
                fresh = 0 < ((state['sequence'] - request['sequence']) & 0xffffffff) < 0x80000000
                if fresh and state['effects'] == request['mask']:
                    self.effect_request = None
                    self.activity.set("音效状态已由 138K 回读确认。")
                elif time.monotonic() - request['time'] > 4:
                    self.effect_request = None
                    self.activity.set("音效请求未确认，当前按板端实际状态显示。")
            if not self.ready:
                self.ready = True
                if self.recovery:
                    packet, self.recovery = self.recovery, b""
                    self.send(packet)
                self.status.set("已连接 138K · 115200 MIDI → 点击窗口，直接用电脑键盘演奏")
                self.status_label.configure(fg=GREEN)
            notes = " ".join(map(str, state["held_notes"])) or "无"
            self.board.set(f"板端：模式 {state['mode']} · {SOUND_NAMES.get(state['sound'], state['sound'])} · {state['active_voices']} 声部 · 按键 {notes} · 输入错误 0")
            self.confirm_requests(state, ("route",))
            self.update_controls()
            self.record("state", **state)
        elif kind == "E138" and words[0] == self.cpu_sequence and self.last_state and words[0] == self.last_state["sequence"]:
            self.last_expression = expression(words)
            epoch = self.last_expression["panic_epoch"]
            if self.panic_epoch is None:
                self.panic_epoch = epoch
            elif epoch != self.panic_epoch:
                self.synchronize_panic(epoch)
            self.confirm_requests(self.last_expression, ("vibrato", "glide", "bend_index", "snap_request"))
            self.update_controls()
            self.record("expression", **self.last_expression)

    def operate(self, callback, redraw=True):
        if not self.ready:
            self.activity.set("等待 138K 连接就绪后再演奏。")
            return False
        try:
            callback()
        except (OSError, serial.SerialException) as error:
            self.fail(str(error))
            return False
        if redraw:
            self.draw_keys()
        return True

    def key_press(self, event):
        code, key = event.keycode, event.keysym.lower()
        if code in self.releases:
            self.root.after_cancel(self.releases.pop(code))
            released_at = self.release_times.pop(code, None)
            pressed_at = getattr(event, "time", None)
            # X11 synthetic repeat pairs share their server timestamp. A
            # genuine rapid up/down has a new timestamp and must retrigger.
            if released_at is not None and pressed_at is not None and pressed_at != released_at:
                self.finish_release(code)
        if code in self.pressed:
            self.schedule_repeat(code)
            return "break"
        self.pressed[code] = key
        if key in NOTE_KEYS:
            if self.operate(lambda: self.notes.press(code, NOTE_KEYS[key])):
                self.repeat_due[code] = time.monotonic() + REPEAT_DELAY_MS / 1000
                self.schedule_repeat(code)
        elif key in ("left", "right"):
            if self.set_bend(-4096 if key == "left" else 4096):
                self.bend_owned = True
        elif key == "backspace":
            self.set_bend(0)
        elif key == "space":
            self.operate(lambda: self.notes.sustain(True))
        elif key == "escape":
            self.panic()
        elif key in ("f1", "f2", "f3"):
            self.set_mode(int(key[1:]) - 1)
        elif key in ("f5", "f6", "f7", "f8", "f9"):
            self.set_program(PROGRAMS[int(key[1:]) - 5][0])
        elif key in ("f10", "f11", "f12"):
            self.toggle_effect(1 << (int(key[1:]) - 10))
        elif key == "f4":
            self.set_effects(0)
        elif key in ("bracketleft", "bracketright"):
            self.notes.velocity = max(1, min(127, self.notes.velocity + (8 if key == "bracketright" else -8)))
            self.activity.set(f"新音符力度：{self.notes.velocity}")
        return "break"

    def key_release(self, event):
        code = event.keycode
        # Stop repeats on receipt of Release, before the X11 pairing window.
        if code in self.repeat_timers:
            self.root.after_cancel(self.repeat_timers.pop(code))
        if code in self.releases:
            self.root.after_cancel(self.releases[code])
        # Fedora/XWayland can deliver the repeat Press after Tk has become
        # idle. Keep a short bounded release window; timestamp matching avoids
        # swallowing genuine fast taps. Focus/close cleanup remains immediate.
        self.release_times[code] = getattr(event, "time", None)
        self.releases[code] = self.root.after(30, lambda: self.finish_release(code))
        return "break"

    def finish_release(self, code):
        if code in self.repeat_timers:
            self.root.after_cancel(self.repeat_timers.pop(code))
        self.repeat_due.pop(code, None)
        self.releases.pop(code, None)
        self.release_times.pop(code, None)
        key = self.pressed.pop(code, None)
        if self.ready and key in ("left", "right"):
            remaining = [v for v in self.pressed.values() if v in ("left", "right")]
            self.set_bend((-4096 if remaining[-1] == "left" else 4096) if remaining else 0)
            self.bend_owned = bool(remaining)
        elif self.ready:
            self.operate(lambda: self.notes.sustain(False) if key == "space" else self.notes.release(code))

    def schedule_repeat(self, code):
        if (code not in self.repeat_due or code in self.repeat_timers or
                code not in self.notes.held or not self.ready):
            return
        delay = max(1, int((self.repeat_due[code] - time.monotonic()) * 1000 + .999))
        self.repeat_timers[code] = self.root.after(delay, lambda: self.repeat_note(code))

    def repeat_note(self, code):
        self.repeat_timers.pop(code, None)
        if code in self.releases or code not in self.notes.held or not self.ready:
            return
        # Local held-key display is unchanged by a retrigger.
        if self.operate(lambda: self.notes.retrigger(code), redraw=False):
            # Schedule from now: a slow UI/serial write must not catch up by
            # dumping a backlog of Note Ons into the board's finite FIFO.
            self.repeat_due[code] = time.monotonic() + REPEAT_INTERVAL_MS / 1000
            self.schedule_repeat(code)

    def cancel_repeats(self):
        for callback in self.repeat_timers.values():
            self.root.after_cancel(callback)
        self.repeat_timers.clear()
        self.repeat_due.clear()

    def release_owned(self):
        self.cancel_repeats()
        for callback in self.releases.values():
            self.root.after_cancel(callback)
        self.releases.clear()
        self.release_times.clear()
        self.pressed.clear()
        packet = self.notes.drain()
        centering = self.bend_owned
        if self.bend_owned:
            packet += bytes((0xe0, 0, 64))
            self.bend_owned = False
        if packet and self.ready:
            if self.operate(lambda: self.send(packet)) and centering and self.last_expression:
                if "bend" in self.scale_timers:
                    self.root.after_cancel(self.scale_timers.pop("bend"))
                self.requests["bend_index"] = dict(target=128, sequence=self.last_expression["sequence"], time=time.monotonic())
                self.update_controls()
        elif packet:
            self.recovery += packet
        self.draw_keys()

    def check_focus(self):
        if self.closed:
            return
        focused = self.root.focus_displayof()
        if focused is None or focused.winfo_toplevel() != self.root:
            self.release_owned()

    def panic(self):
        # Keep physically held keycodes latched so repeat cannot undo panic.
        def release():
            self.cancel_repeats()
            self.send(self.notes.drain())
            self.send(bytes((0xb0, 120, 0)))
        if self.operate(release):
            self.activity.set("PANIC 已清除全部音符、包络和效果尾音。")

    def synchronize_panic(self, epoch):
        # Keep physical keycodes latched until their real releases arrive, so
        # board-originated PANIC cannot be undone by an OS repeat KeyPress.
        self.cancel_repeats()
        for callback in self.releases.values():
            self.root.after_cancel(callback)
        self.releases.clear()
        self.release_times.clear()
        self.notes.discard()
        self.panic_epoch = epoch
        self.activity.set("板端 PANIC：本机持键和重复状态已同步清除。")
        self.draw_keys()
        self.record("board_panic", panic_epoch=epoch)

    def set_mode(self, mode):
        def change():
            self.cancel_repeats()
            self.send(self.notes.drain())
            self.send(bytes((0xb0, 80, mode)))
        self.operate(change)

    def set_program(self, program):
        self.operate(lambda: self.send(bytes((0xc0, program))))

    def toggle_effect(self, bit):
        # Compose rapid toggles against the outstanding request, so a delayed
        # one-second status cannot erase another button's just-sent setting.
        if self.last_state:
            mask = self.effect_request['mask'] if self.effect_request else self.last_state['effects']
            self.set_effects(mask ^ bit)
        else:
            self.activity.set("等待 138K 回读初始音效状态。")

    def set_effects(self, mask):
        if self.operate(lambda: self.send(bytes((0xb0, 81, mask)))):
            self.effect_request = dict(mask=mask, sequence=self.last_state['sequence'], time=time.monotonic())
            self.activity.set("音效指令已发送，可继续演奏；等待板端回读确认。")
            self.update_controls()

    def request_control(self, field, value, packet):
        state = self.last_state if field == "route" else self.last_expression
        if not state or not self.ready:
            self.activity.set("等待板端控制回读；旧版没有 E138 时，需加载本次控制版。")
            return False
        if self.operate(lambda: self.send(packet)):
            self.requests[field] = dict(target=value, sequence=state["sequence"], time=time.monotonic())
            self.update_controls()
            return True
        return False

    def confirm_requests(self, state, fields):
        for field in fields:
            request = self.requests.get(field)
            if not request:
                continue
            fresh = 0 < ((state["sequence"] - request["sequence"]) & 0xffffffff) < 0x80000000
            confirmed = fresh and state[field] == request["target"]
            if field == "snap_request":
                confirmed = confirmed and state["snap_token"] == request["target"] and (state["snap_done"] or state["snap_error"])
            if confirmed:
                self.requests.pop(field)
            elif time.monotonic() - request["time"] > 5:
                self.requests.pop(field)
                self.activity.set("控制请求未回读确认，已恢复显示板端实际状态。")

    def queue_scale(self, field, value):
        if field in self.scale_timers:
            self.root.after_cancel(self.scale_timers.pop(field))
        def commit():
            self.scale_timers.pop(field, None)
            if field == "bend":
                self.set_bend(int(float(value)))
            else:
                self.set_expression(field, int(float(value)))
        self.scale_timers[field] = self.root.after(40, commit)

    def set_route(self, route):
        return self.request_control("route", ("stereo", "left", "right", "mute")[route], bytes((0xb0, 82, route)))

    def set_expression(self, field, value):
        if field in self.scale_timers:
            self.root.after_cancel(self.scale_timers.pop(field))
        return self.request_control(field, value, bytes((0xb0, 1 if field == "vibrato" else 5, value)))

    def toggle_expression(self, field):
        if not self.last_expression:
            self.activity.set("等待板端颤音 / 滑音状态回读。")
            return
        value = self.requests[field]["target"] if field in self.requests else self.last_expression[field]
        self.set_expression(field, 0 if value else (80 if field == "vibrato" else 64))

    def set_bend(self, value):
        if "bend" in self.scale_timers:
            self.root.after_cancel(self.scale_timers.pop("bend"))
        value = max(-8192, min(8191, value))
        raw = value + 8192
        return self.request_control("bend_index", raw >> 6, bytes((0xe0, raw & 127, raw >> 7)))

    def take_snapshot(self):
        if self.last_expression and "snap_request" not in self.requests:
            token = (self.last_expression["snap_request"] + 1) & 63
            self.request_control("snap_request", token, bytes((0xb0, 83, 127)))
        else:
            self.activity.set("等待板端快照就绪或上一次快照完成。")

    def update_controls(self):
        state = self.last_state if self.ready else None
        for mode, button in self.mode_buttons.items():
            on = state and state['mode'] == 'ABC'[mode]
            button.configure(bg=GREEN if on else PANEL, fg=BG if on else TEXT)
        for index, button in self.sound_buttons.items():
            on = state and state['sound'] == list(SOUND_NAMES)[index]
            button.configure(bg=GREEN if on else PANEL, fg=BG if on else TEXT)
        for index, (bit, name) in enumerate(EFFECTS):
            pending = bool(self.effect_request)
            mask = self.effect_request['mask'] if pending else state['effects'] if state else 0
            on = bool(mask & bit)
            suffix = ('开' if on else '关') + (' · 待确认' if pending else '')
            color = '#edbd68' if pending else GREEN if on else PANEL
            self.effect_buttons[bit].configure(text=f"F{index + 10}  {name} · {suffix}", bg=color, fg=BG if pending or on else TEXT)

        pending_route = self.requests.get("route")
        for route, button in self.route_buttons.items():
            selected = state and state["route"] == ("stereo", "left", "right", "mute")[route]
            pending = pending_route and pending_route["target"] == ("stereo", "left", "right", "mute")[route]
            button.configure(bg="#edbd68" if pending else GREEN if selected else PANEL, fg=BG if pending or selected else TEXT)
        extended = self.last_expression if self.ready else None
        for field, name in (("vibrato", "VIBR 颤音"), ("glide", "GLIDE 过渡")):
            request = self.requests.get(field)
            value = request["target"] if request else extended[field] if extended else 0
            self.expression_buttons[field].configure(text=name + (" · 待确认" if request else ""),
                bg="#edbd68" if request else GREEN if value else PANEL, fg=BG if request or value else TEXT)
            if field not in self.scale_timers:
                self.scale_vars[field].set(value)
        bend = self.requests.get("bend_index")
        bend_value = (bend["target"]-128)*64 if bend else extended["bend"] if extended else 0
        if "bend" not in self.scale_timers:
            self.scale_vars["bend"].set(bend_value)
        self.bend_label.configure(text="待确认" if bend else f"实际 {bend_value:+d}" if extended else "待回读", fg="#edbd68" if bend else MUTED)
        snap = self.requests.get("snap_request")
        self.snap_button.configure(state="disabled" if snap or not extended else "normal", bg="#edbd68" if snap else PANEL)
        if snap:
            self.snapshot_text.set("SNAP：已触发，等待 AE350 完成板内 PCM 快照。")
        elif extended and extended["snap_error"]:
            self.snapshot_text.set("SNAP：板端采集未成功，可重试；音频继续运行。")
        elif extended and extended["snap_done"] and extended["snap_token"] == extended["snap_request"]:
            self.snapshot_text.set(f"SNAP #{extended['snap_completed']}：已采集 {extended['snap_count']} 帧（板内） · 首帧 L {extended['snap_left']} / R {extended['snap_right']}")
        elif extended:
            self.snapshot_text.set("SNAP：一次采集少量 PCM 帧保存在板内，并回读首帧；不生成录音文件。")

    def draw_keys(self):
        self.canvas.delete("all")
        width = max(880, self.canvas.winfo_width()) - 8
        step = width / 15
        held = set(self.notes.held.values())
        keys = {note: key.upper() for key, note in NOTE_KEYS.items()}
        for i, note in enumerate(WHITE_NOTES):
            x = 4 + i * step
            self.canvas.create_rectangle(x, 2, x + step - 2, 202, fill=GREEN if note in held else "#e5edf1", outline=BG)
            self.canvas.create_text(x + step / 2, 157, text=keys[note], fill=BG, font=("Sans", 13, "bold"))
            pitch = ("C", "", "D", "", "E", "F", "", "G", "", "A", "", "B")[note % 12]
            self.canvas.create_text(x + step / 2, 185, text=f"{pitch}{note // 12 - 1}", fill="#526778", font=("Sans", 10))
        for i, note in enumerate(WHITE_NOTES[:-1]):
            if WHITE_NOTES[i + 1] - note != 2:
                continue
            note += 1
            x = 4 + (i + 1) * step
            self.canvas.create_rectangle(x - step * .3, 2, x + step * .3, 120, fill=GREEN if note in held else PANEL, outline=BG)
            self.canvas.create_text(x, 98, text=keys[note], fill=BG if note in held else TEXT, font=("Sans", 12, "bold"))

    def close(self):
        if self.closed:
            return
        self.release_owned()
        self.closed = True
        for timer in self.scale_timers.values():
            self.root.after_cancel(timer)
        self.scale_timers.clear()
        self.root.after_cancel(self.poll_id)
        if self.port:
            self.port.close()
        self.record("closed")
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=DEFAULT_PORT)
    args = parser.parse_args()
    result = Path(__file__).resolve().parents[2] / "results" / datetime.datetime.now().strftime("keyboard_session_%Y%m%d_%H%M%S_%f")
    result.mkdir()
    (result / "session.json").write_text(json.dumps(dict(port=args.port, source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()), indent=2) + "\n")
    print("键盘窗口日志：", result, flush=True)
    with (result / "events.jsonl").open("w") as log:
        root = tk.Tk()
        app = KeyboardWindow(root, args.port, log)
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda number, frame: root.after(0, app.close))
        try:
            root.mainloop()
        finally:
            if not app.closed:
                app.close()


if __name__ == "__main__":
    main()
