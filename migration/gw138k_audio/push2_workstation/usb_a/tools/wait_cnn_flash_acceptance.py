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
def read_completed_json(path):
    try:return json.loads(path.read_text())
    except (FileNotFoundError,json.JSONDecodeError):return None

while time.monotonic()<deadline:
    status=build/'tool_result.json'
    prior=[]
    build_result=read_completed_json(status)
    if build_result is not None:
        assert build_result['exit_code']==0 and build_result['inputs_unchanged'],'build failed or source drift; no hardware IO'
    # tool_result is published before memory audit and image packaging. Wait
    # for these terminal artifacts too, rather than rejecting a valid build
    # in that short window. Malformed in-progress reports cannot authorize IO.
    ready=build_result is not None and all(read_completed_json(build/name) is not None for name in ('workstation_memory.json','flash_bundle.json'))
    for candidate in a.predecessor:
        report=candidate.resolve()/'automatic_acceptance/result.json'
        result=read_completed_json(report)
        if result is None or not result.get('finished_at'):ready=False;break
        prior.append(result)
    if ready:
        for predecessor in prior:
            assert not predecessor.get('programming_started') or predecessor.get('hardware_tested'), 'prior attempted deployment did not verify hardware; inspect rollback before continuing'
        command=[sys.executable,str(ROOT/'tools/verify_cnn_flash_workstation.py'),str(build),'--output',str(output)]
        if a.program and not any(result.get('hardware_tested') for result in prior):command.append('--program')
        elif a.program:print('A predecessor passed hardware verification; this candidate gets local gate only',flush=True)
        exit_code=subprocess.call(command,cwd=ROOT)
        refresh=ROOT/'tools/refresh_cnn_flash_status.py'
        if refresh.is_file():
            refreshed=subprocess.run([sys.executable,str(refresh)],cwd=ROOT)
            if refreshed.returncode:print('Acceptance completed; status refresh failed, read its result.json directly',file=sys.stderr,flush=True)
        raise SystemExit(exit_code)
    time.sleep(min(15,max(0,deadline-time.monotonic())))
raise SystemExit('build/predecessors not ready within timeout; no hardware IO')
