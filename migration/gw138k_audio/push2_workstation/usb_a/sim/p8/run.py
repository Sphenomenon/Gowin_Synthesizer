from pathlib import Path
import sys,subprocess,json,hashlib,xml.etree.ElementTree as ET
from datetime import datetime
build=Path(sys.argv[1]).resolve();p=build/'Prj1';kind=sys.argv[2];src=Path(__file__).resolve().parent
out=build/('p8_'+kind+'_'+datetime.now().strftime('%H%M%S'));out.mkdir();print(out,flush=True)
(out/'sim').symlink_to(p/'sim',target_is_directory=True)
if kind=='slide':sources=[p/'src/video/feedback_dashboard.v',p/'src/video/video_font_5x7.v']
else:
 sources=[p/f.get('path') for f in ET.parse(p/'Prj1.gprj').find('FileList') if f.get('type')=='file.verilog']
 sources=[f for f in sources if not any(x in str(f.relative_to(p)) for x in ['vendor/','src/memory/','src/platform/','src/top/','src/ae350/riscv_','workstation_top.v','workstation_top.sv','gw138k_cpu_pll_cell.v','gw138k_audio_clock.v'])]
sources+=[src/('tb_effect_'+kind+'.sv')]
(out/'inputs.json').write_text(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources},indent=2)+'\n')
commands=[['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_effect_'+kind,'--Mdir',str(out/'obj'),'-I'+str(p),'-I'+str(p/'src/usb_a'),*map(str,sources)], [str(out/('obj/Vtb_effect_'+kind))]]
for name,cmd in zip(['compile','simulation'],commands):
 with (out/(name+'.log')).open('w') as log:r=subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT)
 print(name,r.returncode,flush=True)
 if r.returncode:print((out/(name+'.log')).read_text()[-5000:]);raise SystemExit(1)
print((out/'simulation.log').read_text());(out/'verification.json').write_text(json.dumps(dict(passed=True,hardware_tested=False),indent=2)+'\n')
