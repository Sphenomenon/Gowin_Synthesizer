#!/usr/bin/env python3
"""Prove and simulate the exact maintained 35-bit chorus CSA function.

Requires Python z3-solver, iverilog and vvp. Uses only versioned sources,
the exact old complete fixture and the public locked baseline math package.
--output must name a new directory. Does not select a build profile or board.
"""
from pathlib import Path
import argparse
import hashlib,json,re,subprocess,time,sys
import z3

USB_ROOT=Path(__file__).resolve().parents[2]
SOURCE=USB_ROOT/'rtl/audio/workstation_runtime_chorus_effect.sv'
FIXTURE=USB_ROOT/'sim/audio/fixtures/chorus_before_affine35_csa.sv'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def source_guard():
    assert sha(SOURCE)=='1cc7ddd5e00edcb5975ed64cc2eceb4707029f5add724467700fbeae30b61ea5','maintained source drift'
    assert sha(FIXTURE)=='28ef32d47d55a0d44eef8ec23fa3437cdbef647d4ca0b023f98cb184bd8ce50c','exact old complete fixture drift'
    old,new=FIXTURE.read_text(),SOURCE.read_text()
    pattern=r'  function automatic \[15:0\] rate_delay\(.*?  endfunction'
    a,b=re.search(pattern,old,re.S),re.search(pattern,new,re.S)
    assert a and b,'function anchor drift'
    assert old[:a.start()]==new[:b.start()] and old[a.end():]==new[b.end():],'change outside approved function'
    assert hashlib.sha256(a.group().encode()).hexdigest()=='305af3e1e9024a690f1da61cd432375f2ba72ad689eee3bb2e2032fb1ed48189'
    assert hashlib.sha256(b.group().encode()).hexdigest()=='1f0675e98817a8e67d022977c4f6a3ca54add40caf64215f2614bb562b970899'
    return {'source':str(SOURCE),'source_sha256':sha(SOURCE),'fixture':str(FIXTURE),'fixture_sha256':sha(FIXTURE),'outside_function_identical':True,'old_function_sha256':hashlib.sha256(a.group().encode()).hexdigest(),'new_function_sha256':hashlib.sha256(b.group().encode()).hexdigest()}

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
identity=source_guard()
old,new=FIXTURE.read_text(),SOURCE.read_text()
ROOT=args.output.resolve();ROOT.mkdir(parents=True,exist_ok=False)
(ROOT/'base.sv').write_bytes(FIXTURE.read_bytes())
(ROOT/'workstation_runtime_chorus_effect.sv').write_bytes(SOURCE.read_bytes())

t16=z3.BitVec('triangle',16);t=z3.ZeroExt(19,t16)
original=z3.Extract(15,0,z3.LShR(t*361267+134225920,28))+z3.BitVecVal(441,16)
def csa(a,b,c):return a^b^c,((a&b)|(a&c)|(b&c))<<1
def candidate(bias=134225920,drop_first=False,drop_final=False):
 s0,c0=csa(t,t<<1,t<<4)
 if drop_first:s0=(t<<1)^(t<<4)
 s1,c1=csa(t<<5,t<<8,t<<9);s2,c2=csa(t<<15,t<<16,t<<18)
 s3,c3=csa(s0,c0,s1);s4,c4=csa(c1,s2,c2)
 s5,c5=csa(s3,c3,s4);s6,c6=csa(s5,c5,c4)
 s7,c7=csa(s6,c6,z3.BitVecVal(bias,35))
 total=s7 if drop_final else s7+c7
 return z3.Extract(15,0,z3.LShR(total,28))+z3.BitVecVal(441,16)
proof={}
x,y,z=z3.BitVecs('csa_x csa_y csa_z',35)
sum_generic,carry_generic=csa(x,y,z)
solver=z3.Solver();solver.add(sum_generic+carry_generic!=x+y+z)
assert solver.check()==z3.unsat
(ROOT/'generic-three35-csa.smt2').write_text(solver.to_smt2())
proof['arbitrary_three35_csa']={'result':'unsat','arbitrary_bits':105,'modular_width':35}
for name,expr,expected in [('all16_binary',candidate(),z3.unsat),
 ('missing_shift_term',candidate(drop_first=True),z3.sat),
 ('bad_bias',candidate(bias=134217728),z3.sat),
 ('lost_final_carry',candidate(drop_final=True),z3.sat)]:
 s=z3.Solver();s.set(timeout=120000);s.add(original!=expr)
 start=time.monotonic();result=s.check();assert result==expected,(name,result)
 (ROOT/(name+'.smt2')).write_text(s.to_smt2())
 proof[name]={'result':str(result),'seconds':time.monotonic()-start}
 if result==z3.sat:proof[name]['triangle']=s.model().eval(t16,model_completion=True).as_long()
