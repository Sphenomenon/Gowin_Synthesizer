"""Read-only latency inspector; all UART work stays in the serial owner thread."""
import tkinter as tk
from tkinter import ttk
import time

from instrument_backend import input_to_digital_interval
from instrument_backend.protocol import OPCODE_NAMES
from .widgets import COLORS


class LatencyWindow:
    def __init__(self, app):
        self.app = app
        self.closed = False
        self.snapshot = None
        self.snapshot_connection = None
        self.snapshot_generation = None
        self.record_label = "FPGA 记录：尚未读取"
        self.onset_cache = {}
        self.onset_cache_connection = app.connection_id
        self._selected_onset_voice = 0
        self._last_tab = 0
        self.poll_job = None
        self.root = tk.Toplevel(app.root)
        self.root.title("Mega Synth · 延迟检测")
        self.root.geometry("910x900")
        self.root.minsize(910, 890)
        self.root.configure(background=COLORS["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="延迟检测 · 声部起音与全链路", font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
        ttk.Label(outer, text="测量停止于双声道最后一位 BCK 上升沿；不包含 DAC 模拟滤波、耳机或声学传播。",
                  foreground=COLORS["muted"], wraplength=850).pack(anchor="w", pady=(5, 16))
        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(0, 10))
        ttk.Button(actions, text="读取当前页记录", command=self.read).pack(side="left")
        self.auto_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(actions, text="每秒查询当前页 / 当前声部", variable=self.auto_var).pack(side="left", padx=15)
        self.pages = ttk.Notebook(outer)
        self.pages.pack(fill="both", expand=True)
        onset_page = ttk.Frame(self.pages)
        chain_page = ttk.Frame(self.pages)
        self.pages.add(onset_page, text="声部起音 · 0x0F")
        self.pages.add(chain_page, text="全链路 · 0x0E")
        self._build_onset(onset_page)
        outer = chain_page
        host = ttk.Frame(outer, style="Card.TFrame", padding=12)
        host.pack(fill="x")
        ttk.Label(host, text="本连接最近成功声音命令", style="Card.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        self.host_vars = {}
        for column, (key, label) in enumerate((("queue_wait_ms", "提交 → 写串口"), ("rtt_ms", "写串口 → 完整 ACK"), ("host_total_ms", "提交 → 完整 ACK"))):
            host.columnconfigure(column, weight=1)
            ttk.Label(host, text=label, style="Card.TLabel", foreground=COLORS["muted"]).grid(row=1, column=column, sticky="w", pady=(10, 3))
            variable = tk.StringVar(value="—")
            self.host_vars[key] = variable
            ttk.Label(host, textvariable=variable, style="Card.TLabel", font=("Cascadia Code", 17)).grid(row=2, column=column, sticky="w")
        self.host_info = tk.StringVar(value="尚无本连接的声音命令")
        ttk.Label(host, textvariable=self.host_info, style="Card.TLabel", foreground=COLORS["muted"]).grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.info_var = tk.StringVar(value="查询可被演奏命令逐字节打断；不会提交新的声音命令。")
        ttk.Label(outer, textvariable=self.info_var, foreground=COLORS["muted"], wraplength=850).pack(anchor="w", pady=(10, 0))
        self.record_var = tk.StringVar(value="FPGA 记录：尚未读取")
        ttk.Label(outer, textvariable=self.record_var).pack(anchor="w", pady=(12, 8))
        grid = ttk.Frame(outer, style="Card.TFrame", padding=12)
        grid.pack(fill="x")
        self.stage_vars = {}
        stages = (("uart_rx_ms", "UART 收包（首同步起始位 → CRC 接受）"),
                  ("packet_to_commit_ms", "CRC 接受 → 声音命令提交"),
                  ("latest_compute_ms", "最近一帧合成计算"),
                  ("commit_to_state_sample_ms", "提交 → 首个新状态样本（可为零）"),
                  ("commit_to_dac_state_ms", "提交 → 新状态双声道帧串完"),
                  ("commit_to_note_sample_ms", "NOTE_ON → 该声部首次非零贡献样本"),
                  ("commit_to_dac_note_ms", "NOTE_ON → 非零贡献双声道帧串完"),
                  ("start_to_ack_ready_ms", "UART 起始 → ACK ready"),
                  ("start_to_ack_done_ms", "UART 起始 → ACK 发送完成"))
        for row, (key, label) in enumerate(stages):
            ttk.Label(grid, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=3)
            variable = tk.StringVar(value="—")
            self.stage_vars[key] = variable
            ttk.Label(grid, textvariable=variable, style="Card.TLabel", font=("Cascadia Code", 10)).grid(row=row, column=1, sticky="e", padx=(25, 0))
        grid.columnconfigure(0, weight=1)
        self.interval_var = tk.StringVar(value="输入 → 数字输出：等待匹配的主机与 FPGA 记录")
        ttk.Label(outer, textvariable=self.interval_var, foreground=COLORS["accent"], wraplength=850,
                  font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", pady=(14, 6))
        ttk.Label(outer, text="非零贡献只针对命令指定声部；混音仍可能相消，不能据此判定已听到声音。\n"
                  "USB 往返延迟无法拆成单程，因此只给有依据的区间，不能把 RTT 与 FPGA 时长直接相加。",
                  foreground=COLORS["muted"], wraplength=850).pack(anchor="w")
        self.root.update_idletasks()
        self.refresh_host()
        self.pages.bind("<<NotebookTabChanged>>", self._tab_changed)
        self.poll_job = self.root.after(1000, self._poll)
        self.read()

    def _build_onset(self, outer):
        selector = ttk.Frame(outer)
        selector.pack(fill="x", pady=(12, 10))
        ttk.Label(selector, text="声部 ID 0–31（对应主窗口 01–32）").pack(side="left")
        self.onset_voice = tk.IntVar(value=0)
        combo = ttk.Combobox(selector, values=tuple(range(32)), textvariable=self.onset_voice, state="readonly", width=5)
        combo.pack(side="left", padx=12)
        combo.bind("<<ComboboxSelected>>", self._select_onset_voice)
        self.onset_info_var = tk.StringVar(value="只读取当前声部；下表为各声部最后一次查询的缓存，不是同步扫描。")
        ttk.Label(outer, textvariable=self.onset_info_var, foreground=COLORS["muted"], wraplength=850).pack(anchor="w")
        self.onset_record_var = tk.StringVar(value="声部 0：尚未读取")
        ttk.Label(outer, textvariable=self.onset_record_var, font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", pady=(12, 5))
        self.onset_state_var = tk.StringVar(value="—")
        ttk.Label(outer, textvariable=self.onset_state_var, foreground=COLORS["accent"], wraplength=850).pack(anchor="w", pady=(0, 10))
        timing = ttk.Frame(outer, style="Card.TFrame", padding=12)
        timing.pack(fill="x")
        self.onset_vars = {}
        for column, (key, label) in enumerate((("trigger_to_sample_ms", "触发 → 有效目标 PCM 贡献"),
                                                ("trigger_to_dac_ms", "触发 → DAC 双槽发送完成"))):
            timing.columnconfigure(column, weight=1)
            ttk.Label(timing, text=label, style="Card.TLabel", foreground=COLORS["muted"]).grid(row=0, column=column, sticky="w")
            variable = tk.StringVar(value="—")
            self.onset_vars[key] = variable
            ttk.Label(timing, textvariable=variable, style="Card.TLabel", font=("Cascadia Code", 20)).grid(row=1, column=column, sticky="w", pady=(6, 0))
        self.onset_amp_var = tk.StringVar(value="DAC 终点功放静音状态：尚无记录")
        ttk.Label(outer, textvariable=self.onset_amp_var, foreground=COLORS["muted"], wraplength=850).pack(anchor="w", pady=(9, 12))
        table_frame = ttk.Frame(outer)
        table_frame.pack(fill="both", expand=True)
        style = ttk.Style(self.root)
        style.configure("Onset.Treeview", background=COLORS["panel"], fieldbackground=COLORS["panel"],
                        foreground=COLORS["text"], rowheight=26)
        style.configure("Onset.Treeview.Heading", background=COLORS["panel_alt"], foreground=COLORS["text"])
        style.map("Onset.Treeview", background=[("selected", COLORS["accent"])], foreground=[("selected", COLORS["bg"])])
        columns = ("voice", "id", "sequence", "state", "sample", "dac", "updated")
        self.onset_table = ttk.Treeview(table_frame, columns=columns, show="headings", height=10, selectmode="browse", style="Onset.Treeview")
        for name, label, width in zip(columns, ("声部 ID", "NOTE ID", "序号", "缓存状态", "有效 PCM", "DAC 双槽", "查询时间"),
                                      (58, 78, 48, 245, 105, 105, 78)):
            self.onset_table.heading(name, text=label)
            self.onset_table.column(name, width=width, minwidth=40, stretch=name == "state")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.onset_table.yview)
        self.onset_table.configure(yscrollcommand=scrollbar.set)
        self.onset_table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        for voice in range(32):
            self.onset_table.insert("", "end", iid=str(voice), values=(voice, "—", "—", "未查询", "—", "—", "—"))
        self.onset_table.selection_set("0")
        self.onset_table.bind("<<TreeviewSelect>>", self._select_onset_row)
        ttk.Label(outer, text="记录只由同声部的新 NOTE_ON 替换；参数、其他声部及松键不覆盖已完成记录。\n"
                  "阈值是该声部 /32 后量化为非零 PCM16；不是混音结果，更不是模拟耳机起音。\n"
                  "活动声部重触发可能已有声音；取消仅停止等待，不代表无声。",
                  foreground=COLORS["muted"], wraplength=850).pack(anchor="w", pady=(12, 0))

    def _select_onset_row(self, event=None):
        selected = self.onset_table.selection()
        if selected:
            self.onset_voice.set(int(selected[0]))
            self._select_onset_voice()

    def _select_onset_voice(self, event=None):
        voice = self.onset_voice.get()
        if voice == self._selected_onset_voice:
            return
        self._selected_onset_voice = voice
        self.onset_table.selection_set(str(voice))
        self.onset_table.see(str(voice))
        self._render_onset()
        self.app.worker.cancel_voice_onset_status()
        if self.pages.index("current") == 0:
            self.read()

    def _render_onset(self):
        voice = self.onset_voice.get()
        cached = self.onset_cache.get(voice)
        status = cached["status"] if cached else None
        for key, variable in self.onset_vars.items():
            variable.set(self._duration(status[key]) if status and not cached.get("pending") else "—")
        if cached and cached.get("pending"):
            self.onset_record_var.set(f"声部 {voice}：新的 NOTE_ON 已确认")
            self.onset_state_var.set("等待查询新记录；旧缓存不作为本次起音时间。")
            self.onset_amp_var.set("DAC 终点功放静音状态：等待新记录")
            return
        if status is None:
            self.onset_record_var.set(f"声部 {voice}：尚未读取")
            self.onset_state_var.set("—")
            self.onset_amp_var.set("DAC 终点功放静音状态：尚无记录")
            return
        self.onset_record_var.set(f"声部 {voice} · NOTE ID {status['note_id']} · NOTE_ON 序号 {status['sequence']} · revision {status['revision']}")
        trigger = "活动声部重触发，可能已有声音" if status["was_active"] else "从空闲状态触发"
        self.onset_state_var.set(status["state_text"] + (f" · {trigger}" if status["valid"] else ""))
        amp = ("静音" if status["amp_muted_at_dac"] else "未静音") if status["valid"] and status["dac_seen"] else "尚未到达 DAC 终点"
        elapsed = self._duration(status["elapsed_ms"])
        cancelled = " · 取消于 " + self._duration(status["trigger_to_cancel_ms"]) if status["cancelled"] else ""
        self.onset_amp_var.set(f"DAC 终点功放静音状态：{amp} · 记录耗时/年龄 {elapsed}{cancelled}\n缓存读取于 {cached['updated']}；只表示该次查询观察到的状态。")

    def observe_sound_ack(self, event):
        if event.get("opcode") != 1 or event.get("status") != 0:
            return
        voice = event.get("voice")
        if type(voice) is not int or voice not in range(32):
            return
        prior = self.onset_cache.get(voice, {"status": None, "updated": "—"})
        self.onset_cache[voice] = {**prior, "pending": True}
        status = prior["status"]
        self.onset_table.item(str(voice), values=(voice, status["note_id"] if status else "—",
                              event.get("sequence"), "新触发待查询（旧缓存）", "—", "—", prior["updated"]))
        if voice == self.onset_voice.get():
            self._render_onset()

    def _tab_changed(self, event=None):
        current = self.pages.index("current")
        if current == self._last_tab:
            return
        self._last_tab = current
        self.app.worker.cancel_latency_status()
        self.app.worker.cancel_voice_onset_status()
        self.read()

    @staticmethod
    def _duration(value):
        if value is None:
            return "—"
        return f"{value * 1000:.2f} µs" if value < 1 else f"{value:.3f} ms"

    def refresh_host(self):
        if self.onset_cache_connection != self.app.connection_id:
            self.onset_cache_connection = self.app.connection_id
            self.onset_cache.clear()
            for voice in range(32):
                self.onset_table.item(str(voice), values=(voice, "—", "—", "未查询", "—", "—", "—"))
            self._render_onset()
        ack = self.app.last_sound_ack
        for key, variable in self.host_vars.items():
            variable.set(self._duration(ack.get(key)) if ack else "—")
        if ack:
            prefix = "离线模拟（不是硬件计时）" if ack.get("simulated") else "主机单调时钟"
            self.host_info.set(f"{prefix} · seq {ack.get('sequence')} · {OPCODE_NAMES.get(ack.get('opcode'), 'UNKNOWN')} 0x{ack.get('opcode', 0):02X} · voice {ack.get('voice')}")
        else:
            self.host_info.set("尚无本连接的成功声音命令；连接握手和后台查询不作为输入测量。")
        self._render_interval()

    def _render_interval(self):
        if self.snapshot is None or self.snapshot_connection != self.app.connection_id:
            if self.snapshot is not None:
                self.record_var.set(self.record_label + " · 历史记录（其他连接）")
            self.interval_var.set("输入 → 数字输出：等待当前连接的 FPGA 记录")
            return
        current = self.app.last_sound_ack
        historical = current is None or current.get("sound_generation") != self.snapshot_generation
        self.record_var.set(self.record_label + (" · 历史记录" if historical else ""))
        result = input_to_digital_interval(self.snapshot, current, self.snapshot_connection, self.snapshot_generation)
        if result["available"]:
            self.interval_var.set(f"输入 → 数字输出：{result['lower_ms']:.3f}–{result['upper_ms']:.3f} ms\n端点：{result['reason']}")
        else:
            self.interval_var.set("输入 → 数字输出：" + result["reason"])

    def receive(self, event):
        if event.get("connection_id") != self.app.connection_id:
            return
        kind = event["type"]
        if kind == "voice_onset_status":
            status = event["status"]
            voice = status["voice"]
            updated = time.strftime("%H:%M:%S")
            self.onset_cache[voice] = {"status": status, "updated": updated}
            self.onset_table.item(str(voice), values=(voice, status["note_id"], status["sequence"], status["state_text"],
                                  self._duration(status["trigger_to_sample_ms"]), self._duration(status["trigger_to_dac_ms"]), updated))
            if voice == self.onset_voice.get():
                self.onset_info_var.set("已更新当前声部；其他行仍为各自上次查询的缓存。")
                self._render_onset()
        elif kind == "voice_onset_unsupported":
            self.auto_var.set(False)
            self.onset_info_var.set("离线模式不提供真实声部起音测量。" if event.get("simulated") else "当前位流不支持独立声部起音记录；需下载新版位流，演奏连接保持可用。")
        elif kind == "voice_onset_aborted":
            if event.get("voice") == self.onset_voice.get():
                self.onset_info_var.set("本次查询已让出演奏或声部切换；半份快照已丢弃，旧缓存保留。")
        elif kind == "latency_status":
            self.snapshot = status = event["status"]
            self.snapshot_connection = event["connection_id"]
            self.snapshot_generation = event.get("sound_generation")
            for key, variable in self.stage_vars.items():
                variable.set(self._duration(status[key]))
            self.record_label = (f"FPGA 记录 #{status['trace_id']} · seq {status['sequence']} · {status.get('opcode_name', 'UNKNOWN')} 0x{status['opcode']:02X} · voice {status['voice']}"
                                 + (" · 已过期" if status['expired'] else ""))
            self.info_var.set(f"时钟 {status['clock_hz'] / 1e6:g} MHz · 样本周期 {status['sample_period_cycles']} 拍 · "
                              f"记录年龄 {self._duration(status['trace_age_ms'])} · 覆盖未完成记录 {status['overwritten_pending_count']}")
            self._render_interval()
        elif kind == "latency_unsupported":
            self.auto_var.set(False)
            self.info_var.set("离线模式不提供 FPGA 延迟测量。" if event.get("simulated") else "当前位流不支持延迟诊断；需下载新版位流。演奏连接保持可用。")
        elif kind == "latency_status_aborted":
            self.info_var.set("本次查询已让出演奏命令，半份快照已丢弃；下次空闲时重读。")

    def read(self):
        onset = self.pages.index("current") == 0
        info = self.onset_info_var if onset else self.info_var
        if not self.app.connected:
            info.set("请先在主窗口连接设备。")
        elif (self.app.worker.request_voice_onset_status(self.onset_voice.get()) if onset
              else self.app.worker.request_latency_status()):
            info.set("已请求读取当前声部；等待演奏队列空闲。" if onset else "已请求读取；等待演奏队列空闲。")

    def _poll(self):
        if self.closed:
            return
        if self.auto_var.get():
            self.read()
        self.poll_job = self.root.after(1000, self._poll)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.poll_job is not None:
            self.root.after_cancel(self.poll_job)
        self.app.worker.cancel_latency_status()
        self.app.worker.cancel_voice_onset_status()
        self.app.latency_window = None
        self.root.destroy()
