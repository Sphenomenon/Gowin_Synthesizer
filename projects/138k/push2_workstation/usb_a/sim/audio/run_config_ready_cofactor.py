#!/usr/bin/env python3
"""Run exact-source, binary, complete M/W four-state and M/W/legacy temporal checks."""
from pathlib import Path
import argparse,subprocess,sys,json,hashlib
P=Path(__file__).resolve().parent
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--project',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
commands=[['prove_config_ready_cofactor.py','--output',str(out/'proof')],
 ['run_config_ready_four_state.py','--project',str(a.project.resolve()),'--output',str(out/'four-state')],
 ['run_event_config_contract.py','--project',str(a.project.resolve()),'--output',str(out/'full-module'),'--config-ready-miter']]
for cmd in commands:subprocess.run([sys.executable,str(P/cmd[0]),*cmd[1:]],check=True)
checks=[out/n/'verification.json'for n in ('proof','four-state','full-module')]
assert all(json.loads(p.read_text())['passed']for p in checks)
result={'schema':1,'passed':True,'stage':'public_config_ready_cofactor_actual_source_and_full_module_verification','hardware_accepted':False,'physical_timing_verified':False,'resource_saving_claimed':False,'checks':{str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in checks}}
(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS maintained public configuration-ready cofactor')
