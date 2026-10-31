#!/usr/bin/env python3
"""Check same-cycle grouped TF admission against its original four-state equations."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import z3

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prove_equations():
    # Equality, relations and parity use the same unknown semantics for X/Z.
    # Encode scalar 0/1/X as 0/1/2; the SV test also checks returned Z slices.
    upper, known, capacity = z3.BitVecs('upper known capacity', 26)

    def equal4(value, mask, constant, width):
        mismatch = (mask & (value ^ constant)) != 0
        return z3.If(mismatch, 0, z3.If(mask == (1 << width) - 1, 1, 2))

    def and4(parts):
        return z3.If(z3.Or(*[x == 0 for x in parts]), 0,
                     z3.If(z3.And(*[x == 1 for x in parts]), 1, 2))

    parts = [equal4(z3.Extract(hi, lo, upper), z3.Extract(hi, lo, known),
                    z3.Extract(hi, lo, capacity), hi - lo + 1)
             for hi, lo in ((5, 0), (12, 6), (19, 13), (25, 20))]
    value, mask = z3.BitVecs('available available_known', 32)
    original_full = z3.If(mask == 0xffffffff, z3.If(z3.UGE(value, 32), 1, 0), 2)
    grouped_full = z3.If(mask == 0xffffffff,
                        z3.If(z3.Extract(31, 5, value) != 0, 1, 0), original_full)
    less = z3.If(mask == 0xffffffff, z3.If(z3.ULT(value, 32), 1, 0), 2)
    complement = z3.If(grouped_full == 0, 1, z3.If(grouped_full == 1, 0, 2))
    pairs = {
        'capacity26_equality_groups_four_state':
            (equal4(upper, known, capacity, 26), and4(parts)),
        'full32_groups_with_relational_unknown_fallback': (original_full, grouped_full),
        'chunk_less32_equals_not_guarded_full': (less, complement),
    }
    results = {}
    for label, (old, new) in pairs.items():
        solver = z3.Solver()
        solver.add(old != new)
        results[label] = str(solver.check()).upper()
        if results[label] != 'UNSAT':
            raise ValueError('TF threshold expression differs: ' + label)
    return dict(results=results, z3_version=z3.get_version_string(),
                capacity_free_bits=78, threshold_free_bits=64,
                scope='Expression algebra, not formal SystemVerilog elaboration',
                reachability_assumptions=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'rtl/tf_audio/workstation_tf_runtime_dma.sv'
    tb = Path(__file__).with_name('tb_tf_dma_threshold_groups.sv')
    header = ROOT / 'rtl/ddr_address_map.vh'
    inputs = [source, tb, header, Path(__file__).resolve()]
    before = {str(p): sha(p) for p in inputs}
    result = dict(passed=False, input_sha256=before, symbolic=prove_equations(),
                  hardware_tested=False, mapping_verified=False,
                  routed_timing_verified=False, runs=[])
    mutations = {
        'full_unknown_fallback_lost':
            ("default: read_has_full_beat = (available_bytes >= 32'd32);",
             'default: read_has_full_beat = available_full_binary;'),
        'full_bit31_lost':
            ('assign available_full_group_3 = |available_bytes[31:26];',
             'assign available_full_group_3 = |available_bytes[30:26];'),
        'capacity_group2_lost':
            ('upper_equal = upper_equal_0 && upper_equal_1 && upper_equal_2 && upper_equal_3;',
             'upper_equal = upper_equal_0 && upper_equal_1 && upper_equal_3;'),
        'chunk_guard_lost':
            ('(eof_finalized && !read_has_full_beat) ?',
             '(eof_finalized && !available_full_binary) ?'),
    }
    try:
        include = out / 'src/memory'
        include.mkdir(parents=True)
        (include / header.name).write_bytes(header.read_bytes())
        for label, bank in [('scaled', 64), ('hardware_capacity', 67108864)] + [
                (name, 67108864) for name in mutations]:
            selected = source
            if label in mutations:
                anchor, replacement = mutations[label]
                text = source.read_text()
                if text.count(anchor) != 1:
                    raise ValueError('TF threshold mutation anchor drift: ' + label)
                selected = out / (label + '.sv')
                selected.write_text(text.replace(anchor, replacement))
            binary = out / (label + '.vvp')
            command = ['iverilog', '-g2012', '-I', str(out), '-s', 'tb_tf_dma_threshold_groups',
                       '-Ptb_tf_dma_threshold_groups.BANK_BYTES=' + str(bank),
                       '-o', str(binary), str(selected), str(tb)]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
            (out / (label + '_compile.log')).write_text(compiled.stdout + compiled.stderr)
            compiled.check_returncode()
            run = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=90)
            log = run.stdout + run.stderr
            (out / (label + '.log')).write_text(log)
            negative = label in mutations
            passed = (run.returncode != 0 and 'threshold ' in log and ' differs ' in log) if negative else (
                run.returncode == 0 and 'PASS threshold capacity four-state:' in log)
            result['runs'].append(dict(label=label, bank_bytes=bank, passed=passed,
                                       negative_control=negative, exit_code=run.returncode,
                                       command=command, output=log.strip()))
            if not passed:
                raise ValueError(label + ' failed: ' + log)
            print(label, log.strip(), flush=True)
        if before != {str(p): sha(p) for p in inputs}:
            raise ValueError('TF threshold verification inputs changed')
        result.update(passed=True, inputs_unchanged=True)
    finally:
        (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
