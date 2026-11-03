#!/usr/bin/env python3
"""Reject drift in the exact W Pitch integration and prove M C preprocessing."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_stream_pitch_provenance as lineage
from tools import workstation_dispatch_slot_provenance as dispatch


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
            raise AssertionError('Pitch lineage accepted ' + name)

    sources = {name: (ROOT/name).read_bytes() for name in lineage.HUNKS}
    parents = {}
    for name, source in sources.items():
        parent = lineage.restore_parent(name, source)
        parents[name] = parent
        assert lineage.normalize_source(name, parent) == parent
        assert lineage.normalize_source(name, source) == parent
        positives.append('exact current/parent roundtrip: '+name)
        reject('unrelated byte: '+name, lambda n=name, s=source: lineage.normalize_source(n, s+b' '))
        reject('changed parent: '+name, lambda n=name, p=parent: lineage.normalize_source(n, p+b' '))
        # Apply the Pitch inverse mutations to its exact reviewed stage. The
        # later default-off CNN branch has separate whole-source drift tests.
        from tools.workstation_pr2_storage_reference import RECORDS, restore_parent as restore_merged
        anchor_source = restore_merged(source, name)[0] if name in RECORDS else source
        for i, (before, after) in enumerate(lineage.HUNKS[name]):
            assert anchor_source.count(after.encode()) == 1
            reject('partial inverse '+str(i)+': '+name,
                lambda n=name, s=anchor_source, b=before, a=after: lineage.normalize_source(n, s.replace(a.encode(), b.encode())))
    event = 'rtl/audio/gw138k_event_workstation.sv'
    assert dispatch.normalize_source(event, sources[event]) == dispatch.normalize_source(event, parents[event])
    positives.append('event reverses Pitch then the exact original dispatch ancestry')
    with tempfile.TemporaryDirectory(prefix='stream-pitch-provenance-') as tmp:
        tmp = Path(tmp)
        module = tmp/lineage.IMPLEMENTATION
        module.parent.mkdir(parents=True, exist_ok=True)
        module.write_bytes((ROOT/lineage.IMPLEMENTATION).read_bytes())
        for name, parent in parents.items():
            target = tmp/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(parent)
        assert lineage.source_bundle(tmp)['stage'] == 'parent'
        for name, source in sources.items():
            (tmp/name).write_bytes(source)
            reject('mixed owners: '+name, lambda: lineage.source_bundle(tmp))
            (tmp/name).write_bytes(parents[name])
        for name, source in sources.items():
            (tmp/name).write_bytes(source)
        assert lineage.source_bundle(tmp)['stage'] == 'stream_pitch'
        module.write_bytes(module.read_bytes()+b' ')
        reject('DSP implementation changed', lambda: lineage.source_bundle(tmp))
        positives.append('all-old/all-current accepted; every single mixed owner rejected')
        # M production and legacy firmware must be exactly the original
        # preprocessed C bytes, not only semantically similar source snippets.
        vendor = ROOT/'vendor/usb_host_fs_8fc3/firmware'
        results = []
        for native in (False, True):
            for label, payloads in [('parent', parents), ('current', sources)]:
                directory = tmp/(label+'-'+str(int(native)))
                directory.mkdir()
                for name in ('firmware.c', 'gw25k_panel.h'):
                    (directory/name).write_bytes(payloads[name])
                command = ['cc', '-E', '-P', '-I'+str(ROOT), '-I'+str(vendor), '-I'+str(vendor/'usb')]
                if native:
                    command += ['-DWORKSTATION_USB2_NATIVE=1', '-I'+str(ROOT/'drivers/usb2')]
                command += [str(directory/'firmware.c')]
                result = subprocess.run(command, check=True, capture_output=True).stdout
                results.append(result)
            assert results[-2] == results[-1], 'M firmware preprocessing differs'
            positives.append('M firmware/panel macro-off exact preprocessing native='+str(native))
    inputs = [Path(__file__).resolve(), ROOT/'tools/workstation_stream_pitch_provenance.py',
              ROOT/'tools/workstation_dispatch_slot_provenance.py', ROOT/lineage.IMPLEMENTATION,
              *(ROOT/name for name in lineage.HUNKS)]
    report = dict(schema=1, passed=True, positive_cases=positives,
        rejected_negative_controls=negatives, source_bundle=lineage.source_bundle(ROOT),
        input_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        immutable_manifests_modified=False, hardware_tested=False, physical_timing_verified=False)
    (args.output/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(passed=True, positive_cases=len(positives), rejected_negative_controls=len(negatives))))


if __name__ == '__main__':
    main()
