#!/usr/bin/env python3
"""Compare native runtime controls with the actual locked48k implementation."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_baselines import load_baseline


class RuntimePitch(unittest.TestCase):
    def test_locked_equivalence_and_physical_time(self):
        reference = load_baseline(ROOT, 'resource_rework_route0').read_bytes('legacy/rtl/audio/pitch_expression.sv')
        self.assertEqual(hashlib.sha256(reference).hexdigest(),
                         'f91e15e3a8768a8bfd86877dc1fd8b6e50a0e9f8a8a8e56c5541cbdaae098591')
        sources = [ROOT/'rtl/audio/workstation_rate_pitch_expression.sv',
                   ROOT/'sim/audio/tb_workstation_rate_pitch_expression.sv']
        inputs = sources + [Path(__file__).resolve()]
        hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
        with tempfile.TemporaryDirectory(prefix='workstation-runtime-pitch-') as directory:
            directory = Path(directory)
            parent = directory/'pitch_expression.sv'; parent.write_bytes(reference)
            binary = directory/'pitch.vvp'
            r = subprocess.run(['iverilog', '-g2012', '-s', 'tb_workstation_rate_pitch_expression', '-o', str(binary),
                                str(parent), *map(str,sources)], capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
            r = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
            self.assertIn('PASS runtime pitch:', r.stdout)
            print(r.stdout)
            original = sources[0].read_text()
            for name,before,after in (
                ('upward_boundary', "upward_test={1'b0,upward_distance}-{6'd0,current_glide_step}-23'd1;",
                 "upward_test={1'b0,upward_distance}-{6'd0,current_glide_step}-23'd2;"),
                ('zero_step', 'if (glide_step_q20_i == 0)', 'if (glide_step_q20_i == 1)')):
                self.assertEqual(original.count(before), 1)
                mutant = directory / (name + '.sv')
                mutant.write_text(original.replace(before, after))
                negative = directory / (name + '.vvp')
                r = subprocess.run(['iverilog','-g2012','-s','tb_workstation_rate_pitch_expression',
                    '-o',str(negative),str(parent),str(mutant),str(sources[1])],
                    capture_output=True,text=True,timeout=30)
                self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
                r = subprocess.run(['vvp',str(negative)],capture_output=True,text=True,timeout=60)
                self.assertNotEqual(r.returncode, 0, name+' escaped')
                self.assertTrue('independent pitch mismatch' in r.stdout or '48k differs from locked reference' in r.stdout,
                                r.stdout+r.stderr)
                print('REJECTED',name,r.stdout.strip().splitlines()[0])
        self.assertEqual(hashes, {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs})
        for name,digest in hashes.items(): print('SOURCE', name, 'SHA256='+digest)


if __name__ == '__main__': unittest.main()
