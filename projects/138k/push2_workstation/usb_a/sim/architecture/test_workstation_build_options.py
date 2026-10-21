import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import build_resource_rework as builder


class ResourceBuildOptions(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name)
        self.stage = self.output / 'Prj1'
        (self.stage / 'scripts').mkdir(parents=True)
        (self.stage / 'rtl/music').mkdir(parents=True)
        (self.stage / 'scripts/build.tcl').write_text(
            'open_project [file join $root Prj1.gprj]\n'
            'set_option -place_option 2\n'
            'set_option -route_option 0\n')
        (self.stage / 'rtl/music/basic_pitch_workstation_link.sv').write_text(
            '.WIN_LEN(44100),.FRAME_LIMIT(8),.OCTAVE_LIMIT(9),\n'
            '.CQT_HOP_NUMERATOR(22050),.CQT_HOP_DENOMINATOR(4),\n'
            ".FEATURE_TILE_COLS(16),.COARSE_GUIDANCE(1'b1), u_trace_cdc\n")

    def prepare(self, *options):
        arguments = ['build_resource_rework.py', '--flow', 'prepare', *options]
        metadata = {'candidate': 'resource_rework_4hz_tiles_spatial'}
        with patch.object(sys, 'argv', arguments), patch.object(
                builder, 'prepare', return_value=(self.output, self.stage, metadata)), \
                contextlib.redirect_stdout(io.StringIO()):
            builder.main()
        return json.loads((self.output / 'build_metadata.json').read_text())

    def test_replication_is_explicit_and_hash_bound(self):
        metadata = self.prepare('--replicate-resources', '--route-option', '1')
        self.assertTrue(metadata['replicate_resources'])
        self.assertEqual(metadata['route_option'], 1)
        script = self.stage / 'scripts/build.tcl'
        self.assertEqual(script.read_text().count('set_option -replicate_resources 1'), 1)
        inputs = json.loads((self.output / 'workstation_inputs.json').read_text())
        self.assertEqual(inputs['scripts/build.tcl'], builder.sha(script))

    def test_default_does_not_inherit_replication(self):
        self.prepare('--replicate-resources')
        metadata = self.prepare()
        self.assertFalse(metadata['replicate_resources'])
        self.assertNotIn('-replicate_resources', (self.stage / 'scripts/build.tcl').read_text())

    def test_explicit_placement_is_recorded_and_hash_bound(self):
        metadata = self.prepare('--place-option', '4')
        self.assertEqual(metadata['place_option'], 4)
        script = self.stage / 'scripts/build.tcl'
        self.assertEqual(script.read_text().count('set_option -place_option 4'), 1)
        inputs = json.loads((self.output / 'workstation_inputs.json').read_text())
        self.assertEqual(inputs['scripts/build.tcl'], builder.sha(script))

    def test_accepted_profile_rejects_placement_flag(self):
        process = subprocess.run(
            [sys.executable, str(ROOT / 'build.py'), '--current-workstation',
             '--prepare-only', '--place-option', '3'], capture_output=True, text=True)
        self.assertEqual(process.returncode, 2)
        self.assertIn('--place-option requires --resource-rework', process.stderr)

    def test_synthesis_fanout_is_explicit_and_hash_bound(self):
        metadata = self.prepare('--max-fanout', '64')
        self.assertEqual(metadata['synthesis_max_fanout'], 64)
        script = self.stage / 'scripts/build.tcl'
        self.assertEqual(script.read_text().count('set_option -max_fanout 64'), 1)
        inputs = json.loads((self.output / 'workstation_inputs.json').read_text())
        self.assertEqual(inputs['scripts/build.tcl'], builder.sha(script))
        metadata = self.prepare()
        self.assertIsNone(metadata['synthesis_max_fanout'])
        self.assertNotIn('-max_fanout', script.read_text())

    def test_accepted_profile_rejects_synthesis_fanout_flag(self):
        process = subprocess.run(
            [sys.executable, str(ROOT / 'build.py'), '--current-workstation',
             '--prepare-only', '--max-fanout', '64'], capture_output=True, text=True)
        self.assertEqual(process.returncode, 2)
        self.assertIn('--max-fanout requires --resource-rework', process.stderr)

    def test_invalid_synthesis_fanout_fails_before_preparation(self):
        with patch.object(sys, 'argv', ['builder', '--max-fanout', '0']), \
                patch.object(builder, 'prepare') as prepare, \
                contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit) as raised:
            builder.main()
        self.assertEqual(raised.exception.code, 2)
        prepare.assert_not_called()

    def test_accepted_profile_rejects_replication_flag(self):
        process = subprocess.run(
            [sys.executable, str(ROOT / 'build.py'), '--current-workstation',
             '--prepare-only', '--replicate-resources'], capture_output=True, text=True)
        self.assertEqual(process.returncode, 2)
        self.assertIn('--replicate-resources requires --resource-rework', process.stderr)

    def test_source_profiles_never_silently_mix(self):
        for options in [('--resource-rework', '--current-workstation'),
                        ('--resource-rework', '--cnn-timing85'),
                        ('--cnn-timing85',)]:
            with self.subTest(options=options):
                process = subprocess.run(
                    [sys.executable, str(ROOT / 'build.py'), '--prepare-only', *options],
                    capture_output=True, text=True)
                self.assertEqual(process.returncode, 2)
                self.assertIn('error:', process.stderr)

    def test_full_build_requires_identity_before_preparation(self):
        with patch.object(sys, 'argv', ['builder', '--flow', 'all']), \
                patch.object(builder, 'prepare') as prepare, \
                contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit) as raised:
            builder.main()
        self.assertEqual(raised.exception.code, 2)
        prepare.assert_not_called()

    def test_failed_physical_gate_exits_nonzero_despite_tool_success(self):
        with patch.object(builder.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)), \
                patch.object(builder, 'audit_outputs', return_value=False), \
                self.assertRaises(SystemExit) as raised:
            self.prepare('--flow', 'all', '--user-code', 'C11021F1')
        self.assertEqual(raised.exception.code, 2)
        result = json.loads((self.output / 'resource_all_result.json').read_text())
        self.assertTrue(result['passed'])

    def test_passed_physical_gate_finishes_successfully(self):
        with patch.object(builder.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)), \
                patch.object(builder, 'audit_outputs', return_value=True):
            metadata = self.prepare('--flow', 'all', '--user-code', 'C11021F2')
        self.assertEqual(metadata['user_code'], '0xC11021F2')


if __name__ == '__main__':
    unittest.main()
