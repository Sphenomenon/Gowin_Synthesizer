#!/usr/bin/env python3
"""Verify current lineage and original affine arithmetic with Z3.

The maintained CSA function is checked by run_chorus_affine35_csa.py. This
earlier affine proof retains its exact grammar after the checked CSA inverse.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import z3

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.workstation_chorus_provenance import restore_affine35_csa
CURRENT = 'rtl/audio/workstation_runtime_chorus_effect.sv'
BEFORE = 'sim/audio/fixtures/chorus_before_affine44.sv'
CURRENT_SHA = '28ef32d47d55a0d44eef8ec23fa3437cdbef647d4ca0b023f98cb184bd8ce50c'
BEFORE_SHA = 'a2e09369634b35628920c3198b0020a51a0d4154fe690a2faf93465f8ff57900'


def sha(value):
    return hashlib.sha256(value).hexdigest()


def function(payload):
    matches = re.findall(r'  function automatic \[15:0\] rate_delay\(.*?  endfunction',
                         payload.decode(), re.S)
    if len(matches) != 1:
        raise ValueError('actual rate_delay function anchor drift')
    return re.sub(r'\s+', '', re.sub(r'//[^\n]*', '', matches[0]))


def extract(current, before):
    new_pattern = (r"functionautomatic\[15:0\]rate_delay\(input\[15:0\]triangle_value,inputlogicrate44\);"
        r"logic\[(?P<top>\d+):0\]rounded_phase44;logic\[17:0\]triangle_times3;beginif\(rate44\)begin"
        r"rounded_phase44=35'\(triangle_value\)\*35'd(?P<coefficient>\d+)\+35'd(?P<bias>\d+);"
        r"rate_delay=16'd(?P<base>\d+)\+16'\(rounded_phase44>>(?P<shift>\d+)\);endelsebegin"
        r"triangle_times3=18'\(triangle_value\)\*18'd3;rate_delay=16'd480\+16'\(triangle_times3>>11\);endendendfunction")
    old_pattern = (r"functionautomatic\[15:0\]rate_delay\(input\[15:0\]triangle_value,inputlogicrate44\);"
        r"logic\[24:0\]triangle_times441;logic\[27:0\]rounded_numerator44;logic\[11:0\]scaled_high44;"
        r"logic\[17:0\]triangle_times3;beginif\(rate44\)begin"
        r"triangle_times441=25'\(triangle_value\)\*25'd(?P<coefficient>\d+);"
        r"rounded_numerator44=28'd(?P<bias>\d+)\+\{3'd0,triangle_times441\};"
        r"scaled_high44=rounded_numerator44\[27:16\];rate_delay=16'\(scaled_high44/12'd(?P<divisor>\d+)\);endelsebegin"
        r"triangle_times3=18'\(triangle_value\)\*18'd3;rate_delay=16'd480\+16'\(triangle_times3>>11\);endendendfunction")
    new, old = re.fullmatch(new_pattern, current), re.fullmatch(old_pattern, before)
    if new is None or old is None:
        raise ValueError('actual arithmetic is outside the exact modeled SV grammar')
    return ({k: int(v) for k, v in new.groupdict().items()},
            {k: int(v) for k, v in old.groupdict().items()})


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    files = [ROOT / CURRENT, ROOT / BEFORE, Path(__file__).resolve(),
             ROOT / 'tools/workstation_chorus_provenance.py']
    hashes = {str(p): sha(p.read_bytes()) for p in files}
    normalized = restore_affine35_csa(files[0].read_bytes())
    if sha(normalized) != CURRENT_SHA or hashes[str(files[1])] != BEFORE_SHA:
        raise ValueError('reviewed actual source identity drift')
    new_function, old_function = function(normalized), function(files[1].read_bytes())
    new, old = extract(new_function, old_function)
    triangle = z3.BitVec('triangle', 16)
    old_product = z3.ZeroExt(9, triangle) * z3.BitVecVal(old['coefficient'], 25)
    old_sum = z3.BitVecVal(old['bias'], 28) + z3.ZeroExt(3, old_product)
    previous = z3.ZeroExt(4, z3.UDiv(z3.Extract(27, 16, old_sum), z3.BitVecVal(old['divisor'], 12)))

    def actual(parameters):
        # RHS is35 bits; assignment truncates only if the actual declaration
        # is narrower. Shift and final16-bit cast follow actual SV widths.
        rhs = z3.ZeroExt(19, triangle) * z3.BitVecVal(parameters['coefficient'], 35)
        rhs = rhs + z3.BitVecVal(parameters['bias'], 35)
        assigned = z3.Extract(parameters['top'], 0, rhs)
        shifted = z3.LShR(assigned, parameters['shift'])
        return z3.BitVecVal(parameters['base'], 16) + z3.Extract(15, 0, shifted)

    checks = []
    def check(name, proposition, expected, counterexample=False):
        solver = z3.Solver()
        solver.set(timeout=60000)
        solver.add(proposition)
        result = solver.check()
        (output / (name + '.smt2')).write_text(solver.to_smt2())
        if result != expected:
            raise ValueError(name + ': ' + str(result) + ' expected ' + str(expected))
        row = dict(name=name, result=str(result))
        if counterexample:
            model = solver.model()
            row['triangle'] = model.eval(triangle, model_completion=True).as_long()
        checks.append(row)
        return row

    check('all_16bit_44100_actual_old_new', previous != actual(new), z3.unsat)
    wide_triangle = z3.BV2Int(triangle)
    check('35bit_product_and_sum_cannot_overflow',
          wide_triangle * new['coefficient'] + new['bias'] >= (1 << (new['top'] + 1)), z3.unsat)
    # Both strict grammars contain the same untouched48k branch. Prove its
    # modeled18-bit arithmetic equals the independent exact integer tap rule.
    product48 = z3.ZeroExt(2, triangle) * z3.BitVecVal(3, 18)
    actual48 = 480 + z3.BV2Int(z3.LShR(product48, 11))
    check('all_16bit_48000_unchanged_exact_rule', actual48 != 480 + wide_triangle * 96 / 65536, z3.unsat)
    for name, key, value in [('wrong_coefficient', 'coefficient', 361266),
                             ('wrong_bias', 'bias', 134217728),
                             ('truncated_assignment', 'top', 33)]:
        mutant = dict(new, **{key: value})
        row = check(name, previous != actual(mutant), z3.sat, True)
        t = row['triangle']
        row['old_result'] = (old['bias'] + t * old['coefficient']) // (65536 * old['divisor'])
        row['mutant_result'] = mutant['base'] + (((t * mutant['coefficient'] + mutant['bias']) &
                                                ((1 << (mutant['top'] + 1)) - 1)) >> mutant['shift'])
        if row['old_result'] == row['mutant_result']:
            raise ValueError('SMT negative did not reproduce with independent integers')
    if any(sha(Path(p).read_bytes()) != value for p, value in hashes.items()):
        raise ValueError('proof input changed during verification')
    report = dict(schema=1, passed=True, z3_version=z3.get_version_string(), input_sha256=hashes,
                  normalized_affine_source_sha256=sha(normalized),
                  csa_inverse_checked=hashes[str(files[0])] != sha(normalized),
                  scope='Original affine proof after exact CSA inverse; current CSA arithmetic and actual-source proof are separate run_chorus_affine35_csa.py checks.',
                  exact_normalized_affine_function_sha256=sha(new_function.encode()),
                  exact_actual_current_function_sha256=sha(function(files[0].read_bytes()).encode()),
                  exact_old_function_sha256=sha(old_function.encode()), extracted_current=new,
                  extracted_old=old, checks=checks, triangle_domain_bits=16,
                  modeled_actual_SV_assignment_widths=True, added_registers=0,
                  physical_timing_verified=False, hardware_tested=False)
    target = output / 'verification.json'
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(passed=True, report=str(target), sha256=sha(target.read_bytes()))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
