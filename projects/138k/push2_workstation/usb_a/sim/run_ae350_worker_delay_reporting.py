#!/usr/bin/env python3
"""W capability negotiation over the actual Classic ACL API, with raw packets."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frozen-source', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    repo = root.parents[3]
    output = args.output.resolve()
    if output == repo or repo in output.parents:
        parser.error('evidence must be outside repository')
    output.mkdir(parents=True, exist_ok=False)
    firmware = root / 'firmware/ae350'
    source = firmware / 'classic_service.c'
    fixture = root / 'sim/ae350_worker_delay_fixture.c'
    inputs = [source, firmware / 'classic_service.h', fixture,
              root / 'sim/ae350_classic_fixture.c', Path(__file__).resolve()]
    before = {str(path.relative_to(root)): sha(path) for path in inputs}
    cc = Path(shutil.which('cc')).resolve()
    common = [str(cc), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
              '-I' + str(firmware), '-DA138_WORKER_AUDIO_ONLY']
    commands = []
    results = {}

    def run(argv, name, success=True):
        result = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=60)
        (output / (name + '.log')).write_text(result.stdout + result.stderr)
        commands.append({'argv': list(map(str, argv)), 'returncode': result.returncode})
        if success and result.returncode:
            raise RuntimeError((name, result.returncode, result.stdout, result.stderr))
        return result

    def build_run(tag, selected, flags=()):
        run([*common, *flags, selected, fixture, '-o', output / tag], tag + '-compile')
        result = run([output / tag], tag + '-run')
        if 'runtime error:' in result.stderr or 'Sanitizer' in result.stderr:
            raise RuntimeError('sanitizer finding')
        checks = re.search(r'worker delay capability: (\d+) checks passed', result.stdout)
        if not checks:
            raise RuntimeError('missing fixture success')
        wire = []
        for line in result.stdout.splitlines():
            if line.startswith('WIRE '):
                _, case, direction, packet = line.split()
                wire.append({'case': case, 'direction': direction, 'hci_acl_hex': packet})
        if len(wire) != 14:
            raise RuntimeError('incomplete raw ACL evidence')
        results[tag] = {'checks': int(checks[1]), 'wire': wire}
        return wire

    current = build_run('worker', source)
    sanitized = build_run('worker-sanitized', source,
                          ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'])
    if sanitized != current:
        raise RuntimeError('sanitized wire drift')
    # A negative control restoring the advertised-but-unbound provider must fail
    # independent protocol expectations, not merely a source-string assertion.
    text = source.read_text()
    mutants = {}
    for name, anchor, replacement in [
            ('worker-capability-leak', '#define DELAY_REPORTING_SUPPORTED 0',
             '#define DELAY_REPORTING_SUPPORTED 1'),
            ('worker-selection-gate-removed',
             'if (!DELAY_REPORTING_SUPPORTED) { error=0x17; break; }',
             'if (0) { error=0x17; break; }'),
            ('injected-facts-enable-absent-provider',
             'if (!DELAY_REPORTING_SUPPORTED) { error=0x17; break; }',
             'if (!DELAY_REPORTING_SUPPORTED && !s->delay_valid) { error=0x17; break; }')]:
        if text.count(anchor) != 1:
            raise RuntimeError('worker mutation anchor drift: ' + name)
        mutant = output / (name + '.c')
        mutant.write_text(text.replace(anchor, replacement))
        run([*common, mutant, fixture, '-o', output / name], name + '-compile')
        rejection = run([output / name], name + '-run', False)
        if not rejection.returncode or 'check ' not in rejection.stderr:
            raise RuntimeError('mutant survived or missed assertion: ' + name)
        mutants[name] = {'rejected': True, 'source_sha256': sha(mutant),
                         'failure': rejection.stderr.strip()}
    frozen = None
    if args.frozen_source:
        frozen = args.frozen_source.resolve()
        frozen_hash = sha(frozen)
        old = build_run('frozen-worker', frozen, ['-DA138_EXPECT_FROZEN_DELAY'])
        if [x for x in old if x['direction'] == 'REQUEST'] != [x for x in current if x['direction'] == 'REQUEST']:
            raise RuntimeError('frozen/current request drift')
        if sha(frozen) != frozen_hash:
            raise RuntimeError('frozen source drift')
    for name, digest in before.items():
        if sha(root / name) != digest:
            raise RuntimeError('source drift during verification: ' + name)
    report = {'schema': 'ae350-worker-delay-capability-v1', 'hardware_tested': False,
              'actual_delay_measured': False, 'inputs': before, 'compiler_sha256': sha(cc),
              'profiles': results, 'mutants': mutants, 'commands': commands,
              'frozen_source': str(frozen) if frozen else None,
              'frozen_source_sha256': sha(frozen) if frozen else None}
    report['outputs'] = {str(path.relative_to(output)): sha(path)
                         for path in sorted(output.iterdir()) if path.is_file()}
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'checks': {tag: value['checks'] for tag, value in results.items()},
                      'wire_packets_per_profile': len(current), 'mutants_rejected': len(mutants),
                      'evidence': str(output / 'verification.json')}, indent=2))


if __name__ == '__main__':
    main()
