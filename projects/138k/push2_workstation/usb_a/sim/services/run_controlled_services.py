#!/usr/bin/env python3
"""Byte-equivalent extraction plus real APB/recorder/score functional regression."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.workstation_baselines import load_baseline
from tools import workstation_resource_timing as timing

SOURCE = 'rtl/services/workstation_controlled_services.sv'
PROVENANCE = 'rtl/services/workstation_controlled_services.provenance.json'
STAGED = 'src/ae350/gw138k_controlled_services.sv'


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def run(output, prepared_project=None):
    baseline = load_baseline(ROOT, 'resource_rework_route0')
    original = baseline.read_bytes(STAGED)
    reconstructed = timing.services(original.decode()).encode()
    native = (ROOT / SOURCE).read_bytes()
    provenance = json.loads((ROOT / PROVENANCE).read_text())
    assert native == reconstructed, 'Maintained services differs from the original timing-prepared bytes'
    assert provenance['source'] == SOURCE and provenance['module'] == 'gw138k_controlled_services'
    assert provenance['source_sha256'] == sha(native) and provenance['source_bytes'] == len(native)
    assert provenance['parent_baseline'] == baseline.evidence()
    assert provenance['parent_input'] == baseline.descriptor['files'][STAGED]
    assert provenance['transform']['before_sha256'] == sha(original)
    assert provenance['transform']['after_sha256'] == sha(reconstructed)
    assert provenance['exact_changes'] == []
    # Selection remains an explicit future step. This regression compiles only
    # the maintained services; the legacy overlay is solely its identity oracle.
    from tools.workstation_composition import SOURCES
    assert SOURCE not in SOURCES
    profile = json.loads((ROOT / 'boards/custom_138k/workstation_profile_v1.json').read_text())
    assert not any(path.endswith('/' + SOURCE) for path in profile['source_sha256'])
    prepared = None
    if prepared_project is not None:
        prepared_path = prepared_project.resolve() / STAGED
        assert prepared_path.read_bytes() == native, 'Actual prepared services byte identity differs'
        prepared = dict(path=str(prepared_path), sha256=sha(prepared_path.read_bytes()), exact=True)
    output.mkdir(parents=True, exist_ok=False)
    apb = output / 'gw138k_apb_cdc.sv'
    apb.write_bytes(timing.apb(baseline.read_bytes('src/migration/gw138k_apb_cdc.sv').decode()).encode())
    sources = [ROOT / SOURCE, apb, ROOT / 'rtl/audio/audio_capture_fifo.sv',
               ROOT / 'rtl/input/score_led_player.sv', ROOT / 'rtl/memory/workstation_sdp.sv',
               Path(__file__).with_name('tb_workstation_controlled_services.sv')]
    inputs = sources + [Path(__file__).resolve(), ROOT / PROVENANCE,
                       ROOT / 'tools/workstation_resource_timing.py',
                       ROOT / 'tools/workstation_baselines.py', baseline.manifest]
    hashes = {str(path): sha(path.read_bytes()) for path in inputs}
    result = dict(schema=1, passed=False, validation_stage='offline-source-identity-and-functional-simulation',
                  source_identity='native-controlled-services-v1-' + sha(native)[:16], bitstream_sha256=None,
                  hardware_tested=False, profile_changed=False, legacy_overlay_changed=False,
                  native_source=dict(path=SOURCE, sha256=sha(native), bytes=len(native)),
                  byte_equivalence=dict(baseline=baseline.evidence(), staged_path=STAGED,
                                        before_sha256=sha(original), after_sha256=sha(reconstructed),
                                        exact=True, prepared_reference=prepared),
                  input_sha256=hashes,
                  limits='No runtime top/profile selection, new rate/record metadata, synthesis, P&R or hardware acceptance')
    try:
        commands = [
            ['iverilog', '-g2012', '-s', 'tb_workstation_controlled_services',
             '-o', str(output / 'services.vvp'), *map(str, sources)],
            ['vvp', str(output / 'services.vvp')],
        ]
        for name, command in zip(('compile', 'run'), commands):
            process = subprocess.run(command, text=True, capture_output=True, timeout=60)
            log = process.stdout + process.stderr
            (output / (name + '.log')).write_text(log)
            result[name + '_argv'] = command
            result[name + '_log_sha256'] = sha(log.encode())
            if process.returncode:
                raise RuntimeError(name + ' failed:\n' + log[-6000:])
        log = (output / 'run.log').read_text()
        assert 'PASS controlled_services:' in log, 'Missing functional verification marker'
        result['metrics'] = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', log)}
        compile_log = (output / 'compile.log').read_text()
        result['compile_diagnostics'] = dict(
            constant_select_sensitivity_notices=compile_log.count('sorry: constant selects'),
            note='Icarus expands always_* sensitivity to the whole input; native bytes equal the prepared source')
        result['inputs_unchanged_during_run'] = hashes == {str(path): sha(path.read_bytes()) for path in inputs}
        assert result['inputs_unchanged_during_run'], 'Verification inputs changed during the run'
        result['passed'] = True
        print(log, end='')
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--prepared-project', type=Path)
    args = parser.parse_args()
    if args.output is not None:
        run(args.output.resolve(), args.prepared_project)
    else:
        with tempfile.TemporaryDirectory(prefix='gw138k-services-') as directory:
            run(Path(directory) / 'verification', args.prepared_project)


if __name__ == '__main__':
    main()
