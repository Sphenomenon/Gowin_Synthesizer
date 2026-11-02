#!/usr/bin/env python3
"""Real CPU mailbox -> private HCI RAM -> physical transport session allowlist."""
import argparse,json,subprocess
from pathlib import Path
from run_workstation_hci_native import ROOT,OWNER,MODULES,BENCH,BRIDGE,sha

def run(output):
 output.mkdir(parents=True,exist_ok=False)
 inputs=[*MODULES,BENCH,BRIDGE,Path(__file__).resolve()]
 identities={str(p):sha(p) for p in inputs}
 result=dict(passed=False,stage='offline-native-session-allowlist',input_sha256=identities,
             hardware_tested=False,radio_paired=False,command_credits_preserved=True,cases={},mutations={})
 def check(name,policy,replacement=None,negative=False):
  folder=output/name;folder.mkdir()
  mods=[replacement if replacement and p.name==replacement.name else p for p in MODULES]
  commands=[['iverilog','-g2012','-s','tb_workstation_hci_native_transport',
             '-Ptb_workstation_hci_native_transport.SESSION_CONTRACT_ONLY=1',
             '-Ptb_workstation_hci_native_transport.SESSION_ONLY_PAIRING='+str(policy),
             '-o',str(folder/'bench.vvp'),str(BENCH),*map(str,mods),str(BRIDGE)],
            ['vvp',str(folder/'bench.vvp')]]
  for index,cmd in enumerate(commands):
   r=subprocess.run(cmd,capture_output=True,text=True,timeout=120);log=r.stdout+r.stderr;(folder/('compile.log' if index==0 else 'run.log')).write_text(log)
   if index==0:r.check_returncode()
  if negative:
   assert r.returncode and 'FAIL ' in log,name+' escaped';result['mutations'][name]=dict(rejected=True,result=log.strip());print('REJECTED '+name,flush=True)
  else:
   if r.returncode:raise RuntimeError(log)
   assert 'PASS native session policy='in log;result['cases'][name]=dict(passed=True,result=log.strip());print(log.strip(),flush=True)
 try:
  check('default',0);check('worker',1)
  source=OWNER/'workstation_hci_native_transport.sv';original=source.read_text()
  mutants=[('missing_sixth_header_byte','if(tx_index<6)tx_header','if(tx_index<5)tx_header',1),
           ('allow_wrong_cod_tail',"byte5==8'h24","1'b1",1),
           ('default_discovers',"(SESSION_ONLY_PAIRING && byte3==3)","(byte3==3)",0),
           ('scan_any_value',"(byte3==2 || (SESSION_ONLY_PAIRING && byte3==3))","1'b1",1),
           ('cod_wrong_length',"length==6 && byte3==8'h14","length>=5 && byte3==8'h14",1),
           ('default_reads_controller_identity',"16'h0c24,16'h1009,16'h0c19:cpu_opcode_allowed=SESSION_ONLY_PAIRING;",
             "16'h0c24,16'h1009,16'h0c19:cpu_opcode_allowed=1;",0),
           ('controller_read_has_parameters',"16'h1009,16'h0c19:cpu_command_shape=SESSION_ONLY_PAIRING && length==3;",
             "16'h1009,16'h0c19:cpu_command_shape=SESSION_ONLY_PAIRING && length>=3;",1)]
  for name,before,after,policy in mutants:
   assert original.count(before)==1,(name,'anchor drift')
   mutated=original.replace(before,after)
   if name=='default_reads_controller_identity':
    # Both independent policy gates must be removed for this negative to
    # admit a default-policy packet. Keeping either gate still rejects it.
    shape="16'h1009,16'h0c19:cpu_command_shape=SESSION_ONLY_PAIRING && length==3;"
    assert mutated.count(shape)==1,(name,'shape anchor drift')
    mutated=mutated.replace(shape,"16'h1009,16'h0c19:cpu_command_shape=length==3;")
   folder=output/(name+'-source');folder.mkdir();path=folder/source.name;path.write_text(mutated)
   check(name,policy,path,True)
  assert identities=={str(p):sha(p) for p in inputs};result['passed']=True
 finally:
  (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);run(p.parse_args().output.resolve())
