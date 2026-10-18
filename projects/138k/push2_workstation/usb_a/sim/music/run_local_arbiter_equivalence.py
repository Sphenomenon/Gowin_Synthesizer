#!/usr/bin/env python3
"""Exhaustively compare the exact local DDR arbiter RTL to the accepted version."""
from pathlib import Path
import argparse
import json
import subprocess

ROOT=Path(__file__).resolve().parents[2]
CLIENTS=['sig','front_coeff','cqt_coeff','norm','model','cache','feature','weight','lut','nn','dp']
WRITES={'sig','norm','model','cache','feature','nn','dp'}
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',type=Path,default=ROOT/'results/clk50_fix_20261007/local_arbiter_equivalence')
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
prefix=subprocess.check_output(['git','rev-parse','--show-prefix'],cwd=ROOT,text=True).strip()
reference=subprocess.check_output(['git','show','cnn83-accepted-20261006:'+prefix+'rtl/music/basic_pitch_pcm_pipeline.sv'],cwd=ROOT,text=True)
live=(ROOT/'rtl/music/basic_pitch_pcm_pipeline.sv').read_text()

def body(text):
    start=text.index('logic read_outstanding;')
    end=text.index('    always_ff @(posedge clk_i or negedge run_rst_ni) begin',start)
    # read_outstanding is an explicit test input; keep owner/grant statements verbatim.
    return text[start:end].replace('logic read_outstanding;','',1)

def wrap(name,text):
    s=f'''module {name}(input wire [10:0] requests, input wire ready,blocked,
        input wire [31:0] salt, input wire pattern,
        output wire [10:0] client_ready, output logic mem_req_o,mem_write_o,
        output logic [31:0] mem_byte_addr_o, output logic [15:0] mem_wdata_o,
        output wire [3:0] owner);
    wire mem_ready_i=ready,read_outstanding=blocked;
'''
    for i,c in enumerate(CLIENTS):
        s+=f'    wire {c}_mem_req=requests[{i}];\n    logic {c}_mem_ready;\n'
        s+=f"    wire [31:0] {c}_mem_addr=salt ^ 32'h{(0x91847321*(i+1))&0xffffffff:08x};\n"
        if c not in {'front_coeff','cqt_coeff','lut'}:
            s+=f"    wire [15:0] {c}_mem_wdata=salt[15:0] ^ 16'h{(0x2513*(i+1))&0xffff:04x};\n"
        if c in WRITES:
            s+=f"    wire {c}_mem_write=pattern ^ 1'b{i%2};\n"
        s+=f'    assign client_ready[{i}]={c}_mem_ready;\n'
    s+=body(text)+'\n    assign owner=request_owner;\nendmodule\n'
    return s
sv=wrap('accepted_arbiter',reference)+wrap('candidate_arbiter',live)+'''
module tb;
    reg [10:0] requests=0;
    reg ready=0,blocked=0,pattern=0;
    reg [31:0] salt=32'h12345678;
    wire [10:0] cr[0:1];
    wire req[0:1],wr[0:1];
    wire [31:0] addr[0:1];
    wire [15:0] data[0:1];
    wire [3:0] owner[0:1];
    integer checks=0;
    accepted_arbiter a(requests,ready,blocked,salt,pattern,cr[0],req[0],wr[0],addr[0],data[0],owner[0]);
    candidate_arbiter b(requests,ready,blocked,salt,pattern,cr[1],req[1],wr[1],addr[1],data[1],owner[1]);
    initial begin
        for(integer p=0;p<2;p=p+1) begin
            pattern=p;
            for(integer r=0;r<2;r=r+1) begin
                ready=r;
                for(integer hold=0;hold<2;hold=hold+1) begin
                    blocked=hold;
                    for(integer bits=0;bits<2048;bits=bits+1) begin
                        requests=bits;salt={salt[30:0],salt[31]^salt[21]^salt[1]^salt[0]};
                        #1;
                        if({cr[0],req[0],wr[0],addr[0],data[0],owner[0]} !==
                           {cr[1],req[1],wr[1],addr[1],data[1],owner[1]})
                            $fatal(1,"local arbiter mismatch req=%h ready=%b blocked=%b pattern=%b",requests,ready,blocked,pattern);
                        if((cr[1] & (cr[1]-1'b1)) != 0) $fatal(1,"non-one-hot ready");
                        checks=checks+1;
                    end
                end
            end
        end
        $display("PASS local DDR arbiter %0d cases: all 2048 request masks x ready/blocked/write pattern, payload and owner exact",checks);
        $finish;
    end
endmodule
'''
source=out/'tb.sv';source.write_text(sv)
compile=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(out/'tb.vvp'),str(source)],capture_output=True,text=True,cwd=ROOT)
(out/'compile.log').write_text(compile.stdout+compile.stderr);compile.check_returncode()
run=subprocess.run(['vvp',str(out/'tb.vvp')],capture_output=True,text=True,cwd=ROOT,timeout=60)
(out/'run.log').write_text(run.stdout+run.stderr);print(run.stdout,end='');run.check_returncode()
assert 'PASS local DDR arbiter 16384 cases' in run.stdout
(out/'result.json').write_text(json.dumps({'passed':True,'cases':16384,'reference':'cnn83-accepted-20261006','checks':['every request mask','ready/backpressure','read outstanding suppression','read/write combinations','one-hot client ready','payload and owner exact']},indent=2)+'\n')
