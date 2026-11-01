#!/usr/bin/env python3
"""Actual final-scanout rate table: no PCM is needed to update its status."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.workstation_baselines import load_baseline
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    owner=ROOT/'rtl/workstation/workstation_hdmi_display.sv';text=owner.read_text();begin=text.index('module workstation_audio_rate_overlay(');end=text.index('endmodule',begin)+len('endmodule')
    selected=out/'overlay.sv';selected.write_text(text[begin:end]+'\n')
    tb=out/'testbench.sv';tb.write_bytes(Path(__file__).with_name('tb_workstation_audio_rate_overlay.sv').read_bytes())
    baseline=load_baseline(ROOT,'resource_rework_route0');support=[]
    for n in ('src/migration/gw138k_stream_cdc.sv','src/video/video_font_5x7.v'):
        p=out/Path(n).name;p.write_bytes(baseline.read_bytes(n));support.append(p)
    records=[]
    for name in ('actual','midframe_status','rate_echo'):
        source=selected
        if name!='actual':
            source=out/(name+'.sv');s=selected.read_text()
            old,new=(('if(frame_start_i && status_seen)frame_status<=pixel_status;','if(status_seen)frame_status<=pixel_status;') if name=='midframe_status' else ('wire [255:0] rate_word=frame_status[0]','wire [255:0] rate_word=frame_status[2]'))
            assert s.count(old)==1;source.write_text(s.replace(old,new))
        argv=['iverilog','-g2012','-s','tb_workstation_audio_rate_overlay','-o',str(out/(name+'.vvp')),str(source),str(tb),*map(str,support)]
        p=subprocess.run(argv,capture_output=True,text=True,timeout=60);(out/(name+'-compile.log')).write_text(p.stdout+p.stderr)
        if p.returncode:raise RuntimeError(p.stdout+p.stderr)
        p=subprocess.run(['vvp',str(out/(name+'.vvp'))],capture_output=True,text=True,timeout=120);log=p.stdout+p.stderr;(out/(name+'-run.log')).write_text(log)
        passed=p.returncode==0 and 'PASS audio_rate_overlay' in log
        if passed!=(name=='actual'):raise RuntimeError(name+': '+log)
        records.append(dict(name=name,expected_outcome_verified=True,exit_code=p.returncode,argv=argv,source_sha256=sha(source),log=log))
        print(name+': '+log.strip(),flush=True)
    d=dict(schema=1,passed=True,owner=str(owner),owner_sha256=sha(owner),extracted_module_sha256=sha(selected),runner_sha256=sha(Path(__file__)),testbench_sha256=sha(tb),support={str(p):sha(p)for p in support},baseline=baseline.evidence(),cases=records,hardware_tested=False)
    (out/'verification.json').write_text(json.dumps(d,indent=2)+'\n')
if __name__=='__main__':main()
