#!/usr/bin/env python3
"""Focused board-PANIC feedback test; no serial port or board is opened."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys,time,tkinter as tk

source=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(source.parent))
spec=importlib.util.spec_from_file_location('panic_keyboard',source)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
root=tk.Tk();root.withdraw();app=module.KeyboardWindow(root,connect=False);root.update();root.after_cancel(app.poll_id)
sent=[]
app.ready=True;app.send=lambda data:sent.append(data);app.notes.send=app.send
def pump(ms):
    end=time.monotonic()+ms/1000
    while time.monotonic()<end:root.update();time.sleep(.001)
def event(stamp,key='z',code=52):return SimpleNamespace(keycode=code,keysym=key,time=stamp)
try:
    app.key_press(event(100));pump(340)
    assert app.notes.held and app.repeat_timers and len(sent)>=3
    before=len(sent);app.cpu_sequence=7
    app.last_state={'sequence':7,'mode':'C','sound':'piano','route':'stereo','effects':0,
                    'active_voices':1,'pc_input_errors':0,'held_notes':[60]}
    app.panic_epoch=0
    words=[7,0,(1<<22)|1048576,0,0,0,0,0x43545231]
    app.receive('E138',words)
    assert not app.notes.held and not app.repeat_timers and app.panic_epoch==1 and len(sent)==before
    assert 52 in app.pressed
    app.key_press(event(101));pump(120);assert len(sent)==before
    app.key_release(event(200));pump(40);app.key_press(event(201));
    assert sent[-1]==bytes.fromhex('90 3c 64')
    app.key_release(event(202));pump(40)
    assert app.notes.held=={} and app.panic_epoch==1
    print('PASS PANIC computer UI: feedback clears held/repeat locally and latches physical key until release')
finally:
    app.close()
