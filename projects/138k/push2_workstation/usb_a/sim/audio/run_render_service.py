#!/usr/bin/env python3
"""Compare native request-driven 48k render with actual prepared legacy audio."""

import argparse
import hashlib
import json
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
    parser.add_argument('--phases', type=int, default=1600)
    parser.add_argument('--runtime-engines', action='store_true', help='Opt in native pitch/osc/vector at 48 kHz; effects remain fixed-rate')
    args = parser.parse_args()
    if not 1 <= args.phases <= 1600:
        parser.error('--phases must be 1..1600')
    project, output = args.project.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    reference = project / 'src/ae350/gw138k_event_workstation.sv'
    original = reference.read_text()
    if original.count('module gw138k_event_workstation #(') != 1:
        raise ValueError('Prepared reference module declaration drifted')
    renamed = output / 'prepared_reference_event_workstation.sv'
    renamed.write_text(original.replace('module gw138k_event_workstation #(',
                                       'module prepared_reference_event_workstation #('))
    sources = sorted((project / 'legacy/rtl/audio').glob('*.sv'),
                     key=lambda path: (not path.name.endswith('_pkg.sv'), str(path)))
    sources += [project / name for name in (
        'legacy/rtl/input/midi_stream_decoder.sv', 'src/ae350/gw138k_three_event_arbiter.sv',
        'rtl/music/music_async_fifo.sv', 'rtl/audio/serial_spatial_reverb.sv',
        'rtl/memory/workstation_sdp.sv', 'rtl/memory/workstation_sdp_banked.sv',
        'rtl/audio/workstation_frame_delivery.sv')]
    for folder in ('rtl/audio/scope_vec', 'rtl/control', 'rtl/audio/delay_ddr'):
        sources += sorted((project / folder).glob('*.sv'))
    sources += [ROOT / 'rtl/audio/gw138k_event_workstation.sv',
                ROOT / 'rtl/audio/workstation_audio_render_service.sv', renamed,
                Path(__file__).with_name('tb_workstation_audio_render_service.sv')]
    if args.runtime_engines:
        sources += [ROOT / ('rtl/audio/' + name) for name in (
            'workstation_rate_pitch_expression.sv', 'workstation_runtime_oscillator_engine.sv',
            'workstation_runtime_scope_vec.sv', 'workstation_runtime_render_engines.sv')]
    inputs = [*sources, reference, Path(__file__).resolve()]
    inputs += sorted((project / 'sim/data').rglob('*.mem'))
    inputs += sorted((project / 'sim/matlab/output').rglob('*.mem'))
    inputs += [project / 'rtl/audio/spatial_room_preset.svh']
    hashes = {str(path): digest(path) for path in inputs}
    profile_path = project.parents[1] / 'workstation_profile.json'
    profile = json.loads(profile_path.read_text()) if profile_path.exists() else {}
    result = dict(schema=1, scope='Independent 48k synth/vector render service; no source selection or final master volume',
                  passed=False, hardware_tested=False, profile_changed=False, runtime_engines=args.runtime_engines,
                  prepared_reference_candidate=profile.get('candidate_identity'),
                  prepared_reference_sha256=digest(reference),
                  reference_adaptation='Only the single module declaration is renamed for parallel test instantiation',
                  project=str(project), input_sha256=hashes, phases_per_source_per_cancel_type=args.phases,
                  test_echo_samples=32, production_default_echo_samples=9600,
                  delay_storage_model='Ordered memory-side FIFO/history/flush marker; not a physical DDR timing model')
    try:
        compile_command = ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
                           '--top-module', 'tb_workstation_audio_render_service',
                           '--Mdir', str(output / 'obj'), '-I' + str(project), *map(str, sources)]
        if args.runtime_engines:
            compile_command += ['-GRUNTIME_ENGINES=1', '-DRUNTIME_RENDER_ENGINES_TEST']
        result['compile_argv'] = compile_command
        with (output / 'compile.log').open('w') as stream:
            subprocess.run(compile_command, cwd=project, stdout=stream, stderr=subprocess.STDOUT,
                           check=True, timeout=300)
        run_command = [str(output / 'obj/Vtb_workstation_audio_render_service'), f'+PHASES={args.phases}']
        result['run_argv'] = run_command
        with (output / 'run.log').open('w') as stream:
            subprocess.run(run_command, cwd=project, stdout=stream, stderr=subprocess.STDOUT,
                           check=True, timeout=300)
        log = (output / 'run.log').read_text()
        matches = [line for line in log.splitlines() if line.startswith('PASS audio_render_service48:')]
        if len(matches) != 1:
            raise ValueError('Missing render service verification')
        result['metrics'] = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', matches[0])}
        result['per_source_timbre_metrics'] = [
            {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', line)}
            for line in log.splitlines() if line.startswith('NORMAL ')]
        result['compile_warning_counts'] = {}
        for name in re.findall(r'^%Warning-(\w+):', (output / 'compile.log').read_text(), re.M):
            result['compile_warning_counts'][name] = result['compile_warning_counts'].get(name, 0) + 1
        if 'UNOPTFLAT' in result['compile_warning_counts']:
            raise ValueError('Combinational admission loop')
        result['run_log_sha256'] = digest(output / 'run.log')
        result['inputs_unchanged_during_run'] = hashes == {str(path): digest(path) for path in inputs}
        if not result['inputs_unchanged_during_run']:
            raise ValueError('Render verification inputs drifted')
        result['passed'] = True
        print(log, end='')
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
