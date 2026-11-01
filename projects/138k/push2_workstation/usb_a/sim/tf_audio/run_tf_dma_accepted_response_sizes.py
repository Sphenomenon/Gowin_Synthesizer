#!/usr/bin/env python3
"""Bind accepted response-size cofactors to the maintained complete DMA.

Binary expression proof is hand-lifted, not formal SV elaboration. The actual
complete-module four-state simulation is bounded and checks unused arithmetic
alternatives as well as the selected next occupancies. No EDA is invoked.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import z3
from tf_dma_read_preload_sources import (
    SOURCE_SHA256, PRELOAD_SOURCE_SHA256, before_accepted_response_sizes,
    before_read_preload,
)
from run_tf_dma_available_response_cofactor import (
    before_available_response_cofactor, four_state_testbench,
)
from run_tf_dma_response_cofactor import before_response_cofactor

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'rtl/tf_audio/workstation_tf_runtime_dma.sv'
MUTATIONS = [
    ('full_read_off_by_one',
     "accepted_full_read = add_occupancy_delta(accepted_used, 7'd96);",
     "accepted_full_read = add_occupancy_delta(accepted_used, 7'd95);"),
    ('full_input_read_off_by_one',
     "accepted_full_input_read = add_occupancy_delta(accepted_used, 7'd97);",
     "accepted_full_input_read = add_occupancy_delta(accepted_used, 7'd96);"),
    ('partial_read_lost',
     "accepted_partial_read = add_occupancy_delta(accepted_used, 7'd0 - {1'b0, available_bytes[5:0]});",
     "accepted_partial_read = add_occupancy_delta(accepted_used, 7'd0);"),
    ('pending_uses_full', 'accepted_after_read = accepted_pending_read;',
     'accepted_after_read = accepted_full_read;'),
    ('unknown_fallback_lost', 'accepted_after_read = accepted_read_generic;',
     'accepted_after_read = accepted_full_read;'),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binary_proof(text, old):
    helper = lambda value: re.findall(
        r'(    function \[31:0\] add_occupancy_delta;.*?endfunction)', value, re.S)
    if len(helper(old)) != 1 or helper(text) != helper(old):
        raise ValueError('TF accepted-response arithmetic helper changed')
    accepted, available = z3.BitVecs('accepted available', 32)
    response = z3.BitVec('pending_response_bytes', 6)
    read_pending, eof = z3.Bools('read_pending eof')

    def add(occupancy, delta):
        low = z3.ZeroExt(1, z3.Extract(5, 0, occupancy)) + z3.ZeroExt(1, z3.Extract(5, 0, delta))
        upper = z3.Extract(31, 6, occupancy)
        carry = z3.Extract(6, 6, low) == 1
        adjusted = z3.If(z3.Extract(6, 6, delta) == 1,
                         z3.If(carry, upper, upper - 1), z3.If(carry, upper + 1, upper))
        return z3.Concat(adjusted, z3.Extract(5, 0, low))

    partial = z3.And(eof, z3.ULT(available, z3.BitVecVal(32, 32)))
    chunk = z3.If(partial, z3.Extract(5, 0, available), z3.BitVecVal(32, 6))
    amount = z3.If(read_pending, response, chunk)
    rows = []
    for label, base in [('accepted_after_read', 0), ('accepted_after_input_read', 1)]:
        initial = z3.BitVecVal(base, 7)
        before = add(accepted, initial - z3.ZeroExt(1, amount))
        after = z3.If(read_pending, add(accepted, initial - z3.ZeroExt(1, response)),
                      z3.If(partial, add(accepted, initial - z3.ZeroExt(1, z3.Extract(5, 0, available))),
                            add(accepted, z3.BitVecVal((base - 32) % 128, 7))))
        solver = z3.Solver()
        solver.add(before != after)
        status = str(solver.check()).upper()
        if status != 'UNSAT':
            raise ValueError('TF accepted-response expression differs: ' + label)
        rows.append(dict(label=label, result=status))
    return dict(rows=rows, free_bits=72, reachability_assumptions=False,
                arbitrary_32bit_accepted_and_available=True,
                independent_6bit_pending_size=True,
                helper_sha256=hashlib.sha256(helper(old)[0].encode()).hexdigest(),
                scope='Source-pinned hand-lifted expression algebra, not formal SystemVerilog elaboration',
                z3_version=z3.get_version_string())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    base_tb = Path(__file__).with_name('tb_tf_dma_response_cofactor_four_state.sv')
    header = ROOT / 'rtl/ddr_address_map.vh'
    inputs = [SOURCE, Path(__file__).resolve(), base_tb, header, *[
        Path(__file__).with_name(name) for name in (
            'tf_dma_read_preload_sources.py', 'run_tf_dma_available_response_cofactor.py',
            'run_tf_dma_response_cofactor.py')]]
    before = {str(path): sha(path) for path in inputs}
    for path in inputs:
        copy = out / 'inputs' / path.relative_to(ROOT)
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(path.read_bytes())
    report = dict(schema=1, passed=False, source_sha256=sha(SOURCE), input_sha256=before,
                  runs=[], EDA_invoked=False, SDC_modified=False,
                  hardware_tested=False, timing_or_resource_gain_claimed=False)
    try:
        text = SOURCE.read_text()
        old = before_accepted_response_sizes(text)
        if sha(SOURCE) != SOURCE_SHA256:
            raise ValueError('actual maintained accepted-response source changed')
        nba = lambda value: re.findall(r'\b(\w+(?:\[[^]]+\])?)\s*<=\s*([^;]+);', value)
        if nba(text) != nba(old):
            raise ValueError('TF accepted-response NBA target/RHS/order changed')
        inverses = {name: hashlib.sha256(function(text).encode()).hexdigest() for name, function in (
            ('before_accepted_response_sizes', before_accepted_response_sizes),
            ('before_read_preload', before_read_preload),
            ('before_available_response_cofactor', before_available_response_cofactor),
            ('before_response_cofactor', before_response_cofactor))}
        if inverses != dict(
                before_accepted_response_sizes=PRELOAD_SOURCE_SHA256,
                before_read_preload='1baa71464c9180f13fa03a281c81d9cd7d8cb3ace0c538b674e610604d6f25e7',
                before_available_response_cofactor='3f9eb8afa2c3308d270ce215693723bfb7cb48584ee96c3c3fbe749a4902e7b6',
                before_response_cofactor='5ac87cbacd1ddc35f897fdf7c3427f80bcf7b151e44370baae6fb3305a596d3b'):
            raise ValueError('TF exact complete-source inverse chain changed')
        report.update(exact_complete_source_inverse_sha256=inverses,
                      all_NBA_targets_RHS_order_identical=True, no_added_cycle=True,
                      binary=binary_proof(text, old), source_drift_controls=[])
        for label, anchor in [('new_size_cofactor', "accepted_used, 7'd97)"),
                              ('private_preload', "1'b0: read_buf <= app_rdata;")]:
            if text.count(anchor) != 1:
                raise ValueError('TF accepted-response drift-control anchor changed')
            try:
                before_accepted_response_sizes(text.replace(anchor, anchor + ' ', 1))
            except ValueError:
                report['source_drift_controls'].append(dict(label=label, rejected=True))
            else:
                raise ValueError('TF accepted-response source gate accepted drift')
        reference = out / 'reference.sv'
        module = 'module workstation_tf_runtime_dma #('
        if old.count(module) != 1:
            raise ValueError('TF accepted-response reference identity drift')
        reference.write_text(old.replace(module, 'module reference_workstation_tf_runtime_dma #(', 1))
        include = out / 'src/memory'
        include.mkdir(parents=True)
        (include / header.name).write_bytes(header.read_bytes())
        tb_text = four_state_testbench(base_tb.read_text())
        anchor = 'if(dut.available_after_read !== reference.available_after_read ||'
        replacement = '''if(dut.accepted_after_read !== reference.accepted_after_read ||
           dut.accepted_after_input_read !== reference.accepted_after_input_read ||
           dut.accepted_without_write !== reference.accepted_without_write ||
           dut.accepted_pending_only !== reference.accepted_pending_only ||
           dut.available_after_read !== reference.available_after_read ||'''
        if tb_text.count(anchor) != 1:
            raise ValueError('TF accepted-response four-state oracle anchor changed')
        tb = out / 'accepted-size-four-state.sv'
        tb.write_text(tb_text.replace(anchor, replacement, 1))
        cases = [('actual_maintained', SOURCE, False)]
        for label, anchor, replacement in MUTATIONS:
            if text.count(anchor) != 1:
                raise ValueError('TF accepted-response mutation anchor changed: ' + label)
            path = out / (label + '.sv')
            path.write_text(text.replace(anchor, replacement, 1))
            cases.append((label, path, True))
        for label, path, negative in cases:
            binary = out / (label + '.vvp')
            command = ['iverilog', '-g2012', '-I', str(out), '-s', 'tf_response_four',
                       '-o', str(binary), str(path), str(reference), str(tb)]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
            compile_log = out / (label + '-compile.log')
            compile_log.write_text(compiled.stdout + compiled.stderr)
            compiled.check_returncode()
            run = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=240)
            log = out / (label + '-run.log')
            log.write_text(run.stdout + run.stderr)
            passed = (run.returncode != 0 and 'cofactor four-state differs' in log.read_text()) if negative else (
                run.returncode == 0 and 'PASS actual DMA cofactor four-state vectors=2097152' in log.read_text())
            report['runs'].append(dict(label=label, passed=passed, negative_control=negative,
                source_sha256=sha(path), command=command, compile_exit_code=compiled.returncode,
                compile_log_sha256=sha(compile_log), exit_code=run.returncode,
                log_sha256=sha(log), binary_sha256=sha(binary), output=log.read_text()))
            if not passed:
                raise ValueError(label + ' failed: ' + log.read_text())
            print(label, 'PASS', log.read_text().strip(), flush=True)
        if before != {str(path): sha(path) for path in inputs}:
            raise ValueError('TF accepted-response verification inputs changed during run')
        report.update(passed=True, inputs_unchanged=True, four_state_vectors=2097152,
                      four_state_scope='Bounded actual complete-module combinational inspection with X/Z; not a sequential or hardware proof')
    finally:
        (out / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    artifacts = {str(path.relative_to(out)): sha(path) for path in sorted(out.rglob('*')) if path.is_file()}
    seal = out / 'final-seal.json'
    seal.write_text(json.dumps(dict(schema=1, passed=True, directory=str(out), artifacts=artifacts,
        source_sha256=sha(SOURCE), hardware_tested=False), indent=2) + '\n')
    print('PASS maintained TF accepted response sizes', sha(SOURCE), 'seal=' + sha(seal))


if __name__ == '__main__':
    main()
