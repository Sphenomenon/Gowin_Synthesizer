#!/usr/bin/env python3
"""Prove and simulate the maintained TF accepted-occupancy response cofactor.

The old pre-occupancy and capacity/threshold oracles remain separate and run
unchanged. This runner additionally checks the actual new selector equations,
the exact reviewed source inverse, and a complete-source four-state twin.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import z3
from tf_dma_read_preload_sources import (
    SOURCE_SHA256 as PRELOAD_SHA256, before_read_preload, apply_read_preload_to_test_mutant)
from run_tf_dma_available_response_cofactor import (
    ORIGINAL_AVAILABLE_LINES, available_cofactor_block, before_available_response_cofactor)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'sim/audio'))
from prove_effect_slot_admission import BooleanSV

SOURCE = ROOT / 'rtl/tf_audio/workstation_tf_runtime_dma.sv'
REFERENCE = Path(__file__).with_name('fixtures') / 'workstation_tf_runtime_dma_before_response_cofactor.sv'
SOURCE_SHA256 = '3f9eb8afa2c3308d270ce215693723bfb7cb48584ee96c3c3fbe749a4902e7b6'
REFERENCE_SHA256 = '5ac87cbacd1ddc35f897fdf7c3427f80bcf7b151e44370baae6fb3305a596d3b'
MUTATIONS = [
    ('drop_immediate_read',
     'read_response_without_write = app_rvalid && (read_pending || read_accept_without_write);',
     'read_response_without_write = app_rvalid && read_pending;'),
    ('invent_unpending_response',
     'read_response_pending_only = app_rvalid && read_pending;',
     'read_response_pending_only = app_rvalid;'),
    ('allow_new_read_with_write',
     "1'b1: next_accepted_used = accepted_pending_only;",
     "1'b1: next_accepted_used = accepted_without_write;"),
    ('lose_simultaneous_input',
     "2'b11: accepted_pending_only = accepted_after_input_read;",
     "2'b11: accepted_pending_only = accepted_after_read;"),
]
FOUR_STATE_MUTATIONS = [
    ('unknown_selection_fallback_lost',
     '            default: begin end\n        endcase\n    end\n',
     '            default: next_accepted_used = accepted_pending_only;\n        endcase\n    end\n'),
    ('zero_delta_pessimism_lost_new_branch',
     "2'b00: accepted_without_write = add_occupancy_delta(accepted_used, 7'd0);",
     '2\'b00: accepted_without_write = accepted_used;'),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def one(text, pattern):
    values = re.findall(pattern, text, re.S)
    if len(values) != 1:
        raise ValueError('TF cofactor source anchor drift: ' + pattern)
    return values[0]


def before_response_cofactor(text):
    """Recover only the reviewed baseline; reject any source or anchor drift."""
    if hashlib.sha256(text.encode()).hexdigest() != SOURCE_SHA256:
        # The later available-response insertion has its own exact full-file
        # gate. Reverse only that reviewed hunk, then retain the original
        # response-cofactor source pin and complete baseline inverse below.
        text = before_available_response_cofactor(text)
    if hashlib.sha256(text.encode()).hexdigest() != SOURCE_SHA256:
        raise ValueError('maintained TF response-cofactor source identity changed')
    block = one(text, r'(    // Compute both read-response cofactors.*?)(?=    reg \[31:0\] next_available_bytes)')
    tail = one(text, r"(        case \(write_selected\)\n            1'b0: next_accepted_used.*?        endcase\n)")
    restored = text.replace(block, '', 1).replace(tail, '', 1)
    if hashlib.sha256(restored.encode()).hexdigest() != REFERENCE_SHA256:
        raise ValueError('exact pre-response-cofactor reconstruction changed')
    return restored


def response_mutant(text, anchor, replacement):
    """Apply the unchanged response mutant before restoring the later hunk.

    The later combinational case has a matching default/endcase spelling;
    derive mutants in the original pinned source to keep the original unique
    anchor and oracle, then simulate both cofactors in the actual module.
    """
    preloaded = hashlib.sha256(text.encode()).hexdigest() == PRELOAD_SHA256
    if preloaded:
        text = before_read_preload(text)
    block = None
    if hashlib.sha256(text.encode()).hexdigest() != SOURCE_SHA256:
        block = available_cofactor_block(text)
        text = before_available_response_cofactor(text)
    if text.count(anchor) != 1:
        raise ValueError('TF cofactor source mutation anchor drift')
    mutant = text.replace(anchor, replacement, 1)
    if block is not None:
        if mutant.count(ORIGINAL_AVAILABLE_LINES) != 1:
            raise ValueError('TF available cofactor mutation reconstruction drift')
        mutant = mutant.replace(ORIGINAL_AVAILABLE_LINES, block, 1)
    return apply_read_preload_to_test_mutant(mutant) if preloaded else mutant


def equation(text, name):
    return one(text, r'\bwire\s+' + re.escape(name) + r'\s*=\s*(.*?);')


def case_rows(text, selector, target):
    body = one(text, r'case \(' + re.escape(selector) + r'\)(.*?)endcase')
    rows = re.findall(r"2'b([01]{2}):\s*" + target + r'\s*=\s*(.*?);', body)
    fallback = one(body, r'default:\s*' + target + r'\s*=\s*(.*?);')
    if len(rows) != 4 or set(k for k, _ in rows) != {'00', '01', '10', '11'}:
        raise ValueError('TF cofactor case inventory changed: ' + target)
    return dict(rows), fallback


def selector_model(text):
    # Lift the four unchanged arithmetic results to independent 32-bit words.
    # This is stronger than their real arithmetic relationship. The exact
    # inverse separately checks every existing arithmetic definition and NBA.
    names = ('mem_ready runtime_hold_i write_pending ring_can_commit stream_started '
             'read_pending read_buf_valid fifo_out_full read_has_full_beat '
             'read_has_partial_beat app_rdy app_rvalid input_byte_accepted').split()
    env = {name: z3.Bool(name) for name in names}
    env.update(state=z3.BitVec('state', 2), S_STREAM=z3.BitVecVal(0, 2))
    equations = {}
    for name in ('write_selected', 'read_request', 'read_accept', 'read_response',
                 'read_request_without_write', 'read_accept_without_write',
                 'read_response_without_write', 'read_response_pending_only'):
        equations[name] = equation(text, name)
        env[name] = BooleanSV(equations[name], env).result()
    candidates = {name: z3.BitVec(name, 32) for name in
                  ('accepted_after_read', 'accepted_after_input', 'accepted_after_input_read')}
    candidates["add_occupancy_delta(accepted_used, 7'd0)"] = z3.BitVec('hold_after_zero_delta', 32)

    def mux(selector, target, response):
        rows, fallback = case_rows(text, selector, target)
        if fallback != 'add_occupancy_delta(accepted_used, accepted_delta)':
            raise ValueError('TF cofactor four-state fallback changed: ' + target)
        values = {key: candidates[value] for key, value in rows.items()}
        return z3.If(env['input_byte_accepted'],
                     z3.If(response, values['11'], values['10']),
                     z3.If(response, values['01'], values['00']))

    original = mux('{input_byte_accepted, read_response}', 'next_accepted_used', env['read_response'])
    without = mux('{input_byte_accepted, read_response_without_write}',
                  'accepted_without_write', env['read_response_without_write'])
    pending = mux('{input_byte_accepted, read_response_pending_only}',
                  'accepted_pending_only', env['read_response_pending_only'])
    body = one(text, r'case \(write_selected\)(.*?)endcase')
    branches = dict(re.findall(r"1'b([01]):\s*next_accepted_used\s*=\s*(\w+);", body))
    if set(branches) != {'0', '1'} or re.sub(r'\s+', '', one(body, r'default:(.*)')) != 'beginend':
        raise ValueError('TF cofactor final selection/fallback changed')
    targets = {'accepted_without_write': without, 'accepted_pending_only': pending}
    final = z3.If(env['write_selected'], targets[branches['1']], targets[branches['0']])
    return env, original, final, equations


def binary_proof(text):
    env, original, final, equations = selector_model(text)
    rows = []
    for label, condition in [
            ('read_response_when_selected', z3.And(env['write_selected'],
                env['read_response'] != env['read_response_pending_only'])),
            ('read_response_without_write', z3.And(z3.Not(env['write_selected']),
                env['read_response'] != env['read_response_without_write'])),
            ('new_read_excludes_selected_write', z3.And(env['write_selected'], env['read_accept'])),
            ('accepted_next_arbitrary_candidates', original != final)]:
        solver = z3.Solver()
        solver.add(condition)
        status = str(solver.check()).upper()
        if status != 'UNSAT':
            raise ValueError('actual TF cofactor differs: ' + label)
        rows.append(dict(label=label, result=status))
    for label, anchor, replacement in MUTATIONS:
        if text.count(anchor) != 1:
            raise ValueError('TF cofactor binary mutant anchor drift: ' + label)
        _, original, final, _ = selector_model(text.replace(anchor, replacement, 1))
        solver = z3.Solver()
        solver.add(original != final)
        status = str(solver.check()).upper()
        if status != 'SAT':
            raise ValueError('TF cofactor binary mutant escaped: ' + label)
        rows.append(dict(negative=label, result=status, counterexample=str(solver.model())))
    return dict(rows=rows, actual_source_equations=equations, free_bits=143,
                arithmetic_candidates='four arbitrary independent 32-bit unchanged RHS values',
                unreachable_state_assumptions=False, arbitrary_four_state_proof=False,
                z3_version=z3.get_version_string())


def simulate(out, label, path, reference, tb, negative=False):
    binary = out / (label + '.vvp')
    command = ['iverilog', '-g2012', '-I', str(out), '-s', 'tf_response_four',
               '-o', str(binary), str(path), str(reference), str(tb)]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (out / (label + '_compile.log')).write_text(compiled.stdout + compiled.stderr)
    compiled.check_returncode()
    run = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=180)
    log = run.stdout + run.stderr
    log_path = out / (label + '.log')
    log_path.write_text(log)
    passed = (run.returncode != 0 and 'cofactor four-state differs' in log) if negative else (
        run.returncode == 0 and 'PASS actual DMA cofactor four-state vectors=1048576' in log)
    if not passed:
        raise ValueError(label + ' failed: ' + log)
    print(label, log.strip(), flush=True)
    return dict(label=label, negative_control=negative, passed=passed,
                command=command, exit_code=run.returncode, output=log.strip(),
                binary_sha256=sha(binary), log_sha256=sha(log_path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    tb = Path(__file__).with_name('tb_tf_dma_response_cofactor_four_state.sv')
    header = ROOT / 'rtl/ddr_address_map.vh'
    scripts = {name: Path(__file__).with_name('run_tf_dma_' + name + '.py')
               for name in ('occupancy_equivalence', 'threshold_groups')}
    inputs = [SOURCE, REFERENCE, Path(__file__).resolve(), tb, header,
              Path(__file__).with_name('tf_dma_read_preload_sources.py'),
              Path(__file__).with_name('fixtures') / 'workstation_tf_runtime_dma_before_read_preload.sv',
              Path(__file__).with_name('run_tf_dma_available_response_cofactor.py'),
              Path(__file__).with_name('fixtures') / 'workstation_tf_runtime_dma_before_available_response_cofactor.sv',
              ROOT / 'sim/audio/prove_effect_slot_admission.py',
              ROOT / 'tools/test_cnn_tf_write_buffer_retime.py',
              ROOT / 'tools/cnn_ddr_pipeline_patch.py',
              Path(__file__).with_name('fixtures') / 'workstation_tf_runtime_dma_pre_occupancy.sv',
              Path(__file__).with_name('tb_tf_dma_occupancy_equivalence.sv'),
              Path(__file__).with_name('tb_tf_dma_threshold_groups.sv'),
              Path(__file__).with_name('tb_tf_audio_ddr_dma.sv'), *scripts.values()]
    before = {str(path): sha(path) for path in inputs}
    snapshots = {}
    for path in inputs:
        copy = out / 'inputs' / path.relative_to(ROOT)
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(path.read_bytes())
        snapshots[str(path)] = dict(path=str(copy), sha256=sha(copy))
    result = dict(schema=1, passed=False, source_sha256=sha(SOURCE),
                  fixture_sha256=sha(REFERENCE), input_sha256=before, input_snapshots=snapshots,
                  source_implementation=True, synthesis=False, pnr=False, hardware_tested=False,
                  timing_or_resource_gain_claimed=False, runs=[], existing_regressions={})
    try:
        if sha(REFERENCE) != REFERENCE_SHA256:
            raise ValueError('pinned pre-response-cofactor fixture changed')
        text = SOURCE.read_text()
        old = before_response_cofactor(text)
        if old != REFERENCE.read_text():
            raise ValueError('reviewed inverse is not the entire pinned module')
        nba = lambda value: re.findall(r'\b(\w+(?:\[[^]]+\])?)\s*<=\s*([^;]+);', value)
        if nba(before_read_preload(text)) != nba(old):
            raise ValueError('TF cofactor changed sequential target/RHS/order')
        result.update(exact_source_inverse=True, NBA_targets_RHS_order_identical=True,
                      reviewed_private_preload_inverse_sha256=hashlib.sha256(before_read_preload(text).encode()).hexdigest(),
                      actual_preloaded_module_simulated=True,
                      binary=binary_proof(text))
        result['source_drift_controls'] = []
        for label, anchor in [('candidate_drift', '    reg [31:0] accepted_without_write'),
                              ('selection_drift', "1'b1: next_accepted_used = accepted_pending_only;")]:
            if text.count(anchor) != 1:
                raise ValueError('TF cofactor drift-control anchor changed')
            try:
                before_response_cofactor(text.replace(anchor, anchor + ' ', 1))
            except ValueError:
                result['source_drift_controls'].append(dict(label=label, rejected=True))
            else:
                raise ValueError('TF cofactor source gate accepted drift')
        reference = out / 'reference.sv'
        anchor = 'module workstation_tf_runtime_dma #('
        if old.count(anchor) != 1:
            raise ValueError('TF cofactor reference module identity drift')
        reference.write_text(old.replace(anchor, 'module reference_workstation_tf_runtime_dma #(', 1))
        include = out / 'src/memory'
        include.mkdir(parents=True)
        (include / header.name).write_bytes(header.read_bytes())
        result['runs'].append(simulate(out, 'four_state', SOURCE, reference, tb))
        for label, anchor, replacement in MUTATIONS + FOUR_STATE_MUTATIONS:
            mutant = out / (label + '.sv')
            mutant.write_text(response_mutant(text, anchor, replacement))
            result['runs'].append(simulate(out, label, mutant, reference, tb, negative=True))
        # Do not normalize or replace either existing oracle. Both consume
        # the actual maintained source and retain every old negative control.
        for name, script in scripts.items():
            folder = out / name
            command = [sys.executable, '-B', str(script), '--output', str(folder)]
            run = subprocess.run(command, capture_output=True, text=True, timeout=300)
            (out / (name + '.log')).write_text(run.stdout + run.stderr)
            run.check_returncode()
            verification = folder / 'verification.json'
            record = json.loads(verification.read_text())
            if not record['passed']:
                raise ValueError('existing TF regression failed: ' + name)
            result['existing_regressions'][name] = dict(path=str(verification),
                sha256=sha(verification), passed=True, runs=len(record['runs']),
                negative_controls=sum(row.get('negative_control', False) for row in record['runs']))
            print('PASS unchanged existing', name, 'runs=' + str(len(record['runs'])), flush=True)
        if before != {str(path): sha(path) for path in inputs}:
            raise ValueError('TF cofactor verification inputs changed during run')
        result.update(passed=True, inputs_unchanged=True)
    finally:
        (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    artifacts = {str(path): sha(path) for path in sorted(out.rglob('*')) if path.is_file()}
    (out / 'final-seal.json').write_text(json.dumps(dict(schema=1, passed=True,
        artifacts=artifacts, all_input_versions_preserved=True,
        no_physical_gain_claimed=True), indent=2) + '\n')
    print('PASS maintained TF response cofactor', sha(SOURCE), 'seal=' + sha(out / 'final-seal.json'))


if __name__ == '__main__':
    main()
