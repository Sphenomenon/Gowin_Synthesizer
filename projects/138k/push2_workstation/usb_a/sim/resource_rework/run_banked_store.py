#!/usr/bin/env python3
"""Verify full 32-bit serialized words on unmodified GW5A SDPB models."""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'out/resource_banked_vendor'
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 lib=Path.home()/'.local/opt/gowin-1.9.12.03/IDE/simlib/gw5a/prim_sim.v'
 text=lib.read_text();parts=[]
 for name in ('GSR','SDPB'):
  a=text.index('module '+name+' (');b=text.index('endmodule',a)+len('endmodule');parts.append(text[a:b])
 (OUT/'vendor.v').write_text('\n'.join(parts))
 tb=r'''`timescale 1ns/1ps
module tb;
reg clk=0,rst=0,clear=0,we=0,rq=0;reg[11:0] wa=0,ra=0;reg[31:0] wd=0;
wire rv;wire[31:0] rd;
reg[31:0] expected[0:2130];reg[31:0] rng=32'h9182fc67;integer reads=0;
always #5 clk=~clk;
GSR GSR(.GSRI(1'b1));
workstation_sdp_banked #(.WORDS(2131),.ADDR_WIDTH(12)) dut(.rst_ni(rst),.clear_i(clear),
.write_clk_i(clk),.write_enable_i(we),.write_addr_i(wa),.write_data_i(wd),
.read_clk_i(clk),.read_request_i(rq),.read_addr_i(ra),.read_valid_o(rv),.read_data_o(rd));
task write_word(input integer addr,input reg[31:0] value);
 begin @(negedge clk);we=1;wa=12'(addr);wd=value;
 @(negedge clk);we=0;@(negedge clk);expected[addr]=value;end
endtask
task read_word(input integer addr);
 integer limit;
 begin @(negedge clk);rq=1;ra=12'(addr);@(negedge clk);rq=0;limit=0;
 while(!rv && limit<5)begin @(negedge clk);limit=limit+1;end
 if(!rv || rd!==expected[addr])$fatal(1,"word %0d got=%h expected=%h valid=%b",addr,rd,expected[addr],rv);
 reads=reads+1;end
endtask
initial begin
 repeat(3)@(negedge clk);rst=1;
 for(integer a=0;a<2131;a=a+1)begin
  rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};write_word(a,rng);
 end
 for(integer a=0;a<2131;a=a+1)read_word(a);
 for(integer n=0;n<3000;n=n+1)begin
  rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
  if(n%3==0)write_word(rng%2131,rng^32'h89abcdef);else read_word(rng%2131);
 end
 // Clear cancels a high-half write in flight; a subsequent complete rewrite
 // must recover both halves and the request/valid state without clearing RAM.
 @(negedge clk);we=1;wa=2048;wd=32'haaaa5555;
 @(negedge clk);we=0;clear=1;@(negedge clk);clear=0;
 write_word(2048,32'h12345678);read_word(2048);
 $display("PASS banked native SDP: %0d full-precision reads, all five banks, 511/512 boundaries, random rewrites, clear abort",reads);$finish;
end
endmodule
'''
 (OUT/'tb.sv').write_text(tb)
 sources=[ROOT/'rtl/memory/workstation_sdp.sv',ROOT/'rtl/memory/workstation_sdp_banked.sv',OUT/'vendor.v',OUT/'tb.sv']
 commands=[['iverilog','-g2012','-DWORKSTATION_SDP_VENDOR_SIM','-s','tb','-o',str(OUT/'sim')]+list(map(str,sources)),['vvp',str(OUT/'sim')]]
 logs=''
 for c in commands:
  p=subprocess.run(c,cwd=ROOT,capture_output=True,text=True);logs+=p.stdout+p.stderr
  if p.returncode:break
 (OUT/'test.log').write_text(logs);print(logs)
 result=dict(passed=p.returncode==0 and 'PASS banked' in logs,hardware_tested=False,source_sha256={str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in sources})
 (OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
 if not result['passed']:raise SystemExit(1)
if __name__=='__main__':main()
