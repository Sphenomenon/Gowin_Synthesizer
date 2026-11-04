#!/usr/bin/env python3
"""Offline LCD transport, policy and four-state pin checks; never operate hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output):
    root = Path(__file__).resolve().parents[2]
    repository = root.parents[3]
    phy = root / 'rtl/workstation/workstation_task3_lcd_phy.sv'
    transport = root / 'rtl/workstation/workstation_task3_lcd_transport.sv'
    pins = root / 'rtl/workstation/workstation_task3_lcd_pins.sv'
    tb_transport = root / 'sim/workstation/tb_task3_lcd_transport.sv'
    tb_pins = root / 'sim/workstation/tb_task3_lcd_pins.sv'
    plan_path = root / 'boards/custom_138k/task3_lcd_probe_pinplan.json'
    cst = root / 'boards/custom_138k/task3_lcd_probe.cst'
    plan = json.loads(plan_path.read_text())
    basis = [repository / name for name in plan['source_basis']]
    tracked = [phy, transport, pins, tb_transport, tb_pins, plan_path, cst,
               Path(__file__).resolve(), *basis]
    before = {str(p): sha(p) for p in tracked}
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema=1, passed=False, source_sha256=before,
                  scope='offline four-phase nibble CDC model, frames, bounded queues, '
                        'policy and four-state pad ownership; no electrical, routed CDC, '
                        'throughput, jitter or physical latency acceptance',
                  hardware_operated=False, hardware_tested=False, bitstream=None,
                  cases={}, commands=[])

    def command(name, argv, marker=None):
        result = subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=120)
        log = output / (name + '.log')
        log.write_text(result.stdout)
        entry = dict(name=name, argv=argv, exit=result.returncode,
                     log=str(log), log_sha256=sha(log))
        report['commands'].append(entry)
        if result.returncode or (marker and marker not in result.stdout):
            raise RuntimeError('failed ' + name + ': ' + str(log))
        return result.stdout

    try:
        # Check the standalone fragment against the reviewed 40-pin plan.
        if [p['pin'] for p in plan['pins']] != list(range(1, 41)):
            raise RuntimeError('incomplete or reordered FPC4 pin plan')
        programmable = {p['port']: p['fpga_ball'] for p in plan['pins']
                        if p['kind'] == 'programmable'}
        locations = re.findall(r'IO_LOC\s+"([^"]+)"\s+(\w+)\s*;', cst.read_text())
        if (len(programmable) != 25 or len(locations) != 25 or
                dict(locations) != programmable or
                len(set(programmable.values())) != 25):
            raise RuntimeError('CST port/ball mismatch or duplicate')
        settings = re.findall(r'IO_PORT\s+"([^"]+)"\s+([^;]+);', cst.read_text())
        expected_setting = 'IO_TYPE=LVCMOS33 PULL_MODE=NONE DRIVE=4 BANK_VCCIO=3.3'
        if len(settings) != 25 or {port for port, _ in settings} != set(programmable) or any(
                setting.strip() != expected_setting for _, setting in settings):
            raise RuntimeError('unexpected probe electrical declaration')
        for name, expected in plan['source_basis'].items():
            if sha(repository / name) != expected:
                raise RuntimeError('reviewed pin-plan source drift: ' + name)
        report['cases']['pinplan_cst_and_basis'] = True
        report['tool_versions'] = {
            'verilator': command('verilator_version', ['verilator', '--version']).strip(),
            'iverilog': command('iverilog_version', ['iverilog', '-V']).splitlines()[0],
        }
        for allow in (0, 1):
            name = 'transport_business_' + str(allow)
            obj = output / (name + '_obj')
            command(name + '_build', ['verilator', '--binary', '--timing', '--build-jobs', '4',
                    '--top-module', 'tb_task3_lcd_transport',
                    '-GTEST_ALLOW_BUSINESS=' + str(allow), '--Mdir', str(obj),
                    str(transport), str(phy), str(tb_transport)])
            result = command(name + '_run', [str(obj / 'Vtb_task3_lcd_transport')],
                             'PASS task3_lcd_transport')
            report['cases'][name] = True
            print(result, end='')
        command('pins_build', ['iverilog', '-g2012', '-s', 'tb_task3_lcd_pins',
                '-o', str(output / 'pins.vvp'), str(pins), str(tb_pins)])
        result = command('pins_run', ['vvp', str(output / 'pins.vvp')],
                         'PASS task3_lcd_pins')
        report['cases']['four_state_pins'] = True
        print(result, end='')
        report['source_unchanged'] = before == {str(p): sha(p) for p in tracked}
        if not report['source_unchanged']:
            raise RuntimeError('verification inputs changed during execution')
        report['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
