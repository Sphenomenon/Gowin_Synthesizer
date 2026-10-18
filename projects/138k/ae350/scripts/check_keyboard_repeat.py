#!/usr/bin/env python3
"""P22 focused Tk callback/timer checks; no serial port or board is opened."""
import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import time
from types import SimpleNamespace
import tkinter as tk

parser = argparse.ArgumentParser()
parser.add_argument('source', nargs='?', type=Path, default=Path(__file__).with_name('keyboard_midi.py'))
parser.add_argument('--results', type=Path, default=Path(__file__).resolve().parents[2] / 'results')
args = parser.parse_args()
source = args.source.resolve()
spec = importlib.util.spec_from_file_location('subject_keyboard', source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
out = args.results / datetime.now().strftime('p22_keyboard_%Y%m%d_%H%M%S_%f')
out.mkdir(parents=True)
print(out, flush=True)
(out / 'inputs.json').write_text(json.dumps({str(p): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in (source, Path(__file__))}, indent=2) + '\n')
(out / 'keyboard_midi.py').write_bytes(source.read_bytes())
(out / 'test.py').write_bytes(Path(__file__).read_bytes())
root = tk.Tk()
root.withdraw()
app = module.KeyboardWindow(root, connect=False)
root.update()
root.after_cancel(app.poll_id)  # Receive/telemetry is outside this no-port test.
callback_errors = []
root.report_callback_exception = lambda *error: callback_errors.append(str(error))
sent, checks, timings = [], [], {}
def send(data):
    sent.append((time.monotonic(), data))
app.ready = True
app.send = send
app.notes.send = send
def pump(ms):
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        root.update()
        time.sleep(.001)
def event(code=52, key='z', stamp=100):
    return SimpleNamespace(keycode=code, keysym=key, time=stamp)
def packets():
    return [data for _, data in sent]
def reset():
    app.release_owned()
    sent.clear()
def assert_balanced():
    counts = {}
    for packet in packets():
        for i in range(0, len(packet), 3):
            status, note, value = packet[i:i+3]
            if status in (0x80, 0x90):
                counts[note] = counts.get(note, 0) + (1 if status == 0x90 else -1)
                assert counts[note] in (0, 1), (note, counts[note], packet)
    assert not any(counts.values()), counts
passed = False
try:
    app.key_press(event())
    pump(100)
    app.key_release(event(stamp=200))
    pump(50)
    assert packets() == [bytes.fromhex('90 3c 64'), bytes.fromhex('80 3c 00')]
    pump(330)
    assert len(sent) == 2
    checks.append('short tap: exactly one Note On/Off, no delayed repeat')

    reset()
    app.key_press(event())
    for _ in range(30):
        app.key_press(event(stamp=101))
    pump(1010)
    on_times = [stamp for stamp, data in sent if data[0] == 0x90]
    assert 9 <= len(on_times) <= 11, len(on_times)
    assert .295 <= on_times[1] - on_times[0] <= .36
    intervals = [b-a for a,b in zip(on_times[1:], on_times[2:])]
    assert all(.075 <= x <= .12 for x in intervals), intervals
    timings['repeat_intervals_ms'] = [round(x*1000, 3) for x in intervals]
    before = len(sent)
    app.key_release(event(stamp=200))
    assert not app.repeat_timers
    pump(200)
    assert len(sent) == before + 1 and not app.notes.held
    assert_balanced()
    checks.append('300 ms delay, nominal 80 ms repeats; release cancels immediately and leaves no held note')

    reset()
    app.key_press(event())
    for index in range(24):
        pump(18)
        stamp = 300 + index
        app.key_release(event(stamp=stamp))
        count = len(sent)
        released = time.monotonic()
        pump([1, 5, 12, 25][index % 4])
        assert len(sent) == count, (index, time.monotonic()-released, packets()[count:])
        app.key_press(event(stamp=stamp))
    assert len([d for d in packets() if d[0] == 0x90]) >= 4
    assert len(app.repeat_timers) == 1
    app.key_release(event(key='Z', stamp=800))
    pump(50)
    assert_balanced()
    assert not app.releases and not app.pressed and not app.repeat_timers
    checks.append('X11 repeat pairs across 1..25 ms gaps retain one timer; modifier-safe release')

    reset()
    app.key_press(event(stamp=1000))
    app.key_release(event(stamp=1001))
    pump(2)
    app.key_press(event(stamp=1002))
    app.key_release(event(stamp=1003))
    pump(50)
    assert packets() == [bytes.fromhex(h) for h in ['90 3c 64', '80 3c 00'] * 2]
    checks.append('real rapid taps with different timestamps still retrigger once per tap')

    reset()
    for code, key in [(52,'z'), (54,'c'), (56,'b')]:
        app.key_press(event(code,key))
    pump(560)
    assert len(app.repeat_timers) == 3
    app.release_owned()
    count = len(sent)
    pump(150)
    assert len(sent) == count and not app.notes.held and not app.repeat_timers
    assert_balanced()
    checks.append('three-note repeats; focus cleanup stops every timer and balances notes')

    reset()
    app.key_press(event())
    app.key_press(event(65,'space'))
    pump(500)
    assert len([d for d in packets() if d[0] == 0x90]) == 1
    app.key_release(event(65,'space',200))
    pump(140)
    assert len([d for d in packets() if d[0] == 0x90]) >= 2
    app.release_owned()
    assert_balanced()
    checks.append('local sustain pauses repeat; pedal release resumes without global cleanup CC')

    for name, action in [('panic', app.panic), ('mode', lambda: app.set_mode(0))]:
        reset()
        app.key_press(event())
        pump(320)
        action()
        count = len(sent)
        app.key_release(event(stamp=200))
        pump(5)
        app.key_press(event(stamp=200))
        pump(400)
        assert len(sent) == count and not app.notes.held and not app.repeat_timers
        checks.append(name + ': existing physical-key latch prevents repeat restart after drain')

    reset()
    app.key_press(event())
    class BrokenPort:
        is_open = True
        def write(self, data):
            if data[0] == 0x90:
                raise module.serial.SerialException('test disconnection')
            return len(data)
        def close(self):
            self.is_open = False
    app.port = BrokenPort()
    # Invoke through the actual pending timer and existing send/fail/recovery.
    app.notes.send = lambda data: module.KeyboardWindow.send(app, data)
    pump(340)
    assert not app.ready and not app.notes.held and not app.repeat_timers
    pump(100)
    checks.append('repeat write failure drains owned releases and cancels all repeat callbacks')
    app.notes.send = send
    app.ready = True
    reset()
    class SilentPort:
        is_open = True
        in_waiting = 0
        def read(self, count): return b''
        def close(self): self.is_open = False
    app.port = SilentPort()
    app.ready = False
    app.telemetry_seen = False
    app.opened = time.monotonic() - 2.1
    app.poll()
    assert app.ready and not app.telemetry_seen and '单向演奏' in app.status.get()
    checks.append('silent U15 return enters explicit one-way V14 performance state after the two-second drain')
    app.port.close()
    app.port = None
    app.key_press(event())
    app.close()
    assert not app.repeat_timers and not app.notes.held
    assert_balanced()
    checks.append('close releases the final note and removes repeat callbacks')
    assert not callback_errors, callback_errors
    passed = True
finally:
    if not app.closed:
        app.close()
    (out / 'verification.json').write_text(json.dumps(dict(passed=passed, checks=checks,
        timings=timings, hardware_tested=False,
        scope='Actual Tk loop with injected callbacks; no physical keyboard, UART or external device acceptance'), indent=2) + '\n')
    print('passed', passed, checks, flush=True)
