"""Read-only desktop monitor for the USB2/HDMI diagnostic, with an explicit offline demo."""

from pathlib import Path
import argparse
import json
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from tools.capture_workstation_usb2_hdmi import capture


DEVICE_NAMES = {'25k': '25K 键盘', 'push': 'Push 垫', 'generic_midi': '通用 MIDI 设备'}
STAGE_NAMES = {'reset': 'USB 控制器复位中', 'cpu_fault': 'USB CPU 故障', 'phy_failed': 'PHY 初始化失败',
               'reference_reset': 'PHY 参考域仍在复位', 'host_disabled': 'USB Host 尚未使能',
               'ulpi_clock_failed': 'ULPI 时钟监控失败', 'ulpi_init_failed': 'USB3300 寄存器初始化失败',
               'ulpi_clock_not_observed': '未观察到 ULPI 时钟，PHY 尚不能工作',
               'snapshot_unavailable': 'ULPI 状态快照未更新，尚不能判断链路',
               'phy_initializing': 'PHY 初始化中', 'waiting_for_link': '等待插入设备／链路建立',
               'enumerating_or_unrecognized': '事务链路就绪，正在枚举／识别', 'configured': '枚举与设备识别成功'}
COUNTERS = (('sof_count', 'USB SOF'), ('received_events', '收到的输入'), ('accepted_events', '交付的事件'),
            ('lifecycle_events', '生命周期事件'), ('cancel_events', '取消事件'), ('push_frames', 'Push 完整帧'),
            ('commands', 'Push 控制命令'), ('in_errors', 'USB IN 错误'), ('out_errors', 'USB OUT 错误'),
            ('disconnects', '断连计数'), ('naks', 'NAK（正常等待）'), ('cpu_fault', 'CPU 故障字'))


def presentation(record=None, error=None, age=0):
    if error:
        return dict(device='未知', stage='JTAG 读回失败', good=False, link='不可读', detail=str(error))
    if record is None:
        return dict(device='等待首个读回', stage='正在读取 JTAG', good=False, link='等待', detail='')
    if age > 20:
        return dict(device='未知（数据过期）', stage='等待新的 JTAG 读回', good=False, link='过期', detail='')
    sample = record['last']
    device = DEVICE_NAMES.get(sample['recognized_device'], '未识别到设备')
    good = bool(sample['enumeration_complete'] and sample['transaction_ready'] and not sample['cpu_fault'])
    phy = sample.get('phy')
    diagnostics = record.get('phy_diagnostics', {})
    detail = f'最近读回 {age:.1f} 秒前；计数自复位累计，不等于本次插入的增量'
    if phy:
        detail += (f'\n时钟状态 {phy["clock_supervisor_state"]} / 故障 {phy["clock_failure"]}'
                   f'；参考心跳沿 {diagnostics.get("reference_heartbeat_edges", 0)}'
                   f'；快照更新 {diagnostics.get("link_snapshot_updates", 0)}'
                   f'\nPHY 初始化 {phy["init_stage"]} / 故障 {phy["init_failure"]}'
                   f'；端口状态 {phy["port_state"]} / 故障 {phy["port_failure"]}')
    return dict(device=device, stage=STAGE_NAMES.get(sample['stage'], sample['stage']), good=good,
                link=('高速 HS' if sample['high_speed'] else '全速 FS') if sample['transaction_ready'] else '未就绪',
                detail=detail)


