#!/usr/bin/env python3
from datetime import datetime
from pathlib import Path
import hashlib,json,subprocess,sys

build=Path(sys.argv[1]).resolve()
project=build/'Prj1'
source_root=Path(__file__).resolve().parent
out=build/datetime.now().strftime('p10_serial_effects_%H%M%S_%f')
out.mkdir()
print(out,flush=True)
sources=[
    project/'legacy/rtl/audio/audio_math_pkg.sv',
    project/'legacy/rtl/audio/stereo_effects.sv',
    source_root/'tb_serial_effect_order.sv'
]
(out/'inputs.json').write_text(json.dumps({str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},indent=2)+'\n')
commands=[
    ['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_serial_effect_order','--Mdir',str(out/'obj'),*map(str,sources)],
    [str(out/'obj/Vtb_serial_effect_order')]
]
for name,command in zip(['compile','simulation'],commands):
    result=subprocess.run(command,cwd=out,capture_output=True,text=True)
    (out/(name+'.log')).write_text(result.stdout+result.stderr)
    print(name,result.returncode,flush=True)
    if result.returncode:
        print((out/(name+'.log')).read_text()[-5000:])
        raise SystemExit(1)
print((out/'simulation.log').read_text())
(out/'verification.json').write_text(json.dumps({'passed':True,'hardware_tested':False},indent=2)+'\n')
