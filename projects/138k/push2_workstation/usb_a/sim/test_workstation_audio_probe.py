#!/usr/bin/env python3
"""Probe source closure, unknown SDK refusal and actual top-level CDC/I2S."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_audio_probe as probe


class AudioProbeTest(unittest.TestCase):
    def test_prepare_closure_and_drift_refusal(self):
        with tempfile.TemporaryDirectory(prefix='audio-probe-prepare-') as directory:
            output = Path(directory) / 'candidate'
            with mock.patch.object(subprocess, 'run', wraps=subprocess.run) as calls:
                result = probe.prepare(output, 'C11030B1')
            self.assertTrue(all(call.args[0][0] == 'git' for call in calls.call_args_list),
                            'prepare must never run EDA/capture/programmer')
            self.assertEqual(result['validation_stage'], 'prepare_only')
            self.assertFalse(result['full_workstation'])
            self.assertFalse(result['physical_audit_complete'])
            self.assertEqual(probe.verify(output)['source_paths'], result['source_paths'])
            document = probe.ET.parse(output / 'debug/audio_probe.gao')
            self.assertEqual(document.find('AoCore').get('sample_clock'), 'clk_50mhz')
            self.assertEqual(len(document.findall('.//Bus/Signal')), 800)
            with self.assertRaises(FileExistsError):
                probe.prepare(output, 'C11030B1')
            with self.assertRaises(ValueError):
                probe.prepare(Path(directory) / 'reserved', 'C11028E5')
            source = output / result['source_paths'][0]
            original = source.read_bytes()
            source.write_bytes(original + b'// deliberate drift\n')
            with self.assertRaisesRegex(ValueError, 'Prepared probe input changed'):
                probe.verify(output)
            source.write_bytes(original)
            extra = output / 'rtl/unlisted.sv'
            extra.write_text('module unlisted; endmodule\n')
            with self.assertRaisesRegex(ValueError, 'Unexpected/missing staged probe RTL'):
                probe.verify(output)
            print('PASS audio probe prepare: explicit five-source closure,800-bit50MHz GAO, checked pins, new UserCode/output, tamper/extra-source refusal; no EDA or board access')

    def test_unknown_sdk_is_explicitly_blocked(self):
        with tempfile.TemporaryDirectory(prefix='audio-probe-sdk-') as directory:
            output = Path(directory) / 'candidate'
            result = probe.prepare(output, 'C11030B2', Path(directory) / 'unknown-sdk')
            self.assertTrue(result['build_blocked'])
            self.assertIn('No false-path fallback', result['sdk_capability']['blocker'])
            with mock.patch.object(subprocess, 'run', side_effect=AssertionError('EDA must not run')):
                with self.assertRaisesRegex(ValueError, 'Unverified SDK dual-master'):
                    probe.build(output)
            print('PASS audio probe unknown SDK: explicit dual-master support blocker, build refuses before EDA; no false-path fallback')

    def test_actual_probe_top(self):
        for executable in ('iverilog', 'vvp'):
            self.assertIsNotNone(shutil.which(executable), executable)
        library = probe.DEFAULT_IDE / 'simlib/gw5a/prim_sim.v'
        self.assertTrue(library.is_file())
        config = probe.load_config(ROOT)
        with tempfile.TemporaryDirectory(prefix='audio-probe-sim-') as directory:
            binary = Path(directory) / 'probe.vvp'
            result = subprocess.run(['iverilog', '-g2012', '-s', 'tb_workstation_audio_probe',
                '-o', str(binary), str(ROOT / 'sim/audio/tb_workstation_audio_probe.sv'),
                *[str(ROOT / name) for name in config['source_paths']], str(library)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS standalone muted audio probe', result.stdout)
            print(result.stdout.strip())
            print('GW5A simulator SHA256=' + hashlib.sha256(library.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
