#!/usr/bin/env python3
"""Verify cancellation delivery with the actual prepared native audio sources."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools'))
from workstation_composition import verify


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    evidence_path = project.parent / 'workstation_composition.json'
    evidence = json.loads(evidence_path.read_text())
    verify(project, evidence)
    manifest = project.parent / 'workstation_inputs.json'
    staged_inputs = json.loads(manifest.read_text())
    if any(digest(project / name) != value for name, value in staged_inputs.items()):
        raise ValueError('prepared source drift')
    sources = sorted((project / 'legacy/rtl/audio').glob('*.sv'),
                     key=lambda path: (not path.name.endswith('_pkg.sv'), str(path)))
    sources += [project / name for name in (
        'legacy/rtl/input/midi_stream_decoder.sv', 'src/ae350/gw138k_three_event_arbiter.sv',
        'rtl/music/music_async_fifo.sv', 'src/ae350/gw138k_event_workstation.sv',
        'src/audio/pt8211_tx.v', 'rtl/audio/serial_spatial_reverb.sv',
        'rtl/memory/workstation_sdp.sv', 'rtl/memory/workstation_sdp_banked.sv',
        'rtl/audio/workstation_frame_delivery.sv')]
    for folder in ('rtl/audio/scope_vec', 'rtl/control', 'rtl/audio/delay_ddr'):
        sources += sorted((project / folder).glob('*.sv'))
    unit_bench = HERE / 'tb_workstation_frame_delivery.sv'
    serial_bench = HERE / 'tb_workstation_serial_delivery.sv'
    inputs = sources + [unit_bench, serial_bench, Path(__file__), manifest, evidence_path]
    hashes = {str(path): digest(path) for path in inputs}
    (output / 'inputs.json').write_text(json.dumps(hashes, indent=2) + '\n')
    result = dict(passed=False, hardware_tested=False, project=str(project),
                  scope='explicit cancel-zero delivery, unchanged serial cadence; raw negative control', tests={})
    try:
        unit = output / 'unit'
        commands = [
            ('unit_compile', ['iverilog', '-g2012', '-s', 'tb_workstation_frame_delivery', '-o',
                              str(unit), str(project / 'rtl/audio/workstation_frame_delivery.sv'), str(unit_bench)]),
            ('unit_run', ['vvp', str(unit)]),
            ('serial_compile', ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
                                '--top-module', 'tb_workstation_serial_delivery', '--Mdir', str(output / 'obj'),
                                '-I' + str(project / 'rtl'), *map(str, sources), str(serial_bench)]),
            ('serial_run', [str(output / 'obj/Vtb_workstation_serial_delivery')]),
        ]
        for name, command in commands:
            with (output / (name + '.log')).open('w') as stream:
                subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT,
                               check=True, timeout=300)
            if name.endswith('_run'):
                lines = (output / (name + '.log')).read_text().splitlines()
                passed = [line for line in lines if line.startswith('PASS workstation_')]
                if len(passed) != 1:
                    raise ValueError('missing delivery verification: ' + name)
                result['tests'][name] = passed[0]
                print(passed[0], flush=True)
        if hashes != {str(path): digest(path) for path in inputs}:
            raise ValueError('verification input drift')
        verify(project, evidence)
        result['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
