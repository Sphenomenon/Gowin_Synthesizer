#!/usr/bin/env python3
"""Verify explicit W phone batch page, real window drainage and fail-closed cases."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess


def run(output):
    root = Path(__file__).resolve().parents[2]
    adapter = root / 'rtl/workstation/workstation_task3_phone_batch_w.sv'
    tx = root / 'rtl/workstation/workstation_task3_phone_window_tx.sv'
    rx = root / 'rtl/workstation/workstation_task3_phone_window_rx.sv'
    bench = Path(__file__).with_name('tb_task3_phone_batch_w.sv')
    tracked = [adapter, tx, rx, bench, Path(__file__).resolve()]
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = {str(p): sha(p) for p in tracked}
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema=1, passed=False, input_sha256=before, commands=[], mutations=[],
                  scope='actual W batch adapter and window TX/RX with delayed local-clock owner and ACK; not actual PCM owner, endpoint, firmware, physical LCD, RF/SBC or sustained phone/DAC acceptance',
                  hardware_tested=False, physical_acceptance=False)

    def command(name, argv, success=True):
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
        log = output / (name + '.log')
        log.write_text(result.stdout)
        report['commands'].append(dict(argv=argv, exit_code=result.returncode, log=str(log), log_sha256=sha(log)))
        if success and result.returncode:
            raise RuntimeError('contract simulation failed: ' + str(log))
        return result

    def compile_bench(name, sources):
        binary = output / (name + '.vvp')
        command(name + '_compile', ['iverilog', '-g2012', '-s', 'tb_task3_phone_batch_w', '-o', str(binary), *map(str, sources)])
        return binary

    try:
        sources = [adapter, tx, rx, bench]
        result = command('nominal_run', ['vvp', str(compile_bench('nominal', sources))])
        nominal_output = result.stdout
        match = re.search(r'PHONE_BATCH_W checks=(\d+) requests=(\d+) proxies=(\d+) applied=(\d+) blocks=(\d+) negative_cases=(\d+)', result.stdout)
        if not match or 'PASS task3_phone_batch_w' not in result.stdout:
            raise RuntimeError('missing coverage counters/completion')
        checks, requests, proxies, applied, blocks, negatives = map(int, match.groups())
        if checks < 500 or requests < 20 or proxies < 9 or applied < 1 or blocks < 1 or negatives < 40:
            raise RuntimeError('insufficient contract coverage')
        report['coverage'] = dict(checks=checks, transmitted_batch_requests=requests,
                                  unchanged_legacy_completions=proxies, real_model_owner_words=applied,
                                  externally_flushed_window_blocks=blocks, negative_cases=negatives)
        mutations = [
            ('flush_barrier_bypass', adapter, 'FLUSH:if(active && !window_busy_i)state<=SEND;', 'FLUSH:if(active)state<=SEND;'),
            ('external_flush_ignored', tx, '(EXTERNAL_FLUSH_ENABLE && flush_i)', "1'b0"),
            ('wrong_reply_token', adapter, 'response_payload_i[31:0]==token &&', ''),
            ('wrong_reply_sequence', adapter, 'response_payload_i[63:32]==request_payload[63:32] &&', ''),
            ('stale_capture', adapter, 'response_payload_i[191:160]>last_capture', "1'b1"),
            ('invalid_snapshot', adapter, 'response_payload_i[253] &&', ''),
            ('owner_error_ignored', adapter, 'response_payload_i[252]', "1'b0"),
            ('legacy_page_intercepted', adapter, "local_address_i>=12'h100", "local_address_i>=12'h020"),
            ('held_overlap_unfenced', adapter, '!overlap && !response_valid_i', '!response_valid_i'),
            ('transaction_replay', adapter, "next_sequence<=next_sequence+1'b1;", 'next_sequence<=next_sequence;'),
            ('impossible_queue', adapter, 'response_payload_i[245:236]<=10\'d512', "1'b1"),
            ('stale_noncommit_descriptor', adapter, "local_data_i==2?intent_sequence:32'd0", 'intent_sequence'),
        ]
        for name, source, old, new in mutations:
            original = source.read_text()
            # Owner error occurs in validation and capture. Mutate both so the
            # result tests the actual semantic guard, not one redundant copy.
            expected_anchors = 2 if name == 'owner_error_ignored' else 1
            if original.count(old) != expected_anchors:
                raise RuntimeError('mutation anchor drift: ' + name)
            changed = output / (name + '.sv')
            changed.write_text(original.replace(old, new))
            mutant = compile_bench(name, [changed if p == source else p for p in sources])
            result = command(name + '_run', ['vvp', str(mutant)], success=False)
            rejected = result.returncode != 0 and 'PASS task3_phone_batch_w' not in result.stdout
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
