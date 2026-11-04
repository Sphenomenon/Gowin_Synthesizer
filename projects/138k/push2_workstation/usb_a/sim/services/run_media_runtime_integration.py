#!/usr/bin/env python3
"""Enabled native runtime with actual TF stop, DDR/WAV transport and DCS/I2S."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from runtime_media_integration_sources import build_sources,prepare_fixtures,verified_project,input_key,sha
ROOT=Path(__file__).resolve().parents[2]
TOP='tb_workstation_media_runtime_integration'


def compile_and_run(sources,project,output,name,busy_fence_only=False):
    directory=output/name
    directory.mkdir(exist_ok=False)
    argv=['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module',TOP,
          '--Mdir',str(directory/'obj'),'-I'+str(output),'-I'+str(ROOT),
          '-I'+str(project),*map(str,sources)]
    if busy_fence_only:argv+=['-GBUSY_FENCE_ONLY=1']
    # All relative ROM/WAV inputs resolve from the fresh data fixture root.
    with (directory/'compile.log').open('w') as stream:
        process=subprocess.run(argv,cwd=output,stdout=stream,stderr=subprocess.STDOUT,timeout=300)
    if process.returncode:raise RuntimeError((directory/'compile.log').read_text()[-8000:])
    command=[str(directory/('obj/V'+TOP))]
    with (directory/'run.log').open('w') as stream:
        process=subprocess.run(command,cwd=output,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
    return dict(compile_argv=argv,compile_log_sha256=sha(directory/'compile.log'),run_argv=command,
                returncode=process.returncode,run_log_sha256=sha(directory/'run.log')),directory


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--expect-admission-bug',action='store_true')
    p.add_argument('--busy-fence-only',action='store_true')
    args=p.parse_args();project=args.project.resolve();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    support=verified_project(ROOT,project)
    sources=build_sources(ROOT,project)+[Path(__file__).with_name('tb_workstation_media_runtime_integration.sv')]
    fixtures=prepare_fixtures(ROOT,project,output)
    extra=[Path(__file__).resolve(),Path(__file__).with_name('runtime_media_integration_sources.py')]
    paths={input_key(ROOT,project,output,path):path for path in sources+fixtures+extra}
    hashes={key:sha(path) for key,path in paths.items()}
    identity=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    v=dict(schema=1,passed=False,hardware_tested=False,identity='real-runtime-TF-media-offline-v1-'+identity[:16],
        source_set_sha256=identity,input_sha256=hashes,input_paths={k:str(p) for k,p in paths.items()},
        prepared_support=support,validation_stage='enabled-real-runtime-TF-DCS-I2S-functional-integration',
        configuration=dict(enable_media_policy=True,tf_external_stop=True,record_depth=64,media_timeout_cycles=8000,
            tf_stop_timeout_cycles=12000,wav_fixture_frames=4096,reference48_hz=12288000,reference44_hz=16934400,compute_hz=76800000),
        limits='SD/FAT endpoint supplies actual WAV bytes. Shared ordered DDR fixture gives globally ordered port responses; real DDR PHY/arbiter/backpressure calibration/reset/late reordered responses are outside this test. ACK-return fault injection holds real TF acknowledgement after actual clear. Short startup/qualification; no synthesis, physical CDC/timing, board or deployment acceptance.')
    v['configuration']['busy_fence_only']=args.busy_fence_only
    if args.busy_fence_only:
        v['identity']='real-runtime-prepared-busy-offline-v1-'+identity[:16]
        v['validation_stage']='enabled-real-runtime-prepared-change-and-recovery-functional-integration'
    try:
        result,directory=compile_and_run(sources,project,output,'positive',args.busy_fence_only)
        v['positive']=result
        log=(directory/'run.log').read_text()
        lint_log=(directory/'compile.log').read_text()
        owned=('tb_workstation_media_runtime_integration.sv:', 'tf_sd_media_integration_fixture.sv:',
               'workstation_audio_clock_service.sv:', 'workstation_runtime_controlled.sv:',
               'workstation_tf_runtime_service.sv:')
        warnings=[line for line in lint_log.splitlines() if line.startswith('%Warning-')]
        own_warnings=[line for line in warnings if any(name in line for name in owned)]
        structural=[line for line in warnings if re.match(r'%Warning-(UNOPTFLAT|MULTIDRIVEN|LATCH|ALWCOMBORDER|COMBDLY|UNDRIVEN|PINMISSING|PINNOTFOUND|MODDUP):',line)]
        v['lint']=dict(owned_warning_count=len(own_warnings),owned_warnings=own_warnings,
            structural_warning_count=len(structural),structural_warnings=structural,
            warning_counts={name:len(re.findall('^%Warning-'+name+':',lint_log,re.M)) for name in set(re.findall(r'^%Warning-(\w+):',lint_log,re.M))},
            inherited_notices='Official vendor specify/width notices and existing DSP/FFT/storage/FIFO parameter widths are retained in compile.log; zero owned and structural warnings required for the fixed positive source.')
        if args.expect_admission_bug:
            v['known_bug_reproduced']=result['returncode']!=0 and 'joint APB failure addr=1008 expected_error=0 actual=1 reason=11' in log
            assert v['known_bug_reproduced'],log
            v['validation_stage']='negative-real-runtime-active-media-admission-BUS11-reproduction'
        else:
            if own_warnings or structural:raise RuntimeError('\n'.join(own_warnings+structural))
            marker='PASS media_runtime_busy_fence:' if args.busy_fence_only else 'PASS media_runtime_integration:'
            if result['returncode'] or marker not in log:raise RuntimeError(log[-7000:])
            v['negative_controls']=[]
            cases=[
                ('legacy-active-media-admission',ROOT/'rtl/services/workstation_audio_clock_service.sv',
                 '(!core_request_ready_i && !needs_media_stop)','!core_request_ready_i',
                 'joint APB failure addr=1008 expected_error=0 actual=1 reason=11'),
                ('unconditional-admission',ROOT/'rtl/services/workstation_audio_clock_service.sv',
                 '(!core_request_ready_i && !needs_media_stop)',"1'b0",
                 'clock request preceded actual media stop'),
                ('ignore-final-tf-ack',ROOT/'rtl/tf_audio/workstation_tf_runtime_service.sv',
                 'memory_open_sync[1] && !control_pending_o;', 'memory_open_sync[1];',
                 'clock request preceded final TF mailbox ACK'),
                ('retain-abandoned-preparation',ROOT/'rtl/workstation/workstation_runtime_controlled.sv',
                 'if(!media_stop_hold_i || media_stop_request_i || media_stop_failed_o ||',
                 'if(media_stop_request_i || media_stop_failed_o ||',
                 'abandoned media stop retained preparation'),
            ]
            if args.busy_fence_only:
                path=ROOT/'rtl/workstation/workstation_runtime_controlled.sv'
                cases=[
                    ('bypass-change-preparation',path,
                     'wire prepared_request=request_i && (!preparation_required || media_prepared);',
                     'wire prepared_request=request_i;',
                     'unprepared clock request escaped media fence'),
                    ('bypass-recovery-preparation',path,
                     'wire prepared_recover=recover_i && (!ENABLE_MEDIA_POLICY || (media_prepared && qualified_permit));',
                     'wire prepared_recover=recover_i;',
                     'unprepared recovery escaped media fence'),
                ]
            for name,path,before,after,expected in cases:
                original=path.read_text()
                assert original.count(before)==1,'Negative control exact anchor drift: '+name
                mutant=output/(name+'.sv');mutant.write_text(original.replace(before,after))
                group=[mutant if source==path else source for source in sources]
                negative,directory=compile_and_run(group,project,output,name,args.busy_fence_only)
                negative_log=(directory/'run.log').read_text()
                negative.update(name=name,mutant_sha256=sha(mutant),expected_failure=expected,
                    rejected=negative['returncode']!=0 and expected in negative_log)
                v['negative_controls'].append(negative)
                assert negative['rejected'],'Negative escaped or failed for an unrelated reason: '+name+'\n'+negative_log
        v['metrics']={k:int(x) for k,x in re.findall(r'(\w+)=(\d+)',log)}
        v['inputs_unchanged_during_run']=hashes=={k:sha(p) for k,p in paths.items()}
        assert v['inputs_unchanged_during_run'],'Input drift during joint regression'
        v['support_unchanged_after_run']=verified_project(ROOT,project)==support
        assert v['support_unchanged_after_run'],'Immutable support identity drift'
        v['passed']=True;print(log,end='')
    finally:
        (output/'verification.json').write_text(json.dumps(v,indent=2)+'\n')


if __name__=='__main__':main()
