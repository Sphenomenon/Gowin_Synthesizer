"""Merged storage lineage must reject drift and retain the original delay chain."""
from pathlib import Path
import hashlib
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_pr2_storage_reference as adapter
from tools import workstation_delay_storage_provenance as storage


class MergedStorageReference(unittest.TestCase):
    def test_complete_delay_chain_without_rewriting_sources(self):
        paths = (*adapter.RECORDS, storage.PROVENANCE, storage.ADAPTATION)
        before = {p: (ROOT / p).read_bytes() for p in paths}
        evidence = storage.source_bundle(ROOT)
        self.assertEqual(set(evidence['pr2_storage_reference_adaptations']), {storage.FIFO, storage.REFERENCE})
        self.assertTrue(evidence['original_locked_prepared_slice_verified'])
        self.assertFalse(evidence['accepted_baseline_storage_selection_inherited'])
        self.assertEqual(before, {p: (ROOT / p).read_bytes() for p in paths})
        fifo, _ = adapter.restore_parent(before[storage.FIFO], storage.FIFO)
        self.assertEqual(hashlib.sha256(fifo).hexdigest(), storage.FIFO_SHA256)
        self.assertIn(b'parameter bit SMALL_DISTRIBUTED=0', before[storage.FIFO])

    def test_cnn_branches_restore_the_existing_stream_pitch_chain(self):
        from tools import workstation_stream_pitch_provenance as pitch
        self.assertEqual(pitch.source_bundle(ROOT)['stage'], 'stream_pitch')
        for relative in ('rtl/audio/gw138k_event_workstation.sv', 'rtl/control/workstation_parameters.sv'):
            source = (ROOT / relative).read_bytes()
            parent, _ = adapter.restore_parent(source, relative)
            self.assertEqual(pitch.normalize_source(relative, source), pitch.normalize_source(relative, parent))

    def test_custom_header_does_not_stop_at_nested_parameter_else(self):
        from tools.workstation_runtime_cdc import custom_board_header
        source = (ROOT / storage.REFERENCE).read_text()
        selected = custom_board_header(source)
        self.assertIn("wire button1_n=1'b1;", selected)
        self.assertNotIn('module gw138k_push_workstation_top', selected)
        # A declaration in the alternate board branch cannot satisfy the gate.
        moved = source.replace("    wire button1_n=1'b1;\n", '')
        moved = moved.replace('module gw138k_push_workstation_top',
                              "wire button1_n=1'b1;\nmodule gw138k_push_workstation_top")
        self.assertNotIn("wire button1_n=1'b1;", custom_board_header(moved))

    def test_unrelated_edit_and_changed_default_are_rejected(self):
        for relative in adapter.RECORDS:
            source = (ROOT / relative).read_bytes()
            variants = [source + b'\n']
            if relative == storage.FIFO:
                variants.append(source.replace(b'SMALL_DISTRIBUTED=0', b'SMALL_DISTRIBUTED=1'))
            for mutant in variants:
                with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, 'source identity'):
                    adapter.restore_parent(mutant, relative)

    def test_rebased_hash_cannot_hide_wrong_inverse(self):
        for relative, record in adapter.RECORDS.items():
            changed = dict(record)
            edits = list(record['edits'])
            before, after = edits[0]
            edits[0] = (before + '// unrelated change\n', after)
            changed['edits'] = tuple(edits)
            with patch.dict(adapter.RECORDS, {relative: changed}):
                with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, 'parent identity'):
                    adapter.restore_parent((ROOT / relative).read_bytes(), relative)


if __name__ == '__main__':
    unittest.main()
