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
        hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
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
        self.assertEqual(hashes, {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
        for name,digest in hashes.items(): print('SOURCE', name, 'SHA256='+digest)


if __name__ == '__main__': unittest.main()
