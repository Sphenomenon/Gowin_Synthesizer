#!/usr/bin/env python3
"""Compare maintained occupancy state against the pinned pre-change DMA."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import z3

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from test_cnn_tf_write_buffer_retime import stalled_tb, zero_response_tb
OLD_SHA = 'bc1dcfad79af5777c27d7bfa65ae3b397ce103ca0a992b938027201877119752'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prove_parallel_candidates():
    available, accepted = z3.BitVecs('available accepted', 32)
    pending, response, chunk = z3.BitVecs('pending response chunk', 6)
    selected, read_pending, base, ready, write_ready, valid, input_byte = z3.Bools(
        'selected read_pending base ready write_ready valid input_byte')
    read_accept = z3.And(base, z3.Not(read_pending), z3.Not(selected), ready)
    write_accept = z3.And(selected, ready, write_ready)
    read_response = z3.And(valid, z3.Or(read_pending, read_accept))
    old_size = z3.If(read_accept, chunk, response)
    early_size = z3.If(read_pending, response, chunk)
    extend = lambda value: z3.ZeroExt(1, value)
    zero, one = z3.BitVecVal(0, 7), z3.BitVecVal(1, 7)

    def add(occupancy, delta):
        low = z3.ZeroExt(1, z3.Extract(5, 0, occupancy)) + z3.ZeroExt(1, z3.Extract(5, 0, delta))
        upper = z3.Extract(31, 6, occupancy)
        carry = z3.Extract(6, 6, low) == 1
        adjusted = z3.If(z3.Extract(6, 6, delta) == 1,
                         z3.If(carry, upper, upper - 1), z3.If(carry, upper + 1, upper))
        return z3.Concat(adjusted, z3.Extract(5, 0, low))

    def next_value(occupancy, increase, amount):
        old_delta = z3.If(increase, amount, zero) - z3.If(read_response, extend(old_size), zero)
        old = add(occupancy, old_delta)
        new = z3.If(increase,
                    z3.If(read_response, add(occupancy, amount - extend(early_size)), add(occupancy, amount - zero)),
                    z3.If(read_response, add(occupancy, zero - extend(early_size)), add(occupancy, zero)))
        return old, new

    pairs = {'response_size_when_valid': (z3.If(read_response, old_size, z3.BitVecVal(0, 6)),
                                         z3.If(read_response, early_size, z3.BitVecVal(0, 6))),
             'available_next': next_value(available, write_accept, extend(pending)),
             'accepted_next': next_value(accepted, input_byte, one)}
    results = {}
    for name, (old, new) in pairs.items():
        solver = z3.Solver()
        solver.add(old != new)
        results[name] = str(solver.check()).upper()
        if results[name] != 'UNSAT':
            raise ValueError('parallel occupancy relation differs: ' + name)
    return dict(results=results, free_bits=89, z3_version=z3.get_version_string(),
                unreachable_state_assumptions=False, arbitrary_four_state_proof=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'rtl/tf_audio/workstation_tf_runtime_dma.sv'
    old = Path(__file__).with_name('fixtures') / 'workstation_tf_runtime_dma_pre_occupancy.sv'
    tb = Path(__file__).with_name('tb_tf_dma_occupancy_equivalence.sv')
    header = ROOT / 'rtl/ddr_address_map.vh'
    ring_oracle = Path(__file__).with_name('tb_tf_audio_ddr_dma.sv')
    inputs = [source, old, tb, header, Path(__file__).resolve(), ring_oracle,
              ROOT / 'tools/test_cnn_tf_write_buffer_retime.py']
    before = {str(p): sha(p) for p in inputs}
    result = dict(passed=False, input_sha256=before, symbolic=prove_parallel_candidates(), hardware_tested=False,
                  routed_timing_verified=False, deployment_allowed=False, runs=[])
    try:
        if sha(old) != OLD_SHA:
            raise ValueError('pinned old DMA bytes changed')
        anchor = 'module workstation_tf_runtime_dma #('
        text = old.read_text()
        if text.count(anchor) != 1:
            raise ValueError('reference module identity drift')
        reference = out / 'reference.sv'
        reference.write_text(text.replace(anchor, 'module reference_workstation_tf_runtime_dma #('))
        include = out / 'src/memory'
        include.mkdir(parents=True)
        (include / header.name).write_bytes(header.read_bytes())
        mutant = out / 'mutant.sv'
        changed = 'case ({input_byte_accepted, read_response})'
        if source.read_text().count(changed) != 1:
            raise ValueError('negative-control anchor drift')
        mutant.write_text(source.read_text().replace(changed, "case ({1'b0, read_response})"))
        unsigned = out / 'unsigned_delta.sv'
        changed = 'upper = low_sum[6] ? occupancy[31:6] : upper_minus;'
        if source.read_text().count(changed) != 1:
            raise ValueError('signed-delta negative-control anchor drift')
        unsigned.write_text(source.read_text().replace(changed,
            'upper = low_sum[6] ? upper_plus : occupancy[31:6];'))
        carry = out / 'lost_carry.sv'
        changed = 'upper = low_sum[6] ? upper_plus : occupancy[31:6];'
        if source.read_text().count(changed) != 1:
            raise ValueError('small-delta carry negative-control anchor drift')
        carry.write_text(source.read_text().replace(changed,
            'upper = occupancy[31:6];'))
        simultaneous = out / 'simultaneous.sv'
        changed = "2'b11: next_available_bytes = available_after_write_read;"
        if source.read_text().count(changed) != 1:
            raise ValueError('simultaneous negative-control anchor drift')
        simultaneous.write_text(source.read_text().replace(changed,
            "2'b11: next_available_bytes = available_after_read;"))
        commit_carry = out / 'commit_carry.sv'
        changed = 'upper_plus = occupancy[31:6] + 26\'d1;'
        if source.read_text().count(changed) != 2:
            raise ValueError('capacity carry negative-control anchor drift')
        # Only change the capacity predicate, leaving occupancy arithmetic intact.
        prefix, capacity = source.read_text().split('    function pending_fits_ring;', 1)
        commit_carry.write_text(prefix + '    function pending_fits_ring;' +
                               capacity.replace(changed, 'upper_plus = occupancy[31:6];', 1))
        commit_equal = out / 'commit_equal.sv'
        changed = 'low_sum[5:0] <= AUDIO_TOTAL_BYTES[5:0]'
        if source.read_text().count(changed) != 2:
            raise ValueError('capacity equality negative-control anchor drift')
        commit_equal.write_text(source.read_text().replace(changed,
            'low_sum[5:0] < AUDIO_TOTAL_BYTES[5:0]'))
        zero_bypass = out / 'zero_bypass.sv'
        changed = "2'b00: next_available_bytes = add_occupancy_delta(available_bytes, 7'd0);"
        if source.read_text().count(changed) != 1:
            raise ValueError('zero-delta negative-control anchor drift')
        zero_bypass.write_text(source.read_text().replace(changed,
            "2'b00: next_available_bytes = available_bytes;"))
        unknown_fallback = out / 'unknown_fallback.sv'
        changed = 'default: next_available_bytes = add_occupancy_delta(available_bytes, committed_delta);'
        if source.read_text().count(changed) != 1:
            raise ValueError('unknown-admission negative-control anchor drift')
        unknown_fallback.write_text(source.read_text().replace(changed,
            'default: next_available_bytes = available_after_write_read;'))
        for label, path, bank, negative in [('scaled', source, 64, False),
                                             ('hardware_capacity', source, 67108864, False),
                                             ('drop_input_count', mutant, 64, True),
                                             ('unsigned_delta', unsigned, 64, True),
                                             ('lost_upper_carry', carry, 64, True),
                                             ('simultaneous_write_lost', simultaneous, 64, True),
                                             ('capacity_lost_carry', commit_carry, 64, True),
                                             ('capacity_equal_rejected', commit_equal, 64, True),
                                             ('zero_delta_pessimism_lost', zero_bypass, 64, True),
                                             ('unknown_admission_fallback_lost', unknown_fallback, 64, True)]:
            binary = out / (label + '.vvp')
            command = ['iverilog', '-g2012', '-I', str(out), '-s', 'tb_tf_dma_occupancy_equivalence',
                       '-Ptb_tf_dma_occupancy_equivalence.BANK_BYTES=' + str(bank),
                       '-o', str(binary), str(path), str(reference), str(tb)]
            compile_result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            (out / (label + '_compile.log')).write_text(compile_result.stdout + compile_result.stderr)
            compile_result.check_returncode()
            run = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=90)
            log = run.stdout + run.stderr
            (out / (label + '.log')).write_text(log)
            if negative:
                accepted = run.returncode != 0 and (
                    'occupancy invariant differs' in log or 'small-delta arithmetic differs' in log or
                    'pending capacity arithmetic differs' in log or 'parallel occupancy selection differs' in log)
            else:
                accepted = run.returncode == 0 and 'PASS DMA occupancy:' in log
            result['runs'].append(dict(label=label, command=command, exit_code=run.returncode,
                                       passed=accepted, output=log.strip(), negative_control=negative))
            if not accepted:
                raise ValueError(label + ' failed: ' + log)
            print(log.strip())
        # Independent byte/ring oracle: full, partial and empty files, wrap,
        # output backpressure, native stalls, immediate and delayed returns.
        # The native-only hold interface is tied low for this existing oracle.
        ring_text = '`timescale 1ns/1ps\n' + ring_oracle.read_text()
        ring_text = re.sub(r'\btf_audio_ddr_dma\b', 'workstation_tf_runtime_dma', ring_text)
        anchor = ".mem_ready(1'b1)"
        if ring_text.count(anchor) != 2:
            raise ValueError('ring oracle native hold binding drift')
        ring_text = ring_text.replace(anchor,
            anchor + ",.runtime_hold_i(1'b0),.runtime_restart_ack_o()")
        for stall in (False, True):
            for zero in (False, True):
                label = 'ring_stall' + str(int(stall)) + '_zero' + str(int(zero))
                text = zero_response_tb(ring_text, stall) if zero else (
                    stalled_tb(ring_text) if stall else ring_text)
                path = out / (label + '.sv')
                path.write_text(text)
                binary = out / (label + '.vvp')
                command = ['iverilog', '-g2012', '-I', str(out), '-s', 'tb_tf_audio_ddr_dma',
                           '-o', str(binary), str(source), str(path)]
                compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
                (out / (label + '_compile.log')).write_text(compiled.stdout + compiled.stderr)
                compiled.check_returncode()
                run = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=90)
                log = run.stdout + run.stderr
                (out / (label + '.log')).write_text(log)
                passed = run.returncode == 0 and 'PASS tb_tf_audio_ddr_dma:' in log
                result['runs'].append(dict(label=label, command=command, exit_code=run.returncode,
                                           passed=passed, output=log.strip(), independent_ring_oracle=True))
                if not passed:
                    raise ValueError(label + ' failed: ' + log)
                print(label, log.strip())
        if before != {str(p): sha(p) for p in inputs}:
            raise ValueError('DMA equivalence inputs changed')
        result.update(passed=True, inputs_unchanged=True)
    finally:
        (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
