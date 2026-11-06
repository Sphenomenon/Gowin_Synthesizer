#!/usr/bin/env python3
"""Check the F7 glide path's actual capture edges without licensed EDA."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
TB = Path(__file__).with_name('tb_pitch_capture_boundary.sv')
COMPOSITION = ROOT / 'rtl/audio/workstation_runtime_render_engines.sv'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError('capture diagnostic projection anchor changed: ' + before)
    return source.replace(before, after)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = [project / ('legacy/rtl/audio/' + name) for name in (
        'audio_math_pkg.sv', 'midi_step_rom.sv', 'mode_timbre_rom.sv',
        'partial_step_generator_variable.sv', 'sine_interp.sv')]
    native = [ROOT / ('rtl/audio/' + name) for name in (
        'workstation_runtime_div147.sv', 'workstation_rate_pitch_expression.sv',
        'workstation_runtime_oscillator_engine.sv', 'workstation_runtime_scope_vec.sv')]
    # Bind all actual native engine inputs to the retained prepared candidate.
    for path in native + [COMPOSITION]:
        if path.read_bytes() != (project / path.relative_to(ROOT)).read_bytes():
            raise ValueError('maintained engine differs from prepared candidate: ' + str(path))
    inputs = sources + native + [COMPOSITION, TB, Path(__file__).resolve()]
    for folder in ('sim/data', 'sim/matlab/output', 'rtl/audio/scope_vec/data'):
        inputs += sorted((project / folder).rglob('*.mem'))
    hashes = {str(path): digest(path) for path in inputs}
    original = COMPOSITION.read_text()
    marker = '    wire oscillator_quiescent, oscillator_rate_ready;'
    input_delay = replace_once(original, marker,
        '    logic [15:0] delayed_glide;\n'
        '    always_ff @(posedge clk_i or negedge rst_ni)\n'
        "        if(!rst_ni)delayed_glide<=0;else delayed_glide<=glide_step_q20_i;\n" + marker)
    input_delay = replace_once(input_delay,
        '.target_ratio_q20_i, .glide_step_q20_i, .vibrato_depth_i,',
        '.target_ratio_q20_i, .glide_step_q20_i(delayed_glide), .vibrato_depth_i,')
    output_delay = replace_once(original, marker,
        '    wire [21:0] raw_pitch;\n'
        '    logic [21:0] delayed_pitch;\n'
        '    assign pitch_q20_o=delayed_pitch;\n'
        '    always_ff @(posedge clk_i or negedge rst_ni)\n'
        "        if(!rst_ni)delayed_pitch<=22'd1048576;else delayed_pitch<=raw_pitch;\n" + marker)
    output_delay = replace_once(output_delay, '.ratio_q20_o(pitch_q20_o)', '.ratio_q20_o(raw_pitch)')
    report = dict(schema=1, passed=False, input_sha256=hashes, project=str(project),
        scope='Actual native pitch+ordinary32+vector8 consumers and independent integer pitch model; registered last-edge parameters,48/44.1k and PANIC. No USB/effects/serializer or physical timing proof.',
        maintained_sources_equal_prepared_candidate=True, runs={}, production_profile_changed=False,
        new_synthesis_runs=0, new_PnR_runs=0, hardware_tested=False)
    try:
        for name, source in (('production', original), ('input_register_mutant', input_delay),
                             ('output_register_mutant', output_delay)):
            folder = output / name
            folder.mkdir()
            composition = folder / COMPOSITION.name
            composition.write_text(source)
            command = ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
                '--top-module', 'tb_pitch_capture_boundary', '--Mdir', str(folder / 'obj'),
                *map(str, sources + native + [composition, TB])]
            with (folder / 'compile.log').open('w') as stream:
                subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT,
                               check=True, timeout=180)
            warnings = re.findall(r'^%Warning-(\w+):', (folder / 'compile.log').read_text(), re.M)
            if any(w in warnings for w in ('UNOPTFLAT', 'PINMISSING', 'WIDTH', 'WIDTHEXPAND', 'WIDTHTRUNC')):
                raise ValueError('capture diagnostic has a loop, missing pin or width warning: ' + name)
            with (folder / 'run.log').open('w') as stream:
                run = subprocess.run([str(folder / 'obj/Vtb_pitch_capture_boundary')], cwd=project,
                    stdout=stream, stderr=subprocess.STDOUT, timeout=60)
            log = (folder / 'run.log').read_text()
            entry = dict(returncode=run.returncode, expected_failure=name != 'production',
                source_sha256=hashlib.sha256(source.encode()).hexdigest(), compile_argv=command,
                compile_log_sha256=digest(folder / 'compile.log'), run_log_sha256=digest(folder / 'run.log'))
            report['runs'][name] = entry
            if name == 'production':
                lines = [line for line in log.splitlines() if line.startswith('PASS pitch_capture_boundary ')]
                if run.returncode or len(lines) != 1:
                    raise ValueError('actual pitch capture failed: ' + log[-2500:])
                entry['metrics'] = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', lines[0])}
                print(lines[0], flush=True)
            else:
                if not run.returncode or 'PITCH_CAPTURE ' not in log:
                    raise ValueError('register mutant not rejected at actual consumer: ' + name + '\n' + log[-2500:])
                entry['witness'] = next(line for line in log.splitlines() if 'PITCH_CAPTURE ' in line)
                values = {k: int(v) for k, v in re.findall(r'(expected|oscillator|vector)=(\d+)', entry['witness'])}
                if len(values) != 3 or any(values[c] == values['expected'] for c in ('oscillator', 'vector')):
                    raise ValueError('register mutant did not reach both actual consumers: ' + name)
                entry['consumer_values'] = values
                print('REJECTED ' + name + ': ' + entry['witness'], flush=True)
        if hashes != {str(path): digest(path) for path in inputs}:
            raise ValueError('capture diagnostic inputs drifted')
        report['inputs_unchanged_during_run'] = True
        report['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
