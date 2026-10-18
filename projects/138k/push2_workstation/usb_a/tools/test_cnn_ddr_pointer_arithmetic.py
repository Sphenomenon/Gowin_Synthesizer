#!/usr/bin/env python3
"""Bit-exact independent pointer arithmetic at every carry boundary/random words."""
from pathlib import Path
import argparse,tempfile,subprocess,json,hashlib,re
from cnn_ddr_pipeline_patch import DELAY_DMA,TF_DMA,parallel_delay_rptr,power_two_tf_ring
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);a=p.parse_args()
dma=parallel_delay_rptr((BASE/DELAY_DMA).read_text());helper=re.search(r'  function automatic \[31:0\] increment_four.*?  endfunction',dma,re.S)[0]
tf=power_two_tf_ring((BASE/TF_DMA).read_text())
ring_helper=re.search(r'    function \[31:0\] advance_ring;.*?    endfunction',tf,re.S)[0]
capacities=[32,64,128,256,65536,16777216,134217728,96,160,352,134217696]
ring_modules=[]
for capacity in capacities:
 ring_modules.append('module ring_'+str(capacity)+';\nlocalparam [31:0] AUDIO_TOTAL_BYTES='+str(capacity)+';\n'+ring_helper+'''
reg [31:0] value=32'h58964abb,offset,expected;integer checks=0;
task check(input [31:0] v);begin
 expected=(v+32)>=AUDIO_TOTAL_BYTES ? v+32-AUDIO_TOTAL_BYTES : v+32;
 if(advance_ring(v)!==expected)$fatal(1,"ring advance mismatch capacity%0d offset%0d",AUDIO_TOTAL_BYTES,v);
 checks=checks+1;
end endtask
initial begin
 check(0);check(AUDIO_TOTAL_BYTES-32);
 for(integer i=0;i<100000;i=i+1)begin
  value=(value>>1)^({32{value[0]}}&32'h80200003);
  offset=(value%(AUDIO_TOTAL_BYTES/32))*32;check(offset);
 end
 $display("PASS ring capacity%0d, %0d legal aligned offsets/wrap",AUDIO_TOTAL_BYTES,checks);
end
endmodule
''')
tb='`timescale 1ns/1ps\n'+'\n'.join(ring_modules)+'module tb;\n'+''.join('ring_'+str(c)+' r_'+str(c)+'();\n' for c in capacities)+helper+'''\nreg [31:0] value=32'h7914a057;integer checks=0;
task check(input [31:0] v);begin
 if(increment_four(v)!==v+32'd4)$fatal(1,"parallel increment mismatch%h",v);checks=checks+1;
end endtask
initial begin
 for(integer b=0;b<32;b=b+1)for(integer delta=0;delta<16;delta=delta+1)begin check((32'd1<<b)-delta);check((32'd1<<b)+delta);end
 for(integer i=0;i<1000000;i=i+1)begin value=(value>>1)^({32{value[0]}}&32'h80200003);check(value);end
 $display("PASS32bit rptr+4,%0dwords allcarryboundaries/UINT32wrap/nonaligned/random,bitexact",checks);#1;$finish;
end
endmodule'''
with tempfile.TemporaryDirectory(prefix='cnn_pointer_arithmetic_') as temp:
 t=Path(temp);(t/'tb.sv').write_text(tb);exe=t/'sim'
 c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(exe),str(t/'tb.sv')],capture_output=True,text=True);assert c.returncode==0,c.stdout+c.stderr
 v=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=30);assert v.returncode==0 and 'PASS32bit' in v.stdout and v.stdout.count('PASS ring capacity')==len(capacities),v.stdout+v.stderr
 r=dict(passed=True,hardware_tested=False,pcm_saved=False,tf_dma_sha256=hashlib.sha256(tf.encode()).hexdigest(),ring_capacities=capacities,ring_offset_checks=100002*len(capacities),delay_dma_sha256=hashlib.sha256(dma.encode()).hexdigest(),log=v.stdout.strip())
 if a.output:a.output.write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps(r,indent=2))
