#!/usr/bin/env python3
"""Measure the ideal-wire RTL model; never grant a physical PCM budget."""
from pathlib import Path
import argparse
import hashlib
import itertools
import json
import re
import subprocess


def run(output):
    root = Path(__file__).resolve().parents[2]
    sources = [root / ('rtl/workstation/workstation_task3_lcd_' + name + '.sv') for name in ('transport', 'phy')]
    sources.append(Path(__file__).with_name('tb_task3_lcd_budget.sv'))
    tracked = [*sources, Path(__file__).resolve()]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = {str(p): sha(p) for p in tracked}
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema=1, passed=False, source_sha256=before,
        scope='ideal zero-delay wire RTL model; full-duplex 32-byte payload frames with real maintenance traffic',
        M_clock_Hz=50000000, W_clock_Hz_tested=[50000000, 1000000000 / 22], physical_throughput_Bps=None,
        physical_RTT_ns=None, hardware_tested=False, physical_budget_authorized=False,
        business_configuration_changed=False, trials=[], commands=[])

    def command(name, argv):
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
        path = output / (name + '.log')
        path.write_text(result.stdout)
        report['commands'].append(dict(argv=argv, exit_code=result.returncode, log=str(path), log_sha256=sha(path)))
        if result.returncode:
            raise RuntimeError('model failed: ' + str(path))
        return result.stdout

    try:
        report['verilator'] = command('verilator_version', ['verilator', '--version']).strip()
        for half, blocked in itertools.product((10, 11), (0, 1)):
            name = 'duplex_W_half_' + str(half) + '_ready_' + str(blocked)
            obj = output / (name + '_obj')
            command(name + '_build', ['verilator', '--binary', '--timing', '--build-jobs', '4',
                '--top-module', 'tb_task3_lcd_budget', '-GBACKPRESSURE=' + str(blocked),
                '-GW_HALF_NS=' + str(half),
                '--Mdir', str(obj), *map(str, sources)])
            text = command(name + '_run', [str(obj / 'Vtb_task3_lcd_budget')])
            if 'PASS task3_lcd_budget' not in text:
                raise RuntimeError('missing model completion')
            pattern = (r'BUDGET_MODEL receiver=(\d+) packets=(\d+) payload_bytes=(\d+) elapsed_ns=(\d+) '
                r'tx_packets=(\d+) rx_packets=(\d+) max_rtt_cycles=(\d+) probes=(\d+) congestion_cycles=(\d+)')
            rows = []
            for match in re.finditer(pattern, text):
                receiver, packets, payload, elapsed_ps, tx, rx, rtt, probes, congestion = map(int, match.groups())
                # %t renders in the bench precision (1 ps), while $time is ns.
                elapsed_ns = elapsed_ps / 1000
                if packets != 1024 or payload != 32768 or elapsed_ns <= 0 or probes == 0 or rtt == 0:
                    raise RuntimeError('invalid model counters')
                rows.append(dict(receiver='M' if receiver == 0 else 'W', packets=packets,
                    payload_bytes=payload, elapsed_model_ns=elapsed_ns,
                    simulated_payload_Bps=payload * 1000000000 / elapsed_ns,
                    simulated_business_packets_per_second=packets * 1000000000 / elapsed_ns,
                    per_sample_48k_stream_fits_this_model=packets * 1000000000 / elapsed_ns >= 48000,
                    local_transport_tx_packets=tx, local_transport_rx_packets=rx,
                    max_probe_RTT_local_cycles=rtt, completed_probe_results=probes,
                    local_outgoing_congestion_cycles=congestion))
            if len(rows) != 2 or {r['receiver'] for r in rows} != {'M', 'W'}:
                raise RuntimeError('missing duplex measurements')
            report['trials'].append(dict(receiver_ready='one_cycle_in_seven' if blocked else 'continuous',
                W_clock_Hz=1000000000 / (2 * half), W_initial_phase_ns=3, directions=rows))
            print(text, end='')
        report['source_unchanged'] = before == {str(p): sha(p) for p in tracked}
        if not report['source_unchanged']:
            raise RuntimeError('model source changed during run')
        report['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
