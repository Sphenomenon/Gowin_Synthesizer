#!/usr/bin/env python3
"""Runtime-only token-qualified four-sided byte clear and DMA restart proof."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from run_workstation_tf_runtime_service import run as run_nominal

ROOT=Path(__file__).resolve().parents[2]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def run(output):
    output.mkdir(parents=True,exist_ok=False)
    provenance=json.loads((ROOT/'rtl/tf_audio/workstation_tf_runtime_storage.provenance.json').read_text())
    for item in provenance['sources'].values():
        if digest(ROOT/'rtl/tf_audio'/item['origin'])!=item['origin_sha256']:raise ValueError('Runtime storage origin drift')
    run_nominal(output/'nominal')
    nominal=json.loads((output/'nominal/verification.json').read_text())
    tb=Path(__file__).with_name('tb_workstation_tf_runtime_clear.sv')
    hashes={**nominal['input_sha256'],str(tb):digest(tb),str(Path(__file__).resolve()):digest(Path(__file__).resolve())}
    identity=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    result=dict(schema=1,passed=False,hardware_tested=False,profile_changed=False,
        identity='native-tf-runtime-clear-v1-'+identity[:16],source_set_sha256=identity,input_sha256=hashes,
        validation_stage='offline-real-maintained-runtime-storage-token-clear',nominal=nominal,origins_verified=True,
        limits='Ideal clocked protocol checks, byte-boundary SD fixture and ordered DDR model. No analog glitch/metastability model, routed CDC, full-profile preparation, synthesis, P&R, hardware or deployment acceptance.')
    try:
        sources=nominal['compile_argv'][nominal['compile_argv'].index('-o')+2:]+[str(tb)]
        for buffered in (0,1):
            command=['iverilog','-g2012','-Wall','-I',str(output/'nominal'),'-s','tb_workstation_tf_runtime_clear',
                '-Ptb_workstation_tf_runtime_clear.USE_COMMAND_BUFFER='+str(buffered),'-o',str(output/f'clear{buffered}.vvp'),*sources]
            result[f'compile_argv_{buffered}']=command
            compiled=subprocess.run(command,cwd=output/'nominal',text=True,capture_output=True,timeout=90)
            (output/f'compile{buffered}.log').write_text(compiled.stdout+compiled.stderr)
            if compiled.returncode:raise RuntimeError(compiled.stdout+compiled.stderr)
            executed=subprocess.run(['vvp',str(output/f'clear{buffered}.vvp')],cwd=output/'nominal',text=True,capture_output=True,timeout=90)
            log=executed.stdout+executed.stderr;(output/f'run{buffered}.log').write_text(log)
            if executed.returncode or 'PASS tf_runtime_clear:' not in log:raise RuntimeError(log)
            result[f'metrics_{buffered}']={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',log)}
            result[f'run_log_sha256_{buffered}']=digest(output/f'run{buffered}.log');print(log,end='')
        # A temporary adapter that claims every ACK immediately must be
        # rejected while memory is stopped. No maintained input is modified.
        path=ROOT/'rtl/tf_audio/storage/tf_audio_ddr_path.v'
        anchor='    assign runtime_clear_done_o=!NATIVE_RUNTIME_PROTOCOL || runtime_ack_sync=={5{runtime_clear_toggle_i}};'
        source=path.read_text()
        if source.count(anchor)!=1:raise ValueError('ACK bypass negative-control anchor drift')
        mutant=output/'tf_audio_ddr_path_ack_bypass_negative.v'
        mutant.write_text(source.replace(anchor,"    assign runtime_clear_done_o=1'b1;"))
        command=['iverilog','-g2012','-Wall','-I',str(output/'nominal'),'-s','tb_workstation_tf_runtime_clear',
            '-o',str(output/'negative.vvp'),*[str(mutant) if p==str(path) else p for p in sources]]
        compiled=subprocess.run(command,cwd=output/'nominal',text=True,capture_output=True,timeout=90)
        (output/'negative_compile.log').write_text(compiled.stdout+compiled.stderr)
        if compiled.returncode:raise RuntimeError(compiled.stdout+compiled.stderr)
        negative=subprocess.run(['vvp',str(output/'negative.vvp')],cwd=output/'nominal',text=True,capture_output=True,timeout=90)
        log=negative.stdout+negative.stderr;(output/'negative_run.log').write_text(log)
        expected_rejections=('paused memory released clear without local ACK',
            'source pointer nonunit jump escaped clear isolation')
        result['ack_bypass_negative']={'rejected':negative.returncode!=0 and any(reason in log for reason in expected_rejections),
            'returncode':negative.returncode,'mutant_sha256':digest(mutant),'run_log_sha256':digest(output/'negative_run.log'),'run_log':log}
        if not result['ack_bypass_negative']['rejected']:raise ValueError('ACK bypass negative control escaped: '+log)
        result['inputs_unchanged_during_run']=hashes=={p:digest(Path(p)) for p in hashes}
        if not result['inputs_unchanged_during_run']:raise ValueError('Input drift')
        result['passed']=True
    finally:(output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output.resolve())
