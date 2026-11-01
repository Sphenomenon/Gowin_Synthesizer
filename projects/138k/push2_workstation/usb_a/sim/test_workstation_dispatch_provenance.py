#!/usr/bin/env python3
"""Exercise the production whole-source dispatch and immutable ancestry gates."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_dispatch_slot_provenance as dispatch
from tools import workstation_oscillator_expression_provenance as expression
from tools import workstation_oscillator_release_provenance as release
from tools import workstation_runtime_profile as runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    positives, negatives = [], []

    def reject(name, operation):
        try:
            operation()
        except ValueError as error:
            negatives.append(dict(case=name, rejected=str(error)))
        else:
            raise AssertionError('Production provenance accepted ' + name)

    sources = {n: (ROOT / n).read_bytes() for n in dispatch.HUNKS}
    parents = {n: dispatch.restore_parent(n, data) for n, data in sources.items()}
    current_bundle = dispatch.source_bundle(ROOT)
    assert current_bundle['stage'] == 'stored_slots'
    assert 'tools/workstation_dispatch_slot_provenance.py' in runtime.DEPENDENCIES
    positives.append('actual three maintained owner sources pass the production bundle and runtime locks the gate')
    for name, data in sources.items():
        assert dispatch.normalize_source(name, data) == parents[name]
        assert dispatch.normalize_source(name, parents[name]) == parents[name]
        reject('unrelated byte appended: ' + name,
               lambda n=name, d=data: dispatch.normalize_source(n, d + b'\n// unrelated\n'))
        reject('historical parent byte changed: ' + name,
               lambda n=name: dispatch.normalize_source(n, parents[n] + b' '))
        before, after = dispatch.HUNKS[name][0]
        reject('first reviewed hunk omitted: ' + name,
               lambda n=name, d=data, a=after, b=before: dispatch.normalize_source(n, d.replace(a.encode(), b.encode())))
    positives.append('all three exact historical owners retain their original bytes')
    reject('oscillator stored port removed', lambda: dispatch.normalize_source(
        expression.SOURCE, sources[expression.SOURCE].replace(b'    output wire                event_slot_ready_o,\n', b'')))
    with tempfile.TemporaryDirectory(prefix='dispatch-provenance-') as temporary:
        fixture = Path(temporary)
        for name, data in parents.items():
            path = fixture / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        assert dispatch.source_bundle(fixture)['stage'] == 'parent'
        for name in sources:
            (fixture / name).write_bytes(sources[name])
            reject('mixed historical and maintained owners: ' + name,
                   lambda: dispatch.source_bundle(fixture))
            (fixture / name).write_bytes(parents[name])
    positives.append('historical three-owner bundle accepted; every one-owner mixed stage rejected')
    source = sources[expression.SOURCE]
    provenance = (ROOT / expression.PROVENANCE).read_bytes()
    adaptation = (ROOT / expression.ADAPTATION).read_bytes()
    release_adaptation = (ROOT / release.ADAPTATION).read_bytes()
    for name, data in [('maintained slots', source), ('historical release', parents[expression.SOURCE]),
                       ('historical expression', release.restore_parent(source, release_adaptation))]:
        verified = expression.verify(data, provenance, adaptation)
        assert verified['current_source_sha256'] == dispatch.sha(data)
        assert verified['exact_prepared_sha256'] == json.loads(provenance)['prepared_sha256']
        positives.append(name + ' restores the exact immutable prepared oscillator')
    release_bundle = release.source_bundle(ROOT)
    expression_bundle = expression.source_bundle(ROOT)
    assert release_bundle['current_source_sha256'] == dispatch.CURRENT_SHA256[expression.SOURCE]
    assert expression_bundle['current_source_sha256'] == dispatch.CURRENT_SHA256[expression.SOURCE]
    assert expression_bundle['dispatch_slot_source']['stage'] == 'stored_slots'
    positives.append('release/expression bundles report the actual maintained source identity')
    reject('original provenance bytes changed', lambda: expression.verify(source, provenance + b' ', adaptation))
    reject('expression adaptation bytes changed', lambda: expression.verify(source, provenance, adaptation + b' '))
    reject('release adaptation bytes changed', lambda: release.restore_parent(source, release_adaptation + b' '))
    reject('new oscillator arbitrary change through complete ancestry', lambda: expression.verify(source + b' ', provenance, adaptation))
    reject('old expression parent arbitrary change through complete ancestry', lambda: expression.verify(
        release.restore_parent(source, release_adaptation) + b' ', provenance, adaptation))
    files = [Path(__file__).resolve(), ROOT / 'tools/workstation_dispatch_slot_provenance.py',
             ROOT / 'tools/workstation_oscillator_release_provenance.py',
             ROOT / 'tools/workstation_oscillator_expression_provenance.py',
             ROOT / 'tools/workstation_runtime_profile.py',
             ROOT / expression.PROVENANCE, ROOT / expression.ADAPTATION,
             ROOT / release.ADAPTATION, *(ROOT / n for n in sources)]
    result = dict(schema=1, passed=True, positive_cases=positives, rejected_negative_controls=negatives,
                  source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                  dispatch_bundle=current_bundle, release_bundle=release_bundle,
                  expression_bundle=expression_bundle, immutable_manifests_modified=False,
                  physical_timing_verified=False, hardware_tested=False)
    (args.output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(passed=True, positive_cases=len(positives), rejected_negative_controls=len(negatives))))


if __name__ == '__main__':
    main()
