from pathlib import Path
from types import SimpleNamespace
import sys,time,datetime,hashlib,json,importlib.util,tkinter as tk
r=Path(__file__).resolve().parents[2];sys.path.insert(0,str(r/'ae350/scripts'))
source=Path(sys.argv[1]) if len(sys.argv)>1 else r/'ae350/scripts/keyboard_midi.py'
spec=importlib.util.spec_from_file_location('subject_keyboard',source);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
o=r/'results'/datetime.datetime.now().strftime('keyboard_repeat_%Y%m%d_%H%M%S_%f');o.mkdir();print(o,flush=True)
(o/'inputs.json').write_text(json.dumps({str(source):hashlib.sha256(source.read_bytes()).hexdigest()},indent=2)+'\n');(o/'test.py').write_bytes(Path(__file__).read_bytes())
root=tk.Tk();app=module.KeyboardWindow(root,connect=False);root.withdraw();sent=[];app.ready=True;app.send=sent.append;app.notes.send=sent.append;checks=[]
def pump(ms):
 end=time.monotonic()+ms/1000
 while time.monotonic()<end:root.update();time.sleep(.001)
def event(code,key,t):return SimpleNamespace(keycode=code,keysym=key,time=t)
passed=False
try:
 # Baseline fails: idle processing happens before the synthetic repeat Press.
 app.key_press(event(52,'z',100))
 for t,gap in enumerate([1,5,12,25]*3,200):
  app.key_release(event(52,'z',t));pump(gap);app.key_press(event(52,'z',t));pump(2)
 assert sent==[bytes.fromhex('90 3c 64')],sent
 app.key_release(event(52,'z',900));pump(45);assert sent==[bytes.fromhex('90 3c 64'),bytes.fromhex('80 3c 00')]
 checks.append('12 X11 timestamp-matched release/press repeat pairs across idle boundaries, 1..25ms gaps: one Note On/Off')
 sent.clear()
 for code,key,t in [(52,'z',1000),(53,'x',1001),(54,'c',1002)]:app.key_press(event(code,key,t))
 for t in range(1010,1022):
  for code,key in [(52,'z'),(53,'x'),(54,'c')]:app.key_release(event(code,key,t))
  pump(4)
  for code,key in [(52,'z'),(53,'x'),(54,'c')]:app.key_press(event(code,key,t))
 assert len(sent)==3,sent
 app.release_owned();assert len(sent)==4 and len(sent[-1])==9;assert not app.releases and not app.pressed and not app.notes.held
 checks.append('three-note held chord remains stable through repeats; focus cleanup releases each owned note once')
 sent.clear();app.key_press(event(52,'z',2000));app.key_release(event(52,'z',2001));pump(2);app.key_press(event(52,'z',2002));app.key_release(event(52,'z',2003));pump(45)
 assert sent==[bytes.fromhex(h)for h in ['90 3c 64','80 3c 00','90 3c 64','80 3c 00']],sent
 checks.append('real 2ms rapid up/down has different server time and retriggers, not swallowed by repeat window')
 sent.clear();app.key_press(event(65,'space',3000));app.key_release(event(65,'space',3001));pump(10);app.key_press(event(65,'space',3001));assert sent==[bytes.fromhex('b0 40 7f')];app.key_release(event(65,'space',3100));pump(45);assert sent[-1]==bytes.fromhex('b0 40 00')
 checks.append('sustain repeat emits no repeated pedal toggles; real release remains bounded')
 sent.clear();app.key_press(event(52,'z',4000));app.panic();size=len(sent);app.key_release(event(52,'z',4001));pump(8);app.key_press(event(52,'z',4001));assert len(sent)==size;app.release_owned();pump(45);assert len(sent)==size
 checks.append('panic stays latched through repeats and cancels pending release callbacks')
 passed=True
finally:
 app.close();(o/'verification.json').write_text(json.dumps(dict(passed=passed,checks=checks,scope='Actual Tk event loop; injected callback events reproduce X11 timing, not physical key hardware'),indent=2)+'\n');print('passed',passed,checks,flush=True)
