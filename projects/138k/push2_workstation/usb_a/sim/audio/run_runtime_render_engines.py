#!/usr/bin/env python3
"""Native pitch/osc/vector composition: exact48 reference and held dual rate."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np

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
    sources = [project / ('legacy/rtl/audio/' + name) for name in (
        'audio_math_pkg.sv', 'midi_step_rom.sv', 'mode_timbre_rom.sv',
        'partial_step_generator_variable.sv', 'pitch_expression.sv',
        'sine_interp.sv', 'unified_oscillator_engine.sv')]
    sources += [project / 'rtl/audio/scope_vec/scope_vec_engine.sv']
    sources += [ROOT / ('rtl/audio/' + name) for name in (
        'workstation_runtime_div147.sv',
        'workstation_rate_pitch_expression.sv', 'workstation_runtime_oscillator_engine.sv',
        'workstation_runtime_scope_vec.sv', 'workstation_runtime_render_engines.sv')]
    sources += [Path(__file__).with_name('tb_workstation_runtime_render_engines.sv')]
    inputs = sources + [Path(__file__).resolve()]
    inputs += sorted((project / 'sim/data').rglob('*.mem'))
    inputs += sorted((project / 'sim/matlab/output').rglob('*.mem'))
    inputs += sorted((project / 'rtl/audio/scope_vec/data').glob('*.mem'))
    hashes = {str(path): digest(path) for path in inputs}
    result = dict(schema=1, passed=False, hardware_tested=False, profile_changed=False,
                  scope='Independent native pitch, oscillator, vector composition; no effects/source routing/final volume',
                  project=str(project), input_sha256=hashes)
    try:
        command = ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
                   '--top-module', 'tb_workstation_runtime_render_engines',
                   '--Mdir', str(output / 'obj'), *map(str, sources)]
        result['compile_argv'] = command
        with (output / 'compile.log').open('w') as stream:
            subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT,
                           check=True, timeout=180)
        command = [str(output / 'obj/Vtb_workstation_runtime_render_engines')]
        result['run_argv'] = command
        with (output / 'run.log').open('w') as stream:
            subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT,
                           check=True, timeout=180)
        log = (output / 'run.log').read_text()
        lines = [line for line in log.splitlines() if line.startswith('PASS runtime_render_engines:')]
        if len(lines) != 1:
            raise ValueError('Missing combined engine verification')
        result['metrics'] = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', lines[0])}
        measured = {}
        for tag, rate in ((48, 48000), (44, 44100), (49, 48000)):
            samples = np.asarray([[int(x) for x in line.split()[2:]]
                                  for line in log.splitlines() if line.startswith(f'PCM {tag} ')], dtype=float)
            if samples.shape != (1024, 2) or np.max(np.abs(samples)) == 0:
                raise ValueError(f'Invalid PCM capture {tag}')
            hz = float(np.polyfit(np.arange(1024), np.unwrap(np.arctan2(samples[:, 1], samples[:, 0])), 1)[0]
                       * rate / (2 * np.pi))
            if abs(hz - 440) > 0.002:
                raise ValueError(f'PCM frequency drift {tag}: {hz}')
            measured[str(tag)] = dict(sample_rate=rate, fitted_hz=hz)
        result['pcm_frequency'] = measured
        result['compile_warning_counts'] = {}
        for name in re.findall(r'^%Warning-(\w+):', (output / 'compile.log').read_text(), re.M):
            result['compile_warning_counts'][name] = result['compile_warning_counts'].get(name, 0) + 1
        if 'UNOPTFLAT' in result['compile_warning_counts']:
            raise ValueError('Combinational admission loop')
        result['inputs_unchanged_during_run'] = hashes == {str(path): digest(path) for path in inputs}
        if not result['inputs_unchanged_during_run']:
            raise ValueError('Verification inputs drifted')
        result['run_log_sha256'] = digest(output / 'run.log')
        result['passed'] = True
        print('\n'.join(line for line in log.splitlines() if not line.startswith('PCM ')))
        print('PCM_FREQUENCY', json.dumps(measured, sort_keys=True))
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
