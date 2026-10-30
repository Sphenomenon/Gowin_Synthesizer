#!/usr/bin/env python3
"""Actual controlled runtime/owner6 queue versus permanent memory guard faults."""
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
                ROOT / 'rtl/memory/workstation_runtime_memory_guard.sv', Path(__file__).with_name('tb_workstation_runtime_memory_integration.sv')]
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
    inputs = list(dict.fromkeys(sources + [Path(__file__).resolve(),
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
    result = dict(schema=1, passed=False, hardware_tested=False, synthesis_tested=False, profile_changed=False,
        identity='native-runtime-memory-integration-offline-v1-' + source_identity[:16],
        source_set_sha256=source_identity, input_sha256=hashes,
        prepared_reference_candidate=profile['candidate_identity'],
        scope='Real APB/services, native note/parameter/session authority, default audited owner6 ring/DMA, retained functional backend queue, official DCS, physical I2S decoding and permanent guard/mute composition',
        limits='Functional ordered DDR queue, qualification input model and selected top wiring; no complete board top/USB adapter/TF service, real PLL loss, routed CDC/timing or hardware acceptance',
        configuration=dict(reserve_zero_epoch=True, initial_stream_epoch=1,
            compute_hz=76800000, memory_hz=100000000, control_hz=50000000,
            memory_phase_ns=7, ring_samples=16384, echo_samples48=9600,
            memory_guard_timeout_cycles=25, startup_mute_frames=3, pdn_hold_frames=1))
    try:
        command = ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
            '--top-module', 'tb_workstation_runtime_memory_integration', '--Mdir', str(output / 'obj'),
            '-I' + str(ROOT), '-I' + str(project), *map(str, sources)]
        result['compile_argv'] = command
        with (output / 'compile.log').open('w') as stream:
            subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=300)
        warnings = {}
        compile_log = (output / 'compile.log').read_text()
        for name in re.findall(r'^%Warning-(\w+):', compile_log, re.M):
            warnings[name] = warnings.get(name, 0) + 1
        result['warning_counts'] = warnings
        own_warnings = [line for line in compile_log.splitlines() if line.startswith('%Warning-') and
            ('tb_workstation_runtime_memory_integration.sv:' in line or 'workstation_runtime_memory_guard.sv:' in line)]
        result['new_fixture_warning_count'] = len(own_warnings)
        assert not own_warnings and 'UNOPTFLAT' not in warnings, str(own_warnings[:1])
        command = [str(output / 'obj/Vtb_workstation_runtime_memory_integration')]
        result['simulation_argv'] = command
        with (output / 'simulation.log').open('w') as stream:
            subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=300)
        log = (output / 'simulation.log').read_text()
        assert 'PASS runtime_memory_integration:' in log, log[-4000:]
        result['metrics'] = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', log)}
        result['log'] = log
        result['log_sha256'] = digest(output / 'simulation.log')
        result['compile_log_sha256'] = digest(output / 'compile.log')
        result['inputs_unchanged_during_run'] = hashes == {str(path): digest(path) for path in inputs}
        assert result['inputs_unchanged_during_run'], 'Fixture source or data drifted during verification'
        result['passed'] = True
        print(log, end='')
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')

if __name__ == '__main__':
    main()
