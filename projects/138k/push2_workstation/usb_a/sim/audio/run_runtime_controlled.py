#!/usr/bin/env python3
"""Real CPU/APB, USB/UART, physical PCM and context-aware native consumers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--nonzero-epoch',action='store_true')
    parser.add_argument('--inflight-score-boundary',action='store_true')
    args = parser.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    simlib = Path(os.environ.get('GOWIN_GW5A_SIMLIB', '/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/simlib/gw5a/prim_sim.v'))
    sources = sorted((project / 'legacy/rtl/audio').glob('*.sv'),
                     key=lambda path: (not path.name.endswith('_pkg.sv'), str(path)))
    sources += [project / name for name in (
        'legacy/rtl/input/midi_stream_decoder.sv', 'src/ae350/gw138k_three_event_arbiter.sv',
        'rtl/music/music_async_fifo.sv', 'rtl/audio/serial_spatial_reverb.sv',
        'rtl/memory/workstation_sdp.sv', 'rtl/memory/workstation_sdp_banked.sv')]
    for folder in ('rtl/audio/scope_vec', 'rtl/control', 'rtl/audio/delay_ddr'):
        sources += sorted((project / folder).glob('*.sv'))
    sources += [ROOT / ('rtl/audio/' + name) for name in (
        'gw138k_event_workstation.sv', 'workstation_audio_render_service.sv', 'workstation_frame_delivery.sv',
        'workstation_runtime_div147.sv',
        'workstation_rate_pitch_expression.sv', 'workstation_runtime_oscillator_engine.sv',
        'workstation_runtime_scope_vec.sv', 'workstation_runtime_render_engines.sv',
        'workstation_runtime_chorus_effect.sv', 'workstation_runtime_spatial_reverb.sv',
        'workstation_runtime_stereo_effects.sv', 'delay_ddr/workstation_runtime_delay_effect_ddr.sv',
        'delay_ddr/workstation_runtime_delay_ddr_dma.sv', 'workstation_audio_clock_monitor.sv',
        'workstation_sample_rate_switch.sv', 'workstation_audio_clock_domain.sv',
        'workstation_pcm_frame_bridge.sv', 'workstation_i2s_serializer.sv',
        'workstation_final_pcm_router.sv', 'workstation_pcm_frame_fanout.sv')]
    sources += [ROOT / 'rtl/workstation/workstation_runtime_audio.sv', simlib,
                Path(__file__).with_name('tb_workstation_runtime_controlled.sv')]
    sources += [project / ('src/migration/' + name) for name in (
        'gw138k_apb_cdc.sv', 'gw138k_stream_cdc.sv', 'gw138k_counter_cdc.sv')]
    sources += [project / 'legacy/rtl/input/uart_rx.sv']
    sources += [ROOT / name for name in (
        'rtl/services/workstation_controlled_services.sv',
        'rtl/audio/gw138k_usb_lifecycle_merge.sv',
        'rtl/audio/workstation_pcm_observation_bridge.sv',
        'rtl/audio/workstation_observation_consumers.sv',
        'rtl/audio/audio_capture_fifo.sv', 'rtl/input/score_led_player.sv',
        'rtl/workstation/workstation_runtime_controlled.sv')]
    # Prepared audio closure already contains historical capture/score? Keep
    # exactly the maintained copies in this candidate, never duplicate owners.
    sources = [path for path in sources if not (
        path.parent == project / 'legacy/rtl/audio' and path.name == 'audio_capture_fifo.sv')]
    consumer_tb = Path(__file__).with_name('tb_workstation_observation_consumers.sv')
    consumer_sources = [project / 'legacy/rtl/audio/audio_math_pkg.sv',
                        project / 'legacy/rtl/audio/spectrum_fft256.sv',
                        ROOT / 'rtl/memory/workstation_sdp.sv', ROOT / 'rtl/audio/audio_capture_fifo.sv',
                        ROOT / 'rtl/input/score_led_player.sv',
                        ROOT / 'rtl/audio/workstation_observation_consumers.sv', consumer_tb]
    lifecycle_sources = [project / 'src/ae350/gw138k_three_event_arbiter.sv',
                         ROOT / 'rtl/audio/gw138k_usb_lifecycle_merge.sv', ROOT / 'sim/tb_usb_lifecycle_merge.sv']
    inputs = list(dict.fromkeys(sources + consumer_sources + lifecycle_sources + [Path(__file__).resolve(),
        ROOT / 'rtl/audio/runtime_spatial_room_preset.svh',
        ROOT / 'rtl/services/workstation_controlled_services.provenance.json']))
    inputs += sorted((project / 'sim/data').rglob('*.mem'))
    inputs += sorted((project / 'sim/matlab/output').rglob('*.mem'))
    inputs += sorted((project / 'rtl/audio/scope_vec/data').glob('*.mem'))
    inputs += [project / 'rtl/audio/spatial_room_preset.svh']
    profile_path = project.parents[1] / 'workstation_profile.json'
    profile = json.loads(profile_path.read_text())
    inputs += [profile_path, project.parents[1] / 'integration_inputs.json']
    hashes = {str(path): digest(path) for path in inputs}
    source_identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    result = dict(schema=1, passed=False, hardware_tested=False, profile_changed=False,
                  identity='native-runtime-controlled-offline-v2-' + ('inflight-score-' if args.inflight_score_boundary else '') + ('nonzero-' if args.nonzero_epoch else '') + source_identity[:16],
                  source_set_sha256=source_identity, input_sha256=hashes,
                  prepared_reference_candidate=profile['candidate_identity'],
                  scope='Real APB/services, UART 31250/115200 with stopped-consumer drop carry, fair lifecycle merge, native DSP/DMA/official DCS/I2S, physical PCM CDC and recorder/FFT/256cue consumers; registered control/reason sources and REC/score switch boundaries',
                  limits='Source-flop timing assertions use ideal RTL clocks and do not model analog glitches or metastability. Ordered functional DDR model and coherent TF fixture; shorter clock qualification/startup; no top/profile selection, routed CDC, P&R, hardware or recording-file integration',
                  configuration=dict(reserve_zero_epoch=args.nonzero_epoch,initial_stream_epoch=1 if args.nonzero_epoch else 0,
                                     inflight_score_boundary=args.inflight_score_boundary,
                                     compute_hz=76800000,memory_hz=100000000,control_hz=50000000,
                                     default_record_depth=256,test_record_depth=16,consumer_test_record_depth=4,
                                     legacy_96bit_record_rate_hz=48000,physical_observation_bits=98))
    try:
        command = ['iverilog', '-g2012', '-s', 'tb_usb_lifecycle_merge',
                   '-o', str(output / 'lifecycle.vvp'), *map(str, lifecycle_sources)]
        result['lifecycle_compile_argv'] = command
        with (output / 'lifecycle_compile.log').open('w') as stream:
            subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=60)
        with (output / 'lifecycle_run.log').open('w') as stream:
            subprocess.run(['vvp', str(output / 'lifecycle.vvp')], cwd=project, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=60)
        lifecycle_log=(output / 'lifecycle_run.log').read_text()
        if 'PASS USB lifecycle merge:' not in lifecycle_log:
            raise ValueError('Missing stalled normal/lifecycle cancellation checks')
        result['stalled_normal_lifecycle_checks_passed']=True
        print(lifecycle_log,end='')
        command = ['iverilog', '-g2012', '-s', 'tb_workstation_observation_consumers',
                   '-o', str(output / 'consumers.vvp'), *map(str, consumer_sources)]
        result['consumer_compile_argv'] = command
        with (output / 'consumer_compile.log').open('w') as stream:
            subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=60)
        with (output / 'consumer_run.log').open('w') as stream:
            subprocess.run(['vvp', str(output / 'consumers.vvp')], cwd=project, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=60)
        consumer_log=(output / 'consumer_run.log').read_text()
        if 'PASS observation_consumers:' not in consumer_log:
            raise ValueError('Missing consumer checks')
        result['consumer_metrics']={key:int(value) for key,value in re.findall(r'(\w+)=(\d+)',consumer_log)}
        print(consumer_log,end='')
        command = ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
                   '--top-module', 'tb_workstation_runtime_controlled', '--Mdir', str(output / 'obj'),
                   '-I' + str(ROOT), '-I' + str(project), *map(str, sources)]
        if args.nonzero_epoch:
            command += ['-GRESERVE_ZERO_EPOCH=1']
        if args.inflight_score_boundary:
            command += ['-GINFLIGHT_SCORE_BOUNDARY=1']
        result['compile_argv']=command
        with (output / 'compile.log').open('w') as stream:
            subprocess.run(command,cwd=project,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=300)
        command=[str(output / 'obj/Vtb_workstation_runtime_controlled')]
        result['run_argv']=command
        with (output / 'run.log').open('w') as stream:
            subprocess.run(command,cwd=project,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=240)
        log=(output / 'run.log').read_text()
        expected_marker='PASS runtime_controlled_inflight_score:' if args.inflight_score_boundary else 'PASS runtime_controlled:'
        if expected_marker not in log:
            raise ValueError('Missing controlled integration verification')
        result['metrics']={key:int(value) for key,value in re.findall(r'(\w+)=(\d+)',log)}
        if args.inflight_score_boundary:
            # Reproduce the terminal-state race using the same real APB and
            # score path. Only this temporary copy restores two capture edges
            # after the source register. This is ideal timing, not a glitch
            # or metastability model; the expected failure is business state.
            controlled=ROOT/'rtl/workstation/workstation_runtime_controlled.sv'
            switch_bridge=('    always @(posedge compute_clk_i or posedge switch_busy_50 or negedge reset_compute_n)\n'
                '        if(!reset_compute_n)switch_busy_compute<=2\'b11;\n'
                '        else if(switch_busy_50)switch_busy_compute<=2\'b11;\n'
                '        else switch_busy_compute<={switch_busy_compute[0],1\'b0};\n')
            original=controlled.read_text()
            if original.count(switch_bridge)!=1:raise ValueError('Switch bridge negative-control anchor drift')
            mutant=output/'workstation_runtime_controlled_capture_negative.sv'
            mutant.write_text(original.replace(switch_bridge,
                '    always @(posedge compute_clk_i or negedge reset_compute_n)\n'
                '        if(!reset_compute_n)switch_busy_compute<=2\'b11;\n'
                '        else switch_busy_compute<={switch_busy_compute[0],switch_busy_50};\n'))
            negative_command=[str(mutant) if item==str(controlled) else
                              str(output/'obj-negative') if item==str(output/'obj') else item
                              for item in result['compile_argv']]+['-GCHECK_SWITCH_ASYNC=0']
            with (output/'inflight_negative_compile.log').open('w') as stream:
                subprocess.run(negative_command,cwd=project,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=300)
            with (output/'inflight_negative_run.log').open('w') as stream:
                negative=subprocess.run([str(output/'obj-negative/Vtb_workstation_runtime_controlled')],cwd=project,
                                        stdout=stream,stderr=subprocess.STDOUT,timeout=240)
            negative_log=(output/'inflight_negative_run.log').read_text()
            result['inflight_capture_negative']={
                'rejected':negative.returncode!=0 and 'in-flight zero-cue score lost explicit failure' in negative_log,
                'returncode':negative.returncode,'mutant_sha256':digest(mutant),
                'compile_argv':negative_command,
                'compile_log_sha256':digest(output/'inflight_negative_compile.log'),
                'run_log_sha256':digest(output/'inflight_negative_run.log'),'run_log':negative_log}
            if not result['inflight_capture_negative']['rejected']:raise ValueError('In-flight capture negative control escaped')
        warnings={}
        for name in re.findall(r'^%Warning-(\w+):',(output/'compile.log').read_text(),re.M):
            warnings[name]=warnings.get(name,0)+1
        result['warning_counts']=warnings
        new_paths=('workstation_runtime_controlled.sv:', 'workstation_observation_consumers.sv:',
                   'tb_workstation_runtime_controlled.sv:', 'tb_workstation_observation_consumers.sv:')
        own_warnings=[line for line in (output/'compile.log').read_text().splitlines()
                      if line.startswith('%Warning-') and any(name in line for name in new_paths)]
        result['new_composition_and_fixture_warning_count']=len(own_warnings)
        if own_warnings or 'UNOPTFLAT' in warnings:
            raise ValueError('New warning or combinational loop: '+str(own_warnings[:1]))
        result['inputs_unchanged_during_run']=hashes=={str(path):digest(path) for path in inputs}
        if not result['inputs_unchanged_during_run']:
            raise ValueError('Inputs drifted during verification')
        result['logs']={name:dict(sha256=digest(output/name),text=(output/name).read_text() if 'run' in name else None)
                        for name in ('lifecycle_compile.log','lifecycle_run.log','consumer_compile.log','consumer_run.log','compile.log','run.log')}
        result['passed']=True
        print(log,end='')
    finally:
        (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    main()
