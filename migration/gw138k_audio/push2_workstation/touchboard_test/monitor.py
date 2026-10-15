#!/usr/bin/env python3
"""115200 8N1 touchboard telemetry: console or a live Tk dashboard."""
import argparse
import binascii
import fcntl
from datetime import datetime
import json
from pathlib import Path
import queue
import threading
import time

ROOT = Path(__file__).resolve().parent
ERRORS = {0: 'OK', 1: '地址 NACK', 2: '数据 NACK', 3: 'SCL 超时', 4: 'SDA 卡低/已发恢复时钟',
          5: '芯片 ID 不符', 6: '配置读回不符', 7: '芯片复位/需重新配置'}
DEFAULT_PORT = '/dev/serial/by-id/usb-SIPEED_USB_Debugger_2025030317-if01-port0'

def decode(line):
    parts = line.strip().split()
    if len(parts) != 3 or parts[0] not in (b'TB1', b'TB2'):
        raise ValueError('frame format')
    payload = bytes.fromhex(parts[1].decode('ascii'))
    compact = parts[0] == b'TB2'
    if len(payload) != (52 if compact else 168):
        raise ValueError('frame size')
    crc = binascii.crc_hqx(payload, 0xffff)
    if crc != int(parts[2], 16):
        raise ValueError('CRC mismatch')
    def device(offset, raw_offset, bit, error):
        status = payload[offset:offset+7]
        channel = payload[24+bit] if compact else None
        if compact:
            sig,ref = [None]*16,[None]*16
            if channel >= 16: raise ValueError('invalid diagnostic channel')
            if payload[9] & (1 << (bit+4)):
                at=28+bit*4
                sig[channel]=int.from_bytes(payload[at:at+2],'little')
                ref[channel]=int.from_bytes(payload[at+2:at+4],'little')
        else:
            raw = payload[raw_offset:raw_offset+64]
            sig = [int.from_bytes(raw[k:k+2], 'little') for k in range(0, 32, 2)]
            ref = [int.from_bytes(raw[k:k+2], 'little') for k in range(32, 64, 2)]
        return dict(online=bool(payload[6] & (1 << bit)), configured=bool(payload[9] & (1 << bit)),
                    raw_valid=bool(payload[9] & (1 << (bit+4))), sleeping=bool(payload[9] & (1 << (bit+2))), error=error,
                    i2c_address=(payload[26+bit] or 0x0d) if compact else 0x0d,
                    chip_id=status[0], version=status[1], general=status[2],
                    keys=int.from_bytes(status[3:5], 'little'), slider_detect=bool(status[2] & 1),
                    slider_position=status[5], gpio=status[6], signals=sig, references=ref,
                    deltas=[r-s if r is not None and s is not None else None for r, s in zip(ref, sig)],
                    diagnostic_channel=channel)
    scan = int.from_bytes(payload[36:52] if compact else payload[152:168], 'little')
    return dict(compact=compact,timestamp=datetime.now().astimezone().isoformat(),
                sequence=int.from_bytes(payload[:4], 'little'), io=payload[4], change_n=payload[5],
                key_device=device(10, 24, 0, payload[7] & 15),
                slider_device=device(17, 88, 1, payload[8] & 15),
                scan_error=payload[8] >> 4, scan_ack=[k for k in range(128) if scan & (1 << k)])

def ready(device):
    return device['online'] and device['configured']

def concise(frame):
    a, b = frame['key_device'], frame['slider_device']
    keys = ','.join(str(k) for k in range(16) if a['keys'] & (1 << k)) if ready(a) else '?'
    position = str(b['slider_position']) if ready(b) and b['slider_detect'] else '--'
    scan = ','.join(f'0x{k:02X}' for k in frame['scan_ack']) or '--'
    return (f"seq={frame['sequence']:7} U1={'READY' if ready(a) else 'OFFLINE'} keys=[{keys}] "
            f"U2={'READY' if ready(b) else 'OFFLINE'} slider={position:>3} "
            f"CHANGE={frame['change_n']} I2C3=[{scan}] "
            f"e1={ERRORS.get(a['error'],a['error'])} e2={ERRORS.get(b['error'],b['error'])}")

