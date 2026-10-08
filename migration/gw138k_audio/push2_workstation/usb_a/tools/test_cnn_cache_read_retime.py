#!/usr/bin/env python3
"""Cycle-exact cache retiming versus frozen full85 plus dwell-update equivalence."""
import json,subprocess,tempfile,argparse,re,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);args=p.parse_args();results=[]
with tempfile.TemporaryDirectory(prefix='cnn_cache_read_') as tmp:
 tmp=Path(tmp);old=tmp/'old.sv';old.write_text((BASE/'rtl/music/basic_pitch_weight_cache.sv').read_text().replace('module basic_pitch_weight_cache','module basic_pitch_weight_cache_old'))
 for words in (1,31,7488):
  exe=tmp/f'{words}.vvp'
  subprocess.run(['iverilog','-g2012','-I',str(ROOT/'rtl/music'),'-s','tb_cache_read_retime','-P',f'tb_cache_read_retime.WORDS={words}','-o',str(exe),str(ROOT/'sim/model_flash/tb_cache_read_retime.sv'),str(old),str(ROOT/'rtl/music/basic_pitch_weight_cache.sv')],check=True,capture_output=True,text=True)
  r=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=60);assert r.returncode==0 and 'PASS cache' in r.stdout,r.stdout+r.stderr;print(r.stdout.strip());results.append(dict(words=words,log=r.stdout.strip()))
 # Extract actual old/new HDL dwell blocks and compare all counters/snapshots
 # every cycle. Shorten only the common report period to exercise boundaries.
 text=(BASE/'rtl/music/basic_pitch_pcm_pipeline.sv').read_text()
 constants="\n".join(re.findall(r"localparam logic \[5:0\] S_.*?;",text,re.S))
 begin=text.index('    logic [1:0]  dwell_page;');end=text.index('    assign debug_dwell_o',begin)
 end=text.index(';',end)+1;block=text[begin:end].replace("25'd24_999_999","25'd31")
 unrolled=block.replace("            dwell_count[dwell_bucket(state)] <= dwell_count[dwell_bucket(state)] + 1'b1;",
                       "            for (integer i=0;i<8;i=i+1)\n                if (dwell_bucket(state)==i) dwell_count[i] <= dwell_count[i] + 1'b1;")
 def module(name,body):
  return f'module {name}(input clk_i,rst_ni,input [5:0] state,output [15:0] debug_dwell_o); wire run_rst_ni=rst_ni;\n'+constants+'\n'+body+'\nendmodule\n'
 dwell=tmp/'dwell.sv';dwell.write_text(module('dwell_old',block)+module('dwell_new',unrolled)+'''
module tb_dwell;
 reg clk=0,rst=0;reg [5:0] state=0;wire [15:0] a,b;always #10 clk=~clk;
 dwell_old old(.clk_i(clk),.rst_ni(rst),.state(state),.debug_dwell_o(a));
 dwell_new fresh(.clk_i(clk),.rst_ni(rst),.state(state),.debug_dwell_o(b));
 integer n,i;
 initial begin
  for(n=0;n<10000;n=n+1)begin
   @(negedge clk);rst=n%997!=0;state=$urandom%64;
   @(posedge clk);#1;
   if(a!==b || old.dwell_page!==fresh.dwell_page || old.dwell_div!==fresh.dwell_div)$fatal(1,"dwell output/cadence changed");
   for(i=0;i<8;i=i+1)if(old.dwell_count[i]!==fresh.dwell_count[i] || old.dwell_snap[i]!==fresh.dwell_snap[i])$fatal(1,"dwell count/window changed");
  end
  $display("PASS dwell HDL equivalence: all buckets, exact cycles/windows/resets, 10000 cycles");$finish;
 end
endmodule
''')
 exe=tmp/'dwell.vvp';compile_result=subprocess.run(['iverilog','-g2012','-s','tb_dwell','-o',str(exe),str(dwell)],capture_output=True,text=True);assert compile_result.returncode==0,compile_result.stderr
 r=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=30);assert r.returncode==0 and 'PASS dwell' in r.stdout,r.stdout+r.stderr;print(r.stdout.strip())
 d=dict(passed=True,cache_tests=results,dwell_update_equivalence_cycles=10000,dwell_hdl_log=r.stdout.strip(),
        original_cache_sha256=hashlib.sha256((BASE/'rtl/music/basic_pitch_weight_cache.sv').read_bytes()).hexdigest(),
        new_cache_sha256=hashlib.sha256((ROOT/'rtl/music/basic_pitch_weight_cache.sv').read_bytes()).hexdigest(),hardware_tested=False)
 if args.output:args.output.write_text(json.dumps(d,indent=2)+'\n')
 print('PASS cache/dwell retiming checks')
