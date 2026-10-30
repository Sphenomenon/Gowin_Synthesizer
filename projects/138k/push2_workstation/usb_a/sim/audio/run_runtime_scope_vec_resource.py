#!/usr/bin/env python3
"""Exact prechange dual-rate vector reference versus resource candidate, cycle by cycle."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.workstation_baselines import load_baseline


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference-cache', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    native = ROOT / 'rtl/audio/workstation_runtime_scope_vec.sv'
    provenance = native.with_suffix('.provenance.json')
    info = json.loads(provenance.read_text())
    change = info['resource_optimization']
    assert digest(native) == change['source_sha256'], 'Optimized source identity drifted'
    reference_text = native.read_text()
    edits = info['edits'][change['reverse_edit_start']:]
    assert len(edits) == change['reverse_edit_count']
    for edit in reversed(edits):
        assert reference_text.count(edit['after']) == edit['occurrences'], 'Reference reverse anchor drift'
        reference_text = reference_text.replace(edit['after'], edit['before'])
    reference_hash = hashlib.sha256(reference_text.encode()).hexdigest()
    assert reference_hash == change['prechange_native_sha256'], 'Actual prechange runtime reference differs'
    if args.reference_cache is not None:
        assert (args.reference_cache.resolve() / 'rtl/audio/workstation_runtime_scope_vec.sv').read_bytes() == reference_text.encode()
    anchor = 'module workstation_runtime_scope_vec #('
    assert reference_text.count(anchor) == 1
    reference_path = output / 'workstation_runtime_scope_vec_reference.sv'
    reference_path.write_text(reference_text.replace(anchor, 'module workstation_runtime_scope_vec_reference #('))
    baseline = load_baseline(ROOT, 'resource_rework_route0')
    default_adsr = baseline.read_bytes('sim/matlab/output/stage13_note_voice/stage13_adsr_q24.mem')
    # Public ADSR_FILE override tests zero, saturation boundaries and fast full
    # envelope lifecycles; it does not force any design state or ROM word.
    stress_rows = ((0, 0, 0xffffff, 0), (0xffffff, 0xffffff, 0, 0xffffff),
                   (15414066, 15414067, 0x123456, 15500000),
                   (0x100000, 0x200000, 0x400000, 0x100000),
                   (0x234567, 0x345678, 0x345678, 0x456789))
    stress_adsr = ''.join(f'{value:06x}\n' for row in stress_rows for value in row).encode()
    tb = Path(__file__).with_name('tb_workstation_runtime_scope_vec_resource.sv')
    data = [ROOT / ('rtl/audio/scope_vec/data/' + name) for name in ('paths.mem', 'rotation.mem', 'note_steps.mem')]
    sources = [reference_path, native, tb]
    inputs = sources + data + [provenance, Path(__file__).resolve(), ROOT / 'tools/workstation_baselines.py', baseline.manifest]
    paths = {('derived/prechange_reference.sv' if path == reference_path else str(path.relative_to(ROOT))): path for path in inputs}
    hashes = {key: digest(path) for key, path in paths.items()}
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    result = dict(schema=1, passed=False, hardware_tested=False, profile_changed=False,
        identity='runtime-vector-resource-offline-v1-' + identity[:16], source_set_sha256=identity,
        native_sha256=digest(native), actual_prechange_reference_sha256=reference_hash,
        reference_policy='Reverse only appended exact optimization edits to the captured actual native dual-rate provider; one module declaration renamed for independent instance; no behavior/parameters rewritten',
        reference_cache=str(args.reference_cache) if args.reference_cache else None,
        baseline=baseline.evidence(), input_sha256=hashes, input_paths={key: str(path) for key, path in paths.items()},
        source_changes=change['changes'], extra_state_budget_bits=change['extra_state_budget_bits'],
        configuration=dict(rates=[48000, 44100], voices=8, profiles_per_rate=5,
                           tests=['default canonical ADSR_FILE', 'override zero/saturation/fast-lifecycle ADSR_FILE']),
        limits='RTL simulation only, no EDA A/B or promised LUT/physical timing savings; accepted profiles and production provider unchanged')
    try:
        lint = ['verilator', '--lint-only', '--top-module', 'workstation_runtime_scope_vec', str(native)]
        result['lint_argv'] = lint
        process = subprocess.run(lint, capture_output=True, text=True, timeout=60)
        (output / 'lint.log').write_text(process.stdout + process.stderr)
        assert process.returncode == 0 and '%Warning-' not in (output / 'lint.log').read_text(), (output / 'lint.log').read_text()
        result['lint_warning_count'] = 0
        command = ['verilator', '--binary', '--timing', '-j', '3', '-Wno-fatal',
                   '--top-module', 'tb_workstation_runtime_scope_vec_resource', '--Mdir', str(output / 'obj'), *map(str, sources)]
        result['compile_argv'] = command
        with (output / 'compile.log').open('w') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=240)
        result['compile_warning_counts'] = {}
        for name in re.findall(r'^%Warning-(\w+):', (output / 'compile.log').read_text(), re.M):
            result['compile_warning_counts'][name] = result['compile_warning_counts'].get(name, 0) + 1
        assert not result['compile_warning_counts'], 'New vector/reference/TB warning'
        result['runs'] = []
        for case, adsr in [('canonical', default_adsr), ('stress', stress_adsr)]:
            directory = output / case
            directory.mkdir()
            (directory / 'adsr.mem').write_bytes(adsr)
            for path in data:
                target = directory / path.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(path.read_bytes())
            command = [str(output / 'obj/Vtb_workstation_runtime_scope_vec_resource')]
            if case == 'stress':
                command.append('+STRESS_ADSR')
            log_path = output / (case + '.log')
            with log_path.open('w') as stream:
                subprocess.run(command, cwd=directory, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=180)
            log = log_path.read_text()
            assert 'PASS vector_resource:' in log, log
            result['runs'].append(dict(case=case, argv=command, metrics={key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', log)},
                adsr_sha256=digest(directory / 'adsr.mem'), log=log, log_sha256=digest(log_path)))
            print(log, end='')
        result['inputs_unchanged_during_run'] = hashes == {key: digest(path) for key, path in paths.items()}
        assert result['inputs_unchanged_during_run'], 'Vector/reference input drift'
        result['compile_log_sha256'] = digest(output / 'compile.log')
        result['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