def demo_record(step):
    phase = (step // 4) % 4
    device = ('25k', None, 'push', None)[phase]
    connected = device is not None
    sample = dict(stage='configured' if connected else 'waiting_for_link', recognized_device=device,
                  enumeration_complete=connected, transaction_ready=connected, high_speed=connected,
                  phy_ready=True, usb_pll_locked=True, audio_pll_locked=True, traffic_enabled=connected,
                  cpu_fault=0, fault_address='0x00000000', instruction_address=f'0x{0x200 + 4 * step:08X}',
                  sof_count=8000 * step, received_events=step * 2, accepted_events=step * 2 + 12,
                  lifecycle_events=12, cancel_events=phase, push_frames=step if device == 'push' else 0,
                  commands=step, in_errors=0, out_errors=0, disconnects=phase, naks=step,
                  last_event='0x00000', canceled_requests=phase)
    return dict(identity='DEMO_NOT_HARDWARE', samples=1024, first=sample, last=sample)


class Monitor:
    def __init__(self, window, candidate, output, demo=False, interval=3):
        self.window, self.candidate, self.output = window, candidate, output
        self.demo, self.interval = demo, interval
        self.messages = queue.Queue(maxsize=1)
        self.stop = threading.Event()
        self.automatic = threading.Event()
        self.automatic.set()
        self.request = threading.Event()
        self.record, self.error, self.updated = None, None, None
        window.title('138K · USB 热插拔监视器' + (' · 模拟演示' if demo else ''))
        window.geometry('900x650')
        window.minsize(760, 580)
        window.configure(bg='#101827')
        style = ttk.Style(window)
        style.theme_use('clam')
        style.configure('TFrame', background='#101827')
        style.configure('TLabel', background='#101827', foreground='#dbe4f0', font=('Sans', 11))
        style.configure('Title.TLabel', font=('Sans', 21, 'bold'), foreground='#f8fafc')
        style.configure('Device.TLabel', font=('Sans', 27, 'bold'), foreground='#94a3b8')
        style.configure('Good.Device.TLabel', font=('Sans', 27, 'bold'), foreground='#34d399')
        style.configure('Treeview', background='#172338', fieldbackground='#172338', foreground='#e2e8f0',
                        rowheight=27, font=('Sans', 11))
        style.configure('Treeview.Heading', background='#22334c', foreground='#f8fafc')
        frame = ttk.Frame(window, padding=24)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='138K USB 热插拔监视器', style='Title.TLabel').pack(anchor='w')
        identity = '模拟数据 · 不读取板卡' if demo else json.loads((candidate / 'inputs.json').read_text())['user_code']
        ttk.Label(frame, text=f'{identity}  |  JTAG 只读  |  HDMI 实现来自 D5').pack(anchor='w', pady=(5, 22))
        self.device = ttk.Label(frame, text='等待首个读回', style='Device.TLabel')
        self.device.pack(anchor='w')
        self.stage = ttk.Label(frame, text='正在读取 JTAG')
        self.stage.pack(anchor='w', pady=(7, 5))
        self.link = ttk.Label(frame, text='')
        self.link.pack(anchor='w', pady=(0, 18))
        self.table = ttk.Treeview(frame, columns=('name', 'value'), show='headings', height=12)
        self.table.heading('name', text='观察项')
        self.table.heading('value', text='实际读回')
        self.table.column('name', width=400)
        self.table.column('value', width=200, anchor='e')
        for key, title in COUNTERS:
            self.table.insert('', 'end', iid=key, values=(title, '—'))
        self.table.pack(fill='both', expand=True)
        self.detail = ttk.Label(frame, text='', wraplength=820)
        self.detail.pack(anchor='w', pady=(12, 8))
        controls = ttk.Frame(frame)
        controls.pack(fill='x')
        ttk.Button(controls, text='立即采样', command=self.request.set).pack(side='left')
        self.pause = ttk.Button(controls, text='暂停自动采样', command=self.toggle)
        self.pause.pack(side='left', padx=12)
        ttk.Label(controls, text='不提供下载、烧写或复位操作').pack(side='right')
        window.protocol('WM_DELETE_WINDOW', self.close)
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()
        self.refresh()

    def toggle(self):
        if self.automatic.is_set():
            self.automatic.clear()
            self.pause.configure(text='恢复自动采样')
        else:
            self.automatic.set()
            self.request.set()
            self.pause.configure(text='暂停自动采样')

    def run(self):
        sequence = 0
        while not self.stop.is_set():
            if not self.automatic.is_set() and not self.request.is_set():
                self.stop.wait(.1)
                continue
            self.request.clear()
            sequence += 1
            try:
                record = demo_record(sequence) if self.demo else capture(
                    self.candidate, self.output / f'capture_{sequence:05d}_{time.time_ns()}')
                message = (record, None, time.monotonic())
            except Exception as error:
                message = (None, str(error), time.monotonic())
            try:
                self.messages.put_nowait(message)
            except queue.Full:
                try:
                    self.messages.get_nowait()
                except queue.Empty:
                    pass
                self.messages.put_nowait(message)
            self.stop.wait(self.interval)

    def refresh(self):
        try:
            self.record, self.error, self.updated = self.messages.get_nowait()
        except queue.Empty:
            pass
        age = time.monotonic() - self.updated if self.updated is not None else 0
        state = presentation(self.record, self.error, age)
        self.device.configure(text=state['device'], style='Good.Device.TLabel' if state['good'] else 'Device.TLabel')
        self.stage.configure(text=state['stage'])
        self.link.configure(text='链路：' + state['link'])
        self.detail.configure(text=state['detail'])
        for key, title in COUNTERS:
            value = self.record['last'].get(key, '—') if self.record is not None else '—'
            self.table.item(key, values=(title, value))
        if not self.stop.is_set():
            self.window.after(200, self.refresh)

    def close(self):
        self.stop.set()
        self.window.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--output', type=Path, default=Path.home() / '.cache/fpga-usb2-monitor')
    parser.add_argument('--demo', action='store_true', help='Explicit simulated data; no JTAG or board access')
    parser.add_argument('--once', action='store_true', help='One JSON readout without opening a window')
    parser.add_argument('--interval', type=float, default=3)
    arguments = parser.parse_args()
    if not arguments.demo and arguments.candidate is None:
        parser.error('--candidate is required for live JTAG data; use --demo for offline UI')
    if arguments.interval < 1:
        parser.error('--interval must be at least one second')
    if arguments.once:
        record = demo_record(0) if arguments.demo else capture(arguments.candidate, arguments.output)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return
    window = tk.Tk()
    Monitor(window, arguments.candidate, arguments.output, arguments.demo, arguments.interval)
    window.mainloop()


if __name__ == '__main__':
    main()
