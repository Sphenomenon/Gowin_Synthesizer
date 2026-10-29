#!/usr/bin/env python3
"""Display snapshot equivalence, stalled packets and real score guidance."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_SHA = 'b686f65d6e3fd67237861da95624bc3685de8bb691533b73c82503ee431d955d'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LightsSnapshot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('iverilog') or not shutil.which('vvp'):
            raise RuntimeError('Icarus Verilog is required')
        cls.temp = tempfile.TemporaryDirectory(prefix='push2-lights-snapshot-')
        cls.output = Path(cls.temp.name)
        original = ROOT / f'baselines/objects/{REFERENCE_SHA}.sv'
        if sha(original) != REFERENCE_SHA:
            raise ValueError('original locked lights bytes changed')
        text = original.read_text()
        if text.count('module push2_lights(') != 1:
            raise ValueError('test-only reference module anchor changed')
        reference = cls.output / 'reference.sv'
        reference.write_text(text.replace('module push2_lights(', 'module push2_lights_reference('))
        lights = ROOT / 'rtl/push2/push2_lights.sv'
        controls = ROOT / 'rtl/audio/push2_controls.sv'
        guide = ROOT / 'rtl/push2/push2_score_guide.sv'
        tb = ROOT / 'sim/guidance/tb_push2_lights_snapshot.sv'
        actual = ROOT / 'sim/guidance/tb_guidance.sv'
        cls.hashes = {path: sha(path) for path in (original, lights, controls, guide, tb, actual)}
        cases = {'snapshot': ('tb_push2_lights_snapshot', [tb, lights, reference]),
                 'guidance': ('tb_guidance', [actual, controls, guide, lights])}
        cls.binaries = {}
        for name, (top, sources) in cases.items():
            binary = cls.output / name
            result = subprocess.run(['iverilog', '-g2012', '-s', top, '-o', str(binary),
                                     *map(str, sources)], capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            cls.binaries[name] = binary

    @classmethod
    def tearDownClass(cls):
        for path, expected in cls.hashes.items():
            if sha(path) != expected:
                raise ValueError('verification source drifted: ' + str(path))
        cls.temp.cleanup()

    def run_case(self, name, expected):
        result = subprocess.run(['vvp', str(self.binaries[name])], capture_output=True,
                                text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(expected, result.stdout)
        print(result.stdout.strip())

    def test_original_startup_and_final_LED_state_arbitrary_stalls_updates_reset(self):
        self.run_case('snapshot', 'PASS lights snapshot')

    def test_existing_CNN_score_to_LED_guidance_contract(self):
        self.run_case('guidance', 'PASS guidance: CNN list')


if __name__ == '__main__':
    unittest.main()
