#!/usr/bin/env python3
"""Wait for isolated candidate and predecessor gates, then verify once without overlapping writes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('build',type=Path)
p.add_argument('--predecessor',type=Path,action='append',default=[])
p.add_argument('--program',action='store_true')
p.add_argument('--timeout-minutes',type=float,default=180)
a=p.parse_args();build=a.build.resolve()
assert a.timeout_minutes>0
output=build/'automatic_acceptance'
assert not output.exists(),'acceptance output already exists; never rerun hardware implicitly'
deadline=time.monotonic()+a.timeout_minutes*60
while time.monotonic()<deadline:
    status=build/'tool_result.json'
    prior=[]
    ready=status.exists()
    for candidate in a.predecessor:
        report=candidate.resolve()/'automatic_acceptance/result.json'
        if not report.exists():ready=False;break
        result=json.loads(report.read_text())
        if not result.get('finished_at'):ready=False;break
        prior.append(result)
    if ready:
        result=json.loads(status.read_text())
        assert result['exit_code']==0 and result['inputs_unchanged'],'build failed or source drift; no hardware IO'
        for predecessor in prior:
            assert not predecessor.get('programming_started') or predecessor.get('hardware_tested'), 'prior attempted deployment did not verify hardware; inspect rollback before continuing'
        command=[sys.executable,str(ROOT/'tools/verify_cnn_flash_workstation.py'),str(build),'--output',str(output)]
        if a.program and not any(result.get('hardware_tested') for result in prior):command.append('--program')
        elif a.program:print('A predecessor passed hardware verification; this candidate gets local gate only',flush=True)
        raise SystemExit(subprocess.call(command,cwd=ROOT))
    time.sleep(min(15,max(0,deadline-time.monotonic())))
raise SystemExit('build/predecessors not ready within timeout; no hardware IO')
