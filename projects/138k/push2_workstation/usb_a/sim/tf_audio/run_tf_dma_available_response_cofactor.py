#!/usr/bin/env python3
"""Check the maintained available-occupancy response cofactor against 3f9.

The complete source identity and exact inverse bind the expression proof to
the reviewed RTL. Whole-module four-state simulations also compare unused
arithmetic alternatives. Existing response, occupancy and threshold oracles
run against the actual maintained source without replacing their assertions.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import z3
from tf_dma_read_preload_sources import before_read_preload

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'rtl/tf_audio/workstation_tf_runtime_dma.sv'
REFERENCE = Path(__file__).with_name('fixtures') / 'workstation_tf_runtime_dma_before_available_response_cofactor.sv'
SOURCE_SHA256 = '1baa71464c9180f13fa03a281c81d9cd7d8cb3ace0c538b674e610604d6f25e7'
REFERENCE_SHA256 = '3f9eb8afa2c3308d270ce215693723bfb7cb48584ee96c3c3fbe749a4902e7b6'
ORIGINAL_AVAILABLE_LINES = (
    '    wire [31:0] available_after_read = add_occupancy_delta(available_bytes, occupancy_read_delta);\n'
    '    wire [31:0] available_after_write_read = add_occupancy_delta(available_bytes, occupancy_write_read_delta);\n')
BLOCK_PATTERN = (r'(    // Precompute the exact full and pending response alternatives before\n.*?)'
                 r'(?=    wire \[31:0\] accepted_after_input)')
MUTATIONS = [
    ('full_size_off_by_one', "available_bytes, 7'd96)", "available_bytes, 7'd97)"),
    ('partial_zero_off_by_one', "available_after_read = 32'd0;", "available_after_read = 32'd1;"),
    ('partial_unknown_pending_bypass',
     "1'b0, 1'b1: available_after_write_read = {26'd0, pending_bytes};\n                            default: begin end",
     "1'b0, 1'b1: available_after_write_read = {26'd0, pending_bytes};\n                            default: available_after_write_read = {26'd0, pending_bytes};"),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def one(text, pattern):
    values = re.findall(pattern, text, re.S)
    if len(values) != 1:
        raise ValueError('TF available cofactor source anchor drift: ' + pattern)
    return values[0]


def available_cofactor_block(text):
    if hashlib.sha256(text.encode()).hexdigest() != SOURCE_SHA256:
        text = before_read_preload(text)
    if hashlib.sha256(text.encode()).hexdigest() != SOURCE_SHA256:
        raise ValueError('maintained TF available-cofactor source identity changed')
    return one(text, BLOCK_PATTERN)


def before_available_response_cofactor(text):
    """Reverse exactly the reviewed insertion, then require all 3f9 bytes."""
    if hashlib.sha256(text.encode()).hexdigest() != SOURCE_SHA256:
        text = before_read_preload(text)
    block = available_cofactor_block(text)
    restored = text.replace(block, ORIGINAL_AVAILABLE_LINES, 1)
    if hashlib.sha256(restored.encode()).hexdigest() != REFERENCE_SHA256:
        raise ValueError('exact pre-available-cofactor reconstruction changed')
    return restored


def binary_proof(text, old):
    # Source pinning and exact inverse above bind this independent expression
    # model. Also record the actual arithmetic assignments and unchanged helper.
    helper = r'(    function \[31:0\] add_occupancy_delta;.*?endfunction)'
    if one(text, helper) != one(old, helper):
        raise ValueError('TF add_occupancy_delta body changed')
    available = z3.BitVec('available', 32)
    pending, response = z3.BitVecs('pending response', 6)
    read_pending, eof, write_accept, read_response = z3.Bools(
        'read_pending eof write_accept read_response')
    extend = lambda value: z3.ZeroExt(1, value)
    zero = z3.BitVecVal(0, 7)

    def add(occupancy, delta):
        low = z3.ZeroExt(1, z3.Extract(5, 0, occupancy)) + z3.ZeroExt(1, z3.Extract(5, 0, delta))
        upper = z3.Extract(31, 6, occupancy)
        carry = z3.Extract(6, 6, low) == 1
        adjusted = z3.If(z3.Extract(6, 6, delta) == 1,
                         z3.If(carry, upper, upper - 1), z3.If(carry, upper + 1, upper))
        return z3.Concat(adjusted, z3.Extract(5, 0, low))

    full = z3.UGE(available, z3.BitVecVal(32, 32))
    partial = z3.And(eof, z3.Not(full))
    chunk = z3.If(partial, z3.Extract(5, 0, available), z3.BitVecVal(32, 6))
    amount = z3.If(read_pending, response, chunk)
    old_read = add(available, zero - extend(amount))
    old_both = add(available, extend(pending) - extend(amount))
    new_read = z3.If(read_pending, add(available, zero - extend(response)),
                    z3.If(partial, z3.BitVecVal(0, 32), add(available, z3.BitVecVal(96, 7))))
    new_both = z3.If(read_pending, add(available, extend(pending) - extend(response)),
                    z3.If(partial, z3.ZeroExt(26, pending),
                          add(available, extend(pending) - z3.BitVecVal(32, 7))))
    old_final = z3.If(write_accept,
                     z3.If(read_response, old_both, add(available, extend(pending))),
                     z3.If(read_response, old_read, add(available, zero)))
    new_final = z3.If(write_accept,
                     z3.If(read_response, new_both, add(available, extend(pending))),
                     z3.If(read_response, new_read, add(available, zero)))
    rows = []
    for name, original, candidate in [
            ('available_read_arbitrary_state', old_read, new_read),
            ('available_write_read_arbitrary_state', old_both, new_both),
            ('unchanged_four_way_selector_arbitrary_write_and_response', old_final, new_final)]:
        solver = z3.Solver()
        solver.add(original != candidate)
        status = str(solver.check()).upper()
        if status != 'UNSAT':
            raise ValueError('TF available cofactor differs: ' + name)
        rows.append(dict(name=name, result=status))
    equations = {name: one(text, r'wire \[31:0\] ' + name + r' = (.*?);') for name in
                 ('available_read_generic', 'available_write_read_generic',
                  'available_full_read', 'available_full_write_read',
                  'available_pending_read', 'available_pending_write_read')}
    return dict(rows=rows, free_bits=48, arbitrary_32bit_occupancy=True,
                independent_6bit_pending_and_delayed_response=True,
                reachability_assumptions=False, arbitrary_four_state_proof=False,
                scope='Expression algebra bound by full source pin and exact inverse; not formal SV elaboration',
                actual_arithmetic_equations=equations,
                unchanged_helper_sha256=hashlib.sha256(one(text, helper).encode()).hexdigest(),
                z3_version=z3.get_version_string())


def four_state_testbench(base):
    # Derive the enhanced twin from the unchanged old test. Every anchor must
    # occur once. Both precomputed arithmetic RHSs and public next values are
    # checked, including forced combinations unreachable in normal operation.
    substitutions = [
        ('pattern<16', 'pattern<32'),
        ('reg probe_selected,', 'reg probe_eof;\n    reg probe_selected,'),
        ('force dut.eof_finalized=1;', 'force dut.eof_finalized=probe_eof;'),
        ('force reference.eof_finalized=1;', 'force reference.eof_finalized=probe_eof;'),
        ('      case(pattern)\n', '      probe_eof=1;\n      case(pattern)\n'),
        ('      for(control=0;', '''      if(pattern>=16)begin
        probe_available=32'(pattern-16);probe_pending=6'(pattern*3);probe_response=6'(pattern*7);
        case(pattern)
          17:probe_pending=6'b00000x;
          18:probe_pending=6'bz00000;
          19:probe_response=6'b00000x;
          20:probe_eof=1'bx;
          21:probe_eof=1'bz;
          22:probe_pending=6'd32;
          23:probe_pending=6'd63;
          24:probe_available=32'hffffffff;
          25:probe_available=32'hfffffff0;
          26:begin probe_available=32'h0000000x;probe_eof=0;end
          27:begin probe_available=32'hzzzzzzzz;probe_eof=0;end
          28:begin probe_available=32'hfffffff0;probe_eof=1'bx;end
          29:begin probe_available=32'hxxxxxx80;probe_eof=0;end
          30:begin probe_available=31;probe_eof=1'bx;end
          31:begin probe_available=32;probe_eof=1'bz;end
        endcase
      end
      for(control=0;'''),
        ('if(dut.next_available_bytes !== reference.next_available_bytes ||',
         'if(dut.available_after_read !== reference.available_after_read ||\n'
         '           dut.available_after_write_read !== reference.available_after_write_read ||\n'
         '           dut.next_available_bytes !== reference.next_available_bytes ||'),
    ]
    for anchor, replacement in substitutions:
        if base.count(anchor) != 1:
            raise ValueError('TF available four-state test anchor drift: ' + anchor)
        base = base.replace(anchor, replacement, 1)
    return base


def simulate(out, label, path, reference, tb, negative=False):
    binary = out / (label + '.vvp')
    command = ['iverilog', '-g2012', '-I', str(out), '-s', 'tf_response_four',
               '-o', str(binary), str(path), str(reference), str(tb)]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
    compile_log = out / (label + '_compile.log')
    compile_log.write_text(compiled.stdout + compiled.stderr)
    compiled.check_returncode()
    run = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=180)
    log = run.stdout + run.stderr
    log_path = out / (label + '.log')
    log_path.write_text(log)
    passed = (run.returncode != 0 and 'cofactor four-state differs' in log) if negative else (
        run.returncode == 0 and 'PASS actual DMA cofactor four-state vectors=2097152' in log)
    if not passed:
        raise ValueError(label + ' failed: ' + log)
    print(label, log.strip(), flush=True)
    return dict(label=label, negative_control=negative, passed=True,
                command=command, compile_exit_code=compiled.returncode,
                compile_log_sha256=sha(compile_log), exit_code=run.returncode,
                output=log.strip(), binary_sha256=sha(binary), log_sha256=sha(log_path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    base_tb = Path(__file__).with_name('tb_tf_dma_response_cofactor_four_state.sv')
    old_runner = Path(__file__).with_name('run_tf_dma_response_cofactor.py')
    header = ROOT / 'rtl/ddr_address_map.vh'
    names = ['sim/audio/prove_effect_slot_admission.py',
             'tools/test_cnn_tf_write_buffer_retime.py', 'tools/cnn_ddr_pipeline_patch.py',
             'sim/tf_audio/run_tf_dma_occupancy_equivalence.py',
             'sim/tf_audio/run_tf_dma_threshold_groups.py',
             'sim/tf_audio/fixtures/workstation_tf_runtime_dma_pre_occupancy.sv',
             'sim/tf_audio/fixtures/workstation_tf_runtime_dma_before_response_cofactor.sv',
             'sim/tf_audio/tb_tf_dma_occupancy_equivalence.sv',
             'sim/tf_audio/tb_tf_dma_threshold_groups.sv', 'sim/tf_audio/tb_tf_audio_ddr_dma.sv']
    inputs = [SOURCE, REFERENCE, Path(__file__).resolve(), base_tb, old_runner, header,
              Path(__file__).with_name('tf_dma_read_preload_sources.py'),
              Path(__file__).with_name('fixtures') / 'workstation_tf_runtime_dma_before_read_preload.sv',
              *[ROOT / name for name in names]]
    before = {str(path): sha(path) for path in inputs}
    snapshots = {}
    for path in inputs:
        copy = out / 'inputs' / path.relative_to(ROOT)
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(path.read_bytes())
        snapshots[str(path)] = dict(path=str(copy), sha256=sha(copy))
    result = dict(schema=1, passed=False, source_sha256=sha(SOURCE), fixture_sha256=sha(REFERENCE),
                  input_sha256=before, input_snapshots=snapshots, runs=[], existing_regressions={},
                  source_implementation=True, synthesis=False, pnr=False, hardware_tested=False,
                  timing_or_resource_gain_claimed=False, four_state_simulation_is_bounded=True)
    try:
        if sha(REFERENCE) != REFERENCE_SHA256:
            raise ValueError('pinned pre-available-cofactor fixture changed')
        actual_text = SOURCE.read_text()
        text = before_read_preload(actual_text)
        old = before_available_response_cofactor(text)
        if old != REFERENCE.read_text():
            raise ValueError('TF available inverse is not the entire pinned module')
        nba = lambda value: re.findall(r'\b(\w+(?:\[[^]]+\])?)\s*<=\s*([^;]+);', value)
        if nba(text) != nba(old):
            raise ValueError('TF available cofactor changed sequential target/RHS/order')
        tail = '    // Compute both read-response cofactors'
        if text[text.index(tail):] != old[old.index(tail):]:
            raise ValueError('TF accepted-used cofactor or later bytes changed')
        result.update(exact_source_inverse=True, NBA_targets_RHS_order_identical=True,
                      reviewed_private_preload_inverse_sha256=SOURCE_SHA256,
                      actual_preloaded_module_simulated=True,
                      accepted_used_cofactor_and_later_source_byte_identical=True,
                      binary=binary_proof(text, old))
        result['source_drift_controls'] = []
        for label, anchor in [('new_cofactor_drift', "available_bytes, 7'd96)"),
                              ('accepted_cofactor_drift', "1'b1: next_accepted_used = accepted_pending_only;")]:
            if text.count(anchor) != 1:
                raise ValueError('TF available drift-control anchor changed')
            try:
                before_available_response_cofactor(text.replace(anchor, anchor + ' ', 1))
            except ValueError:
                result['source_drift_controls'].append(dict(label=label, rejected=True))
            else:
                raise ValueError('TF available source gate accepted drift')
        reference = out / 'reference.sv'
        module_anchor = 'module workstation_tf_runtime_dma #('
        if old.count(module_anchor) != 1:
            raise ValueError('TF available reference module identity drift')
        reference.write_text(old.replace(module_anchor, 'module reference_workstation_tf_runtime_dma #(', 1))
        include = out / 'src/memory'
        include.mkdir(parents=True)
        (include / header.name).write_bytes(header.read_bytes())
        tb = out / 'four-state-arithmetic-rhs.sv'
        tb.write_text(four_state_testbench(base_tb.read_text()))
        result['runs'].append(simulate(out, 'four_state_arithmetic_rhs', SOURCE, reference, tb))
        for label, anchor, replacement in MUTATIONS:
            if text.count(anchor) != 1:
                raise ValueError('TF available source mutation anchor drift: ' + label)
            mutant = out / (label + '.sv')
            mutant.write_text(actual_text.replace(anchor, replacement, 1))
            result['runs'].append(simulate(out, label, mutant, reference, tb, negative=True))
        folder = out / 'response_cofactor'
        command = [sys.executable, '-B', str(old_runner), '--output', str(folder)]
        run = subprocess.run(command, capture_output=True, text=True, timeout=600)
        (out / 'response_cofactor.log').write_text(run.stdout + run.stderr)
        run.check_returncode()
        verification = folder / 'verification.json'
        record = json.loads(verification.read_text())
        if not record['passed'] or record['source_sha256'] != sha(SOURCE):
            raise ValueError('existing response cofactor did not verify actual maintained source')
        result['existing_regressions']['response_cofactor'] = dict(
            path=str(verification), sha256=sha(verification), passed=True,
            actual_source_sha256=record['source_sha256'],
            runs=len(record['runs']),
            negative_controls=sum(row.get('negative_control', False) for row in record['runs']),
            existing_regressions=record['existing_regressions'])
        print('PASS existing response, occupancy and threshold oracles on actual source', flush=True)
        if before != {str(path): sha(path) for path in inputs}:
            raise ValueError('TF available cofactor verification inputs changed during run')
        result.update(passed=True, inputs_unchanged=True, four_state_vectors=2097152,
                      four_state_contract='Known pending/full use the unchanged helper with exact original operands. Known partial implies known unsigned occupancy below32; pending X/Z keeps original arithmetic. Unknown pending/classification keeps original helper calls; final four-way default delta unchanged.',
                      limitations='Expression proof and bounded RTL simulation only. Additional alternatives may increase area or mux load. No synthesis, P&R, whole-netlist equivalence or hardware acceptance.')
    finally:
        (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    artifacts = {str(path): sha(path) for path in sorted(out.rglob('*')) if path.is_file()}
    (out / 'final-seal.json').write_text(json.dumps(dict(schema=1, passed=True,
        artifacts=artifacts, all_input_versions_preserved=True,
        no_physical_gain_claimed=True), indent=2) + '\n')
    print('PASS maintained TF available response cofactor', sha(SOURCE), 'seal=' + sha(out / 'final-seal.json'))


if __name__ == '__main__':
    main()
