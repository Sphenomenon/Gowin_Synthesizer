#!/usr/bin/env python3
"""UI gesture/render oracle, APB publication races and full scanout pixel tests."""
import datetime,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];TEAM=ROOT.parents[2]/'Mega_138K/Dev/Prj1'
out=ROOT.parent/'results'/datetime.datetime.now().strftime('ae350_ui_sim_%Y%m%d_%H%M%S_%f');out.mkdir();print(out,flush=True)
inputs=[p for p in (ROOT/'ui').glob('*') if p.suffix in ['.c','.h','.v','.sv']]+[ROOT/'sim'/n for n in ['test_ui_host.c','tb_ui_services.sv','tb_ui_scanout.sv','tb_composite_scanout.sv']]+[TEAM/'sim/tb_ddr_framebuffer.sv',TEAM/'src/memory/ddr_frame_writer.v']
hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs if p.is_file()};(out/'inputs.json').write_text(json.dumps(hashes,indent=2)+'\n')
def run(name,cmd):
 with (out/(name+'.log')).open('w') as f:p=subprocess.run(list(map(str,cmd)),stdout=f,stderr=subprocess.STDOUT)
 print(name,p.returncode,flush=True)
 if p.returncode:raise SystemExit(p.returncode)
run('host_compile',['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(ROOT/'ui'),ROOT/'sim/test_ui_host.c',ROOT/'ui/ui_render.c','-o',out/'host'])
run('host',[out/'host',out/'ui.rgb565'])
for top,sources in [
 ('tb_ui_services',[ROOT/'sim/tb_ui_services.sv',ROOT/'ui/gw138k_ui_services.sv',ROOT/'ui/gw138k_view_select.sv']),
 ('tb_ui_scanout',[ROOT/'sim/tb_ui_scanout.sv',ROOT/'ui/video_ddr_scanout.v',TEAM/'src/memory/ddr_frame_writer.v']),
 ('tb_composite_scanout',[ROOT/'sim/tb_composite_scanout.sv',ROOT/'ui/video_ddr_scanout.v',TEAM/'src/memory/ddr_frame_writer.v']),
 ('tb_ddr_framebuffer',[TEAM/'sim/tb_ddr_framebuffer.sv',ROOT/'ui/video_ddr_scanout.v',TEAM/'src/memory/ddr_frame_writer.v'])]:
 run(top+'_compile',['iverilog','-g2012','-s',top,'-o',out/(top+'.vvp'),*sources])
 run(top,['vvp',out/(top+'.vvp')])
assert all(hashlib.sha256(Path(f).read_bytes()).hexdigest()==h for f,h in hashes.items())
(out/'verification.json').write_text(json.dumps(dict(passed=True,inputs_unchanged=True,hardware_tested=False),indent=2)+'\n')
