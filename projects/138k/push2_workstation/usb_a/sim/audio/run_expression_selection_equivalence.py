#!/usr/bin/env python3
"""Per-half-clock whole oscillator equivalence for balanced expression selection."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from workstation_baselines import load_baseline
from workstation_oscillator_expression_provenance import (
    SOURCE, PROVENANCE, ADAPTATION, restore_native, source_bundle)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    paths = [ROOT / name for name in (SOURCE, PROVENANCE, ADAPTATION,
             'tools/workstation_oscillator_expression_provenance.py',
             'rtl/audio/workstation_runtime_div147.sv',
             'sim/audio/tb_oscillator_expression_equivalence.sv')]
    paths.append(Path(__file__).resolve())
    hashes = {str(p): sha(p.read_bytes()) for p in paths}
    source, provenance, adaptation = [p.read_bytes() for p in paths[:3]]
    parent = restore_native(source, provenance, adaptation)
    meta = json.loads(provenance)
    baseline = load_baseline(ROOT, 'resource_rework_route0')
    report = dict(schema=1, identity='whole-oscillator-expression-prefix-equivalence-v1',
                  passed=False, hardware_tested=False, synthesis_or_routed_timing_tested=False,
                  scope='Same PIPELINED_RATE/ENVELOPE real oscillator against exact pre-selection parent at every half-clock; all32 gains/voices, real handshakes and PCM; both rates, all A/B/C and five profiles',
                  provenance=source_bundle(ROOT), input_sha256=hashes,
                  reference_adaptation='Reverse only checked expression bridge, rename oscillator and its private quantizer modules; both instances use identical parameters',
                  baseline=baseline.evidence(), runs={})
    stage = out / 'reconstructed'
    stage.mkdir()
    reference = stage / 'reference_oscillator.sv'
    reference.write_text(parent.decode().replace('workstation_runtime_oscillator_engine', 'fc_reference_oscillator').replace(
        'workstation_runtime_mix_quantizer', 'fc_reference_mix_quantizer'))
    dependencies = []
    report['dependency_sha256'] = {}
    for name, identity in meta['test_dependencies'].items():
        data = baseline.read_bytes(name)
        if sha(data) != identity['baseline_sha256']:
            raise ValueError('locked expression dependency drifted: ' + name)
        if 'prepared_exact_edit' in identity:
            edit = identity['prepared_exact_edit']
            text = data.decode()
            if text.count(edit['before']) != 1:
                raise ValueError('prepared dependency exact anchor drift')
            data = text.replace(edit['before'], edit['after']).encode()
            if sha(data) != identity['prepared_sha256']:
                raise ValueError('prepared dependency exact hash drift')
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        report['dependency_sha256'][name] = sha(data)
        if target.suffix == '.sv':
            dependencies.append(target)
    dependencies.sort(key=lambda p: (not p.name.endswith('_pkg.sv'), str(p)))
    try:
        for name, payload in {'production': source, 'missing_low_group_mutant': source.replace(
                b'expression_prefix_2[group_number-4]', b"1'b0")}.items():
            if name != 'production' and payload == source:
                raise ValueError('expression negative-control anchor drift')
            folder = out / name
            folder.mkdir()
            native = folder / 'workstation_runtime_oscillator_engine.sv'
            native.write_bytes(payload)
            command = ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
                       '--top-module', 'tb_oscillator_expression_equivalence', '--Mdir', str(folder / 'obj'),
                       str(ROOT / 'sim/audio/tb_oscillator_expression_equivalence.sv'), str(native),
                       str(reference), str(ROOT / 'rtl/audio/workstation_runtime_div147.sv'), *map(str, dependencies)]
            with (folder / 'compile.log').open('w') as log:
                compiled = subprocess.run(command, cwd=stage, stdout=log, stderr=subprocess.STDOUT, timeout=300)
            if compiled.returncode or '%Warning-UNOPTFLAT:' in (folder / 'compile.log').read_text():
                raise ValueError('whole oscillator compile failed or admission loop: ' + name)
            with (folder / 'run.log').open('w') as log:
                run = subprocess.run([str(folder / 'obj/Vtb_oscillator_expression_equivalence')],
                                     cwd=stage, stdout=log, stderr=subprocess.STDOUT, timeout=180)
            text = (folder / 'run.log').read_text()
            report['runs'][name] = dict(returncode=run.returncode, compile_argv=command,
                                       log_sha256=sha((folder / 'run.log').read_bytes()),
                                       source_sha256=sha(payload))
            if name == 'production':
                matches = [line for line in text.splitlines() if line.startswith('PASS whole_oscillator_expression:')]
                if run.returncode or len(matches) != 1:
                    raise ValueError('whole oscillator per-half-clock equivalence failed')
                report['metrics'] = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', matches[0])}
                print(matches[0])
            elif not run.returncode or 'EXPRESSION_SELECT_ORACLE' not in text:
                raise ValueError('cross-group priority mutant did not fail for selector-oracle reason')
        for label, args in {
            'source_tamper': (source + b'\n', provenance, adaptation),
            'bridge_tamper': (source, provenance, adaptation + b' '),
            'original_provenance_tamper': (source, provenance + b' ', adaptation),
        }.items():
            try:
                restore_native(*args)
            except ValueError as error:
                report['runs'][label] = dict(rejected=True, reason=str(error))
            else:
                raise ValueError('provenance negative control accepted: ' + label)
        report['inputs_unchanged_during_run'] = hashes == {str(p): sha(p.read_bytes()) for p in paths}
        if not report['inputs_unchanged_during_run']:
            raise ValueError('whole oscillator inputs changed during run')
        report['passed'] = True
        print('PASS whole oscillator selector and provenance negative controls')
    finally:
        (out / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
