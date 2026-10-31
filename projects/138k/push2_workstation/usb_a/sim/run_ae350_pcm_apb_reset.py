#!/usr/bin/env python3
"""Actual sealed prepared F806 bridge reset/cancellation behavioral gate."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.workstation_ae350_pcm_cdc import source_contract
BENCH=ROOT/'sim/tb_ae350_pcm_apb_reset.sv'
MUTANTS=(
 ('request_hold_corrupted','WAIT_RESPONSE: if(ack_settled==request_toggle) begin',
  "WAIT_RESPONSE: begin request_held<=0; if(ack_settled==request_toggle) begin",1,
  'held request mapping or stability'),
 ('response_payload_lost','response_held<={response_error,response_data};',
  "response_held<={response_error,32'd0};",1,'exact held response data and error'),
 ('acknowledgement_not_retired','acknowledge_toggle<=req_settled;',
  'acknowledge_toggle<=acknowledge_toggle;',1,'unexpected or duplicate command acceptance'),
 ('compute_async_reset_removed','always_ff @(posedge audio_clk or negedge reset_n)',
  'always_ff @(posedge audio_clk)',1,'asynchronous common reset revokes both sides'),
)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,msg):
 if not v:raise RuntimeError(msg)
def exercise(out,name,source,mutation=None):
 dest=out/name;dest.mkdir();data=source.read_text()
 if mutation:
  label,before,after,count,failure=mutation
  require(data.count(before)==count,'mutation anchor drift: '+label);data=data.replace(before,after)
  if label=='request_hold_corrupted':
   before='                COMPLETE: if(psel && penable) state<=IDLE;'
   require(data.count(before)==1,'request corrupt end anchor drift');data=data.replace(before,'                end\n'+before)
  local=dest/source.name;local.write_text(data)
 else:local=source
 result=subprocess.run(['iverilog','-g2012','-s','tb_ae350_pcm_apb_reset','-o',str(dest/'bench.vvp'),str(BENCH),str(local)],capture_output=True,text=True)
 (dest/'compile.log').write_text(result.stdout+result.stderr);require(not result.returncode,'APB reset bench failed to compile: '+str(dest))
 result=subprocess.run(['vvp',str(dest/'bench.vvp')],capture_output=True,text=True,timeout=60)
 (dest/'simulation.log').write_text(result.stdout+result.stderr)
 if mutation:
  require(result.returncode!=0 and 'FAIL APB CDC '+failure in result.stdout,'mutant failed outside intended boundary or survived: '+name+' '+result.stdout)
  return dict(rejected=True,source_sha256=sha(local),failure=next(x for x in result.stdout.splitlines()if 'FAIL APB CDC '+failure in x))
 match=re.search(r'PASS APB CDC reset checks=(\d+) accepted=(\d+).*',result.stdout)
 require(not result.returncode and match,'actual APB reset baseline failed: '+result.stdout)
 return dict(summary=match.group(),checks=int(match[1]),accepted=int(match[2]))
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
 policy=source_contract(ROOT);source=a.stage.resolve()/policy['prepared_APB_source']
 require(sha(source)==policy['prepared_APB_sha256'],'actual prepared bridge identity drift')
 out=a.output.resolve()if a.output else Path(tempfile.mkdtemp(prefix='gw138k-apb-reset-'))
 require(ROOT not in out.parents,'evidence must stay outside maintained source')
 out.mkdir(parents=True,exist_ok=True);require(not any(out.iterdir()),'output must be empty')
 inputs={str(q):sha(q)for q in [source,BENCH,Path(__file__)]}
 result=dict(policy='ae350-pcm-actual-prepared-apb-reset-v1',inputs=inputs,baseline=exercise(out,'baseline',source),mutants={},
  physical_CDC_accepted=False,hardware_tested=False,synthesis=False,pnr=False,release_ready=False)
 for mutation in MUTANTS:result['mutants'][mutation[0]]=exercise(out,mutation[0],source,mutation)
 require(inputs=={q:sha(q)for q in inputs},'actual sources drifted during regression')
 result['outputs']={str(q.relative_to(out)):sha(q)for q in out.rglob('*')if q.is_file()}
 (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(dict(output=str(out),checks=result['baseline']['checks'],mutants=len(result['mutants']),physical_CDC_accepted=False)))
if __name__=='__main__':main()
