#!/usr/bin/env python3
"""Actual native HCI owner to held PCM session, at independent clock phases.

The locked existing integration bench supplies real close/reopen, controller
reset and CPU fences. Only an observational session consumer is appended in an
external output directory; no maintained RTL is rewritten. This is source
simulation, never physical CDC, firmware budget or board acceptance.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sim.run_workstation_hci_native import MODULES,BRIDGE,BENCH
SESSION=ROOT/'rtl/audio/workstation_ae350_pcm_session.sv'
BENCH_SHA='50311d163e2b74af740b3fee1090b25afc37711f37e764f65e5ef382f902ec2f'

MONITOR=r'''
    // Distinct 76.8MHz compute clock against the actual 50MHz HCI fixture.
    reg audio_clk=0;
    initial begin #PHASE;forever #6.510417 audio_clk=~audio_clk;end
    wire session_live;
    wire [31:0] session_epoch,session_generation;
    workstation_ae350_pcm_session audio_session(
        .reset_ni(resetn),.clk_i(audio_clk),.source_ready_i(classic_ready),
        .source_epoch_i(epoch),.source_generation_i(generation),
        .live_o(session_live),.epoch_o(session_epoch),.generation_o(session_generation));
    integer session_captures=0,session_revokes=0,ready_edges=0;
    reg was_source_ready=0;
    reg [31:0] previous_epoch=0,previous_generation=0;
    realtime source_fall=-100;
    always @(posedge clk)begin
        #0.003;
        if(resetn && classic_ready && was_source_ready &&
            (epoch!==previous_epoch || generation!==previous_generation))
            $fatal(1,"FAIL CDC source tuple changed while ready remained high");
        was_source_ready=resetn && classic_ready;
        previous_epoch=epoch;previous_generation=generation;
    end
    always @(negedge classic_ready)begin
        source_fall=$realtime;
        if(session_live)session_revokes=session_revokes+1;
        #0.003;if(session_live!==0)$fatal(1,"FAIL CDC ready fall did not asynchronously revoke live");
    end
    always @(posedge classic_ready)begin
        if(resetn && $realtime-source_fall<19.999)
            $fatal(1,"FAIL CDC ready low interval shorter than one source cycle");
    end
    always @(posedge session_live)session_captures=session_captures+1;
    always @(posedge audio_clk or negedge resetn or negedge classic_ready)begin
        if(!resetn || !classic_ready)ready_edges=0;
        else begin
            ready_edges=ready_edges+1;
            #0.003;
            if(session_live && ready_edges<4)$fatal(1,"FAIL CDC live bypassed three settling edges");
            if(session_live && (!classic_ready || session_epoch!==epoch || session_generation!==generation))
                $fatal(1,"FAIL CDC captured session differs from actual source bundle");
        end
    end
'''
COVERAGE=r'''
        check(session_captures>=3 && session_revokes>=3,"actual session open/reopen/reset capture and revoke coverage");
        $display("PASS HCI/session CDC captures=%0d revokes=%0d independent_phase=PHASE",session_captures,session_revokes);
'''
MUTANTS=(
 ('close_pre_revocation_removed','native_transport',
  '(decoder_close && close_slot!=-1 && !known_le[close_slot])',"1'b0",1,
  'FAIL CDC source tuple changed while ready remained high'),
 ('session_settling_bypassed','session','release_pipe[2]','release_pipe[0]',2,
  'FAIL CDC live bypassed three settling edges'),
 ('session_generation_lost','session','generation_o<=source_generation_i;',"generation_o<=32'd0;",1,
  'FAIL CDC captured session differs from actual source bundle'),
 ('session_async_revoke_removed','session',
  'always @(posedge clk_i or negedge reset_ni or negedge source_ready_i)\n        if(!reset_ni || !source_ready_i)live_o<=0;',
  'always @(posedge clk_i or negedge reset_ni)\n        if(!reset_ni || !source_ready_i)live_o<=0;',1,
  'FAIL CDC ready fall did not asynchronously revoke live'),
)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(ok,reason):
 if not ok:raise RuntimeError(reason)
def run(argv,where,log):
 r=subprocess.run(list(map(str,argv)),cwd=where,capture_output=True,text=True,timeout=120)
 log.write_text(r.stdout+r.stderr)
 return r

def exercise(out,name,phase,mutant=None):
 dest=out/name;dest.mkdir()
 data=BENCH.read_text()
 require(sha(BENCH)==BENCH_SHA,'actual integration bench identity drift')
 before='    always #5 clk=~clk;'
 require(data.count(before)==1,'source clock fixture anchor drift')
 data=data.replace(before,'    always #10 clk=~clk;')
 anchor='    initial begin: exercise\n'
 require(data.count(anchor)==1,'monitor insertion anchor drift')
 data=data.replace(anchor,MONITOR.replace('PHASE',str(phase))+'\n'+anchor)
 anchor='        $display("PASS native integration checks='
 require(data.count(anchor)==1,'coverage insertion anchor drift')
 data=data.replace(anchor,COVERAGE.replace('PHASE',str(phase))+'\n'+anchor)
 bench=dest/BENCH.name;bench.write_text(data)
 sources=[*MODULES,BRIDGE,SESSION]
 if mutant:
  label,module,before,after,count,failure=mutant
  source=SESSION if module=='session'else next(p for p in MODULES if p.name=='workstation_hci_'+module+'.sv')
  text=source.read_text();require(text.count(before)==count,'mutation anchor drift: '+label)
  changed=dest/source.name;changed.write_text(text.replace(before,after))
  sources=[changed if p==source else p for p in sources]
 compiled=run(['iverilog','-g2012','-s','tb_workstation_hci_native_transport','-o',dest/'bench.vvp',bench,*sources],out,dest/'compile.log')
 require(compiled.returncode==0,'HCI/session compilation failed: '+str(dest/'compile.log'))
 result=run(['vvp',dest/'bench.vvp'],out,dest/'simulation.log')
 if mutant:
  require(result.returncode!=0 and failure in result.stdout,'mutant did not fail its intended boundary: '+label+' '+result.stdout)
  return dict(rejected=True,expected_failure=failure,observed_failure=next(x for x in result.stdout.splitlines()if failure in x),source_sha256=sha(changed))
 match=re.search(r'PASS HCI/session CDC captures=(\d+) revokes=(\d+).*',result.stdout)
 prior=re.search(r'PASS native integration checks=(\d+).*',result.stdout)
 require(result.returncode==0 and match and prior,'actual HCI/session baseline failed: '+result.stdout)
 return dict(summary=match.group(),captures=int(match[1]),revokes=int(match[2]),native_checks=int(prior[1]),source_clock_ns=20,compute_clock_ns=13.020834,phase_ns=phase)

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);args=parser.parse_args()
 out=args.output.resolve()if args.output else Path(tempfile.mkdtemp(prefix='gw138k-hci-session-'))
 require(ROOT not in out.parents,'generated evidence must stay outside source')
 out.mkdir(parents=True,exist_ok=True);require(not any(out.iterdir()),'evidence output must be empty')
 inputs={str(p):sha(p)for p in [BENCH,*MODULES,BRIDGE,SESSION,Path(__file__)]}
 report=dict(policy='actual-hci-to-audio-session-cdc-source-v1',inputs=inputs,phases={},mutants={},
  actual_native_transport_and_session=True,physical_CDC_accepted=False,hardware_tested=False,
  synthesis=False,pnr=False,sram_programmed=False,flash_programmed=False,release_ready=False)
 for at,phase in enumerate([0.0,1.37,5.9]):report['phases'][str(phase)]=exercise(out,'baseline-'+str(at),phase)
 for mutant in MUTANTS:report['mutants'][mutant[0]]=exercise(out,mutant[0],1.37,mutant)
 require(inputs=={p:sha(p)for p in inputs},'maintained sources changed during simulation')
 report['outputs']={str(p.relative_to(out)):sha(p)for p in out.rglob('*')if p.is_file()}
 (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(output=str(out),phases=len(report['phases']),mutants=len(report['mutants']),hardware_tested=False)))
if __name__=='__main__':main()