class Reader(threading.Thread):
    def __init__(self, port, events, stop, output, demo=False):
        super().__init__(daemon=True)
        self.port, self.events, self.stop, self.output, self.demo = port, events, stop, output, demo
        self.crc_errors, self.dropped, self.previous = 0, 0, None
        self.log = None
        self.diagnostic_cache = [dict(),dict()]
        self.slider_was_active = False
        self.slider_touch_count = 0
        self.slider_last_touch_at = None
        self.slider_last_position = None

    def publish(self, frame):
        if self.previous is not None and ((frame['sequence']-self.previous) & 0xffffffff) > 0x80000000:
            self.diagnostic_cache = [dict(),dict()]
            self.slider_was_active = False
            self.slider_touch_count = 0
            self.slider_last_touch_at = None
            self.slider_last_position = None
        if frame.get('compact'):
            for device,cache in zip((frame['key_device'],frame['slider_device']),self.diagnostic_cache):
                if not ready(device): cache.clear()
                if ready(device) and device['raw_valid']:
                    ch=device['diagnostic_channel']
                    cache[ch]=(device['signals'][ch],device['references'][ch])
                device['signals']=[cache[k][0] if k in cache else None for k in range(16)]
                device['references']=[cache[k][1] if k in cache else None for k in range(16)]
                device['deltas']=[r-s if r is not None else None for r,s in zip(device['references'],device['signals'])]
                device['raw_valid']=bool(cache) and ready(device)
        if self.previous is not None:
            difference = (frame['sequence']-self.previous) & 0xffffffff
            if 1 < difference < 0x80000000:
                self.dropped += difference-1
        self.previous = frame['sequence']
        frame['crc_errors'], frame['dropped'] = self.crc_errors, self.dropped
        slider = frame['slider_device']
        active = ready(slider) and slider['slider_detect']
        if active:
            if not self.slider_was_active:
                self.slider_touch_count += 1
            self.slider_last_touch_at = frame['timestamp']
            self.slider_last_position = slider['slider_position']
        self.slider_was_active = active
        frame['slider_touch_count'] = self.slider_touch_count
        frame['slider_last_touch_at'] = self.slider_last_touch_at
        frame['slider_last_touch_position'] = self.slider_last_position
        frame['received_monotonic'] = time.monotonic()
        if self.log:
            self.log.write(json.dumps(frame, ensure_ascii=False)+'\n')
            self.log.flush()
        self.events.put(('frame', frame))

    def run(self):
        if self.output:
            self.output.parent.mkdir(parents=True, exist_ok=True)
            self.log = self.output.open('a', buffering=1)
        try:
            if self.demo:
                sequence = 0
                while not self.stop.wait(.05):
                    payload = bytearray(168)
                    payload[:4] = sequence.to_bytes(4, 'little')
                    payload[4:10] = bytes([255, 0, 3, 0, 0, 0x33])
                    payload[10:17] = bytes([0x11, 0x40, 0, 1 << ((sequence//8)%8), 0, 0, 0])
                    payload[17:24] = bytes([0x11, 0x40, 1, 3, 0, sequence % 256, 0])
                    for offset in (24, 88):
                        for k in range(16):
                            payload[offset+k*2:offset+k*2+2] = (1000-(sequence+k)%20).to_bytes(2,'little')
                            payload[offset+32+k*2:offset+34+k*2] = (1000).to_bytes(2,'little')
                    payload[152] = 1
                    line = b'TB1 '+payload.hex().encode()+f' {binascii.crc_hqx(payload,0xffff):04X}'.encode()
                    self.publish(decode(line))
                    sequence += 1
                return
            import serial
            while not self.stop.is_set():
                try:
                    connection = serial.Serial(port=None, baudrate=115200, timeout=.5, exclusive=True)
                    connection.dtr = False
                    connection.rts = False
                    connection.port = self.port
                    connection.open()
                    connection.reset_input_buffer() # Drop telemetry buffered before this reader/bitstream.
                    self.previous = None
                    self.diagnostic_cache = [dict(),dict()]
                    self.slider_was_active = False
                    self.slider_touch_count = 0
                    self.slider_last_touch_at = None
                    self.slider_last_position = None
                    self.events.put(('state', f'串口已连接：{self.port}；等待 TB2 遥测'))
                    with connection:
                        last_frame = time.monotonic()
                        stale_reported = False
                        while not self.stop.is_set():
                            line = connection.read_until(b'\n', 4096)
                            if not line:
                                if time.monotonic()-last_frame > 2 and not stale_reported:
                                    self.diagnostic_cache = [dict(),dict()]
                                    self.events.put(('state', '串口已打开，但 2 秒内没有 TB2 帧；检查是否已下载测试镜像'))
                                    stale_reported = True
                                continue
                            try:
                                frame = decode(line)
                            except (ValueError, UnicodeError):
                                if line.startswith((b'TB1 ',b'TB2 ')):
                                    self.crc_errors += 1
                                continue
                            last_frame = time.monotonic()
                            stale_reported = False
                            self.publish(frame)
                except (serial.SerialException, OSError) as error:
                    self.previous = None
                    self.diagnostic_cache = [dict(),dict()]
                    self.events.put(('state', f'等待下载器 UART：{self.port} ({error})'))
                    self.stop.wait(2)
        finally:
            if self.log:
                self.log.close()

class Dashboard:
    def __init__(self, events, stop, output, demo):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk, self.events, self.stop = tk, ttk, events, stop
        self.root = tk.Tk()
        self.root.title('138K 触摸板信号测试' + (' [模拟显示，非实体数据]' if demo else ''))
        self.root.geometry('1130x830')
        self.root.configure(bg='#152030')
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background='#152030')
        style.configure('TLabel', background='#152030', foreground='#E1EAF5', font=('Sans', 11))
        style.configure('Title.TLabel', font=('Sans', 19, 'bold'))
        style.configure('Treeview', rowheight=24, font=('Monospace', 10))
        style.configure('Touched.Horizontal.TProgressbar', background='#19A889')
        style.configure('Released.Horizontal.TProgressbar', background='#607487')
        box = ttk.Frame(self.root, padding=18)
        box.pack(fill='both', expand=True)
        ttk.Label(box, text='138K · 触摸板信号测试', style='Title.TLabel').pack(anchor='w')
        self.connection = ttk.Label(box, text='等待 UART；实体数据到达后刷新', wraplength=1060)
        self.connection.pack(anchor='w', pady=(9, 3))
        self.health = ttk.Label(box, text='U1: 未知    U2: 未知    CHANGE: --    I²C3 ACK: --')
        self.health.pack(anchor='w', pady=3)
        ttk.Label(box, text='按键编号 = QT2160 通道编号；实体 4×4 排列需逐键核对。启动校准时保持手离开触摸区。').pack(anchor='w', pady=3)
        row = ttk.Frame(box)
        row.pack(fill='x', pady=10)
        pads = ttk.Frame(row)
        pads.pack(side='left')
        self.pads = []
        for k in range(16):
            label = tk.Label(pads, text=f'K{k:02}', width=8, height=2, bg='#46505B', fg='white',
                             font=('Monospace', 14, 'bold'), relief='flat')
            label.grid(row=k//8, column=k%8, padx=3, pady=3)
            self.pads.append(label)
        self.slider = ttk.Progressbar(box, maximum=255, length=900)
        self.slider.pack(fill='x', pady=3)
        self.slider_label = ttk.Label(box, text='滑条：未知')
        self.slider_label.pack(anchor='w')
        self.slider_history = ttk.Label(box, text='触摸事件：等待数据', wraplength=1060)
        self.slider_history.pack(anchor='w', pady=3)
        tables = ttk.Frame(box)
        tables.pack(fill='both', expand=True, pady=12)
        self.tables = []
        for title in ('U1 · 16 键原始信号', 'U2 · 滑条原始信号（有效 K0–K7）'):
            panel = ttk.Frame(tables)
            panel.pack(side='left', fill='both', expand=True, padx=5)
            ttk.Label(panel, text=title).pack(anchor='w', pady=4)
            tree = ttk.Treeview(panel, columns=('key','signal','reference','delta'), show='headings', height=16)
            for col, text in [('key','通道'),('signal','Signal'),('reference','Reference'),('delta','Ref − Sig')]:
                tree.heading(col, text=text)
                tree.column(col, width=100, anchor='center')
            tree.tag_configure('active', background='#C8F5E5')
            for k in range(16):
                tree.insert('', 'end', iid=str(k), values=(f'K{k:02}', '--','--','--'))
            tree.pack(fill='both', expand=True)
            self.tables.append(tree)
        self.footer = ttk.Label(box, text=f'115200 8N1 · JSON 数据可由日志复查：{output or "未记录"}', wraplength=1060)
        self.footer.pack(anchor='w', pady=4)
        self.last_frame = 0
        self.last_table_update = 0
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.after(50, self.update)

    def close(self):
        self.stop.set()
        self.root.destroy()

    def render(self, f):
        self.last_frame = time.monotonic()
        a,b = f['key_device'], f['slider_device']
        display_age = max(0, (time.monotonic()-f.get('received_monotonic',time.monotonic()))*1000)
        self.connection.config(text=f"遥测正常 · seq {f['sequence']} · CRC 错误 {f['crc_errors']} · 丢帧 {f['dropped']} · 主机显示滞后 {display_age:.0f} ms")
        descriptions = []
        for name, d in [('U1', a), ('U2', b)]:
            descriptions.append(f"{name}: {'通信/配置通过' if ready(d) else '未就绪'} @0x{d.get('i2c_address',0x0d):02X} ID={d['chip_id']:02X} / {ERRORS.get(d['error'],d['error'])}")
        scan = ', '.join(f'0x{k:02X}' for k in f['scan_ack']) or '无'
        self.health.config(text='    '.join(descriptions) + f"    CHANGE={f['change_n']}    I²C3 ACK={scan}")
        for k,label in enumerate(self.pads):
            label.config(bg=('#19A889' if a['keys'] & (1<<k) else '#27384E') if ready(a) else '#46505B')
        empty_reference = ready(b) and b['raw_valid'] and all(r==0 for r in b['references'][:8])
        active = ready(b) and b['slider_detect'] and not empty_reference
        self.slider['value'] = b['slider_position'] if active else 0
        self.slider.configure(style='Touched.Horizontal.TProgressbar' if active else 'Released.Horizontal.TProgressbar')
        if empty_reference:
            self.slider_label.config(text='滑条：基准全零，触摸判定不可用（芯片上报事件仍保存在日志）')
        else:
            self.slider_label.config(text=f"滑条：{'触摸' if active else '松开/未就绪'} · 位置 {b['slider_position'] if active else '--'} / 255")
        segments = ','.join(str(k) for k in range(8) if b['keys'] & (1<<k)) if ready(b) else '--'
        last_touch = f.get('slider_last_touch_at')
        last_description = f"最近 {last_touch[11:23]}，位置 {f.get('slider_last_touch_position')}" if last_touch else '尚未收到触摸'
        self.slider_history.config(text=f"芯片上报触摸 {f.get('slider_touch_count',0)} 次 · {last_description} · 当前滑条段 [{segments}]；需用无触摸/实际触摸对照判断误触")
        refresh_tables = time.monotonic()-self.last_table_update >= .2
        for d,table in zip((a,b), self.tables):
            if not refresh_tables: continue
            valid = ready(d) and d['raw_valid']
            for k in range(16):
                values = (f'K{k:02}', d['signals'][k], d['references'][k], d['deltas'][k]) if valid and d['signals'][k] is not None else (f'K{k:02}','--','--','--')
                table.item(str(k), values=values, tags=('active',) if ready(d) and d['keys'] & (1<<k) else ())
        if refresh_tables: self.last_table_update = time.monotonic()
        warnings = []
        if ready(a) and a['keys']==0xffff:
            warnings.append('U1 同时上报16键，请与实物触摸对照')
        if ready(a) and a['raw_valid'] and all(s==0 for s in a['signals']):
            warnings.append('U1 原始信号全零，不能据此判定正常')
        if ready(a) and a['raw_valid'] and all(r is not None for r in a['references']) and any(r==0 for r in a['references']):
            warnings.append('U1 存在零基准通道')
        if a.get('sleeping') or b.get('sleeping'):
            warnings.append('诊断休眠标志已置位，不作为触摸验收')
        if ready(b) and b['raw_valid'] and all(s==0 for s in b['signals'][:8]):
            warnings.append('U2 有效段原始信号全零，需排查')
        if ready(b) and b['general'] & 0x40:
            warnings.append('U2 扫描周期超时')
        self.footer.config(text=f"IO=0x{f['io']:02X} · U1 general=0x{a['general']:02X} · U2 general=0x{b['general']:02X} · I²C3={ERRORS.get(f['scan_error'],f['scan_error'])} · LED 状态以实物为准；通信通过不等于触摸正常 · {'；'.join(warnings)}")

    def invalidate(self):
        self.last_frame = 0
        self.health.config(text='遥测不可用：按键/滑条状态未知')
        for label in self.pads: label.config(bg='#46505B')
        self.slider['value'] = 0
        self.slider_label.config(text='滑条：未知（遥测不可用）')
        self.slider_history.config(text='触摸事件：遥测不可用')
        for table in self.tables:
            for k in range(16):
                table.item(str(k), values=(f'K{k:02}', '--','--','--'), tags=())

    def update(self):
        latest = None
        state = None
        try:
            while True:
                kind,value = self.events.get_nowait()
                if kind == 'frame': latest = value
                else: state = value
        except queue.Empty:
            pass
        if latest: self.render(latest)
        elif state:
            self.connection.config(text=state)
            self.invalidate()
        if self.last_frame and time.monotonic()-self.last_frame > 2:
            self.connection.config(text='遥测已停止，显示值已失效；检查 UART/板卡连接')
            self.invalidate()
        if not self.stop.is_set(): self.root.after(20, self.update)

    def run(self):
        self.root.mainloop()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default=DEFAULT_PORT)
    parser.add_argument('--gui', action='store_true')
    parser.add_argument('--demo', action='store_true', help='synthetic UI only, clearly marked, no hardware access')
    parser.add_argument('--no-log', action='store_true')
    parser.add_argument('--seconds', type=float, help='console capture duration')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    gui_lock = None
    if args.gui and not args.demo:
        gui_lock = Path('/tmp/touchboard_138k_gui.lock').open('a+')
        try:
            fcntl.flock(gui_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('触摸测试 GUI 已打开，请使用现有窗口。', flush=True)
            gui_lock.close()
            return
    output = None if args.no_log else (args.output or ROOT / 'results' / datetime.now().strftime('capture_%Y%m%d_%H%M%S.jsonl'))
    events, stop = queue.Queue(), threading.Event()
    reader = Reader(args.port, events, stop, output, args.demo)
    dashboard = Dashboard(events, stop, output, args.demo) if args.gui else None
    reader.start()
    try:
        if dashboard:
            dashboard.run()
        else:
            if args.demo: print('模拟显示，非实体数据', flush=True)
            deadline = time.monotonic()+args.seconds if args.seconds else float('inf')
            while time.monotonic() < deadline:
                try: kind, value = events.get(timeout=.5)
                except queue.Empty: continue
                print(concise(value) if kind=='frame' else value, flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        reader.join(timeout=2)
        if output: print(f'日志：{output}', flush=True)
        if gui_lock: gui_lock.close()

if __name__ == '__main__':
    main()
