#!/usr/bin/env python3
"""Check opposite-edge reset release against the byte-pinned old monitor."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
REFERENCE_SHA = '1d073cbf98ff683603f36ae521fcc5f62bfc6920526ff442e184c02466519d15'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'rtl/audio/workstation_audio_clock_monitor.sv'
    reference = Path(__file__).with_name('fixtures') / 'workstation_audio_clock_monitor_pre_m9.sv'
    tb = Path(__file__).with_name('tb_clock_monitor_release.sv')
    domain_test = ROOT / 'sim/test_workstation_audio_clock_domain.py'
    paths = [source, reference, tb, Path(__file__).resolve(), domain_test,
             ROOT / 'rtl/audio/workstation_audio_clock_domain.sv',
             ROOT / 'rtl/audio/workstation_sample_rate_switch.sv',
             ROOT / 'sim/audio/tb_workstation_audio_clock_domain.sv',
             ROOT / 'sim/audio/tb_workstation_audio_clock_monitor.sv']
    before = {str(p): sha(p) for p in paths}
    result = dict(passed=False, input_sha256=before, hardware_tested=False,
                  routed_timing_verified=False, deployment_allowed=False, commands={})

    def run(name, command, negative=False):
        result['commands'][name] = list(map(str, command))
        process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=90)
        text = process.stdout + process.stderr
        (out / (name + '.log')).write_text(text)
        if negative:
            if process.returncode == 0 or 'release did not use the opposite source edge' not in text:
                raise ValueError('original rising-edge release did not fail the targeted margin check')
        elif process.returncode:
            raise ValueError(text)
        return text

    try:
        if sha(reference) != REFERENCE_SHA:
            raise ValueError('pinned pre-M9 clock monitor identity changed')
        text = reference.read_text()
        anchor = 'module workstation_audio_clock_monitor #('
        if text.count(anchor) != 1:
            raise ValueError('reference module rename anchor drift')
        renamed = out / 'reference_monitor.sv'
        renamed.write_text(text.replace(anchor, 'module reference_workstation_audio_clock_monitor #('))
        binary = out / 'equivalence.vvp'
        run('compile', ['iverilog', '-g2012', '-s', 'tb_clock_monitor_release', '-o', binary,
                        source, renamed, tb])
        log = run('equivalence', ['vvp', binary])
        if log.count('PASS clock_monitor_release:') != 2:
            raise ValueError('both common-reset policies must complete')
        result['equivalence_metrics'] = log.strip().splitlines()
        original_binary = out / 'rising_edge.vvp'
        run('negative_compile', ['iverilog', '-g2012', '-s', 'tb_clock_monitor_release',
                                '-o', original_binary, reference, renamed, tb])
        run('negative_original_release', ['vvp', original_binary], negative=True)
        result['original_rising_edge_margin_negative_rejected'] = True
        log = run('complete_domain', [sys.executable, domain_test])
        if log.count('PASS audio clock domain:') != 3 or 'PASS production clock monitor:' not in log:
            raise ValueError('complete clock domain/production monitor regression incomplete')
        if before != {str(p): sha(p) for p in paths}:
            raise ValueError('clock release verification inputs changed')
        result['inputs_unchanged'] = True
        result['passed'] = True
        print('\n'.join(result['equivalence_metrics']))
    finally:
        (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
