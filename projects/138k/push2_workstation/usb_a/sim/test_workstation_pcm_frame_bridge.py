#!/usr/bin/env python3
"""Real serializer/PCM bridge diagnostics; bounded renderer, not DSP acceptance."""

import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PCMFrameBridgeTest(unittest.TestCase):
    def test_real_serializer_two_clock_offsets_and_phases(self):
        for executable in ('iverilog', 'vvp'):
            self.assertIsNotNone(shutil.which(executable), executable)
        sources = [ROOT / name for name in (
            'sim/audio/tb_workstation_pcm_frame_bridge.sv',
            'rtl/audio/workstation_pcm_frame_bridge.sv',
            'rtl/audio/workstation_i2s_serializer.sv')]
        before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
        for clock_case in (0, 1):
            with self.subTest(clock_case=clock_case), tempfile.TemporaryDirectory(prefix='pcm-frame-bridge-') as directory:
                binary = Path(directory) / 'bridge.vvp'
                result = subprocess.run(['iverilog', '-g2012', '-s', 'tb_workstation_pcm_frame_bridge',
                    f'-Ptb_workstation_pcm_frame_bridge.CLOCK_CASE={clock_case}', '-o', str(binary),
                    *map(str, sources)], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                result = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('PASS PCM frame bridge:', result.stdout)
                self.assertIn('SOURCE_ERRORS physical_zero_frames=4 prefill_and_running_both_rates=1 stopped_old_reply_preserved=1',
                              result.stdout)
                print(result.stdout.strip())
        self.assertEqual(before, {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
                         'bridge/serializer/TB changed during verification')
        for path, digest in before.items():
            print(f'SOURCE {Path(path).relative_to(ROOT)} SHA256={digest}')


if __name__ == '__main__':
    unittest.main()
