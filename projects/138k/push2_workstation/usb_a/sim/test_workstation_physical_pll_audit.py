#!/usr/bin/env python3
"""Reject evidence drift before and during the maintained physical PLL gate."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from workstation_physical_pll_audit import physical_snapshot, sha, verify_unchanged


class InputBindingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.input = self.root / 'physical.sdc'
        self.input.write_text('original constraint\n')
        self.route = self.root / 'routed.sdf'
        self.route.write_text('original routed delay\n')
        self.manifest = self.root / 'physical_inputs.json'
        self.manifest.write_text(json.dumps({'identity': 'test-physical',
                                            'input_sha256': {'physical.sdc': sha(self.input)}}))

    def snapshot(self):
        return physical_snapshot(self.root, (self.route,))

    def test_unchanged_inputs_pass(self):
        inputs, snapshot = self.snapshot()
        self.assertEqual(inputs['identity'], 'test-physical')
        verify_unchanged(snapshot)

    def test_reject_initial_input_drift(self):
        self.input.write_text('changed before audit\n')
        with self.assertRaisesRegex(ValueError, 'Physical input drift'):
            self.snapshot()

    def test_reject_manifest_mutation_even_if_still_valid_json(self):
        inputs, snapshot = self.snapshot()
        self.manifest.write_text(self.manifest.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'physical_inputs.json'):
            verify_unchanged(snapshot)

    def test_reject_physical_input_mutation(self):
        inputs, snapshot = self.snapshot()
        self.input.write_text('changed during audit\n')
        with self.assertRaisesRegex(ValueError, 'physical.sdc'):
            verify_unchanged(snapshot)

    def test_reject_routed_evidence_mutation(self):
        inputs, snapshot = self.snapshot()
        self.route.write_text('changed during audit\n')
        with self.assertRaisesRegex(ValueError, 'routed.sdf'):
            verify_unchanged(snapshot)

    def test_reject_manifest_path_escape(self):
        self.manifest.write_text(json.dumps({'input_sha256': {'../outside': 'unused'}}))
        with self.assertRaisesRegex(ValueError, 'Physical input drift'):
            self.snapshot()


if __name__ == '__main__':
    unittest.main()
