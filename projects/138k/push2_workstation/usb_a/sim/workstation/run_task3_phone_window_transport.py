#!/usr/bin/env python3
"""Check bounded posted phone-window queues, ordering and failure contracts."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess


def run(output):
    root = Path(__file__).resolve().parents[2]
    tx = root / 'rtl/workstation/workstation_task3_phone_window_tx.sv'
    rx = root / 'rtl/workstation/workstation_task3_phone_window_rx.sv'
    bench = Path(__file__).with_name('tb_task3_phone_window_transport.sv')
    tracked = [tx, rx, bench, Path(__file__).resolve()]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = {str(p): sha(p) for p in tracked}
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema=1, passed=False, input_sha256=before, commands=[], mutations=[],
                  scope='actual phone-window TX/RX, local-clock held-APB owner model; no physical LCD, actual PCM owner, firmware or sustained phone-audio acceptance',
                  hardware_tested=False, physical_acceptance=False)

    def command(name, argv, success=True):
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
        log = output / (name + '.log')
        log.write_text(result.stdout)
        report['commands'].append(dict(argv=argv, exit_code=result.returncode, log=str(log), log_sha256=sha(log)))
        if success and result.returncode:
            raise RuntimeError('contract simulation failed: ' + str(log))
        return result

    try:
        binary = output / 'phone_windows.vvp'
        command('compile', ['iverilog', '-g2012', '-s', 'tb_task3_phone_window_transport', '-o', str(binary), str(tx), str(rx), str(bench)])
        result = command('run', ['vvp', str(binary)])
        nominal_output = result.stdout
        match = re.search(r'PHONE_WINDOWS checks=(\d+) words=(\d+) blocks=(\d+) proxies=(\d+) negative_cases=(\d+)', result.stdout)
        if not match or 'PASS task3_phone_window_transport' not in result.stdout:
            raise RuntimeError('missing coverage counters/completion')
        checks, words, blocks, proxies, negatives = map(int, match.groups())
        if checks < 200 or words < 18 or blocks < 10 or proxies < 6 or negatives < 19:
            raise RuntimeError('insufficient contract coverage')
        report['coverage'] = dict(checks=checks, real_model_owner_words=words, transmitted_blocks=blocks,
                                  remotely_completed_model_commands=proxies, negative_cases=negatives)
        mutations = [
            ('barrier_overtake', tx, 'building_count==0 && flight==FLIGHT_IDLE;', "1'b1;"),
            ('missing_owner_release', rx, 'end else state<=GAP;', 'end else state<=WAIT_OWNER;'),
            ('early_ack', rx, 'end else state<=GAP;', 'end else state<=ACK;'),
            ('nonzero_padding', rx, 'shape_good && tail_good &&', 'shape_good &&'),
        ]
        for name, source, old, new in mutations:
            original = source.read_text()
            if original.count(old) != 1:
                raise RuntimeError('mutation anchor drift: ' + name)
            changed = output / (name + '.sv')
            changed.write_text(original.replace(old, new))
            sources = [changed if p == source else p for p in (tx, rx, bench)]
            mutant = output / (name + '.vvp')
            command(name + '_compile', ['iverilog', '-g2012', '-s', 'tb_task3_phone_window_transport', '-o', str(mutant), *map(str, sources)])
            result = command(name + '_run', ['vvp', str(mutant)], success=False)
            rejected = result.returncode != 0 and 'PASS task3_phone_window_transport' not in result.stdout
            report['mutations'].append(dict(name=name, rejected=rejected))
            if not rejected:
                raise RuntimeError('mutant survived: ' + name)
        report['inputs_unchanged'] = before == {str(p): sha(p) for p in tracked}
        if not report['inputs_unchanged']:
            raise RuntimeError('contract inputs changed during verification')
        report['passed'] = True
        print(nominal_output, end='')
        print(json.dumps(report['coverage']))
    finally:
        (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
