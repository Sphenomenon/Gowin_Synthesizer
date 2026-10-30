#!/usr/bin/env python3
"""Guard accepted CNN/DDR inputs against ongoing source work and drift."""
from pathlib import Path
import shutil
from unittest.mock import patch
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import workstation_sources as sources
from baseline_fixture import write_baseline
from workstation_baselines import load_baseline
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
        self.root = Path(self.temp.name) / 'repository/projects/138k/push2_workstation/usb_a'
        files = {}
        self.accepted = {}
        for name in sources.TIMING85_OVERLAYS + ('rtl/music/unchanged.sv', 'src/top.sv'):
            files[name] = name + '\n'
        fixture = write_baseline(self.root, 'timing85', files)
        self.project = fixture.project
        self.manifest = fixture.original
        self.inputs = fixture.inputs
        for name in self.inputs:
            if name.startswith('rtl/music/'):
                self.accepted[name] = 'old' if name in sources.TIMING85_OVERLAYS else self.inputs[name]
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


class AcceptedDdrSources(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repository/projects/138k/push2_workstation/usb_a'
        files = {staged: 'accepted ' + staged + '\n'
                 for staged, _ in sources.ACCEPTED_DDR_INPUTS.values()}
        self.fixture = write_baseline(self.root, 'accepted_full83', files)
        self.selected = {live: (staged, self.fixture.inputs[staged])
                         for live, (staged, _) in sources.ACCEPTED_DDR_INPUTS.items()}
        self.input_patch = patch.object(sources, 'ACCEPTED_DDR_INPUTS', self.selected)
        self.input_patch.start(); self.addCleanup(self.input_patch.stop)
        for live, (staged, _) in self.selected.items():
            path = self.root / live
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((self.fixture.project / staged).read_bytes())
        self.baseline = load_baseline(self.root, 'accepted_full83')

    def test_live_map_evolution_is_observed_without_changing_selected_bytes(self):
        live_map = self.root / sources.ACCEPTED_DDR_MAP
        live_map.write_text('new recording allocation\n')
        audit = sources.accepted_ddr_source_audit(self.root, self.baseline)
        stage = self.root / 'stage'
        self.baseline.materialize(stage)
        sources.verify_accepted_ddr_map(stage)
        staged, digest = self.selected[sources.ACCEPTED_DDR_MAP]
        self.assertEqual(sha(stage / staged), digest)
        self.assertEqual(audit['policy'], 'accepted_full83_locked_ddr')
        self.assertEqual(audit['selected_baseline'], 'accepted_full83')
        self.assertEqual(audit['selected_sha256'][staged], digest)
        self.assertEqual(audit['live_sha256'][sources.ACCEPTED_DDR_MAP], sha(live_map))
        self.assertNotEqual(audit['live_sha256'][sources.ACCEPTED_DDR_MAP], digest)
        self.assertEqual(audit['live_to_staged'][sources.ACCEPTED_DDR_MAP], staged)
        self.assertEqual(audit['live_observed_only'], [sources.ACCEPTED_DDR_MAP])
        self.assertEqual(set(audit['live_guarded']), self.selected.keys() - {sources.ACCEPTED_DDR_MAP})
        self.assertFalse(audit['live_ddr_overlay'])
        self.assertEqual(live_map.read_text(), 'new recording allocation\n')

    def test_missing_unselected_live_map_is_explicitly_observed(self):
        (self.root / sources.ACCEPTED_DDR_MAP).unlink()
        audit = sources.accepted_ddr_source_audit(self.root, self.baseline)
        self.assertIsNone(audit['live_sha256'][sources.ACCEPTED_DDR_MAP])

    def test_other_four_live_ddr_guards_reject_missing_or_changed_inputs(self):
        for live in self.selected.keys() - {sources.ACCEPTED_DDR_MAP}:
            path = self.root / live
            original = path.read_bytes()
            for action in ('changed', 'missing'):
                with self.subTest(live=live, action=action):
                    if action == 'changed':
                        path.write_text('unaccepted live DDR change\n')
                    else:
                        path.unlink()
                    with self.assertRaisesRegex(ValueError, 'accepted DDR input drift: ' + live):
                        sources.accepted_ddr_source_audit(self.root, self.baseline)
                    path.write_bytes(original)

    def test_locked_map_missing_or_corrupt_cannot_fall_back_to_valid_live_map(self):
        staged, _ = self.selected[sources.ACCEPTED_DDR_MAP]
        path = self.fixture.project / staged
        original = path.read_bytes()
        for action in ('changed', 'missing'):
            with self.subTest(action=action):
                if action == 'changed':
                    path.write_text('wrong locked map\n')
                else:
                    path.unlink()
                with self.assertRaisesRegex(ValueError, 'input tree drifted: ' + staged):
                    sources.accepted_ddr_source_audit(self.root, self.baseline)
                path.write_bytes(original)

    def test_rebound_locked_map_still_must_match_the_accepted_digest(self):
        staged, _ = self.selected[sources.ACCEPTED_DDR_MAP]
        files = {name: (self.fixture.project / name).read_bytes() for name in self.fixture.inputs}
        files[staged] = b'rebound locked map\n'
        write_baseline(self.root, 'accepted_full83', files)
        rebound = load_baseline(self.root, 'accepted_full83')
        with self.assertRaisesRegex(ValueError, 'accepted DDR baseline input drift: ' + staged):
            sources.accepted_ddr_source_audit(self.root, rebound)

    def test_map_omitted_from_locked_inputs_cannot_fall_back_to_live_map(self):
        staged, _ = self.selected[sources.ACCEPTED_DDR_MAP]
        files = {name: (self.fixture.project / name).read_bytes()
                 for name in self.fixture.inputs if name != staged}
        write_baseline(self.root, 'accepted_full83', files)
        incomplete = load_baseline(self.root, 'accepted_full83')
        with self.assertRaisesRegex(ValueError, 'accepted DDR baseline input missing: ' + staged):
            sources.accepted_ddr_source_audit(self.root, incomplete)

    def test_final_stage_map_cannot_be_changed_or_removed_by_overlays(self):
        stage = self.root / 'stage'
        self.baseline.materialize(stage)
        staged, _ = self.selected[sources.ACCEPTED_DDR_MAP]
        path = stage / staged
        for action in ('changed', 'missing'):
            with self.subTest(action=action):
                if action == 'changed':
                    path.write_text('unaccepted map overlay\n')
                else:
                    path.unlink()
                with self.assertRaisesRegex(ValueError, 'accepted DDR staged map drift: ' + staged):
                    sources.verify_accepted_ddr_map(stage)


if __name__ == '__main__':
    unittest.main()
