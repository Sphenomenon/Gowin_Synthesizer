#!/usr/bin/env python3
"""Correlate two actual-owner interfaces without resetting either owner."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    output=parser.parse_args().output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    rtl=ROOT/'rtl/services/workstation_media_preparation.sv'
    tb=Path(__file__).with_name('tb_workstation_media_preparation.sv')
    inputs={str(p):sha(p) for p in (rtl,tb,Path(__file__).resolve(),
        ROOT/'rtl/services/MEDIA_PREPARATION_CONTRACT.md')}
    result=dict(schema=1,passed=False,input_sha256=inputs,
        identity='native-media-preparation-v1-'+hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:16],
        scope='50MHz result correlation and held lifecycle; backend request/completion fixtures',
        hardware_tested=False,backend_protocols_verified_here=False,full_workstation_verified=False)
    try:
        def run(name,source):
            command=['iverilog','-g2012','-Wall','-s','tb_workstation_media_preparation','-o',str(output/(name+'.vvp')),str(source),str(tb)]
            compiled=subprocess.run(command,capture_output=True,text=True,timeout=30)
            (output/(name+'_compile.log')).write_text(compiled.stdout+compiled.stderr)
            if compiled.returncode:raise RuntimeError(compiled.stderr)
            process=subprocess.run(['vvp',str(output/(name+'.vvp'))],capture_output=True,text=True,timeout=30)
            log=process.stdout+process.stderr;(output/(name+'_run.log')).write_text(log)
            return process.returncode,log,command
        code,log,command=run('positive',rtl)
        if code or 'PASS media_preparation:' not in log:raise RuntimeError(log)
        result.update(command=command,metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',log)})
        print(log,end='')
        anchor='        assign done_o=done,failed_o=failed,failure_code_o=failure_code;'
        source=rtl.read_text()
        if source.count(anchor)!=1:raise ValueError('Completion negative-control anchor drift')
        mutant=output/'workstation_media_preparation_early_done_negative.sv'
        mutant.write_text(source.replace(anchor,'        assign done_o=runtime_done_i,failed_o=failed,failure_code_o=failure_code;'))
        code,log,command=run('negative',mutant)
        result['negative']=dict(rejected=code!=0 and 'premature aggregate completion' in log,
            returncode=code,command=command,mutant_sha256=sha(mutant),log_sha256=sha(output/'negative_run.log'))
        if not result['negative']['rejected']:raise ValueError('Early completion escaped: '+log)
        stale=source.replace('!runtime_request && (runtime_done_i || runtime_failed_i)',
                             '(runtime_done_i || runtime_failed_i)').replace(
                             '!ble_request && (ble_done_i || ble_failed_i)',
                             '(ble_done_i || ble_failed_i)')
        if stale==source:raise ValueError('Stale result negative-control anchor drift')
        mutant=output/'workstation_media_preparation_stale_negative.sv';mutant.write_text(stale)
        code,log,command=run('stale_negative',mutant)
        result['stale_negative']=dict(rejected=code!=0 and 'old completion satisfied new request' in log,
            returncode=code,command=command,mutant_sha256=sha(mutant),log_sha256=sha(output/'stale_negative_run.log'))
        if not result['stale_negative']['rejected']:raise ValueError('Stale completion escaped: '+log)
        if inputs!={p:sha(Path(p)) for p in inputs}:raise ValueError('Source drift')
        result['passed']=True
    finally:
        (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
