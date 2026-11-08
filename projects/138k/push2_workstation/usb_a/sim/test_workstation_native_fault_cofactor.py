"""Diagnostic-only selection, complete wiring and exact lineage controls."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_native_fault_cofactor as repair
from tools import workstation_ble_pack_cofactor as pack
from tools import workstation_ble_terminal_tuple as terminal_tuple
from tools import workstation_ble_terminal_cofactor as terminal
from tools import workstation_ble_completion_publication as publication


class NativeFaultSelection(unittest.TestCase):
    def configuration(self):
        return {repair.KEY: repair.POLICY, pack.KEY: pack.POLICY,
                terminal_tuple.KEY: terminal_tuple.POLICY, terminal.KEY: terminal.POLICY,
                publication.KEY: publication.POLICY, 'demo_role': 'W',
                'preboard_cdc_policy': 'task3_W_proven_release_and_CNN_drain_CDC_v1'}

    def copy_sources(self, directory):
        stage = Path(directory)
        for source in repair.manifest()['sources']:
            path = stage / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / source).read_bytes())
        return stage

    def select(self, stage):
        config = self.configuration()
        for older in (publication, terminal, terminal_tuple, pack):
            older.select(stage, config)
        return repair.select(stage, config)

    def test_selection_and_complete_lineage(self):
        raw = (ROOT / repair.SOURCE).read_text()
        parent = repair.restore_raw(raw)
        for older in (pack, terminal_tuple, terminal, publication):
            self.assertEqual(older.restore(raw), older.restore(parent))
        for source, row in repair.manifest()['sources'].items():
            text = (ROOT / source).read_text()
            self.assertEqual(repair.digest(repair.restore(source, text)), row['parent_sha256'])
        with tempfile.TemporaryDirectory() as directory:
            stage = self.copy_sources(directory)
            self.assertIsNone(repair.select(stage, {}))
            receipt = self.select(stage)
            self.assertTrue(receipt['diagnostic_probes_only'])
            self.assertEqual(receipt['added_state_bits'], 0)
            self.assertEqual(set(receipt['source_sha256']), set(repair.manifest()['sources']))
            self.assertEqual(repair.restore_raw((stage / repair.SOURCE).read_text()), parent)
            with self.assertRaises(ValueError):
                repair.select(stage, self.configuration())

    def test_reject_partial_selection(self):
        config = self.configuration()
        for bad in ({repair.KEY: 'unknown'}, dict(config, demo_role='M'),
                    dict(config, raw_pack_policy=None), dict(config, raw_completion_policy=None)):
            with self.assertRaises(ValueError):
                repair.configured(bad)

    def test_reject_authority_or_wiring_changes(self):
        controls = [
            ('rtl/memory/workstation_recording_ddr_arbiter_pipeline.sv',
             'assign native_accept_o[client]=app_en', 'assign native_accept_o[client]=native_fault_probe'),
            ('rtl/memory/workstation_recording_ddr_client_queues.sv',
             '.app_ready_fault_probe_i(app_ready_fault_probe_i)', '.app_ready_fault_probe_i(app_ready)'),
            ('rtl/memory/workstation_media_memory.sv',
             '.app_ready(app_ready_i && !transport_fault_o)', '.app_ready(app_ready_i)'),
            ('rtl/workstation/workstation_task3_w_paired.sv',
             '.native_accept_i(native_accept_o[8])', '.native_accept_i(recording_native_fault_probe)'),
            (repair.SOURCE, 'memory_fault_now=transport_fault_i || fault_without_transport;',
             'memory_fault_now=fault_without_transport;'),
        ]
        for source, before, after in controls:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as directory:
                stage = self.copy_sources(directory)
                self.select(stage)
                path = stage / source
                text = path.read_text()
                self.assertEqual(text.count(before), 1)
                path.write_text(text.replace(before, after, 1))
                with self.assertRaises(ValueError):
                    repair.evidence(stage, self.configuration())


if __name__ == '__main__':
    unittest.main(verbosity=2)