# All X/Z triangle locations: its unshifted bit enters s0 and follows XOR
# sum0->sum3->sum5->sum6->sum7. XOR cannot resolve unknown, and the final
# arithmetic + therefore makes all35 bits X, matching original multiplication.
proof['four_state_operator_argument']={'unknown_triangle':'Any X/Z follows unshifted s0/s3/s5/s6/s7 XOR path to final arithmetic; final35bit result allX as original multiplication.','unknown_rate':'Procedural if(rate44) untouched; X/Z selects unchanged48k branch.','frontend_formal_proof':False}
(ROOT/'reference.sv').write_text(old.replace('module workstation_runtime_chorus_effect #(','module chorus_reference #('))
BENCH=r'''`timescale 1ns/1ps
module tb;
 reg clk=0,rst=0,clear=0,valid=0,enabled=1,cfg=0,rate=0,history=0;
 reg signed [31:0]left=0,right=0;
 always #5 clk=~clk;
 wire [73:0]np,op;
 workstation_runtime_chorus_effect dut(.clk_i(clk),.rst_ni(rst),.clear_i(clear),.valid_i(valid),.enabled_i(enabled),.left_i(left),.right_i(right),.ready_o(np[73]),.valid_o(np[72]),.active_o(np[71]),.clip_o(np[70]),.config_ready_o(np[69]),.config_applied_o(np[68]),.history_ready_o(np[67]),.history_done_o(np[66]),.quiescent_o(np[65]),.applied_rate_44100_o(np[64]),.left_o(np[63:32]),.right_o(np[31:0]),.config_valid_i(cfg),.rate_44100_i(rate),.history_clear_i(history));
 chorus_reference ref_dut(.clk_i(clk),.rst_ni(rst),.clear_i(clear),.valid_i(valid),.enabled_i(enabled),.left_i(left),.right_i(right),.ready_o(op[73]),.valid_o(op[72]),.active_o(op[71]),.clip_o(op[70]),.config_ready_o(op[69]),.config_applied_o(op[68]),.history_ready_o(op[67]),.history_done_o(op[66]),.quiescent_o(op[65]),.applied_rate_44100_o(op[64]),.left_o(op[63:32]),.right_o(op[31:0]),.config_valid_i(cfg),.rate_44100_i(rate),.history_clear_i(history));
 `define STATE(D) {D.pointer,D.read_address,D.frames,D.state,D.gain,D.lfo,D.chorus_delay,D.gain_remainder,D.lfo_remainder,D.input_l,D.input_r,D.read_l,D.read_r,D.product_l,D.product_r,D.mixed_l,D.mixed_r}
 integer probes=0,halves=0,outputs=0,writes=0,configs=0,histories=0,clears=0,n,i,j,q,r,seed=32'h5a7832;
 integer write_address;
 reg wrote;
 reg [15:0]triangle_bits;
 reg rr;
 function automatic quad(input integer x);case(x)0:quad=0;1:quad=1;2:quad=1'bx;3:quad=1'bz;endcase endfunction
 task probe(input [15:0]a,input r);
  reg[15:0]x,y;integer expected;
  begin
   x=dut.rate_delay(a,r);y=ref_dut.rate_delay(a,r);
   if(x!==y)$fatal(1,"TAP_MISMATCH triangle=%h rate=%b new=%h ref=%h",a,r,x,y);
   if((^a)!==1'bx)begin
    if(r===1'b1)expected=441+(441*a+163840)/327680;
    else expected=480+(3*a)/2048;
    if(x!==16'(expected))$fatal(1,"INTEGER_RULE_MISMATCH");
   end
   probes=probes+1;
  end
 endtask
 always @(clk)begin
  wrote=0;
  if(clk)begin
   wrote=rst && !dut.local_history_clear && dut.state==3;write_address=dut.pointer;
   if(rst && dut.config_accept)configs=configs+1;
   if(rst && dut.history_accept)histories=histories+1;
   if(rst && clear)clears=clears+1;
  end
  #1;
  if(np!==op || `STATE(dut)!==`STATE(ref_dut))$fatal(1,"COMPLETE_CHORUS_MISMATCH time=%0t",$time);
  if(wrote)begin
   if({dut.memory_l[write_address],dut.memory_r[write_address]}!=={ref_dut.memory_l[write_address],ref_dut.memory_r[write_address]})$fatal(1,"CHORUS_WRITE_MISMATCH");
   writes=writes+1;
  end
  if(clk && np[72])outputs=outputs+1;
  halves=halves+1;
 end
 initial begin
  for(i=0;i<65536;i=i+1)for(r=0;r<4;r=r+1)probe(16'(i),quad(r));
  for(i=0;i<16;i=i+1)for(j=0;j<16;j=j+1)for(q=0;q<16;q=q+1)for(r=0;r<4;r=r+1)begin
   triangle_bits=$random(seed);triangle_bits[i]=quad(q%4);triangle_bits[j]=quad(q/4);probe(triangle_bits,quad(r));
  end
  for(i=0;i<16;i=i+1)for(r=0;r<4;r=r+1)begin
   triangle_bits=$random(seed);triangle_bits[i]=1'bx;probe(triangle_bits,quad(r));triangle_bits[i]=1'bz;probe(triangle_bits,quad(r));
  end
  for(r=0;r<4;r=r+1)begin probe('x,quad(r));probe('z,quad(r));end
  repeat(3)@(negedge clk);rst=1;
  for(n=0;n<50000;n=n+1)begin
   @(negedge clk);valid=n%7!=0;enabled=$random(seed);left=$random(seed);right=$random(seed);
   cfg=n%13==0;rate=(n/119)%2;history=n%31==0;clear=n%7001==0;rst=n%17003!=0;
   // Deliberate idle windows let config/history reach the actual quiescent handshake.
   if(n%1000<10)begin valid=0;cfg=1;history=1;end
   else if(n%1000<16)begin valid=0;cfg=0;history=1;end
   if(n%811==0)left[n%32]=1'bx;
   if(n%1201==0)right[n%32]=1'bz;
  end
  @(negedge clk);#2;
  for(i=0;i<1024;i=i+1)if({dut.memory_l[i],dut.memory_r[i]}!=={ref_dut.memory_l[i],ref_dut.memory_r[i]})$fatal(1,"CHORUS_BANK_MISMATCH");
  if(probes!=278664 || outputs<5000 || writes<5000 || configs<10 || histories<5 || clears<5)$fatal(1,"COVERAGE_GAP probes=%0d outputs=%0d writes=%0d configs=%0d histories=%0d clears=%0d",probes,outputs,writes,configs,histories,clears);
  $display("PASS chorus probes=%0d half_clocks=%0d outputs=%0d writes=%0d configs=%0d histories=%0d clears=%0d complete_bank_words=2048",probes,halves,outputs,writes,configs,histories,clears);$finish;
 end
 `undef STATE
endmodule
'''
(ROOT/'tb.sv').write_text(BENCH)
maintenance=USB_ROOT
sys.path.insert(0,str(maintenance))
from tools.workstation_baselines import load_baseline
math=ROOT/'audio_math_pkg.sv'
baseline=load_baseline(maintenance,'resource_rework_route0')
math.write_bytes(baseline.read_bytes('legacy/rtl/audio/audio_math_pkg.sv'))
assert sha(math)=='f07fab099e112b18d9fc142eeb701139cae62be79e2f25596e134aaecea88f3d'
input_files=[SOURCE,FIXTURE,Path(__file__).resolve(),maintenance/'tools/workstation_baselines.py',
             maintenance/'baselines/index.json',baseline.manifest,
             baseline.repository/baseline.descriptor['files']['legacy/rtl/audio/audio_math_pkg.sv']['source']]
