#!/usr/bin/env python3
"""Exhaustively compare actual image-coordinate RTL for every signed input."""
from pathlib import Path
import hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
build=Path(sys.argv[1]).resolve();stage=build/'Prj1';out=build/'image_coordinates';out.mkdir(exist_ok=True)
source=stage/'src/video/output_audio_analysis.v'
old=ROOT/'results/resource_rework_final_route0_20261020_041042/Prj1/src/video/output_audio_analysis.v'
reference=out/'reference.v';reference.write_text(old.read_text().replace('module output_audio_analysis','module output_audio_analysis_reference',1).replace('gw138k_spectrum_column_rom','gw138k_spectrum_column_rom_reference'))
ports='''(.clk(clk),.reset_n(reset_n),.source_clk(clk),.source_reset_n(reset_n),.pcm_pair(32'd0),.sample_valid(1'b0),.release_frame(1'b0),.ready(),.peak_left(),.peak_right(),.image_gain(),.sequence_data(),.skipped_data(),.display_read_enable(1'b0),.spectrum_column(9'd0),.image_addr(16'd0),.spectrum_left(),.spectrum_right(),.image_hit(),.display_valid());'''
bench=out/'tb.sv';bench.write_text('''`timescale 1ns/1ps
module tb;
reg clk=0,reset_n=0;integer gain,value,checked=0;
output_audio_analysis dut'''+ports+'''
output_audio_analysis_reference reference_dut'''+ports+'''
initial begin
 #1;clk=1;#1;clk=0;reset_n=1;
 force dut.plot_nonzero=0;force reference_dut.plot_nonzero=0;
 for(gain=0;gain<8;gain=gain+1)begin
  force dut.state=4;force reference_dut.state=4;
  force dut.computed_gain=gain;force reference_dut.computed_gain=gain;
  #1;clk=1;#1;clk=0;
  if(dut.image_shift!==9-gain)$fatal(1,"shift capture %0d",gain);
  force dut.state=7;force reference_dut.state=7;
  for(value=-65536;value<65536;value=value+1)begin
   dut.plot_mid=value;reference_dut.plot_mid=value;
   dut.plot_side=-1-value;reference_dut.plot_side=-1-value;
   #1;
   if({dut.image_x,dut.image_y}!=={reference_dut.image_x,reference_dut.image_y})
    $fatal(1,"coordinate mismatch gain=%0d value=%0d new=%h ref=%h",gain,value,{dut.image_x,dut.image_y},{reference_dut.image_x,reference_dut.image_y});
   checked=checked+1;
  end
 end
 $display("PASS image coordinates: %0d signed pairs, all gains and saturation boundaries",checked);$finish;
end
endmodule
''')
inputs=[source,reference,stage/'src/video/output_audio_capture.v',stage/'src/video/audio_analysis_rom.v',bench]
result=dict(passed=False,source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [old,*inputs]},hardware_tested=False)
try:
 for label,command in [('compile',['iverilog','-g2012','-s','tb','-o',str(out/'tb.vvp'),*map(str,inputs)]),('run',['vvp',str(out/'tb.vvp')])]:
  with (out/(label+'.log')).open('w') as log:done=subprocess.run(command,cwd=stage,stdout=log,stderr=subprocess.STDOUT,timeout=180)
  if done.returncode:raise RuntimeError((out/(label+'.log')).read_text()[-3000:])
 log=(out/'run.log').read_text();assert 'PASS image coordinates' in log
 result.update(passed=True,compared_pairs=1048576,gains=8,complete_signed_17_bit_range=True);print(log)
finally:(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
