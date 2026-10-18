from pathlib import Path
from datetime import datetime
import hashlib,json,subprocess,re,os,signal,time
B=Path(__file__).resolve().parents[1];O=Path(json.loads((B/'PENDING_BOARD.json').read_text())['directory'])
pre=json.loads((O/'preflight.json').read_text());P=Path(pre['probe']);FS=P/'impl/pnr/probe.fs'
assert hashlib.sha256(FS.read_bytes()).hexdigest()==pre['probe_sha256'];assert pre['firmware_verified'] and pre['diagnostic_only']
header=FS.read_text()[:1000];assert '//Device Version: C' in header and '//Part Number: GW5AST-LV138PG484AC2/I1' in header
code=re.search(r'//UserCode: (0x[0-9A-Fa-f]+)',header)[1]
usb=Path('/sys/bus/usb/devices/3-6');assert (usb/'serial').read_text().strip()=='2025030317' and (usb/'idVendor').read_text().strip()=='0403' and (usb/'idProduct').read_text().strip()=='6010'
pid=282642
try:
 cmd=Path(f'/proc/{pid}/cmdline').read_bytes();assert b'keyboard_midi.py' in cmd
 os.kill(pid,signal.SIGTERM);time.sleep(1)
except FileNotFoundError:pass
cli=[str(Path.home()/'.local/opt/gowin-programmer-1.9.12.02/bin/programmer_cli'),'--device','GW5AST-138C','--cable-index','5','--location','54','--frequency','0.9MHz']
ops=[]
def run(name,args,expected):
 r=subprocess.run(cli+args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=90);(O/(name+'.log')).write_text(r.stdout)
 good=r.returncode==0 and 'User Code is: '+expected in r.stdout and 'Finished.' in r.stdout and not re.search(r'\b(error|failed|failure)\b',r.stdout,re.I)
 ops.append(dict(name=name,args=args,usercode=expected,passed=good,time=datetime.now().isoformat()));(O/'operations.json').write_text(json.dumps(ops,indent=2)+'\n');print(name,good,flush=True);assert good,r.stdout
run('before',['--operation_index','0'],'0x000093D0')
run('probe_sram',['--operation_index','2','--fsFile',str(FS)],code)
run('after',['--operation_index','0'],code)
(O/'download.json').write_text(json.dumps(dict(programmed=True,usercode=code,bitstream_sha256=pre['probe_sha256'],fpga_flash_written=False,diagnostic_only=True),indent=2)+'\n')
print(O,flush=True)
