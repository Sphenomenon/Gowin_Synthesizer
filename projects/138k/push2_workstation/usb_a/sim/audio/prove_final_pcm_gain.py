#!/usr/bin/env python3
"""All-input bit-vector proof for the final PCM mute/slew factorization."""
import argparse
import hashlib
import json
from pathlib import Path
import re

import z3

ROOT = Path(__file__).resolve().parents[2]


def verify():
    source = ROOT / 'rtl/audio/workstation_final_pcm_router.sv'
    normalized = re.sub(r'\s+', '', source.read_text())
    # Bind the proved equations to the consumed maintained implementation.
    for anchor in (
        "wire[16:0]rate_step_product=17'd40960+{9'd0,gain_remainder};",
        "wire[8:0]gain_step=request_44k1_i?9'(rate_step_product/17'd147):9'd256;",
        "wire[16:0]gain_upper={1'b0,applied_gain}+{8'd0,gain_step};",
        "wire[16:0]gain_lower={1'b0,applied_gain}-{8'd0,gain_step};",
        "wire[15:0]slewed_gain=master_volume_i==0?16'd0:{1'b0,master_volume_i}>gain_upper?gain_upper[15:0]:!gain_lower[16]&&{1'b0,master_volume_i}<gain_lower?gain_lower[15:0]:master_volume_i;",
        "wire[15:0]next_gain=mute_i?16'd0:slewed_gain;",
        "if(request_44k1_i&&!mute_i&&master_volume_i!=0)gain_remainder<=8'(rate_step_product%17'd147);",
    ):
        if normalized.count(anchor) != 1:
            raise AssertionError('Gain source identity drift: ' + anchor)
    applied, volume = z3.BitVecs('applied volume', 16)
    remainder = z3.BitVec('remainder', 8)
    rate, mute = z3.Bools('rate mute')
    total = z3.BitVecVal(40960, 17) + z3.ZeroExt(9, remainder)
    step = z3.If(rate, z3.Extract(8, 0, z3.UDiv(total, 147)), z3.BitVecVal(256, 9))
    upper = z3.ZeroExt(1, applied) + z3.ZeroExt(8, step)
    lower = z3.ZeroExt(1, applied) - z3.ZeroExt(8, step)

    def slew(target, zero_immediate=True):
        body = z3.If(z3.UGT(z3.ZeroExt(1, target), upper), z3.Extract(15, 0, upper),
                     z3.If(z3.And(z3.Extract(16, 16, lower) == 0,
                                  z3.ULT(z3.ZeroExt(1, target), lower)),
                           z3.Extract(15, 0, lower), target))
        return z3.If(target == 0, z3.BitVecVal(0, 16), body) if zero_immediate else body

    old_target = z3.If(mute, z3.BitVecVal(0, 16), volume)
    old_gain = slew(old_target)
    new_gain = z3.If(mute, z3.BitVecVal(0, 16), slew(volume))
    next_remainder = z3.Extract(7, 0, z3.URem(total, 147))
    old_remainder = z3.If(z3.And(rate, old_target != 0), next_remainder, remainder)
    new_remainder = z3.If(z3.And(rate, z3.Not(mute), volume != 0), next_remainder, remainder)
    solver = z3.Solver()
    solver.add(z3.Or(old_gain != new_gain, old_remainder != new_remainder))
    if solver.check() != z3.unsat:
        raise AssertionError('Gain/remainder counterexample: ' + str(solver.model()))
    negatives = {}
    for name, mutant in (
        ('missing_mute', old_gain != slew(volume)),
        ('missing_immediate_zero', old_gain != z3.If(mute, z3.BitVecVal(0, 16), slew(volume, False))),
        ('muted_remainder_advances', old_remainder != z3.If(z3.And(rate, volume != 0), next_remainder, remainder)),
    ):
        check = z3.Solver()
        check.add(mutant)
        if check.check() != z3.sat:
            raise AssertionError('Undetected semantic mutation: ' + name)
        negatives[name] = str(check.model())
    return dict(passed=True, proof='unsat', arbitrary_input_bits=42,
                scope='Every 16-bit applied gain and master volume, 8-bit remainder, rate and mute; exact unsigned widths/wrap and both gain/remainder next-state',
                solver_version=z3.get_version_string(), source=str(source),
                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                semantic_negatives_rejected=negatives,
                hardware_tested=False, physical_timing_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify()
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('PASS final PCM gain: all 42 input bits; gain/remainder equivalent; 3 semantic mutants rejected')
