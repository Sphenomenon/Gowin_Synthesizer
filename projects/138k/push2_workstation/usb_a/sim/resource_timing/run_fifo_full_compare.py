#!/usr/bin/env python3
"""Four-state edge comparison and all-assignment SMT proof of FIFO full-Q.

Use run_large_fifo.py alongside this for independent external data/capacity
checks; this test targets arbitrary internal state and ambiguous write select.
"""
from pathlib import Path
import hashlib,json,subprocess
import z3
import sys
u=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(u))
from tools.workstation_fifo_full_compare import SOURCE,transform
base=Path(sys.argv[1]).resolve();out=base/'equivalence';out.mkdir(parents=True,exist_ok=False)
old=u/SOURCE;new=out/'selected.sv';new.write_text(transform(old.read_text()));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();result=dict(passed=False,source_sha256={str(p):sha(p)for p in (old,new)},four_state=[],two_state=[])
(out/'reference.sv').write_text(old.read_text().replace('module music_async_fifo #(','module music_async_fifo_reference #(',1))
(out/'tb.sv').write_text('''`timescale 1ns/1ps
module tb;
parameter AB=8;localparam P=AB+1;
reg clk=0,rst=0,wv=0;reg[P-1:0]binary=0,gray=0,remote=0;wire ar,br,av,bv;wire[64:0]ad,bd;
always #5 clk=~clk;
music_async_fifo_reference #(.WIDTH(65),.ADDRESS_BITS(AB)) a(clk,rst,wv,ar,65'd0,clk,rst,av,1'b0,ad);
music_async_fifo #(.WIDTH(65),.ADDRESS_BITS(AB)) b(clk,rst,wv,br,65'd0,clk,rst,bv,1'b0,bd);
initial begin
 force a.write_binary=binary;force b.write_binary=binary;
 force a.write_gray=gray;force b.write_gray=gray;
 force a.read_gray_sync=remote;force b.read_gray_sync=remote;
 repeat(2)@(negedge clk);rst=1;
 for(integer i=0;i<20000;i=i+1)begin
  @(negedge clk);binary=$urandom;gray=$urandom;remote=$urandom;
  case(i%4)0:wv=0;1:wv=1;2:wv=1'bx;3:wv=1'bz;endcase
  if(i%7==0)binary[i%P]=1'bx;
  if(i%9==0)gray[(i/3)%P]=1'bx;
  if(i%11==0)remote[(i/7)%P]=1'bz;
  @(posedge clk);#1;
  if(a.g_large_head.full_q!==b.g_large_head.full_q)$fatal(1,"four-state full mismatch i=%0d",i);
 end
 $display("PASS exact four-state full next-Q: AB=%0d 20000 arbitrary pointer and X/Z-fire edges",AB);$finish;
end
endmodule
''')
for bits in (8,9):
 cmd=['iverilog','-g2012','-s','tb','-Ptb.AB='+str(bits),'-o',str(out/('test'+str(bits))),str(out/'reference.sv'),str(new),str(out/'tb.sv')];p=subprocess.run(cmd,capture_output=True,text=True,timeout=30);assert p.returncode==0,p.stderr
 p=subprocess.run(['vvp',str(out/('test'+str(bits)))],capture_output=True,text=True,timeout=30);(out/('fourstate'+str(bits)+'.log')).write_text(p.stdout+p.stderr);assert p.returncode==0 and 'PASS exact four-state'in p.stdout
 result['four_state'].append(dict(address_bits=bits,edges=20000,passed=True));print(p.stdout.strip(),flush=True)
 width=bits+1;binary,gray,remote=z3.BitVecs('binary gray remote',width);fire=z3.Bool('fire');nxt=binary+1;ng=z3.LShR(nxt,1)^nxt;target=remote^z3.BitVecVal(3<<(width-2),width)
 original=z3.If(fire,ng,gray)==target;selected=z3.If(fire,ng==target,gray==target);s=z3.Solver();s.add(z3.Xor(original,selected));status=s.check();assert status==z3.unsat;result['two_state'].append(dict(address_bits=bits,result=str(status),all_binary_gray_remote_and_fire_assignments=True))
 s=z3.Solver();s.add(z3.Xor(original,z3.If(fire,(ng^1)==target,gray==target)));assert s.check()==z3.sat
result.update(passed=True,negative_wrong_next_pointer_rejected=True,new_state_bits=0,new_cycles=0,hardware_tested=False);(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
