#!/usr/bin/env python3
"""Opt-in media stop protocol through real APB, REC FIFO, score and rate core."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.workstation_baselines import load_baseline
from tools import workstation_resource_timing as timing


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    baseline=load_baseline(ROOT,'resource_rework_route0')
    apb=output/'gw138k_apb_cdc.sv'
    apb.write_text(timing.apb(baseline.read_bytes('src/migration/gw138k_apb_cdc.sv').decode()))
    support=[]
    for name in ('audio_math_pkg.sv','spectrum_fft256.sv'):
        target=output/name;target.write_bytes(baseline.read_bytes('legacy/rtl/audio/'+name));support.append(target)
    sources=[ROOT/name for name in (
        'rtl/services/workstation_audio_clock_service.sv','rtl/services/workstation_controlled_services.sv',
        'rtl/audio/workstation_observation_consumers.sv','rtl/audio/audio_capture_fifo.sv',
        'rtl/input/score_led_player.sv','rtl/memory/workstation_sdp.sv',
        'rtl/audio/workstation_sample_rate_switch.sv','rtl/workstation/workstation_runtime_controlled.sv')]
    sources=support+sources+[apb,Path(__file__).with_name('tb_workstation_media_policy.sv')]
    tables=[]
    for name in ('fft_tw_re.mem','fft_tw_im.mem','fft_hann.mem'):
        rel='sim/data/audio_chain/'+name;target=output/rel;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(baseline.read_bytes(rel));tables.append(target)
    score_tb=Path(__file__).with_name('tb_workstation_media_policy_score.sv')
    paths=sources+tables+[score_tb,Path(__file__).resolve(),ROOT/'tools/workstation_baselines.py',
        ROOT/'tools/workstation_resource_timing.py',ROOT/'rtl/services/workstation_controlled_services.provenance.json',
        ROOT/'rtl/services/AUDIO_CLOCK_SERVICE_CONTRACT.md',ROOT/'rtl/services/MEDIA_STOP_POLICY.md',baseline.manifest]
    def input_key(path):
        if path.is_relative_to(output):return 'reconstructed/'+str(path.relative_to(output))
        return str(path.relative_to(ROOT))
    input_paths={input_key(path):path for path in paths}
    hashes={key:sha(path) for key,path in input_paths.items()}
    identity=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    result=dict(schema=1,passed=False,identity='native-media-policy-offline-v1-'+identity[:16],
        source_set_sha256=identity,input_sha256=hashes,input_paths={key:str(path) for key,path in input_paths.items()},hardware_tested=False,profile_changed=False,
        validation_stage='offline-real-APB-REC-score-rate-core-with-explicit-TF-completion-fixture',
        configuration=dict(enable_media_policy=True,record_depth=4,media_timeout_cycles=1000,
            held_notes_policy='preserve existing runtime state; no synthesized MIDI/PANIC'),
        limits='TF fixture tests protocol ordering and late/failure responses, not TF physical drain; no complete DSP/DCS integration, synthesis, P&R, board or long-recording/BLE acceptance')
    try:
        argv=['iverilog','-g2012','-s','tb_workstation_media_policy','-o',str(output/'policy.vvp'),*map(str,sources)]
        result['compile_argv']=argv
        process=subprocess.run(argv,cwd=output,capture_output=True,text=True,timeout=60)
        (output/'compile.log').write_text(process.stdout+process.stderr)
        if process.returncode:raise RuntimeError((output/'compile.log').read_text())
        score_sources=sources[:-1]+[score_tb]
        score_argv=['iverilog','-g2012','-s','tb_workstation_media_policy_score','-o',str(output/'score.vvp'),*map(str,score_sources)]
        process=subprocess.run(score_argv,cwd=output,capture_output=True,text=True,timeout=60)
        (output/'score_compile.log').write_text(process.stdout+process.stderr)
        if process.returncode:raise RuntimeError((output/'score_compile.log').read_text())
        process=subprocess.run(['vvp',str(output/'score.vvp')],cwd=output,capture_output=True,text=True,timeout=60)
        score_log=process.stdout+process.stderr;(output/'score_run.log').write_text(score_log)
        if process.returncode or 'ERROR:' in score_log or 'PASS media_policy_score:' not in score_log:raise RuntimeError(score_log)
        result['score']=dict(compile_argv=score_argv,log_sha256=sha(output/'score_run.log'),
            metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',score_log)})
        print(score_log,end='')
        lint_argv=['verilator','--lint-only','--timing','-Wno-fatal','--top-module','tb_workstation_media_policy',*map(str,sources)]
        process=subprocess.run(lint_argv,cwd=output,capture_output=True,text=True,timeout=60)
        lint_log=process.stdout+process.stderr;(output/'lint.log').write_text(lint_log)
        owned=('workstation_audio_clock_service.sv:', 'workstation_controlled_services.sv:',
               'workstation_observation_consumers.sv:', 'workstation_runtime_controlled.sv:')
        own_warnings=[line for line in lint_log.splitlines() if line.startswith('%Warning-') and any(n in line for n in owned)]
        result['lint']=dict(argv=lint_argv,log_sha256=sha(output/'lint.log'),owned_warning_count=len(own_warnings),
            warning_counts={name:len(re.findall('^%Warning-'+name+':',lint_log,re.M)) for name in set(re.findall(r'^%Warning-(\w+):',lint_log,re.M))},
            legacy_notices='Frozen FFT widths/timescale and unchanged FIFO depth comparison; fixture dynamic bus phase is strictly positive in all three runs')
        if process.returncode or own_warnings or '%Warning-UNOPTFLAT:' in lint_log:raise RuntimeError(lint_log)
        result['runs']=[]
        for index,phase in enumerate((0.1,3.7,21.9)):
            argv=['vvp',str(output/'policy.vvp'),'+BUS_PHASE='+str(phase)]
            process=subprocess.run(argv,cwd=output,capture_output=True,text=True,timeout=60)
            log=process.stdout+process.stderr;(output/f'run{index}.log').write_text(log)
            if process.returncode or 'ERROR:' in log or 'PASS media_policy:' not in log:raise RuntimeError(log)
            result['runs'].append(dict(phase_ns=phase,argv=argv,log_sha256=sha(output/f'run{index}.log'),
                metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',log)}))
            print(log,end='')
        # Each negative control deliberately violates one public behavior.
        # Only temporary copies are compiled; maintained sources stay unchanged.
        cases=[
            ('early-core',ROOT/'rtl/services/workstation_audio_clock_service.sv',
             'request_o<=!submitted_media_stop && submitted_operation!=2;',
             'request_o<=submitted_operation!=2;', 'tb_workstation_media_policy', sources,
             'core pulse preceded actual media stop'),
            ('seal-flush',ROOT/'rtl/audio/workstation_observation_consumers.sv',
             'recorder_reset_n<=!(record_enable && (record_failed_o || record_abort));',
             'recorder_reset_n<=!(record_enable && (record_failed_o || record_abort)); if(seal_request)recorder_reset_n<=0;',
             'tb_workstation_media_policy',sources,'read addr=009c got=00000013 expected=0000001b'),
            ('missing-cancel',ROOT/'rtl/audio/workstation_observation_consumers.sv',
             'score_cancelled_o<=1;', 'score_cancelled_o<=0;',
             'tb_workstation_media_policy_score',score_sources,'planned score stop lost explicit cancellation'),
            ('stale-media',ROOT/'rtl/services/workstation_audio_clock_service.sv',
             'else if(prepare_media && !media_stop_ready_i)operation_admission=BUS_MEDIA_NOT_READY;',
             "else if(1'b0)operation_admission=BUS_MEDIA_NOT_READY;",
             'tb_workstation_media_policy',sources,'bus error addr=1008 got=0 expected=1'),
        ]
        result['negative_controls']=[]
        for name,path,before,after,top,group,expected in cases:
            original=path.read_text()
            assert original.count(before)==1,'Negative control anchor drift '+name
            mutant=output/(name+'.sv');mutant.write_text(original.replace(before,after))
            compiled=output/(name+'.vvp')
            command=['iverilog','-g2012','-s',top,'-o',str(compiled),*[str(mutant if source==path else source) for source in group]]
            process=subprocess.run(command,cwd=output,capture_output=True,text=True,timeout=60)
            (output/(name+'-compile.log')).write_text(process.stdout+process.stderr)
            if process.returncode:raise RuntimeError(process.stdout+process.stderr)
            process=subprocess.run(['vvp',str(compiled)],cwd=output,capture_output=True,text=True,timeout=60)
            log=process.stdout+process.stderr;(output/(name+'-run.log')).write_text(log)
            rejected=process.returncode!=0 and expected in log
            result['negative_controls'].append(dict(name=name,rejected=rejected,expected=expected,
                mutant_sha256=sha(mutant),compile_argv=command,returncode=process.returncode,run_log_sha256=sha(output/(name+'-run.log'))))
            assert rejected,'Negative control escaped or failed for an unrelated reason: '+name+'\n'+log
        result['inputs_unchanged_during_run']=hashes=={key:sha(path) for key,path in input_paths.items()}
        assert result['inputs_unchanged_during_run'],'Media policy sources changed during run'
        result['passed']=True
    finally:
        (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
