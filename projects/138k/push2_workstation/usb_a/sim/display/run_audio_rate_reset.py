#!/usr/bin/env python3
"""Existing 1080p reset owner, real release RTL, and overlay consumer boundary."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.workstation_baselines import load_baseline
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    owner=ROOT/'rtl/workstation/workstation_hdmi_display.sv';owner_before=sha(owner);text=owner.read_text()
    begin=text.index('module workstation_audio_rate_overlay(');end=text.index('endmodule',begin)+len('endmodule')
    selected=out/'overlay.sv';selected.write_text(text[begin:end]+'\n')
    tb=out/'testbench.sv';tb.write_bytes(Path(__file__).with_name('tb_workstation_audio_rate_reset.sv').read_bytes())
    baseline=load_baseline(ROOT,'resource_rework_route0');support=[]
    for name in ['src/migration/gw138k_stream_cdc.sv','src/video/video_font_5x7.v',
                 'src/platform/video_clock_1080p.v','vendor/sipeed_dvi/video_pll_1080p_gw5a.v',
                 'sim/models/video_clock_1080p_model.v']:
        p=out/Path(name).name;p.write_bytes(baseline.read_bytes(name));support.append(p)
    records=[]
    for name in ['actual','raw_common_reset','early_pixel_release','synchronous_assertion']:
        source=selected;testbench=tb
        if name=='raw_common_reset':
            source=out/(name+'.sv');s=selected.read_text();old='always @(posedge pixel_clk_i or negedge pixel_reset_ni)begin\n        if(!pixel_reset_ni)begin'
            assert s.count(old)==2;source.write_text(s.replace(old,'always @(posedge pixel_clk_i or negedge reset_ni)begin\n        if(!reset_ni)begin'))
        elif name=='early_pixel_release':
            testbench=out/(name+'-tb.sv');s=tb.read_text();old='.pixel_reset_ni(pixel_reset_n)';assert s.count(old)==1
            testbench.write_text(s.replace(old,'.pixel_reset_ni(clock_owner.pixel_reset_pipe[2])'))
        elif name=='synchronous_assertion':
            source=out/(name+'.sv');s=selected.read_text();old='always @(posedge pixel_clk_i or negedge pixel_reset_ni)';assert s.count(old)==2
            source.write_text(s.replace(old,'always @(posedge pixel_clk_i)'))
        argv=['iverilog','-g2012','-s','tb_workstation_audio_rate_reset','-o',str(out/(name+'.vvp')),str(source),str(testbench),*map(str,support)]
        compiled=subprocess.run(argv,capture_output=True,text=True,timeout=60);(out/(name+'-compile.log')).write_text(compiled.stdout+compiled.stderr)
        if compiled.returncode:raise RuntimeError(compiled.stdout+compiled.stderr)
        result=subprocess.run(['vvp',str(out/(name+'.vvp'))],capture_output=True,text=True,timeout=120);log=result.stdout+result.stderr
        (out/(name+'-run.log')).write_text(log);passed=result.returncode==0 and 'PASS audio_rate_reset' in log
        if passed!=(name=='actual'):raise RuntimeError(name+': '+log)
        records.append(dict(name=name,expected_outcome_verified=True,exit_code=result.returncode,source_sha256=sha(source),testbench_sha256=sha(testbench),argv=argv,log=log))
        print(name+': '+log.strip(),flush=True)
    assert sha(owner)==owner_before,'maintained source changed during reset regression'
    result=dict(schema=1,passed=True,owner=str(owner),owner_sha256=sha(owner),runner_sha256=sha(__file__),
        extracted_module_sha256=sha(selected),testbench_sha256=sha(tb),baseline=baseline.evidence(),support={str(p):sha(p) for p in support},
        cases=records,analog_pll_behavior_verified=False,physical_timing_verified=False,hardware_tested=False)
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
