"""Production clock monitors and switching composition with official GW5A DCS."""

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AudioClockDomain(unittest.TestCase):
    def test_production_monitor_defaults(self):
        with tempfile.TemporaryDirectory(prefix='workstation-clock-monitor-') as directory:
            binary = Path(directory) / 'simulation'
            result = subprocess.run(['iverilog', '-g2012', '-s', 'tb_workstation_audio_clock_monitor',
                '-o', str(binary), str(ROOT / 'sim/audio/tb_workstation_audio_clock_monitor.sv'),
                str(ROOT / 'rtl/audio/workstation_audio_clock_monitor.sv')],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS production clock monitor:', result.stdout)
            print(result.stdout.strip())

    def test_async_phases_frequency_and_failures(self):
        library = Path(os.environ.get('GOWIN_GW5A_SIMLIB',
            '/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/simlib/gw5a/prim_sim.v'))
        self.assertTrue(library.is_file(), 'GOWIN_GW5A_SIMLIB must identify the official gw5a/prim_sim.v')
        with tempfile.TemporaryDirectory(prefix='workstation-audio-clocks-') as directory:
            binary = Path(directory) / 'simulation'
            sources = ['sim/audio/tb_workstation_audio_clock_domain.sv',
                'rtl/audio/workstation_audio_clock_monitor.sv',
                'rtl/audio/workstation_audio_clock_domain.sv',
                'rtl/audio/workstation_sample_rate_switch.sv']
            result = subprocess.run(['iverilog', '-g2012', '-s', 'tb_workstation_audio_clock_domain',
                '-o', str(binary), *[str(ROOT / source) for source in sources], str(library)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for phase48, phase44 in ((3.7, 17.2), (0.001, 29.4), (39.8, 0.2)):
                with self.subTest(phase48=phase48, phase44=phase44):
                    result = subprocess.run(['vvp', str(binary), f'+PHASE48={phase48}', f'+PHASE44={phase44}'],
                        capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('PASS audio clock domain:', result.stdout)
                    print(result.stdout.strip())
            print(f'GW5A simulator SHA256={hashlib.sha256(library.read_bytes()).hexdigest()}')


if __name__ == '__main__':
    unittest.main()
