#!/usr/bin/env python3
"""Guard the boundary between accepted CNN inputs and ongoing source work."""
from pathlib import Path
import shutil
import json
from unittest.mock import patch
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import workstation_sources as sources
from workstation_sources import accepted_cnn_inputs, cnn_source_audit, sha, verify_cnn_inputs


class AcceptedCnnSources(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.baseline = self.root / 'accepted'
        self.live = self.root / 'live'
        self.inputs = {}
        for name, text in {'rtl/music/core.sv': 'accepted core\n',
                           'rtl/music/cache.sv': 'accepted cache\n',
                           'src/top.sv': 'accepted top\n'}.items():
            path = self.baseline / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            self.inputs[name] = sha(path)
        shutil.copytree(self.baseline, self.live)

    def test_live_changes_are_reported_without_changing_selected_inputs(self):
        (self.live / 'rtl/music/core.sv').write_text('ongoing optimization\n')
        (self.live / 'rtl/music/flash.sv').write_text('ongoing flash boot\n')
        selected = accepted_cnn_inputs(self.baseline, self.inputs)
        audit = cnn_source_audit(self.live, selected)
        self.assertEqual(audit['policy'], 'accepted_full83')
        self.assertEqual(audit['changed'], ['rtl/music/core.sv'])
        self.assertEqual(audit['added'], ['rtl/music/flash.sv'])
        self.assertEqual(audit['missing'], [])
        self.assertFalse(audit['live_cnn_overlay'])
        self.assertEqual(selected['rtl/music/core.sv'], self.inputs['rtl/music/core.sv'])
        self.assertNotIn('rtl/music/flash.sv', selected)
        verify_cnn_inputs(self.baseline, selected)

    def test_missing_live_source_does_not_change_accepted_build(self):
        (self.live / 'rtl/music/cache.sv').unlink()
        selected = accepted_cnn_inputs(self.baseline, self.inputs)
        self.assertEqual(cnn_source_audit(self.live, selected)['missing'], ['rtl/music/cache.sv'])
        verify_cnn_inputs(self.baseline, selected)

    def test_missing_or_corrupt_accepted_inputs_fail_including_non_cnn(self):
        for name in ('rtl/music/core.sv', 'src/top.sv'):
            path = self.baseline / name
            original = path.read_bytes()
            for action in ('corrupt', 'missing'):
                with self.subTest(name=name, action=action):
                    if action == 'corrupt':
                        path.write_text('wrong input\n')
                    else:
                        path.unlink()
                    with self.assertRaisesRegex(ValueError, 'accepted input tree drifted: ' + name):
                        accepted_cnn_inputs(self.baseline, self.inputs)
                    path.write_bytes(original)

    def test_unlisted_baseline_cnn_is_rejected(self):
        (self.baseline / 'rtl/music/extra.svh').write_text('implicit include\n')
        with self.assertRaisesRegex(ValueError, "added.*rtl/music/extra.svh"):
            accepted_cnn_inputs(self.baseline, self.inputs)

    def test_missing_cnn_manifest_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'manifest has no CNN files'):
            accepted_cnn_inputs(self.baseline, {'src/top.sv': self.inputs['src/top.sv']})

    def test_overlay_cannot_add_modify_or_remove_accepted_cnn(self):
        selected = accepted_cnn_inputs(self.baseline, self.inputs)
        for action in ('added', 'changed', 'missing'):
            with self.subTest(action=action):
                stage = self.root / action
                shutil.copytree(self.baseline, stage)
                path = stage / 'rtl/music/core.sv'
                if action == 'added':
                    (stage / 'rtl/music/new.sv').write_text('unaccepted overlay\n')
                elif action == 'changed':
                    path.write_text('unaccepted optimization\n')
                else:
                    path.unlink()
                with self.assertRaisesRegex(ValueError, 'accepted CNN input mismatch:'):
                    verify_cnn_inputs(stage, selected)


class PinnedTimingSources(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snapshot = self.root / 'snapshot'
        self.project = self.snapshot / 'Prj1'
        self.inputs = {}
        self.accepted = {}
        for name in sources.TIMING85_OVERLAYS + ('rtl/music/unchanged.sv', 'src/top.sv'):
            path = self.project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(name + '\n')
            self.inputs[name] = sha(path)
            if name.startswith('rtl/music/'):
                self.accepted[name] = 'old' if name in sources.TIMING85_OVERLAYS else self.inputs[name]
        self.manifest = self.snapshot / 'workstation_inputs.json'
        self.manifest.write_text(json.dumps(self.inputs))
        self.path_patch = patch.object(sources, 'TIMING85_BUILD', 'snapshot')
        self.path_patch.start(); self.addCleanup(self.path_patch.stop)
        self.hash_patch = patch.object(sources, 'TIMING85_MANIFEST_SHA256', sha(self.manifest))
        self.hash_patch.start(); self.addCleanup(self.hash_patch.stop)

    def test_exact_six_are_selected(self):
        selected = sources.timing85_cnn_inputs(self.root, self.accepted)
        self.assertEqual(selected, {n: h for n, h in self.inputs.items() if n.startswith('rtl/music/')})
        self.assertEqual(self.accepted[sources.TIMING85_OVERLAYS[0]], 'old')

    def test_manifest_drift_is_rejected(self):
        self.manifest.write_text(self.manifest.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'manifest is missing or changed'):
            sources.timing85_cnn_inputs(self.root, self.accepted)

    def test_snapshot_input_drift_is_rejected_even_outside_cnn(self):
        (self.project / 'src/top.sv').write_text('corrupt')
        with self.assertRaisesRegex(ValueError, 'input tree drifted: src/top.sv'):
            sources.timing85_cnn_inputs(self.root, self.accepted)

    def test_seventh_overlay_or_missing_patch_is_rejected(self):
        for name in ('rtl/music/unchanged.sv', sources.TIMING85_OVERLAYS[0]):
            accepted = dict(self.accepted)
            accepted[name] = 'other' if name.endswith('unchanged.sv') else self.inputs[name]
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'exceed the six fixed overlays'):
                sources.timing85_cnn_inputs(self.root, accepted)


if __name__ == '__main__':
    unittest.main()
