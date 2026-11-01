#!/usr/bin/env python3
"""Compare every enabled pixel with the sealed M23 dashboard, including stalls."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dashboard_predicate_sources as predicates
REFERENCE_SHA256 = '750d5347036619b88b06112a93c99fcb9fad039c0c25076b64837bdd3b2a1964'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-dashboard', type=Path, required=True)
    parser.add_argument('--support-project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--negative-coordinate', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    reference = args.reference_dashboard.resolve()
    assert sha(reference) == REFERENCE_SHA256, 'sealed M23 dashboard drift'
    old = out / 'feedback_dashboard_m23.v'
    text = reference.read_text()
    assert text.count('module feedback_dashboard #') == 1
    old.write_text(text.replace('module feedback_dashboard #', 'module feedback_dashboard_m23 #'))
    current = ROOT / 'rtl/display_data/feedback_dashboard.v'
    assert predicates.reference_view(current.read_text()) == reference.read_text(), 'exact whole-source predicate inverse failed'
    selected = current
    if args.negative_coordinate:
        text = current.read_text()
        anchor = 'a_analysis_wave_box<=(pixel_x>=64 && pixel_x<1088 && pixel_y>=208 && pixel_y<464);'
        assert text.count(anchor) == 1
        selected = out / 'feedback_dashboard_mutant.v'
        selected.write_text(text.replace(anchor, "a_analysis_wave_box<=1'b0;"))
    bench = out / 'tb.sv'
    bench.write_text(r'''`timescale 1ns/1ps
module tb;
reg clk=0,rst=0,en=1,fs=0;reg [10:0] x=0,y=0;
reg [128:0] params=0;reg[2:0] mask=7;reg[5:0] order=6'b10_01_00;
reg signed[31:0] wave=0,previous=0;reg[7:0] sl=112,sr=80;
reg[15:0] pl=16384,pr=8192;reg[31:0] peak=32'h40000000;
wire[31:0] got[0:3],want[0:3];integer ticks=0,stalls=0,pixels=0;
`define PORTS .clk(clk),.reset_n(rst),.enable(en),.frame_start(fs),.pixel_x(x),.pixel_y(y),.wave_sample(wave),.wave_previous(previous),.waveform_held(1'b0),.spectrum_left(sl),.spectrum_right(sr),.image_hit(x[4:0]==y[4:0]),.peak_left(pl),.peak_right(pr),.image_gain(3'd0),.analysis_sequence(32'd91),.analysis_skipped(32'd0),.peak_data(peak),.active_voices(32'hffff),.status_data(32'd0),.applied_parameters(params),.effect_mask(mask),.effect_order(order),.sequence_data(32'd91),.skipped_data(32'd0),.memory_status(32'd3),.underruns(32'd0),.framecount(32'd1)
for(genvar n=0;n<4;n=n+1)begin:configs
 feedback_dashboard #(.ENABLE_ANALYSIS(n&1),.HMI_D_ONLY(n>>1)) actual(`PORTS,.pixel_data(got[n]));
 feedback_dashboard_m23 #(.ENABLE_ANALYSIS(n&1),.HMI_D_ONLY(n>>1)) reference(`PORTS,.pixel_data(want[n]));
end
task tick(input bit live);
reg[127:0] before_pixels;
begin
 en=live;before_pixels={got[0],got[1],got[2],got[3]};#2;clk=1;#2;
 for(integer n=0;n<4;n=n+1)if(got[n]!==want[n])$fatal(1,"M23 coordinate retime differs config=%0d tick=%0d xy=%0d,%0d got=%h want=%h",n,ticks,x,y,got[n],want[n]);
 if(!live)begin if(before_pixels!=={got[0],got[1],got[2],got[3]})$fatal(1,"stalled output moved");stalls=stalls+1;end
 clk=0;ticks=ticks+1;
end endtask
initial begin
 #1;rst=0;tick(0);rst=1;
 params={1'b0,32'h00000100,16'h6000,6'd16,3'd2,2'd0,2'd2,3'b111,32'h00100000,11'd0,7'd64,7'd96,7'd32};
 // Consecutive frame starts exercise exact effect-card state, with stalls.
 fs=1;repeat(100)tick(1);fs=0;
 for(integer yy=0;yy<1080;yy=yy+1)for(integer xx=0;xx<1920;xx=xx+1)begin
  x=11'(xx);y=11'(yy);previous=wave;wave=($signed({1'b0,x[8:0]})-32'sd256)<<<22;
  sl=8'(xx+yy);sr=8'(xx*3+yy);pl=16'(xx*29+yy);pr=16'(xx+yy*31);peak={1'b0,31'(xx*65521+yy)};
  if((xx+yy)%97==0)tick(0);tick(1);pixels=pixels+1;
 end
 // Out-of-canvas and all eleven-bit coordinates, changing actual parameters
 // and frame boundaries as data to both complete modules on the same edge.
 for(integer k=0;k<65536;k=k+1)begin
  x=11'(k*37);y=11'(k*91);params[95:88]=8'(k);params[17:4]=14'(k);params[128]=1'(k);
  fs=(k%71)==0;mask=3'(k>>4);order=6'(k>>7);tick((k%13)!=0);
 end
 if(pixels!=2073600 || stalls<20000)$fatal(1,"coverage");
 $display("PASS M23 dashboard: configs=4 pixels_per_config=%0d extra_vectors=65536 ticks=%0d stalls=%0d latency_changed=0",pixels,ticks,stalls);$finish;
end
endmodule
''')
    sources = [selected, old, ROOT / 'rtl/display_data/workstation_contest_brand.sv',
               args.support_project.resolve() / 'src/video/video_font_5x7.v', bench]
    inputs = {str(p): sha(p) for p in sources + [reference, current, Path(__file__).resolve()] + predicates.contract_inputs()}
    shutil.copytree(ROOT / 'rtl/display_data/assets', out / 'rtl/display_data/assets')
    compile_command = ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal', '--top-module', 'tb',
                       '--Mdir', str(out / 'obj'), *map(str, sources)]
    with (out / 'compile.log').open('w') as log:
        subprocess.run(compile_command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
    with (out / 'run.log').open('w') as log:
        run = subprocess.run([str(out / 'obj/Vtb')], cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=180)
    assert (run.returncode == 0) != args.negative_coordinate, 'unexpected full dashboard comparison outcome'
    log = (out / 'run.log').read_text()
    assert ('M23 coordinate retime differs' if args.negative_coordinate else 'PASS M23 dashboard') in log
    assert all(sha(p) == value for p, value in inputs.items()), 'dashboard input drift'
    result = dict(passed=True, negative_coordinate_rejected=args.negative_coordinate,
                  exact_whole_source_inverse=True,
                  reference_sha256=REFERENCE_SHA256, input_sha256=inputs,
                  output_log_sha256=sha(out / 'run.log'), physical_timing_verified=False, hardware_tested=False,
                  scope='Whole maintained and sealed M23 dashboard, all four analysis/role configurations, unchanged existing pipeline and stalls')
    (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(log, end='')


if __name__ == '__main__':
    main()
