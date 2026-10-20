#!/usr/bin/env python3
"""Full real-weight pipeline: untiled vs tiled at identical 4-Hz feature times.
Checks all six layer hashes at every completed wave, score events and cycles.
"""
from pathlib import Path
import importlib.util,json,subprocess,argparse,time,hashlib,re
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('config_ab',ROOT/'sim/music/run_bp_config_ab.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--frames',type=int,default=8)
    parser.add_argument('--ddr-latency',type=int,default=3);args=parser.parse_args()
    out=ROOT/'out/resource_cnn_tiles';out.mkdir(parents=True,exist_ok=True)
    (out/'summary.json').unlink(missing_ok=True)
    tb=(ROOT/'sim/music/tb_bp_config_ab.sv').read_text()
    tb=tb.replace('.USE_ALL_DDR(1\'b1), .USE_DDR_FRONT_COEFF',
       '.USE_EXTERNAL_WEIGHTS(1\'b1),.USE_EXTERNAL_FEATURES(1\'b1),\n        .USE_ALL_DDR(1\'b0),.USE_DDR_SIGNAL(1\'b1),.USE_DDR_FRONT_COEFF')
    tb=tb.replace('.WIN_LEN(WIN_LEN), .FRAME_LIMIT(FRAMES), .OCTAVE_LIMIT(9),',
       '.WIN_LEN(WIN_LEN), .FRAME_LIMIT(FRAMES), .OCTAVE_LIMIT(9),\n        .CQT_HOP_NUMERATOR(22050),.CQT_HOP_DENOMINATOR(4),.COARSE_GUIDANCE(1\'b1),')
    idx=tb.index('    ) dut_b (');prev=tb.rfind('.USE_DDR_FRONT_COEFF',0,idx)
    tb=tb[:prev]+'.FEATURE_TILE_COLS(16),\n        '+tb[prev:]
    tb=tb.replace('$writememh("sim/music/gen/run_a_hashes.mem", a_hash_snap);','').replace('$writememh("sim/music/gen/run_b_hashes.mem", b_hash_snap);','')
    tb=tb.replace('    integer a_notes = 0,', '    integer cycles_a=0,cycles_b=0;\n    always @(posedge clk) if(rstn) begin if(run_a)cycles_a=cycles_a+1;else cycles_b=cycles_b+1;end\n    integer a_notes = 0,')
    tb=tb.replace('if (errors == 0) $display("PASS dual-config equivalence (%0d notes)", a_notes);',
       'if (errors == 0) $display("PASS dual-config equivalence (%0d notes) cycles_untiled=%0d cycles_tiled=%0d", a_notes,cycles_a,cycles_b);')
    (out/'tb.sv').write_text(tb)
    sources=[str(ROOT/'rtl/music/basic_pitch_nn_ddr.sv')]+[str(ROOT/'rtl/music'/s) for s in base.MUSIC_SOURCES if s!='basic_pitch_nn_ddr.sv']
    sources+=[str(ROOT/'rtl/memory/workstation_sdp.sv'),str(out/'tb.sv')]
    input_hashes={str(Path(p).relative_to(ROOT)):hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sources}
    command=['verilator','--binary','--timing','--build-jobs','4','-Wno-fatal',
       '--top-module','tb_bp_config_ab','--Mdir',str(out/'obj_dir'),'-I'+str(ROOT/'rtl/music'),
       '-GFRAMES='+str(args.frames),'-GWIN_LEN=44100','-GDDR_READ_CYCLES='+str(args.ddr_latency),'-GMAX_CYCLES=1000000000']+sources
    with (out/'build.log').open('w') as log:p=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    if p.returncode:raise SystemExit('compile failed: '+str(out/'build.log'))
    start=time.monotonic()
    with (out/'simulation.log').open('w') as log:p=subprocess.run([str(out/'obj_dir/Vtb_bp_config_ab')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    text=(out/'simulation.log').read_text();passed=p.returncode==0 and 'PASS dual-config equivalence' in text
    counts=re.search(r'cycles_untiled=(\d+) cycles_tiled=(\d+)',text)
    cycles={}
    if counts:
        untiled,tiled=map(int,counts.groups());cycles=dict(untiled=untiled,tiled=tiled,overhead_percent=(tiled/untiled-1)*100)
    (out/'summary.json').write_text(json.dumps(dict(passed=passed,frames=args.frames,ddr_latency=args.ddr_latency,seconds=time.monotonic()-start,cycles=cycles,source_sha256=input_hashes),indent=2)+'\n')
    print(text[-2600:]);print(out)
    if not passed:raise SystemExit(1)
if __name__=='__main__':main()
