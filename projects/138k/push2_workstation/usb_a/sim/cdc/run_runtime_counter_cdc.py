#!/usr/bin/env python3
"""All-input GF(2) proof plus asynchronous sequential comparison to locked RTL."""
from pathlib import Path
from collections import Counter
import argparse
import hashlib
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.workstation_baselines import load_baseline
from tools.workstation_runtime_counter import LEGACY, LEGACY_SHA256, NATIVE


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tokens(text):
    return re.findall(r'\w+|\S', re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S))


def prove(legacy, native):
    """Prove the exact RTL's linear transform over all2**32 input words.

    Symbolic rows are bit masks over independent GF(2) basis variables. Equal
    rows establish every binary input, rather than a sampled integer range.
    An unchanged sequential token prefix lifts comb equality to arbitrary
    shared clock/reset schedules. No metastability/propagation claim follows.
    """
    gray_port = ',\n    output wire [31:0] destination_gray'
    gray_alias = 'assign destination_gray=sync_value;'
    if native.count(gray_port) != 1 or native.count(gray_alias) != 1:
        raise ValueError('read-only synchronized Gray output changed')
    native = native.replace(gray_port, '').replace(gray_alias, '')
    if tokens(legacy.split('integer i;')[0]) != tokens(native.split('wire [31:0] prefix1')[0]):
        raise ValueError('registered source/synchronizer/reset boundary changed')
    legacy_tail = legacy[legacy.index('integer i;'):]
    if tokens(legacy_tail) != tokens('integer i;always @* begin destination_count[31]=sync_value[31];for(i=30;i>=0;i=i-1) destination_count[i]=destination_count[i+1]^sync_value[i];end endmodule'):
        raise ValueError('locked serial recurrence changed')
    clean = re.sub(r'//[^\n]*|/\*.*?\*/', '', native, flags=re.S)
    stages = re.findall(r'wire \[31:0\] (prefix\d+)=(\w+)\^\(\2>>(\d+)\);', clean)
    expected = ''.join(f'wire [31:0] {name}={source}^({source}>>{shift});' for name, source, shift in stages)
    tail = clean[clean.index('wire [31:0] prefix1'):]
    if not stages or tokens(tail) != tokens(expected + 'always @* begin destination_count[31]=sync_value[31];destination_count[30:0]=prefix16[30:0];end endmodule'):
        raise ValueError('unreviewed combinational decode structure')
    rows = {'sync_value': [1 << i for i in range(32)]}
    terms = {'sync_value': [Counter({i:1}) for i in range(32)]}
    depths = {'sync_value': [0] * 32}
    for name, source, shift in stages:
        shift = int(shift)
        if source not in rows or name in rows or not 0 < shift < 32:
            raise ValueError('invalid prefix dependency')
        rows[name] = [rows[source][i] ^ (rows[source][i + shift] if i + shift < 32 else 0) for i in range(32)]
        terms[name] = [terms[source][i] + (terms[source][i + shift] if i + shift < 32 else Counter()) for i in range(32)]
        depths[name] = [1 + max(depths[source][i], depths[source][i + shift]) if i + shift < 32 else depths[source][i] for i in range(32)]
    expected_rows = [0] * 32
    expected_rows[31] = 1 << 31
    for i in range(30, -1, -1):
        expected_rows[i] = expected_rows[i + 1] ^ (1 << i)
    if rows.get('prefix16') != expected_rows:
        raise ValueError('all-input GF2 equivalence failed')
    roundtrip = [expected_rows[i] ^ (expected_rows[i + 1] if i < 31 else 0) for i in range(32)]
    if roundtrip != [1 << i for i in range(32)]:
        raise ValueError('Gray decode is not bijective')
    if any(set(t.values()) != {1} for t in terms['prefix16']):
        raise ValueError('duplicated terms invalidate four-state reassociation')
    if len(stages) != 5 or max(depths['prefix16']) != 5:
        raise ValueError('balanced depth changed')
    return dict(method='exact_RTL_symbolic_GF2_basis_matrix', input_bits=32, output_bits=32,
                universal_binary_input_count=4294967296, equal_output_rows=32,
                each_suffix_variable_appears_exactly_once=True, sequential_boundary_tokens_equal=True,
                synchronized_gray_read_only_alias=True, gray_change_detection_all_binary_pairs_equivalent=True,
                destination_clock_latency_added=0, legacy_max_xor_depth=31, native_max_xor_depth=5,
                physical_mapping_or_timing_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    legacy_bytes = load_baseline(ROOT, 'resource_rework_route0').read_bytes(LEGACY)
    if sha(legacy_bytes) != LEGACY_SHA256:
        raise ValueError('locked reference counter drift')
    legacy = legacy_bytes.decode()
    native = (ROOT / NATIVE).read_text()
    proof = prove(legacy, native)
    negative = []
    for name, old, new in [('missing_high_span', 'prefix8>>16', 'prefix8>>8'),
                           ('source_binary', 'gray<=source_count^(source_count>>1)', 'gray<=source_count'),
                           ('sync_stage_bypass', 'sync_value<=meta', 'sync_value<=gray'),
                           ('added_latency', 'always @* begin', 'always @(posedge destination_clk) begin'),
                           ('gray_output_bypass', 'assign destination_gray=sync_value;', 'assign destination_gray=meta;')]:
        assert native.count(old) == 1
        try:
            prove(legacy, native.replace(old, new))
        except ValueError as error:
            negative.append(dict(name=name, rejected=True, reason=str(error)))
        else:
            raise AssertionError('proof mutant accepted: ' + name)
    old_module = 'module gw138k_counter_cdc ('
    if legacy.count(old_module) != 1:
        raise ValueError('legacy fixture module anchor changed')
    reference = out / 'legacy_counter_cdc.sv'
    reference.write_text(legacy.replace(old_module, 'module legacy_counter_cdc ('))
    tb = Path(__file__).with_name('tb_runtime_counter_cdc.sv')
    native_path = ROOT / NATIVE
    inputs = {str(p): sha(p.read_bytes()) for p in [native_path, tb, Path(__file__), ROOT / 'tools/workstation_runtime_counter.py']}
    commands = []
    def run(name, argv):
        commands.append(dict(name=name, argv=list(map(str, argv))))
        with (out / (name + '.log')).open('w') as log:
            subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
        return (out / (name + '.log')).read_text()
    run('lint', ['verilator', '--lint-only', '-Wno-fatal', '--top-module', 'gw138k_counter_cdc', str(native_path)])
    if '%Warning-' in (out / 'lint.log').read_text():
        raise ValueError('native counter lint warning')
    run('compile', ['iverilog', '-g2012', '-s', 'tb_runtime_counter_cdc', '-o', str(out / 'test.vvp'), str(reference), str(native_path), str(tb)])
    runs = []
    for i, values in enumerate([(3.7,5.1,0.2,1.3),(9.3,2.9,1.7,0.1),(4.1,4.7,0.0,2.3)]):
        args = [f'+{key}={value}' for key,value in zip(('SOURCE_HALF','DESTINATION_HALF','SOURCE_PHASE','DESTINATION_PHASE'), values)]
        log = run('run' + str(i), ['vvp', str(out / 'test.vvp'), *args])
        match = re.search(r'PASS runtime_counter_cdc checks=(\d+) final_deliveries=4 stopped_resets=1 wraps=1 latency_equal=1', log)
        if not match or int(match[1]) < 250:
            raise ValueError('incomplete asynchronous/stop/reset/wrap comparison')
        runs.append(dict(clocks_ns=values, checks=int(match[1]), final_deliveries=4, stopped_resets=1, wraps=1))
    if inputs != {str(p): sha(p.read_bytes()) for p in map(Path, inputs)}:
        raise ValueError('verification source changed during run')
    result = dict(schema=1, passed=True, validation_stage='offline_source_equivalence', proof=proof,
        legacy_reference=dict(baseline='resource_rework_route0', source=LEGACY, sha256=LEGACY_SHA256),
        input_sha256=inputs, negative_controls=negative, runs=runs, commands=commands,
        synthesis_run=False, pnr_run=False, physical_cdc_accepted=False, hardware_tested=False, deployment_allowed=False)
    (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(passed=True, universal_inputs=4294967296, max_depth=5, runs=len(runs), negative_controls=len(negative))))


if __name__ == '__main__':
    main()