input_sha256={str(p):sha(p)for p in input_files}
mutations={'missing_shift_term':('s0=t^(t<<1)^(t<<4);','s0=(t<<1)^(t<<4);'),
 'bad_bias':("35'd134225920","35'd134217728"),
 'lost_final_carry':('rounded_phase44=s7+c7;','rounded_phase44=s7;')}
sources={'actual':ROOT/'workstation_runtime_chorus_effect.sv'}
for name,(before,after)in mutations.items():
 assert new.count(before)==(3 if name=='bad_bias' else 1),(name,new.count(before))
 p=ROOT/(name+'.sv');p.write_text(new.replace(before,after));sources[name]=p
cases={}
for name,source in sources.items():
 binary=ROOT/(name+'.vvp')
 argv=['iverilog','-g2012','-s','tb','-o',str(binary),str(math),str(source),str(ROOT/'reference.sv'),str(ROOT/'tb.sv')]
 run=subprocess.run(argv,capture_output=True,text=True);(ROOT/(name+'-compile.log')).write_text(run.stdout+run.stderr)
 assert run.returncode==0,(name,run.stderr)
 start=time.monotonic();run=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=180)
 log=ROOT/(name+'.log');log.write_text(run.stdout+run.stderr)
 assert (run.returncode==0)==(name=='actual'),(name,log.read_text()[-2000:])
 if name!='actual':assert 'TAP_MISMATCH' in run.stdout,(name,'unintended failure')
 cases[name]={'returncode':run.returncode,'seconds':time.monotonic()-start,'summary':run.stdout[-1500:],'source_sha256':sha(source),'log_sha256':sha(log)}
 print(name,run.returncode,flush=True)
assert source_guard()==identity,'maintained verification inputs changed during run'
assert {str(p):sha(p)for p in input_files}==input_sha256,'verification dependency changed during run'
record={'schema':1,'status':'passed','stage':'maintained_chorus_affine35_csa_regression','source_implementation':True,'source_identity':identity,'runner_sha256':sha(Path(__file__)),'input_sha256':input_sha256,'binary_and_negative_proofs':proof,'actual_complete_module_simulation':cases,'math_pkg_sha256':sha(math),'scope':'Independent hand translated arithmetic and IEEE operator argument bound to complete source hashes; actual whole-module twin on selected clocks/inputs. No source frontend or whole temporal formal proof.','synthesized':False,'resource_improvement_measured':False,'routed_timing_verified':False,'hardware_tested':False,'artifacts_sha256':{p.name:sha(p)for p in sorted(ROOT.iterdir())if p.is_file()and p.suffix!='.vvp'}}
(ROOT/'verification.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'status':'passed','verification_sha256':sha(ROOT/'verification.json')}))
