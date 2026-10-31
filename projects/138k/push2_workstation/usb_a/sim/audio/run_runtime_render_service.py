#!/usr/bin/env python3
"""Verify real dual-rate render/service transactions and modeled wet PCM."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'sim'))
from test_workstation_runtime_effects import Effects


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = sorted((project / 'legacy/rtl/audio').glob('*.sv'),
                     key=lambda path: (not path.name.endswith('_pkg.sv'), str(path)))
    sources += [project / name for name in (
        'legacy/rtl/input/midi_stream_decoder.sv', 'src/ae350/gw138k_three_event_arbiter.sv',
        'rtl/audio/serial_spatial_reverb.sv', 'rtl/memory/workstation_sdp.sv',
        'rtl/memory/workstation_sdp_banked.sv')]
    for folder in ('rtl/audio/scope_vec', 'rtl/control', 'rtl/audio/delay_ddr'):
        sources += sorted((project / folder).glob('*.sv'))
    sources += [ROOT / name for name in (
        'rtl/music/music_async_fifo.sv', 'rtl/audio/gw138k_event_workstation.sv',
        'rtl/audio/workstation_audio_render_service.sv', 'rtl/audio/workstation_frame_delivery.sv',
        'rtl/audio/workstation_runtime_div147.sv',
        'rtl/audio/workstation_rate_pitch_expression.sv', 'rtl/audio/workstation_runtime_oscillator_engine.sv',
        'rtl/audio/workstation_runtime_scope_vec.sv', 'rtl/audio/workstation_runtime_render_engines.sv',
        'rtl/audio/workstation_runtime_stereo_effects.sv', 'rtl/audio/workstation_runtime_chorus_effect.sv',
        'rtl/audio/workstation_runtime_spatial_reverb.sv',
        'rtl/audio/delay_ddr/workstation_runtime_delay_effect_ddr.sv',
        'rtl/audio/delay_ddr/workstation_runtime_delay_ddr_dma.sv')]
    maintained_names = {path.name for path in sources if path.is_relative_to(ROOT)}
    sources = [path for path in sources if not (
        path.is_relative_to(project / 'rtl/audio/delay_ddr') and path.name in maintained_names)]
    memory_reference = ROOT / 'sim/audio/tb_workstation_runtime_effects.sv'
    memory_text = memory_reference.read_text()
    anchor = '\nmodule tb_workstation_runtime_effects;'
    if memory_text.count(anchor) != 1:
        raise ValueError('Posted DDR model extraction anchor drift')
    memory = output / 'ordered_posted_ddr_model.sv'
    memory.write_text(memory_text[:memory_text.index(anchor)])
    tb = Path(__file__).with_name('tb_workstation_runtime_render_service.sv')
    sources += [memory, tb]
    banks_path = ROOT / 'rtl/audio/runtime_spatial_room_preset.json'
    inputs = [*sources, memory_reference, Path(__file__).resolve(), banks_path,
              ROOT / 'sim/test_workstation_runtime_effects.py', ROOT / 'sim/test_workstation_runtime_reverb.py',
              ROOT / 'rtl/audio/runtime_spatial_room_preset.svh']
    inputs += sorted((project / 'sim/data').rglob('*.mem'))
    inputs += sorted((project / 'sim/matlab/output').rglob('*.mem'))
    hashes = {str(path): digest(path) for path in inputs}
    result = dict(schema=1, passed=False, hardware_tested=False, profile_changed=False,
                  scope='Opt-in full native dual-rate render service; real 200ms delay ring and ordered posted DDR model',
                  project=str(project), input_sha256=hashes,
                  memory_model='Exact leading module extracted from committed effects TB; writes execute after command acceptance, fence ACK follows ordered read response')
    try:
        command = ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
                   '--top-module', 'tb_workstation_runtime_render_service', '--Mdir', str(output / 'obj'),
                   '-I' + str(ROOT), '-I' + str(project), *map(str, sources)]
        result['compile_argv'] = command
        with (output / 'compile.log').open('w') as stream:
            subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=300)
        result['compile_warning_counts'] = {}
        for name in re.findall(r'^%Warning-(\w+):', (output / 'compile.log').read_text(), re.M):
            result['compile_warning_counts'][name] = result['compile_warning_counts'].get(name, 0) + 1
        if 'UNOPTFLAT' in result['compile_warning_counts']:
            raise ValueError('Combinational ready/admission loop')
        trace = output / 'pcm.txt'
        command = [str(output / 'obj/Vtb_workstation_runtime_render_service'), '+TRACE=' + str(trace)]
        result['run_argv'] = command
        with (output / 'run.log').open('w') as stream:
            subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=300)
        log = (output / 'run.log').read_text()
        matches = [line for line in log.splitlines() if line.startswith('PASS runtime_render_service:')]
        if len(matches) != 1:
            raise ValueError('Missing runtime service verification')
        result['metrics'] = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', matches[0])}
        model = Effects(json.loads(banks_path.read_text())['banks'])
        expected = None
        compared = {48000: 0, 44100: 0}
        for number, line in enumerate(trace.read_text().splitlines(), 1):
            operation, *values = line.split()
            values = list(map(int, values))
            if operation == 'C':
                if expected is not None:
                    raise ValueError(f'Barrier crossed unfinished frame at trace line {number}')
                model.clear(values[0])
            elif operation == 'F':
                if expected is not None:
                    raise ValueError(f'Second unfinished frame at trace line {number}')
                expected = model.frame(*values)[:2]
            elif operation == 'O':
                if tuple(values) != expected:
                    raise ValueError(f'Independent wet PCM mismatch line {number}: RTL={values} model={expected}')
                compared[model.rate] += 1
                expected = None
            else:
                raise ValueError('Unknown trace operation')
        if expected is not None or min(compared.values()) < 24000:
            raise ValueError('Missing complete modeled dual-rate frames')
        result['independent_fixed_point_compared_frames'] = compared
        result['trace_sha256'] = digest(trace)
        result['inputs_unchanged_during_run'] = hashes == {str(path): digest(path) for path in inputs}
        if not result['inputs_unchanged_during_run']:
            raise ValueError('Integration inputs drifted during verification')
        result['passed'] = True
        print(log, end='')
        print('Independent effects PCM comparisons:', compared)
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
