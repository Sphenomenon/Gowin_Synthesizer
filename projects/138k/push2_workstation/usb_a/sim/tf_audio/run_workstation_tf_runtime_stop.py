#!/usr/bin/env python3
"""Explicit TF stop policy with real storage/bridge/final-control ACK proof."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from run_workstation_tf_runtime_clear import run as run_clear

ROOT=Path(__file__).resolve().parents[2]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def run(output):
    output.mkdir(parents=True,exist_ok=False)
    run_clear(output/'clear')
    clear=json.loads((output/'clear/verification.json').read_text())
    nominal=clear['nominal'];fixture=output/'clear/nominal'
    tb=Path(__file__).with_name('tb_workstation_tf_runtime_stop.sv')
    inputs={**clear['input_sha256'],str(tb):digest(tb),str(Path(__file__).resolve()):digest(Path(__file__).resolve()),
        str(ROOT/'rtl/tf_audio/WORKSTATION_TF_RUNTIME_SERVICE_CONTRACT.md'):digest(ROOT/'rtl/tf_audio/WORKSTATION_TF_RUNTIME_SERVICE_CONTRACT.md')}
    identity=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
    result=dict(schema=1,passed=False,identity='native-tf-runtime-stop-v1-'+identity[:16],source_set_sha256=identity,
        input_sha256=inputs,clear_regression=clear,hardware_tested=False,profile_changed=False,
        validation_stage='offline-real-runtime-TF-stop-transaction',
        limits='Ideal clocked protocol checks, byte-boundary SD fixture and ordered DDR model. No routed CDC, full-profile synthesis/P&R, hardware or deployment acceptance. No recorder/clock orchestration integration or no-DDR streaming migration.')
    sources=nominal['compile_argv'][nominal['compile_argv'].index('-o')+2:]+[str(tb)]
    def execute(name,top,extra=(),selected_sources=None,expect_pass=True):
        command=['iverilog','-g2012','-Wall','-I',str(fixture),'-s',top,*extra,'-o',str(output/(name+'.vvp')),
            *(sources if selected_sources is None else selected_sources)]
        result[name+'_compile_argv']=command
        compiled=subprocess.run(command,cwd=fixture,text=True,capture_output=True,timeout=90)
        (output/(name+'_compile.log')).write_text(compiled.stdout+compiled.stderr)
        if compiled.returncode:raise RuntimeError(compiled.stdout+compiled.stderr)
        executed=subprocess.run(['vvp',str(output/(name+'.vvp'))],cwd=fixture,text=True,capture_output=True,timeout=90)
        log=executed.stdout+executed.stderr;(output/(name+'_run.log')).write_text(log)
        if expect_pass and (executed.returncode or 'PASS tf_runtime_stop' not in log):raise RuntimeError(log)
        result[name]={'returncode':executed.returncode,'run_log_sha256':digest(output/(name+'_run.log')),
            'metrics':{k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',log)}}
        if expect_pass:print(log,end='')
        return executed.returncode,log
    try:
        for buffered in (0,1):
            execute(f'stop_{buffered}','tb_workstation_tf_runtime_stop',
                ['-Ptb_workstation_tf_runtime_stop.USE_COMMAND_BUFFER='+str(buffered)])
        execute('disabled','tb_workstation_tf_runtime_stop_disabled')
        service=ROOT/'rtl/tf_audio/workstation_tf_runtime_service.sv'
        anchor='        memory_open_sync[1] && !control_pending_o;'
        source=service.read_text()
        if source.count(anchor)!=1:raise ValueError('Final-control-ACK negative anchor drift')
        mutant=output/'workstation_tf_runtime_stop_ack_bypass_negative.sv'
        mutant.write_text(source.replace(anchor,'        memory_open_sync[1];'))
        code,log=execute('final_ack_bypass_negative','tb_workstation_tf_runtime_stop',
            selected_sources=[str(mutant) if p==str(service) else p for p in sources],expect_pass=False)
        result['final_ack_bypass_negative'].update(rejected=code!=0 and
            ('stop done preceded final mailbox/clear/gate proof' in log or 'stop done bypassed final mailbox ACK' in log),
            mutant_sha256=digest(mutant),run_log=log)
        if not result['final_ack_bypass_negative']['rejected']:raise ValueError('Final mailbox ACK bypass escaped: '+log)
        result['inputs_unchanged_during_run']=inputs=={p:digest(Path(p)) for p in inputs}
        if not result['inputs_unchanged_during_run']:raise ValueError('Input drift')
        result['passed']=True
    finally:(output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output.resolve())
