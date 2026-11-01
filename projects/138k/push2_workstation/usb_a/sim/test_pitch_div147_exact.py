#!/usr/bin/env python3
"""Exact pitch partition proof, actual RTL domain sweep and negative controls."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RTL = ROOT / 'rtl/audio/workstation_rate_pitch_expression.sv'
TB = ROOT / 'sim/audio/tb_pitch_div147_exact.sv'


class PitchExact147(unittest.TestCase):
    def test_independent_integer_domain_proof(self):
        # For t=147*a+b, 0<=b<=146, multiplication adds t*17/(147*2^26).
        # t*17<2^26 keeps that error below1/147, so it cannot cross the next
        # integer even when b=146. The proof covers the whole closed interval,
        # a superset of all input pairs, without assuming a production CC5 cap.
        maximum = 13 * 65535 + 255
        scale = 1 << 26
        multiplier = (scale + 146) // 147
        excess = 147 * multiplier - scale
        self.assertEqual((maximum, multiplier, excess), (852210, 456523, 17))
        self.assertLess(maximum * excess, scale)
        for t in range(maximum + 1):
            q = (t * multiplier) >> 26
            self.assertEqual(q, t // 147, t)
            self.assertEqual(t - q * 147, t % 147, t)
        # Check the exact widths consumed by the implementation.
        self.assertLess(maximum, 1 << 20)
        self.assertLess(maximum * multiplier, 1 << 39)
        self.assertLess(maximum // 147, 1 << 13)
        self.assertEqual((160 * 65535 + 146) // 147, 71331)
        self.assertLess(71331, 1 << 17)
        self.assertGreater(71331, (1 << 16) - 1)
        # New hardware sums the independent quotient/remainder of four
        # nibble-weighted terms. Every table entry is constant at elaboration;
        # q*147+r reconstructs13*s, with a ten-bit final remainder sum.
        tables = [[divmod(13*(16**digit)*value,147) for value in range(16)]
                  for digit in range(4)]
        self.assertLess(sum(max(r for q,r in table) for table in tables)+255, 6*147)
        for step in range(65536):
            parts = [tables[d][(step>>(4*d))&15] for d in range(4)]
            self.assertEqual(sum(q for q,r in parts)*147+sum(r for q,r in parts),13*step)
        print('PROOF interval=0..852210 inputs=65536x256 partition=4x4 max_trial_carry=5')

    def simulate(self, source, quick=False):
        with tempfile.TemporaryDirectory(prefix='pitch-exact147-') as directory:
            directory = Path(directory)
            rtl = directory / RTL.name
            rtl.write_text(source)
            binary = directory / 'test.vvp'
            compile_result = subprocess.run(
                ['iverilog', '-g2012', '-s', 'tb_pitch_div147_exact', '-o', str(binary), str(rtl), str(TB)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(compile_result.returncode, 0, compile_result.stdout + compile_result.stderr)
            return subprocess.run(['vvp', str(binary)] + (['+QUICK'] if quick else []),
                                  capture_output=True, text=True, timeout=180)

    def test_actual_rtl_complete_input_domain_and_transactions(self):
        original = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (RTL, TB)}
        result = self.simulate(RTL.read_text())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('combinational_cases=16777220 transactions=40017', result.stdout)
        self.assertIn('PASS pitch exact147:', result.stdout)
        self.assertEqual(original, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (RTL, TB)})
        print(result.stdout, end='')
        for path, digest in original.items():
            print('SOURCE', path.relative_to(ROOT), 'SHA256=' + digest)

    def test_negative_controls_compile_then_fail_actual_rtl(self):
        source = RTL.read_text()
        cases = (
            ('digit_quotient', "13'((1*WEIGHT)/147)", "13'((1*WEIGHT)/147+1)", 'DOMAIN'),
            ('digit_remainder', "8'((1*WEIGHT)%147)", "8'((1*WEIGHT)%147+1)", 'DOMAIN'),
            ('trial_divisor', "11'(carry*147)", "11'(carry*148)", 'DOMAIN'),
            ('quotient_truncated', "{1'b0,glide_step_q20_i} + {4'd0,glide_extra_step}",
             "17'(16'({1'b0,glide_step_q20_i} + {4'd0,glide_extra_step}))", 'DOMAIN'),
            ('reset_bias_removed', "glide_remainder <= 8'd73;", "glide_remainder <= 8'd0;", 'RESET'),
            ('zero_step_clears_remainder', 'if (rate_44k1_i && glide_step_q20_i != 0)',
             "if (rate_44k1_i && glide_step_q20_i == 0) glide_remainder <= 8'd0;\n            else if (rate_44k1_i && glide_step_q20_i != 0)", 'STATE'),
            ('48k_updates_remainder', 'if (rate_44k1_i && glide_step_q20_i != 0)',
             'if (glide_step_q20_i != 0)', 'STATE'),
        )
        for name, old, new, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(source.count(old), 1)
                result = self.simulate(source.replace(old, new), quick=True)
                self.assertNotEqual(result.returncode, 0, name + ': ' + result.stdout + result.stderr)
                self.assertIn(expected, result.stdout + result.stderr)
                print('NEGATIVE', name, 'compiled_then_failed=' + expected)


if __name__ == '__main__':
    unittest.main()
