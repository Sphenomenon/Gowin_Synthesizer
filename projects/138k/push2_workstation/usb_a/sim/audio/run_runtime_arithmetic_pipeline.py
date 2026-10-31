#!/usr/bin/env python3
"""Exact runtime arithmetic against versioned pre-pipeline oracles and mutants.

No prepared project or historical/private staging tree is required. Only the
recorded arithmetic provenance tail is reversed; production is native RTL.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools'))
from workstation_baselines import load_baseline


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('exact mutation/rename anchor drifted: ' + old)
    return text.replace(old, new)


def checked_command(command, cwd, log, timeout):
    with log.open('w') as stream:
        result = subprocess.run(command, cwd=cwd, stdout=stream,
                                stderr=subprocess.STDOUT, timeout=timeout)
    return result.returncode, log.read_text()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--reference-project', type=Path,
                        help='Optional independent frozen project cross-check; never a dependency')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    for tool in ('iverilog', 'vvp', 'verilator'):
        if not shutil.which(tool):
            raise RuntimeError(tool + ' is required')
    inputs = {}

    def read(path):
        data = path.read_bytes()
        inputs[str(path)] = sha(data)
        return data

    read(Path(__file__).resolve())
    baseline = load_baseline(ROOT, 'resource_rework_route0')
    read(baseline.manifest)
    stage = output / 'reconstructed'
    original, native, ancestry = {}, {}, {}
    names = {'osc': 'workstation_runtime_oscillator_engine.sv',
             'vector': 'workstation_runtime_scope_vec.sv'}
    metadata = {}
    for kind, name in names.items():
        source = ROOT / 'rtl/audio' / name
        data = read(source)
        meta = json.loads(read(source.with_suffix('.provenance.json')))
        revision = meta['registered_runtime_arithmetic']
        if sha(data) != meta['native_sha256'] or sha(data) != revision['source_sha256']:
            raise ValueError('native provenance hash drifted: ' + name)
        edits = meta['forward_edits' if kind == 'osc' else 'edits']
        start, count = revision['reverse_edit_start'], revision['reverse_edit_count']
        if start + count != len(edits):
            raise ValueError('arithmetic edits must be the final provenance tail')
        restored = data.decode()
        for edit in reversed(edits[start:start + count]):
            if restored.count(edit['after']) != edit.get('count', 1):
                raise ValueError('arithmetic reverse anchor drifted: ' + name)
            restored = restored.replace(edit['after'], edit['before'])
        restored_bytes = restored.encode()
        if sha(restored_bytes) != revision['before_sha256']:
            raise ValueError('pre-pipeline oracle identity drifted: ' + name)
        if args.reference_project:
            frozen = args.reference_project.resolve() / 'rtl/audio' / name
            if read(frozen) != restored_bytes:
                raise ValueError('independent frozen oracle differs: ' + str(frozen))
        native[kind] = data.decode()
        original[kind] = write(stage / 'unrenamed' / name, restored_bytes)
        renamed = restored.replace('workstation_runtime_oscillator_engine', 'fc_reference_oscillator').replace(
            'workstation_runtime_mix_quantizer', 'fc_reference_mix_quantizer') if kind == 'osc' else restored.replace(
                'workstation_runtime_scope_vec', 'fc_reference_vector')
        original[kind] = write(stage / (kind + '_reference.sv'), renamed.encode())
        ancestry[kind] = dict(base_commit=revision['base_commit'],
                              oracle_sha256=sha(restored_bytes), reverse_edit_start=start,
                              reverse_edit_count=count, renamed_oracle_sha256=sha(renamed.encode()))
        metadata[kind] = meta
    helper = read(ROOT / 'rtl/audio/workstation_runtime_div147.sv').decode()
    helper_path = write(stage / 'workstation_runtime_div147.sv', helper.encode())
    dependencies, dependency_hashes = [], {}
    specs = dict(metadata['osc']['test_dependencies'])
    for name, identity in specs.items():
        entry = baseline.descriptor['files'][name]
        read(baseline.repository / entry['source'])
        data = baseline.read_bytes(name)
        if sha(data) != identity['baseline_sha256']:
            raise ValueError('locked dependency drifted: ' + name)
        if 'prepared_exact_edit' in identity:
            edit = identity['prepared_exact_edit']
            data = replace_once(data.decode(), edit['before'], edit['after']).encode()
            if sha(data) != identity['prepared_sha256']:
                raise ValueError('prepared sine dependency drifted')
        path = write(stage / name, data)
        dependency_hashes[name] = sha(data)
        if path.suffix == '.sv':
            dependencies.append(path)
    dependencies.sort(key=lambda p: (not p.name.endswith('_pkg.sv'), str(p)))
    for source in sorted((ROOT / 'rtl/audio/scope_vec/data').glob('*.mem')):
        name = source.relative_to(ROOT)
        data = read(source)
        write(stage / name, data)
        dependency_hashes[str(name)] = sha(data)
    fixtures = {kind: HERE / ('tb_runtime_' + label + '_independent.sv') for kind, label in
                (('helper', 'div147'), ('osc', 'oscillator_pipeline'), ('vector', 'vector_pipeline'))}
    for fixture in fixtures.values():
        read(fixture)
    composition = read(ROOT / 'rtl/audio/workstation_runtime_render_engines.sv').decode()
    for anchor in ('.PIPELINED_ENVELOPE(RUNTIME_RATE_ENABLE)', '.PIPELINED_RATE(RUNTIME_RATE_ENABLE)'):
        if anchor not in composition:
            raise ValueError('production runtime pipeline selection drifted')
    report = dict(schema=1, identity='runtime-arithmetic-pipeline-baseline-regression-v1', passed=False,
                  validation_stage='rtl-simulation', synthesis_or_routed_timing_tested=False,
                  hardware_tested=False, deployment_allowed=False,
                  reference_policy='Reverse only checked arithmetic provenance tail; dependencies from locked versioned baseline; rename reference modules only',
                  baseline=baseline.evidence(), ancestry=ancestry, dependency_sha256=dependency_hashes,
                  selected_parameters={'oscillator': {'RUNTIME_RATE_ENABLE': 1, 'PIPELINED_RATE': 1, 'PIPELINED_ENVELOPE': 1},
                                       'vector': {'PIPELINED_RATE': 1}},
                  optional_frozen_crosscheck=args.reference_project is not None)
    (output / 'inputs.json').write_text(json.dumps(report | {'input_sha256': inputs}, indent=2) + '\n')

    def helper_case(item):
        name, mutation = item
        folder = output / name
        folder.mkdir()
        source = helper if mutation is None else replace_once(helper, mutation[0], mutation[1])
        path = write(folder / 'helper.sv', source.encode())
        command = ['iverilog', '-g2012', '-s', 'tb_runtime_div147_independent', '-o', str(folder / 'test.vvp'), str(path), str(fixtures['helper'])]
        rc, log = checked_command(command, stage, folder / 'compile.log', 30)
        result = dict(compile_exit=rc, source_sha256=sha(source.encode()), compile_argv=command)
        if rc == 0:
            rc, log = checked_command(['vvp', str(folder / 'test.vvp')], stage, folder / 'run.log', 30)
            result.update(run_exit=rc, marker='RUNTIME_DIV147_INDEPENDENT_PASS' in log,
                          metrics=[dict((k, int(v)) for k, v in re.findall(r'(\w+)=(\d+)', line)) for line in log.splitlines() if line.startswith('DIV147_INDEPENDENT_PASS')])
        result['passed'] = result['compile_exit'] == 0 and ((result.get('run_exit') == 0 and result.get('marker')) if mutation is None else
                              (result.get('run_exit') != 0 and mutation[2] in log and not result.get('marker')))
        result['log_tail'] = log.strip().splitlines()[-5:]
        return name, result

    def consumer_case(item):
        name, kind, mutation = item
        folder = output / name
        folder.mkdir()
        source = native[kind] if mutation is None else replace_once(native[kind], mutation[0], mutation[1])
        path = write(folder / names[kind], source.encode())
        label = 'oscillator' if kind == 'osc' else 'vector'
        top = 'tb_runtime_' + label + '_pipeline_independent'
        sources = (dependencies if kind == 'osc' else []) + [path, helper_path, original[kind], fixtures[kind]]
        command = ['verilator', '--binary', '--timing', '-j', '2', '-Wno-fatal', '--top-module', top,
                   '--Mdir', str(folder / 'obj'), '-o', 'test', *map(str, sources)]
        rc, log = checked_command(command, stage, folder / 'compile.log', 240)
        warnings = dict(Counter(re.findall(r'^%Warning-(\w+):', log, re.M)))
        result = dict(compile_exit=rc, compile_warnings=warnings, source_sha256=sha(source.encode()), compile_argv=command)
        if rc == 0:
            rc, log = checked_command([str(folder / 'obj/test')], stage, folder / 'run.log', 120)
            marker = 'OSC_PIPELINE_INDEPENDENT_PASS' if kind == 'osc' else 'VECTOR_PIPELINE_INDEPENDENT_PASS'
            result.update(run_exit=rc, marker=marker in log,
                          metrics=dict((k, int(v)) for k, v in re.findall(r'(\w+)=(\d+)', log)),
                          latency_matrix=[dict((k, int(v)) for k, v in re.findall(r'(\w+)=(\d+)', line)) for line in log.splitlines() if line.startswith('OSC_LATENCY ')])
        result['passed'] = result['compile_exit'] == 0 and not (set(warnings) - {'UNSIGNED'}) and (
            (result.get('run_exit') == 0 and result.get('marker')) if mutation is None else
            (result.get('run_exit') != 0 and mutation[2] in log and not result.get('marker')))
        result['log_tail'] = log.strip().splitlines()[-8:]
        return name, result

    try:
        helper_specs = {
            'helper_product': None,
            'helper_wrong_divisor': ("{1'b0,trial}-11'd147", "{1'b0,trial}-11'd146", 'DIV147_NUMERIC'),
            'helper_stale_tag': ('tag[s+1]<=tag[s];', 'tag[s+1]<=tag[0];', 'DIV147_TAG'),
            'helper_ring_wrong_address': ('read_address=address-DELAY;', "read_address=address-DELAY+1'b1;", 'DIV147_TAG'),
            'helper_retain_flush': ("else if(flush_i)valid<='0;", 'else if(flush_i)valid<=valid;', 'DIV147_QUIESCENT'),
            'helper_skip_digit': ('quotient[s+1]<={quotient[s][WIDTH-3:0],digit};', 'quotient[s+1]<=quotient[s];', 'DIV147_NUMERIC')}
        report['helper'] = dict(map(helper_case, helper_specs.items()))
        cases = [
            ('oscillator_product', 'osc', None), ('vector_product', 'vector', None),
            ('oscillator_slot_tag_mutant', 'osc', ('slot_write_address=pitched_tag[124:115];', "slot_write_address=pitched_tag[124:115]+10'd1;", 'OSC_SLOT')),
            ('oscillator_gain_tag_mutant', 'osc', ("pitched_step>=35'd1932735283 ? 16'd0 : pitched_tag[34:19]", "pitched_step>=35'd1932735283 ? 16'd0 : 16'd0", 'OSC_PCM')),
            ('vector_phase_mutant', 'vector', ('phase[phase_result_tag[5:3]]<=phase[phase_result_tag[5:3]]+registered_step[31:0];', "phase[phase_result_tag[5:3]]<=phase[phase_result_tag[5:3]]+registered_step[31:0]+32'd1;", 'VEC_VOICE')),
            ('vector_coefficient_mutant', 'vector', (
                'assign {registered_release,registered_decay,registered_attack}=adsr_44_rom[profile_delay[COEFFICIENT_STAGES]];',
                'assign {registered_release,registered_decay}=adsr_44_rom[profile_delay[COEFFICIENT_STAGES]][71:24];\n'
                "        assign registered_attack=adsr_44_rom[profile_delay[COEFFICIENT_STAGES]][23:0]+24'd1;",
                'VEC_COEFFICIENT'))]
        with ThreadPoolExecutor(max_workers=2) as pool:
            report['consumers'] = dict(pool.map(consumer_case, cases))
        report['passed'] = all(case['passed'] for group in ('helper', 'consumers') for case in report[group].values())
    finally:
        report['input_sha256'] = inputs
        report['inputs_unchanged_during_run'] = all(sha(Path(path).read_bytes()) == expected for path, expected in inputs.items())
        report['passed'] = report['passed'] and report['inputs_unchanged_during_run']
        (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({key: value for key, value in report.items() if key not in ('input_sha256', 'dependency_sha256')}, indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
