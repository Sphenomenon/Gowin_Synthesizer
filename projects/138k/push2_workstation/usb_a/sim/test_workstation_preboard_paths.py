#!/usr/bin/env python3
"""Target the routed M glyph-address/PCM-permission/TF-cancel failures."""
from pathlib import Path
import json
import re
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'sim/audio')]
from tools.workstation_pcm_permission_compare import normalize as compare_inverse
from tools.workstation_pcm_bitmap_permission import normalize as bitmap_inverse
from tools import workstation_brand_chunks as brand
from tools import workstation_tf_failure_path as tf
from run_ae350_pcm_bitmap_context import actual_bench
from run_ae350_pcm_window_gate import bench

class PreboardPaths(unittest.TestCase):
    def simulate(self,folder,name,tb,sources,passing=True):
        source=folder/(name+'.sv');source.write_text(tb);binary=folder/(name+'.vvp')
        r=subprocess.run(['iverilog','-g2012','-I',str(ROOT),'-s','tb','-o',str(binary),str(source),*map(str,sources)],cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        r=subprocess.run(['vvp',str(binary)],cwd=ROOT,capture_output=True,text=True,timeout=180)
        self.assertEqual(r.returncode==0,passing,r.stdout+r.stderr)
        return r.stdout

    def test_pcm_complete_owner_and_raw_four_state(self):
        source=ROOT/'rtl/audio/workstation_ae350_pcm_owner.sv';text=source.read_text()
        parent=compare_inverse(bitmap_inverse(text)).decode()
        with tempfile.TemporaryDirectory()as directory:
            folder=Path(directory);ref=folder/'reference.sv'
            ref.write_text(parent.replace('module workstation_ae350_pcm_owner','module pcm_owner_window_reference',1))
            self.assertIn('checks=52224',self.simulate(folder,'raw',actual_bench(text)[0],[source,ref]))
            self.assertIn('cycles=7190',self.simulate(folder,'sequential',bench(),[source,ref]))
            mutant=folder/'mutant.sv';needle='bitmap_usable_without_context && key_matches && !owned[tail_slot]'
            self.assertEqual(text.count(needle),1)
            mutant.write_text(text.replace(needle,'bitmap_usable_without_context && !owned[tail_slot]',1))
            self.simulate(folder,'missing_key',actual_bench(text)[0],[mutant,ref],False)

    def test_brand_same_pixels_and_stalls(self):
        source=ROOT/brand.SOURCE;parent=brand.normalize(source.read_bytes()).decode()
        with tempfile.TemporaryDirectory()as directory:
            folder=Path(directory);ref=folder/'reference.sv'
            ref.write_text(parent.replace('module workstation_contest_brand (','module brand_parent ('))
            tb='''module tb;
reg clk=0;always #5 clk=~clk;
reg enable=0;reg[10:0] x=0,y=0;wire a,b;wire[23:0] ca,cb;integer checks=0;
workstation_contest_brand newer(clk,enable,x,y,a,ca);
brand_parent older(clk,enable,x,y,b,cb);
initial begin
for(integer row=0;row<120;row=row+1)for(integer col=0;col<1920;col=col+1)begin
 @(negedge clk);x=col;y=row;enable=(col%7!=0);
 @(posedge clk);#1;if(checks>0 && {a,ca}!=={b,cb})$fatal(1,"brand mismatch");checks=checks+1;
 if(!enable)begin @(negedge clk);enable=1;@(posedge clk);#1;
  if({a,ca}!=={b,cb})$fatal(1,"brand stalled mismatch");checks=checks+1;end
end
$display("PASS brand identical pixels/stalls checks=%0d",checks);$finish;end endmodule'''
            self.assertIn('checks=263400',self.simulate(folder,'brand',tb,[source,ref]))
        layout=json.loads((ROOT/'rtl/display_data/assets/contest_brand_layout.json').read_text())
        rows=[int(x,16)for x in (ROOT/'rtl/display_data/assets/contest_brand_glyphs.memh').read_text().split()]
        chunks=[int(x,16)for x in (ROOT/'rtl/display_data/assets/contest_brand_chunks.memh').read_text().split()];expected=[]
        for line in (layout['title'],layout['principle']):
            for chunk in range(128):
                char=line[chunk//3]if chunk//3<len(line)else' '
                for y in range(32):
                    row=rows[layout['text']['characters'].index(char)*24+y]if y<24 else 0
                    expected.append((row>>(16-8*(chunk%3)))&255)
        self.assertEqual(chunks,expected)

    def test_tf_actual_fault_presence_four_state(self):
        text=(ROOT/tf.SOURCE).read_text();tf.normalize(text)
        original=text[text.index('    reg [3:0] failure_now;'):text.index('    // Cancellation needs')]
        modified=text[text.index('    wire [7:0] fault_conditions='):text.index('    wire invalidate=')]
        tb='''module tb;
localparam IDLE=0,LAUNCH=3,FILE=1,INGRESS=2,TRANSPORT=3,CONTEXT=4,EPOCH=5,PHYSICAL=6,EMPTY=7,QUIET_TIMEOUT=8,QUIET_TIMEOUT_CYCLES=10;
reg[2:0] state;reg live,native_file_error,session_applied,native_ingress_error,transport_error_i,bad_context;
reg analysis_live,runtime_44k1_i,session_rate,physical_failure_event,native_empty,failed;
reg[31:0] runtime_epoch_i,session_epoch,quiet_wait;
'''+original+modified+'''
function digit4(input integer v);case(v&3)0:digit4=0;1:digit4=1;2:digit4=1'bx;3:digit4=1'bz;endcase endfunction
integer checks=0;
initial begin
session_applied=1;runtime_44k1_i=0;session_rate=0;session_epoch=0;
for(integer active=0;active<3;active=active+1)for(integer ai=0;ai<2;ai=ai+1)
for(integer k=0;k<65536;k=k+1)begin
state=active==1?LAUNCH:IDLE;live=active==2;analysis_live=ai;
native_file_error=digit4(k);native_ingress_error=digit4(k>>2);transport_error_i=digit4(k>>4);
bad_context=digit4(k>>6);runtime_epoch_i={31'd0,digit4(k>>8)};
physical_failure_event=digit4(k>>10);native_empty=digit4(k>>12);
quiet_wait=(k>>14)==0?0:(k>>14)==1?9:(k>>14)==2?32'hxxxxxxxx:32'hzzzzzzzz;
failed=0;#1;
if(new_failure !== (failure_now!=0 && !failed))$fatal(1,"TF fault mismatch k=%d",k);
checks=checks+1;
end
$display("PASS TF actual fault presence checks=%0d",checks);$finish;end endmodule'''
        with tempfile.TemporaryDirectory()as directory:
            self.assertIn('checks=393216',self.simulate(Path(directory),'tf',tb,[]))

if __name__=='__main__':unittest.main()
