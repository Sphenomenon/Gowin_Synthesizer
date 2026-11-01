#!/usr/bin/env python3
"""Exact Session composition ancestry without rebasing delay provenance."""
from pathlib import Path
import copy
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_top_session_reference as adapter
from tools import workstation_delay_storage_provenance as storage
from tools import workstation_runtime_profile as runtime


class SessionTopReference(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / adapter.SOURCE).read_bytes()
        self.parent, self.evidence = adapter.restore_parent(self.source)

    def test_exact_committed_parent_and_both_directions(self):
        self.assertEqual(storage.REFERENCE_SHA256, '2c4376b7754a9b98486501fb91e258f5b70b4183b4ec5f687b2a588132ba7007')
        self.assertEqual(adapter.sha(self.source), adapter.SOURCE_SHA256)
        self.assertEqual(adapter.sha(self.parent), storage.REFERENCE_SHA256)
        self.assertEqual(self.evidence['exact_inverse_edits'], 4)
        self.assertEqual(self.evidence['round_trip_source_sha256'], adapter.SOURCE_SHA256)
        self.assertTrue(self.evidence['every_reverse_and_forward_anchor_unique'])
        self.assertFalse(self.evidence['input_source_rewritten'])
        for selector in adapter.SELECTORS:
            statement = ('defparam '+selector+'="block_ram";').encode()
            self.assertEqual(self.source.count(statement), 1)
            self.assertEqual(self.parent.count(statement), 1)

    def test_unknown_policy_and_any_unpinned_source_are_rejected(self):
        for policy in ('automatic_latest', '', None, False):
            with self.subTest(policy=policy), self.assertRaisesRegex(ValueError, 'Unknown.*policy'):
                adapter.restore_parent(self.source, policy)
        variants = [self.source+b'\n', self.parent,
                    self.source.replace(b'WORKSTATION_PUSH_RATE_CONTROL', b'OTHER_RATE_CONTROL'),
                    self.source.replace(b'RAM_STYLE="block_ram"', b'RAM_STYLE="distributed_ram"')]
        for source in variants:
            with self.subTest(source=adapter.sha(source)), self.assertRaisesRegex(ValueError, 'source identity'):
                adapter.restore_parent(source)

    def test_each_reverse_and_forward_anchor_must_be_unique(self):
        for index, (before, after) in enumerate(adapter.EXACT_CHANGES):
            for label, text in (('missing', self.source.decode().replace(after, '')),
                                ('duplicate', self.source.decode()+after)):
                with self.subTest(index=index, label=label), self.assertRaisesRegex(ValueError, 'anchor drift'):
                    adapter.replace_once(text, after, before, 'reverse')
            for label, text in (('missing', self.parent.decode().replace(before, '')),
                                ('duplicate', self.parent.decode()+before)):
                with self.subTest(index=index, label=label), self.assertRaisesRegex(ValueError, 'anchor drift'):
                    adapter.replace_once(text, before, after, 'forward')

    def test_unique_but_wrong_inverse_is_rejected_by_parent_hash(self):
        changes = list(adapter.EXACT_CHANGES)
        before, after = changes[0]
        changes[0] = (before+'// unreviewed inverse\n', after)
        with patch.object(adapter, 'EXACT_CHANGES', tuple(changes)):
            with self.assertRaisesRegex(ValueError, 'parent identity'):
                adapter.restore_parent(self.source)

    def make_fixture(self, directory, reference):
        root = Path(directory)
        paths = (storage.SOURCE, storage.PROVENANCE, storage.ADAPTATION, storage.FIFO,
                 storage.REFERENCE, storage.PREPARED_SOURCE, storage.DELAY_SCRATCH_SOURCE,
                 storage.DELAY_SCRATCH_PROVENANCE)
        for relative in paths:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(reference if relative == storage.REFERENCE else (ROOT / relative).read_bytes())
        return root

    def test_legacy_complete_bundle_and_manifests_remain_unchanged(self):
        with tempfile.TemporaryDirectory() as old_dir, tempfile.TemporaryDirectory() as new_dir:
            old_root = self.make_fixture(old_dir, self.parent)
            new_root = self.make_fixture(new_dir, self.source)
            original_inputs = {p: (new_root/p).read_bytes() for p in
                               (storage.PROVENANCE, storage.ADAPTATION, storage.DELAY_SCRATCH_PROVENANCE)}
            legacy = storage.source_bundle(old_root)
            current = storage.source_bundle(new_root)
            self.assertNotIn('storage_policy_reference_adaptation', legacy)
            self.assertEqual(current['storage_policy_reference_adaptation'], self.evidence)
            comparable = copy.deepcopy(current)
            del comparable['storage_policy_reference_adaptation']
            comparable['storage_policy_reference_sha256'] = adapter.PARENT_SHA256
            self.assertEqual(comparable, legacy)
            self.assertEqual(current['storage_policy_reference_sha256'], adapter.SOURCE_SHA256)
            self.assertEqual(original_inputs, {p: (new_root/p).read_bytes() for p in original_inputs})
            self.assertEqual((new_root/storage.REFERENCE).read_bytes(), self.source)

    def test_complete_bundle_refuses_unknown_top_and_manifest_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_fixture(directory, self.source)
            reference = root / storage.REFERENCE
            reference.write_bytes(self.source+b'\n')
            with self.assertRaisesRegex(ValueError, 'source identity'):
                storage.source_bundle(root)
            reference.write_bytes(self.source)
            for relative in (storage.PROVENANCE, storage.ADAPTATION, storage.DELAY_SCRATCH_PROVENANCE):
                path = root / relative
                original = path.read_bytes()
                path.write_bytes(original+b' ')
                with self.subTest(path=relative), self.assertRaises(ValueError):
                    storage.source_bundle(root)
                path.write_bytes(original)

    def test_new_adapter_is_a_single_explicit_source_dependency(self):
        self.assertEqual(runtime.DEPENDENCIES.count(adapter.TOOL), 1)


if __name__ == '__main__':
    unittest.main()
