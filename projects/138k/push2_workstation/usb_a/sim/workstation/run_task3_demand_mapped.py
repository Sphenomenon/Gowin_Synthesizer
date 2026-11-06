#!/usr/bin/env python3
"""Prove the selected complete96-bit demand guard on actual full-M FF-Qs."""
from pathlib import Path
import argparse,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).resolve().parent))
from run_task3_phone_identity_compare import prove
from tools import workstation_profile as profiles
from tools import workstation_task3_demand_identity_compare as demand
from tools.workstation_native_protocol_audit import protocol_netlist

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);a=p.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);candidate=a.candidate.resolve();stage=candidate/'workstation/Prj1';vg=stage/'impl/gwsynthesis/custom_138k_integration.vg'
 paths=[Path(__file__),ROOT/demand.TOOL,ROOT/'sim/workstation/run_task3_phone_identity_compare.py',ROOT/'tools/workstation_task3_phone_batch_mapped_m.py',ROOT/'tools/workstation_runtime_pcm_cdc.py',ROOT/'tools/workstation_native_protocol_audit.py',ROOT/'tools/workstation_synthesis_netlist.py',stage/demand.ENDPOINT,vg,candidate/'workstation_profile.json',candidate/'integration_inputs.json']
 sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();before={str(p):sha(p) for p in paths}
 result=dict(schema=1,passed=False,input_sha256=before,hardware_tested=False,timing_closed=False,full_CDC_accepted=False)
 try:
  artifact=profiles.verify(ROOT,candidate)
  assert artifact['profile']==demand.PROFILE
  selected=demand.evidence(stage,artifact['configuration'])
  n=protocol_netlist(vg.read_text(),mapping='synthesis');scope='u_task3_m_endpoint'
  left=[n.canonical(scope,'task3_pair_rx_payload['+str(i)+']') for i in range(96)];right=[]
  for name in ('generation','session','local_boot'):
   formal='task3_pair_'+name
   assert n.frames[scope]['ports'].get(formal)==formal+'[31:0]'
   right.extend(n.canonical(scope,formal+'['+str(i)+']') for i in range(32))
  proof=prove(n,left,right,n.canonical(scope,'demand_matches'),equality=True)
  if proof['max_serial_ALU_stages']>7:raise ValueError('selected grouping not retained in actual M mapping')
  result.update(passed=True,candidate_identity=artifact['candidate_identity'],source=selected,proof=proof,
   scope='Exact selected combinational function on all192 actual independent M FF-Q operand values,96 missing-bit controls;no endpoint-wide,CDC or physical-timing acceptance.')
 except Exception as exc:result['error']=repr(exc);raise
 finally:
  result['inputs_unchanged']=before=={str(p):sha(p) for p in paths}
  (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
 assert result['inputs_unchanged']
 print(dict(passed=True,serial_ALU_stages=proof['max_serial_ALU_stages'],logic_stages=proof['max_unit_weight_stages'],missing_bits_rejected=len(proof['missing_bit_mutants_rejected'])))
if __name__=='__main__':main()
