#!/usr/bin/env python3
from pathlib import Path
import argparse
from datetime import datetime
import sys,subprocess,json,hashlib,shutil
root=Path(__file__).resolve().parents[2]
ap=argparse.ArgumentParser();ap.add_argument('build',type=Path);ap.add_argument('--write-path',action='store_true');args=ap.parse_args()
build=args.build.resolve();p=build/'Prj1'
out=build/datetime.now().strftime('p11_shared_%H%M%S_%f');out.mkdir();print(out,flush=True)
baseline=root/'results/build_20260913_184716_871458/Prj1'
ref=out/'p10_feedback_renderer.v';ref.write_text((baseline/'src/video/feedback_renderer.v').read_text().replace('module feedback_renderer #','module p10_feedback_renderer #'))
names=['feedback_renderer','feedback_dashboard','feedback_wave_align','feedback_capture','output_audio_capture','output_audio_analysis','audio_analysis_rom','video_font_5x7']
tb=out/'tb_shared_display.sv';shutil.copy2(Path(__file__).with_name(tb.name),tb)
sources=[p/'src/memory/display_data_layout_pkg.sv',p/'src/memory/display_data_writer.v',*[p/f'src/video/{n}.v' for n in names],ref,tb]
top='tb_shared_display'
if args.write_path:
 top='tb_display_write_path'
 tb=out/(top+'.sv');shutil.copy2(Path(__file__).with_name(tb.name),tb)
 sources=[p/'src/memory/display_data_layout_pkg.sv',p/'src/memory/display_data_writer.v',p/'src/memory/ddr_frame_writer.v',p/'src/ae350/gw138k_ddr_arbiter.sv',tb]
(out/'inputs.json').write_text(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources},indent=2)+'\n')
for label,cmd in [('compile',['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module',top,'--Mdir',str(out/'obj'),*map(str,sources)]),('simulation',[str(out/('obj/V'+top))])]:
 r=subprocess.run(cmd,cwd=out,capture_output=True,text=True);(out/(label+'.log')).write_text(r.stdout+r.stderr)
 print(label,r.returncode,flush=True)
 if r.returncode:print((r.stdout+r.stderr)[-8000:]);sys.exit(1)
print((out/'simulation.log').read_text())
(out/'verification.json').write_text(json.dumps(dict(passed=True,hardware_tested=False,scope=top+'; no physical HDMI/Push acceptance'),indent=2)+'\n')
