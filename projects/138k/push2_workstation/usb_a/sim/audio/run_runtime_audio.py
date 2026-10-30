#!/usr/bin/env python3
"""Actual dual-rate DSP, official DCS, final PCM bridge/I2S native composition."""
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
    parser.add_argument('--production-startup', action='store_true')
    parser.add_argument('--nonzero-epoch', action='store_true', help='Explicit stream-owner v1.1 epoch policy; initial1, wrap skips0')
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
        'workstation_rate_pitch_expression.sv', 'workstation_runtime_oscillator_engine.sv',
        'workstation_runtime_scope_vec.sv', 'workstation_runtime_render_engines.sv',
        'workstation_runtime_chorus_effect.sv', 'workstation_runtime_spatial_reverb.sv',
        'workstation_runtime_stereo_effects.sv', 'delay_ddr/workstation_runtime_delay_effect_ddr.sv',
        'delay_ddr/workstation_runtime_delay_ddr_dma.sv', 'workstation_audio_clock_monitor.sv',
        'workstation_sample_rate_switch.sv', 'workstation_audio_clock_domain.sv',
        'workstation_pcm_frame_bridge.sv', 'workstation_i2s_serializer.sv',
        'workstation_final_pcm_router.sv', 'workstation_pcm_frame_fanout.sv')]
    sources += [ROOT / 'rtl/workstation/workstation_runtime_audio.sv', simlib,
                Path(__file__).with_name('tb_workstation_runtime_audio.sv')]
    inputs = sources + [Path(__file__).resolve(), ROOT / 'rtl/audio/runtime_spatial_room_preset.svh']
    inputs += sorted((project / 'sim/data').rglob('*.mem'))
    inputs += sorted((project / 'sim/matlab/output').rglob('*.mem'))
    inputs += sorted((project / 'rtl/audio/scope_vec/data').glob('*.mem'))
    inputs += [project / 'rtl/audio/spatial_room_preset.svh']
    profile_path = project.parents[1] / 'workstation_profile.json'
    profile = json.loads(profile_path.read_text())
    inputs += [profile_path, project.parents[1] / 'integration_inputs.json']
    hashes = {str(path): digest(path) for path in inputs}
    source_set_sha256 = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    result = dict(schema=1, passed=False, hardware_tested=False, profile_changed=False,
                  scope='Opt-in native audio composition; actual DSP, clock transaction/official DCS, owner6 DMA, final PCM, bridge, physical I2S and taps',
                  limits='Ordered DDR functional model; coherent TF packet fixture; external policy authorization only; no CPU command integration, top/profile selection, P&R or hardware acceptance',
                  production_startup=args.production_startup, reserve_zero_epoch=args.nonzero_epoch,
                  initial_stream_epoch=1 if args.nonzero_epoch else 0, project=str(project), input_sha256=hashes,
                  prepared_reference_candidate=profile['candidate_identity'],
                  prepared_profile=profile['profile'], prepared_profile_revision=profile['revision'],
                  source_set_sha256=source_set_sha256,
                  composition_identity='native-runtime-audio-offline-v1-' + ('nonzero-' if args.nonzero_epoch else '') + source_set_sha256[:16],
                  validation_stage='offline-physical-interface-simulation', bitstream_sha256=None,
                  compute_clock_hz=76800000, memory_clock_hz=100000000, switch_state_timeout_50mhz_cycles=2000000)
    try:
        command = ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
                   '--top-module', 'tb_workstation_runtime_audio', '--Mdir', str(output / 'obj'),
                   '-I' + str(ROOT), '-I' + str(project), *map(str, sources)]
        if args.production_startup:
            command += ['-GSTARTUP_FRAMES=1028', '-GPDN_FRAMES=4', '-GPRODUCTION_CLOCKS=1']
        if args.nonzero_epoch:
            command += ['-GRESERVE_ZERO_EPOCH=1']
        result['compile_argv'] = command
        with (output / 'compile.log').open('w') as stream:
            subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=300)
        run_command = [str(output / 'obj/Vtb_workstation_runtime_audio')]
        if args.production_startup:
            run_command += ['+STARTUP_ONLY']
        result['run_argv'] = run_command
        with (output / 'run.log').open('w') as stream:
            subprocess.run(run_command, cwd=project, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=240)
        log = (output / 'run.log').read_text()
        if 'PASS runtime_audio:' not in log:
            raise ValueError('Missing integration verification')
        result['log'] = log
        result['metrics'] = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', log)}
        warnings = {}
        for name in re.findall(r'^%Warning-(\w+):', (output / 'compile.log').read_text(), re.M):
            warnings[name] = warnings.get(name, 0) + 1
        result['warning_counts'] = warnings
        own_warnings = [line for line in (output / 'compile.log').read_text().splitlines()
                        if line.startswith('%Warning-') and any(name in line for name in
                            ('/rtl/workstation/workstation_runtime_audio.sv:', '/sim/audio/tb_workstation_runtime_audio.sv:'))]
        result['composition_and_fixture_warning_count'] = len(own_warnings)
        if own_warnings:
            raise ValueError('New composition/fixture warning: ' + own_warnings[0])
        if 'UNOPTFLAT' in warnings:
            raise ValueError('Combinational loop')
        result['inputs_unchanged_during_run'] = hashes == {str(path): digest(path) for path in inputs}
        if not result['inputs_unchanged_during_run']:
            raise ValueError('Source drift during verification')
        result['compile_log_sha256'] = digest(output / 'compile.log')
        result['run_log_sha256'] = digest(output / 'run.log')
        result['passed'] = True
        print(log, end='')
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
