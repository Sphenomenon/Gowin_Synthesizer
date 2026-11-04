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
    inputs={**clear['input_sha256'],str(tb):digest(tb),str(Path(__file__).resolve()):digest(Path(__file__).resolve())}
    identity=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
    result=dict(schema=2,passed=False,identity='native-tf-runtime-stop-v2-'+identity[:16],source_set_sha256=identity,
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
    def lint(name,selected_sources=None,extra=(),expect_loop=False):
        command=['verilator','--lint-only','--timing','-Wno-fatal','-I'+str(fixture),
            '--top-module','tb_workstation_tf_runtime_stop',*extra,
            *(sources if selected_sources is None else selected_sources)]
        checked=subprocess.run(command,cwd=fixture,text=True,capture_output=True,timeout=90)
        log=checked.stdout+checked.stderr;(output/(name+'.log')).write_text(log)
        warnings=re.findall(r'%Warning-([A-Z0-9_]+):',log)
        found_loop='UNOPTFLAT' in warnings
        result[name]=dict(argv=command,returncode=checked.returncode,log_sha256=digest(output/(name+'.log')),
            warning_counts={kind:warnings.count(kind) for kind in sorted(set(warnings))},
            circular_combinational_logic=found_loop)
        if checked.returncode:raise RuntimeError(log)
        if expect_loop:
            rejected=found_loop and 'stop_cleanup_complete' in log and 'invalidate' in log
            result[name]['rejected']=rejected
            if not rejected:raise ValueError('Original stop loop escaped structural check: '+log)
        elif found_loop:raise ValueError('Circular combinational logic: '+log)
        owned_warning=re.search(r'%Warning-[A-Z0-9_]+: '+re.escape(str(ROOT/'rtl/tf_audio/workstation_tf_runtime_service.sv'))+':',log)
        if not expect_loop and owned_warning:raise ValueError('Owned TF service lint warning: '+log)
    try:
        for buffered in (0,1):
            execute(f'stop_{buffered}','tb_workstation_tf_runtime_stop',
                ['-Ptb_workstation_tf_runtime_stop.USE_COMMAND_BUFFER='+str(buffered)])
            lint(f'stop_{buffered}_structural',extra=['-GUSE_COMMAND_BUFFER='+str(buffered)])
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
        loop_anchor='    wire stop_invalidate=stop_begin && !stop_latched;'
        if source.count(loop_anchor)!=1:raise ValueError('Stop-loop negative anchor drift')
        loop_mutant=output/'workstation_tf_runtime_stop_loop_negative.sv'
        loop_mutant.write_text(source.replace(loop_anchor,
            '    wire stop_invalidate=stop_begin && !(stop_latched && stop_cleanup_complete);'))
        lint('original_loop_negative',selected_sources=[str(loop_mutant) if p==str(service) else p for p in sources],expect_loop=True)
        result['original_loop_negative']['mutant_sha256']=digest(loop_mutant)
        result['inputs_unchanged_during_run']=inputs=={p:digest(Path(p)) for p in inputs}
        if not result['inputs_unchanged_during_run']:raise ValueError('Input drift')
        result['passed']=True
    finally:(output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output.resolve())
