"""Real clock-domain/serializer startup and frame handshakes, without stub ACKs."""

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AudioClockI2s(unittest.TestCase):
    def test_real_startup_switch_and_fault_recovery(self):
        library = Path(os.environ.get('GOWIN_GW5A_SIMLIB',
            '/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/simlib/gw5a/prim_sim.v'))
        self.assertTrue(library.is_file(), 'GOWIN_GW5A_SIMLIB must identify official gw5a/prim_sim.v')
        with tempfile.TemporaryDirectory(prefix='workstation-clock-i2s-') as directory:
            binary = Path(directory) / 'simulation'
            names = ['sim/audio/tb_workstation_audio_clock_i2s.sv',
                'rtl/audio/workstation_audio_clock_monitor.sv', 'rtl/audio/workstation_audio_clock_domain.sv',
                'rtl/audio/workstation_sample_rate_switch.sv', 'rtl/audio/workstation_i2s_serializer.sv']
            result = subprocess.run(['iverilog', '-g2012', '-s', 'tb_workstation_audio_clock_i2s',
                '-o', str(binary), *[str(ROOT / name) for name in names], str(library)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=180)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS clock+I2S actual default', result.stdout)
            print(result.stdout.strip())
            print(f'GW5A simulator SHA256={hashlib.sha256(library.read_bytes()).hexdigest()}')


if __name__ == '__main__':
    unittest.main()
