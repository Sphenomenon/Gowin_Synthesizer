#!/usr/bin/env python3
"""Real C callback contract under every bounded access failure; no physical MMIO."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RecordingApi(unittest.TestCase):
    def test_real_c_api_bounded_accesses_and_failure_output_preservation(self):
        compiler = shutil.which('cc')
        if not compiler:
            self.skipTest('host C compiler unavailable')
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'recording_api'
            subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                '-I' + str(ROOT / 'firmware/ae350'),
                str(ROOT / 'firmware/ae350/recording_service.c'),
                str(ROOT / 'sim/ae350_recording_service_host.c'), '-o', str(executable)],
                check=True, capture_output=True, text=True, timeout=60)
            result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS recording API bounded failures', result.stdout)


if __name__ == '__main__':
    unittest.main()
