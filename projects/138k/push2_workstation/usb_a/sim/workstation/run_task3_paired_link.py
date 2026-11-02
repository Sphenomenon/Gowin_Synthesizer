#!/usr/bin/env python3
"""Full APB CDC/F808/LCD four-state pair, from maintained and locked sources."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output):
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    from tools.workstation_baselines import load_baseline
    baseline = load_baseline(root, 'resource_rework_route0')
    member = 'src/migration/gw138k_apb_cdc.sv'
    payload = baseline.read_bytes(member)
    if hashlib.sha256(payload).hexdigest() != '61047b3c2be74af1bc96567e2aed37be2d78773cd31364eb6bdb1eb4d9d9409a':
        raise RuntimeError('locked actual APB CDC identity changed')
    names = ['rtl/workstation/workstation_task3_paired_link.sv',
             'rtl/workstation/workstation_task3_lcd_transport.sv',
             'rtl/workstation/workstation_task3_lcd_phy.sv',
             'rtl/workstation/workstation_task3_lcd_pins.sv',
             'rtl/services/workstation_task3_pair_config_service.sv',
             'sim/workstation/tb_task3_paired_link.sv']
    sources = [root / name for name in names]
    tracked = sources + [Path(__file__).resolve(), baseline.manifest,
                        root / 'baselines/index.json', root / 'tools/workstation_baselines.py']
    before = {str(p): sha(p) for p in tracked}
    output.mkdir(parents=True, exist_ok=False)
    cdc = output / 'gw138k_apb_cdc.sv'
    cdc.write_bytes(payload)
    report = dict(schema=1, passed=False, source_sha256=before, commands=[],
                  baseline=baseline.evidence(), baseline_member=member,
                  baseline_member_sha256=sha(cdc),
                  scope='four-state one-to-one physical pad model with real APB CDC, '
                        'F808 nonce/grants, duplex typed CRC traffic, budget revoke, '
                        '50000-cycle CPU/external dedicated PANIC and CPU reset; offline only',
                  clocks_are_simulated=True, measured_throughput=None,
                  measured_hardware_latency=None, physical_CDC_accepted=False,
                  hardware_operated=False, hardware_tested=False, bitstream=None)
    try:
        for allow in (0, 1):
            binary = output / ('pair_' + str(allow) + '.vvp')
            build = ['iverilog', '-g2012', '-s', 'tb_task3_paired_link',
                     '-Ptb_task3_paired_link.TEST_ALLOW_BUSINESS=' + str(allow),
                     '-o', str(binary), str(cdc), *map(str, sources)]
            for kind, argv, marker in [('build', build, None),
                    ('run', ['vvp', str(binary)], 'PASS task3_paired_link')]:
                result = subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, timeout=120)
                log = output / (kind + '_' + str(allow) + '.log')
                log.write_text(result.stdout)
                report['commands'].append(dict(argv=argv, exit=result.returncode,
                    log=str(log), log_sha256=sha(log)))
                if result.returncode or (marker and marker not in result.stdout):
                    raise RuntimeError('failed: ' + str(log))
                if kind == 'run':
                    print(result.stdout, end='')
        report['source_unchanged'] = before == {str(p): sha(p) for p in tracked} and cdc.read_bytes() == payload
        if not report['source_unchanged']:
            raise RuntimeError('verification inputs changed')
        report['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
