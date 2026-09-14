from pathlib import Path
from datetime import datetime
import argparse,hashlib,json,re,subprocess
B=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('file',type=Path);p.add_argument('--from-code',required=True)
p.add_argument('--location',type=int,default=54,help='location reported by programmer_cli --scan-cables L')
p.add_argument('--usb-device',type=Path,default=Path('/sys/bus/usb/devices/3-6'),help='sysfs device for the same debugger, serial must match')
a=p.parse_args()
f=a.file.resolve();header=f.read_text()[:1000]
assert '//Device Version: C' in header and '//Part Number: GW5AST-LV138PG484AC2/I1' in header
code=re.search(r'//UserCode: (0x[0-9A-Fa-f]+)',header)[1]
u=a.usb_device;assert (u/'serial').read_text().strip()=='2025030317' and (u/'idVendor').read_text().strip()=='0403' and (u/'idProduct').read_text().strip()=='6010'
o=B/'results'/datetime.now().strftime('sram_%Y%m%d_%H%M%S_%f');o.mkdir();print(o,flush=True)
cli=[str(Path.home()/'.local/opt/gowin-programmer-1.9.12.02/bin/programmer_cli'),'--device','GW5AST-138C','--cable-index','5','--location',str(a.location),'--frequency','0.9MHz']
result=dict(bitstream=str(f),sha256=hashlib.sha256(f.read_bytes()).hexdigest(),from_code=a.from_code,usercode=code,fpga_flash_written=False,cable_location=a.location,usb_device=str(u),operations=[])
for name,args,expected in [('before',['--operation_index','0'],a.from_code),('sram',['--operation_index','2','--fsFile',str(f)],code),('after',['--operation_index','0'],code)]:
 r=subprocess.run(cli+args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=90);(o/(name+'.log')).write_text(r.stdout)
 ok=r.returncode==0 and 'User Code is: '+expected in r.stdout and 'Finished.' in r.stdout and not re.search(r'\b(error|failed|failure)\b',r.stdout,re.I)
 result['operations'].append(dict(name=name,passed=ok));(o/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(name,ok,flush=True);assert ok,r.stdout
