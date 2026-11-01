#!/usr/bin/env python3
"""Compare balanced text selection with the exact M25 complete dashboard."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
REFERENCE_SHA256 = '3fc70e8330543570cd4e5a5924b69ae4d28fb53e7789a505bfee18e138154375'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


BENCH = r'''`timescale 1ns/1ps
module tb;
reg clk=0,rst=0,en=1,fs=0,held=0;
reg [10:0] x=0,y=0;reg [128:0] params=0;
reg [2:0] mask=7,gain=0;reg [5:0] order=6'b10_01_00;
reg signed [31:0] wave=0,previous=0;reg [7:0] sl=112,sr=80;
reg [15:0] pl=16384,pr=8192;reg [31:0] peak=32'h40000000;
reg [31:0] random_state=32'h138d25a7;
wire [31:0] got[0:3],want[0:3],selected[0:3];
wire [255:0] got_line[0:3],want_line[0:3];
wire [76:0] got_meta[0:3],want_meta[0:3];
integer ticks=0,stalls=0,pixels=0,four_state=0;
`define PORTS .clk(clk),.reset_n(rst),.enable(en),.frame_start(fs),.pixel_x(x),.pixel_y(y),.wave_sample(wave),.wave_previous(previous),.waveform_held(held),.spectrum_left(sl),.spectrum_right(sr),.image_hit(x[4:0]==y[4:0]),.peak_left(pl),.peak_right(pr),.image_gain(gain),.analysis_sequence(32'd91),.analysis_skipped(32'd0),.peak_data(peak),.active_voices(32'hffff),.status_data(32'd0),.applied_parameters(params),.effect_mask(mask),.effect_order(order),.sequence_data(32'd91),.skipped_data(32'd0),.memory_status(32'd3),.underruns(32'd0),.framecount(32'd1)
for(genvar n=0;n<4;n=n+1)begin:configs
 feedback_dashboard #(.ENABLE_ANALYSIS(n&1),.HMI_D_ONLY(n>>1)) actual(`PORTS,.pixel_data(got[n]));
 feedback_dashboard_m25 #(.ENABLE_ANALYSIS(n&1),.HMI_D_ONLY(n>>1)) reference(`PORTS,.pixel_data(want[n]));
 assign got_line[n]=actual.text_line;assign want_line[n]=reference.text_line;
 assign selected[n]=actual.text_word_selected;
 assign got_meta[n]={actual.text_x,actual.text_y,actual.text_enable,actual.large_text,actual.hex_word,actual.hex_enable,actual.hex_x,actual.voice_enable,actual.voice_character};
 assign want_meta[n]={reference.text_x,reference.text_y,reference.text_enable,reference.large_text,reference.hex_word,reference.hex_enable,reference.hex_x,reference.voice_enable,reference.voice_character};
end
task compare_words;
begin
 for(integer n=0;n<4;n=n+1)begin
  if(got_line[n]!==want_line[n] || got_meta[n]!==want_meta[n])
   $fatal(1,"M25 text mismatch config=%0d tick=%0d xy=%h,%h got=%h want=%h",n,ticks,x,y,got_line[n],want_line[n]);
  if((selected[n] & (selected[n]-32'd1))!==32'd0 || $isunknown(selected[n]))
   $fatal(1,"word selection is not known and mutually exclusive config=%0d xy=%h,%h select=%h",n,x,y,selected[n]);
 end
end endtask
task tick(input bit live);
reg [127:0] before_pixels;
begin
 en=live;before_pixels={got[0],got[1],got[2],got[3]};#2;compare_words();clk=1;#2;
 for(integer n=0;n<4;n=n+1)if(got[n]!==want[n])
  $fatal(1,"M25 pixel mismatch config=%0d tick=%0d xy=%h,%h got=%h want=%h",n,ticks,x,y,got[n],want[n]);
 if(!live && rst)begin
  if(before_pixels!=={got[0],got[1],got[2],got[3]})$fatal(1,"stalled output moved");
  stalls=stalls+1;
 end
 clk=0;ticks=ticks+1;
end endtask
function [10:0] row(input integer k);
 case(k)
  0:row=168;1:row=200;2:row=480;3:row=528;4:row=568;5:row=632;6:row=696;
  7:row=760;8:row=752;9:row=804;10:row=784;11:row=816;12:row=840;13:row=888;
  14:row=968;15:row=864;16:row=896;17:row=928;18:row=960;19:row=992;default:row=1024;
 endcase
endfunction
function [10:0] column(input integer k);
 case(k)
  0:column=8;1:column=64;2:column=80;3:column=200;4:column=282;5:column=416;
  6:column=536;7:column=562;8:column=640;9:column=752;10:column=834;11:column=872;
  12:column=1040;13:column=1216;14:column=1248;15:column=1280;16:column=1440;
  17:column=1472;default:column=1712;
 endcase
endfunction
initial begin
 #1;rst=0;tick(0);rst=1;
 params={1'b0,32'h00000100,16'h6000,6'd16,3'd2,2'd0,2'd2,3'b111,32'h00100000,11'd0,7'd64,7'd96,7'd32};
 fs=1;repeat(100)tick(1);fs=0;
`ifdef FOUR_STATE
 for(integer yy=0;yy<21;yy=yy+1)for(integer xx=0;xx<19;xx=xx+1)begin
  x=column(xx);y=row(yy);tick(1);
  for(integer b=0;b<11;b=b+1)begin
   x=column(xx);x[b]=1'bx;tick(1);four_state=four_state+1;
   x=column(xx);x[b]=1'bz;tick(0);four_state=four_state+1;
   x=column(xx);y=row(yy);y[b]=1'bx;tick(1);four_state=four_state+1;
   y=row(yy);y[b]=1'bz;tick(1);four_state=four_state+1;y=row(yy);
  end
  x=column(xx);y=row(yy);held=1'bx;gain=3'bxxx;peak=32'hxxxxxxxx;
  params[128]=1'bx;params[95:88]=8'hxx;params[17:4]=14'bx;tick(1);four_state=four_state+1;
  held=1'bz;gain=3'bzzz;peak=32'hzzzzzzzz;params[128]=1'bz;tick(1);four_state=four_state+1;
  held=0;gain=0;peak=32'h40000000;
  params={1'b0,32'h00000100,16'h6000,6'd16,3'd2,2'd0,2'd2,3'b111,32'h00100000,11'd0,7'd64,7'd96,7'd32};
 end
 if(four_state!=18354)$fatal(1,"four-state coverage");
 $display("PASS M25 words FOUR_STATE: configs=4 vectors=%0d ticks=%0d stalls=%0d",four_state,ticks,stalls);
`else
 // Every eleven-bit coordinate includes the full 1920x1080 canvas and all
 // off-canvas inputs. Compare complete pixels and metadata, including stalls.
 for(integer yy=0;yy<2048;yy=yy+1)for(integer xx=0;xx<2048;xx=xx+1)begin
  x=11'(xx);y=11'(yy);previous=wave;wave=($signed({1'b0,x[8:0]})-32'sd256)<<<22;
  sl=8'(xx+yy);sr=8'(xx*3+yy);pl=16'(xx*29+yy);pr=16'(xx+yy*31);peak={1'b0,31'(xx*65521+yy)};
  if((xx+yy)%97==0)tick(0);tick(1);pixels=pixels+1;
 end
 for(integer k=0;k<65536;k=k+1)begin
  // Fixed seed makes random applied values repeatable. Keep committed voice,
  // mode/profile/route, Q20 pitch and the six effect permutations in range.
  random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
  x=column(k%19);y=row(k%21);params[31:0]=random_state;
  params[53:32]=22'h080000+{1'b0,random_state[20:0]};
  params[68:67]=2'(k%3);params[70:69]=2'(k%3);params[73:71]=3'(k%5);
  params[79:74]=6'(k%33);params[95:80]={1'b0,random_state[14:0]};
  params[104]=random_state[8];params[128]=random_state[9];
  held=random_state[10];gain=random_state[13:11];fs=(k%71)==0;mask=random_state[16:14];
  case(k%6)
   0:order=6'b10_01_00;1:order=6'b01_10_00;2:order=6'b10_00_01;
   3:order=6'b00_10_01;4:order=6'b01_00_10;5:order=6'b00_01_10;
  endcase
  tick((k%13)!=0);
 end
 if(pixels!=4194304 || stalls<40000)$fatal(1,"raster coverage");
 $display("PASS M25 words FULL_RASTER: configs=4 coordinates=%0d extra_vectors=65536 ticks=%0d stalls=%0d latency_changed=0",pixels,ticks,stalls);
`endif
 $finish;
end
endmodule
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-dashboard', type=Path, required=True)
    parser.add_argument('--support-project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--negative-word', action='store_true')
    parser.add_argument('--negative-x-control', action='store_true')
    args = parser.parse_args()
    if args.negative_word and args.negative_x_control:
        parser.error('choose one negative control')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    reference = args.reference_dashboard.resolve()
    if sha(reference) != REFERENCE_SHA256:
        raise ValueError('immutable M25 dashboard identity drift')
    current = ROOT / 'rtl/display_data/feedback_dashboard.v'
    old = out / 'feedback_dashboard_m25.v'
    text = reference.read_text()
    anchor = 'module feedback_dashboard #'
    if text.count(anchor) != 1:
        raise ValueError('reference module rename anchor drift')
    old.write_text(text.replace(anchor, 'module feedback_dashboard_m25 #'))
    selected = current
    negative = args.negative_word or args.negative_x_control
    if negative:
        text = current.read_text()
        before, after = (
            ('assign text_word_terms[0]={256{text_word_selected[0]}} & (wave_heading);',
             "assign text_word_terms[0]=256'd0;") if args.negative_word else
            ("begin text_selected=1'b0; if(condition)text_selected=1'b1; end", 'begin text_selected=condition; end'))
        if text.count(before) != 1:
            raise ValueError('negative-control source anchor drift')
        selected = out / 'feedback_dashboard_mutant.v'
        selected.write_text(text.replace(before, after))
    bench = out / 'tb.sv'
    bench.write_text(BENCH)
    sources = [selected, old, ROOT / 'rtl/display_data/workstation_contest_brand.sv',
               args.support_project.resolve() / 'src/video/video_font_5x7.v', bench]
    inputs = {str(p): sha(p) for p in [*sources, reference, current, Path(__file__).resolve()]}
    shutil.copytree(ROOT / 'rtl/display_data/assets', out / 'rtl/display_data/assets')
    result = dict(passed=False, reference_sha256=REFERENCE_SHA256, input_sha256=inputs,
                  synthesis_tested=False, physical_timing_verified=False, hardware_tested=False,
                  scope='Exact M25 complete dashboard pixels, word/metadata priority, all four role/analysis configurations and unchanged enabled stages')

    def run(name, command, expect_failure=False):
        with (out / (name + '.log')).open('w') as stream:
            done = subprocess.run(command, cwd=out, stdout=stream, stderr=subprocess.STDOUT, timeout=300)
        log = (out / (name + '.log')).read_text()
        if (done.returncode != 0) != expect_failure:
            raise ValueError(name + ' unexpected outcome: ' + log[-2000:])
        return log

    try:
        run('four_compile', ['iverilog', '-g2012', '-DFOUR_STATE', '-s', 'tb', '-o', str(out / 'four.vvp'), *map(str, sources)])
        log = run('four_run', ['vvp', str(out / 'four.vvp')], negative)
        if negative:
            if 'M25 text mismatch' not in log and 'word selection is not known' not in log:
                raise ValueError('negative control did not reach the text oracle')
            result['negative_control_rejected'] = True
        else:
            if 'PASS M25 words FOUR_STATE' not in log:
                raise ValueError('four-state evidence missing')
            run('raster_compile', ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
                '--top-module', 'tb', '--Mdir', str(out / 'obj'), *map(str, sources)])
            raster = run('raster_run', [str(out / 'obj/Vtb')])
            if 'PASS M25 words FULL_RASTER' not in raster:
                raise ValueError('raster evidence missing')
            result.update(four_state_vectors=18354, coordinates_per_configuration=4194304,
                          extra_parameter_vectors=65536, random_seed='138d25a7',
                          configurations=4, latency_changed=False)
        if any(sha(p) != value for p, value in inputs.items()):
            raise ValueError('input drift during validation')
        result['passed'] = True
        print(log, end='')
        if not negative:
            print(raster, end='')
    finally:
        (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
