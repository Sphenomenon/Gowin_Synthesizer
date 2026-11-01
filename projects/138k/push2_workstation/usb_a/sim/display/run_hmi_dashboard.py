#!/usr/bin/env python3
"""Render maintained HDMI RTL and check enabled-pipeline stalls and applied UI."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--support-project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = [ROOT / 'rtl/display_data/feedback_dashboard.v',
               ROOT / 'rtl/display_data/workstation_contest_brand.sv',
               args.support_project.resolve() / 'src/video/video_font_5x7.v']
    bench = output / 'tb.sv'
    bench.write_text(r'''`timescale 1ns/1ps
module tb;
reg clk=0,rst=0,en=1,fs=0;
reg [10:0] x=0,y=0;
reg [128:0] params=0;
wire [31:0] m,w;
integer fm,fw,n=0,pixels=0,stalls=0;
reg [3:0] valid=0;
reg [31:0] previous_m,previous_w;
reg signed [31:0] wave;
always @* wave=($signed({1'b0,x[8:0]})-32'sd256)<<<22;
`define PORTS .clk(clk),.reset_n(rst),.enable(en),.frame_start(fs),.pixel_x(x),.pixel_y(y),.wave_sample(wave),.wave_previous(wave-32'sd4194304),.waveform_held(1'b0),.spectrum_left(8'd112),.spectrum_right(8'd80),.image_hit(x[4:0]==y[4:0]),.peak_left(16'd16384),.peak_right(16'd8192),.image_gain(3'd0),.analysis_sequence(32'd91),.analysis_skipped(32'd0),.peak_data(32'h40000000),.active_voices(32'hffff),.status_data(32'd0),.applied_parameters(params),.effect_mask(3'b111),.effect_order(6'b10_01_00),.sequence_data(32'd91),.skipped_data(32'd0),.memory_status(32'd3),.underruns(32'd0),.framecount(32'd1)
feedback_dashboard #(.ENABLE_ANALYSIS(1)) dm(`PORTS,.pixel_data(m));
feedback_dashboard #(.ENABLE_ANALYSIS(1),.HMI_D_ONLY(1)) dw(`PORTS,.pixel_data(w));
task tick(input bit live);
begin
 en=live;previous_m=m;previous_w=w;#2;clk=1;#2;
 if(!live)begin
  if(m!==previous_m || w!==previous_w)$fatal(1,"stalled output moved");
  stalls=stalls+1;
 end else begin
  valid={valid[2:0],rst};
  if(valid[3])begin
   if($isunknown({m,w}))$fatal(1,"unknown raster pixel %0d",pixels);
   $fwrite(fm,"%c%c%c",m[23:16],m[15:8],m[7:0]);
   $fwrite(fw,"%c%c%c",w[23:16],w[15:8],w[7:0]);
   pixels=pixels+1;
  end
 end
 clk=0;n=n+1;
end endtask
initial begin
 fm=$fopen("m.ppm","wb");fw=$fopen("w.ppm","wb");
 $fwrite(fm,"P6\n1920 1080\n255\n");$fwrite(fw,"P6\n1920 1080\n255\n");
 #1;rst=0;tick(0);rst=1;
 params={1'b0,32'h00000100,16'h6000,6'd16,3'd2,2'd0,2'd2,3'b111,32'h00100000,11'd0,7'd64,7'd96,7'd32};
 // Exact committed values, including vector selection, never status_data.
 x=1248;y=864;#1;if(dm.text_line!=="SOURCE   VECTOR / LIVE MIDI     ")$fatal(1,"vector source");
 if(dw.text_line!=="SOURCE   D / BLUETOOTH STREAM   ")$fatal(1,"D source");
 y=896;#1;if(dm.text_line!=={"MASTER 096 / VOICES 016         "})$fatal(1,"volume/voice projection %h",dm.text_line);
 y=960;#1;if(dw.text_line!=={"CRUSH 032 DRIVE 096 SEND 064    "})$fatal(1,"D projection %h",dw.text_line);
 params[128]=1;y=992;#1;if(dm.text_line!=="OUTPUT   44100 HZ / STEREO      ")$fatal(1,"actual rate");params[128]=0;
 // Settle real effect-card positions before capturing their final applied order.
 fs=1;repeat(100)begin #2;clk=1;#2;clk=0;end fs=0;
 valid=0;
 for(integer yy=0;yy<1080;yy=yy+1)for(integer xx=0;xx<1920;xx=xx+1)begin
  x=11'(xx);y=11'(yy);
  if((xx+yy)%97==0)tick(0);
  tick(1);
 end
 repeat(3)tick(1);
 if(pixels!=2073600 || stalls<20000)$fatal(1,"raster/stall count %0d %0d",pixels,stalls);
 $fclose(fm);$fclose(fw);
 $display("PASS HMI: pixels=%0d stalls=%0d applied_vector_volume_voice_D_rate=1",pixels,stalls);$finish;
end
endmodule
''')
    sources.append(bench)
    shutil.copytree(ROOT / 'rtl/display_data/assets', output / 'rtl/display_data/assets')
    commands = [
        ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal', '--top-module', 'tb',
         '--Mdir', str(output / 'obj'), *map(str, sources)],
        [str(output / 'obj/Vtb')],
    ]
    for index, command in enumerate(commands):
        with (output / f'{index}.log').open('w') as stream:
            subprocess.run(command, cwd=ROOT if index == 0 else output, stdout=stream,
                           stderr=subprocess.STDOUT, check=True, timeout=240)
    from PIL import Image
    for role in ('m', 'w'):
        image = Image.open(output / f'{role}.ppm')
        assert image.size == (1920, 1080)
        # Retained analysis panels have live ink, fine grids and white backgrounds.
        assert image.getpixel((80, 220)) == (255, 255, 255)
        assert image.getpixel((100, 700)) != image.getpixel((101, 700))
        assert image.getpixel((1400, 504)) != image.getpixel((1401, 504))
        image.save(output / f'{role}.png')
    inputs = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    result = dict(passed=True, source_sha256=inputs, pixels_per_role=2073600,
                  scope='Actual dashboard RTL, applied state projection and enabled stalls; simulated stimulus only',
                  hardware_tested=False)
    (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
