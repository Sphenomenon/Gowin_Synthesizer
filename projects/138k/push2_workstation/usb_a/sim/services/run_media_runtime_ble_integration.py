#!/usr/bin/env python3
"""Enabled physical native runtime, actual TF and staged real BLE RAM/CRC seal."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from runtime_media_integration_sources import build_sources,prepare_fixtures,verified_project,sha
from runtime_media_ble_integration_sources import prepare_bluetooth,unique_sources
ROOT=Path(__file__).resolve().parents[2]
TOP='tb_workstation_media_runtime_ble'


def compile_and_run(sources,project,output,name):
    directory=output/name
    directory.mkdir(exist_ok=False)
    argv=['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module',TOP,
          '--Mdir',str(directory/'obj'),'-I'+str(output),'-I'+str(ROOT),
          '-I'+str(project),*map(str,sources)]
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
    args=p.parse_args();project=args.project.resolve();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    support=verified_project(ROOT,project)
    fixtures=prepare_fixtures(ROOT,project,output)
    staged,ble_inputs,ble_metadata=prepare_bluetooth(ROOT,output)
    sources=build_sources(ROOT,project)+[ROOT/'rtl/services/workstation_media_preparation.sv',
        ROOT/'rtl/bluetooth/workstation_bluetooth.sv',*staged,Path(__file__).with_name('tb_workstation_media_runtime_ble.sv')]
    unique_sources(sources)
    fixtures+=ble_inputs
    extra=[Path(__file__).resolve(),Path(__file__).with_name('runtime_media_integration_sources.py'),
           Path(__file__).with_name('runtime_media_ble_integration_sources.py'),
           ROOT/'rtl/services/MEDIA_STOP_POLICY.md']
    def input_key(path):
        for prefix,base in (('fixture/',output),('prepared/',project),('repository/',ROOT.parents[3])):
            if path.is_relative_to(base):return prefix+str(path.relative_to(base))
        return 'external/'+path.name
    paths={input_key(path):path for path in sources+fixtures+extra}
    hashes={key:sha(path) for key,path in paths.items()}
    identity=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    v=dict(schema=1,passed=False,hardware_tested=False,identity='real-runtime-TF-BLE-media-offline-v1-'+identity[:16],
        source_set_sha256=identity,input_sha256=hashes,input_paths={k:str(p) for k,p in paths.items()},
        prepared_support=support,ble_preparation=ble_metadata,validation_stage='enabled-real-runtime-TF-BLE-DCS-I2S-functional-integration',
        configuration=dict(enable_ble_aggregate=True,ble_capacity_frames=128,enable_media_policy=True,tf_external_stop=True,record_depth=64,media_timeout_cycles=8000,
            tf_stop_timeout_cycles=12000,wav_fixture_frames=4096,reference48_hz=12288000,reference44_hz=16934400,compute_hz=76800000),
        limits='SD/FAT bytes and globally ordered shared DDR endpoint are fixtures. BLE radio initialization/connection and parsed recorder command dispatch are forced; recorder RAM, per-byte CRC, five seal layers, physical I2S final frame CDC and unmasked native source eligibility are real. TF ACK-return and BLE seal-commit faults exercise actual owners. No radio H5/GATT/wire/Android, DDR PHY/physical arbitration, synthesis, routed timing/CDC/PLL, board or deployment acceptance.')
    try:
        result,directory=compile_and_run(sources,project,output,'positive')
        v['positive']=result
        log=(directory/'run.log').read_text()
        lint_log=(directory/'compile.log').read_text()
        owned=('tb_workstation_media_runtime_ble.sv:', 'workstation_media_preparation.sv:', 'tf_sd_media_integration_fixture.sv:',
               'workstation_audio_clock_service.sv:', 'workstation_runtime_controlled.sv:',
               'workstation_tf_runtime_service.sv:')
        warnings=[line for line in lint_log.splitlines() if line.startswith('%Warning-')]
        own_warnings=[line for line in warnings if any(name in line for name in owned)]
        # Existing bt_acl_bridge.errors is a diagnostic output left open by
        # the frozen shared core. Keep its exact warning and staged/source hash;
        # every other pin/structural warning still rejects the joint closure.
        acl_core=output/'native_bluetooth/bt_verilog_core.v'
        acl_sha='89d47ee7ae8144e39b30743b0c1073aa9757e982fae863590ad74173252579d1'
        assert sha(acl_core)==acl_sha,'Frozen BLE ACL diagnostic allowlist source drift'
        assert acl_core.read_text().splitlines()[79].strip()=='bt_acl_bridge #(.CLK_HZ(CLK_HZ)) acl_bridge (','Frozen ACL diagnostic instance drift'
        acl_notice=re.compile(r'%Warning-PINMISSING: '+re.escape(str(acl_core))+
            r":80:38: Instance has missing pin: 'errors'$")
        inherited_acl_notices=[line for line in warnings if acl_notice.fullmatch(line)]
        assert len(inherited_acl_notices)==1,'Expected exactly one frozen ACL diagnostic output notice'
        structural=[line for line in warnings if re.match(r'%Warning-(UNOPTFLAT|MULTIDRIVEN|LATCH|ALWCOMBORDER|COMBDLY|UNDRIVEN|PINMISSING|PINNOTFOUND|MODDUP):',line) and line not in inherited_acl_notices]
        v['lint']=dict(owned_warning_count=len(own_warnings),owned_warnings=own_warnings,
            structural_warning_count=len(structural),structural_warnings=structural,
            inherited_unused_acl_error_output=inherited_acl_notices,
            inherited_acl_allowlist=dict(source_sha256=acl_sha,module='bt_acl_bridge',instance='acl_bridge',
                port='errors',direction='unused diagnostic output',warning_count=1),
            warning_counts={name:len(re.findall('^%Warning-'+name+':',lint_log,re.M)) for name in set(re.findall(r'^%Warning-(\w+):',lint_log,re.M))},
            inherited_notices='Official vendor specify/width notices and existing DSP/FFT/storage/FIFO parameter widths are retained in compile.log; zero owned and structural warnings required for the fixed positive source.')
        if args.expect_admission_bug:
            v['known_bug_reproduced']=result['returncode']!=0 and 'joint APB failure addr=1008 expected_error=0 actual=1 reason=11' in log
            assert v['known_bug_reproduced'],log
            v['validation_stage']='negative-real-runtime-active-media-admission-BUS11-reproduction'
        else:
            if own_warnings or structural:raise RuntimeError('\n'.join(own_warnings+structural))
            if result['returncode'] or 'PASS media_runtime_ble_integration:' not in log:raise RuntimeError(log[-7000:])
            v['negative_controls']=[]
            cases=[
                ('ble-stereo-swap',ROOT/'rtl/bluetooth/workstation_bluetooth.sv',
                 '.pcm_pair_i({pcm_pair_i[15:0],pcm_pair_i[31:16]})','.pcm_pair_i(pcm_pair_i)',
                 ('BLE recorder RAM differs from physical PCM','BLE sealed physical prefix metadata/CRC mismatch')),
                ('ble-eligible-frame-drop',ROOT/'rtl/bluetooth/workstation_bluetooth.sv',
                 '.pcm_valid_i(pcm_valid_i),.pcm_pair_i(',".pcm_valid_i(1'b0),.pcm_pair_i(",
                 'eligible physical BLE frame was dropped or ineligible frame was captured'),
                ('aggregate-missing-runtime-terminal',ROOT/'rtl/services/workstation_media_preparation.sv',
                 'if((runtime_terminal || runtime_finishes) && (ble_terminal || ble_finishes))begin',
                 'if(ble_terminal || ble_finishes)begin',
                 'aggregate terminal preceded both actual backend terminals'),
                ('legacy-active-media-admission',ROOT/'rtl/services/workstation_audio_clock_service.sv',
                 '(!core_request_ready_i && !prepare_media)','!core_request_ready_i',
                 'joint APB failure addr=1008 expected_error=0 actual=1 reason=11'),
                ('unconditional-admission',ROOT/'rtl/services/workstation_audio_clock_service.sv',
                 '(!core_request_ready_i && !prepare_media)',"1'b0",
                 'clock request preceded actual media stop'),
                ('ignore-final-tf-ack',ROOT/'rtl/tf_audio/workstation_tf_runtime_service.sv',
                 'memory_open_sync[1] && !control_pending_o;', 'memory_open_sync[1];',
                 'clock request preceded final TF mailbox ACK'),
            ]
            for name,path,before,after,expected in cases:
                original=path.read_text()
                assert original.count(before)==1,'Negative control exact anchor drift: '+name
                mutant=output/(name+'.sv');mutant.write_text(original.replace(before,after))
                group=[mutant if source==path else source for source in sources]
                negative,directory=compile_and_run(group,project,output,name)
                negative_log=(directory/'run.log').read_text()
                markers=expected if isinstance(expected,tuple) else (expected,)
                negative.update(name=name,mutant_sha256=sha(mutant),expected_failure=expected,
                    rejected=negative['returncode']!=0 and any(marker in negative_log for marker in markers))
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
