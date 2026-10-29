"""Always-on switching transaction against the official GW5A DCS simulator."""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SampleRateSwitch(unittest.TestCase):
    def test_transaction_and_gowin_glitchless_selector(self):
        library = Path(os.environ.get('GOWIN_GW5A_SIMLIB',
            '/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/simlib/gw5a/prim_sim.v'))
        self.assertTrue(library.is_file(),
            'Set GOWIN_GW5A_SIMLIB to the official Gowin gw5a/prim_sim.v; a mux stub does not validate DCS')
        for command in ('iverilog', 'vvp'):
            self.assertIsNotNone(shutil.which(command), f'{command} must be installed and on PATH')
        with tempfile.TemporaryDirectory(prefix='workstation-rate-switch-') as directory:
            binary = Path(directory) / 'simulation'
            compile_result = subprocess.run([
                'iverilog', '-g2012', '-s', 'tb_workstation_sample_rate_switch',
                '-o', str(binary), str(ROOT / 'sim/audio/tb_workstation_sample_rate_switch.sv'),
                str(ROOT / 'rtl/audio/workstation_sample_rate_switch.sv'), str(library)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(compile_result.returncode, 0, compile_result.stdout + compile_result.stderr)
            result = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS sample-rate switch: official GW5A DCS', result.stdout)
            print(f'GW5A simulator SHA256={hashlib.sha256(library.read_bytes()).hexdigest()}')
            print(result.stdout.strip())


if __name__ == '__main__':
    unittest.main()
