"""Exact annotation and actual cancellation replica faults; explicit fixture."""
from copy import deepcopy
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_cancel_fanout as fanout
from tools.workstation_native_protocol_audit import protocol_netlist


class CancelReplication(unittest.TestCase):
    def stage(self):
        selected = os.environ.get('GW138K_CANCEL_FANOUT_STAGE')
        if not selected:
            self.skipTest('explicit complete M synthesis stage required')
        return Path(selected)

    def test_exact_inverse_and_selection(self):
        selected = (self.stage() / fanout.DESTINATION).read_text()
        parent = fanout.restore(selected)
        self.assertEqual(fanout.digest(parent), fanout.PARENT_SHA256)
        with self.assertRaises(ValueError):
            fanout.restore(selected + '\n')
        with self.assertRaises(ValueError):
            fanout.configured({fanout.KEY: fanout.POLICY, 'demo_role': 'W'})
        configuration = {fanout.KEY: fanout.POLICY, 'demo_role': 'M',
                         'event_admission_policy':
                         'task3_M_combined_sample_event_admission_v1'}
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / fanout.DESTINATION
            p.parent.mkdir(parents=True)
            p.write_text(parent)
            self.assertIsNone(fanout.select(directory, {}))
            self.assertEqual(p.read_text(), parent)
            receipt = fanout.select(directory, configuration)
            self.assertEqual(p.read_text(), selected)
            self.assertEqual(receipt['added_cycles'], 0)
            with self.assertRaises(ValueError):
                fanout.select(directory, configuration)

    def test_actual_inputs_init_fanout_and_inventory(self):
        path = self.stage() / 'impl/gwsynthesis/custom_138k_integration.vg'
        original = path.read_bytes()
        n = protocol_netlist(original.decode(), mapping='synthesis')
        configuration = json.loads((self.stage().parent.parent /
            'workstation_profile.json').read_text())['configuration']
        from tools.workstation_reader_validated_metadata import configured
        result = fanout.audit(n, configuration)
        self.assertEqual(len(result['replicas']), 11 if configured(configuration) else 12)
        self.assertLessEqual(result['max_fanout'], 128)
        p = result['replicas'][0]['register']
        for part, key, value in [('ports', 'D', "1'b0"),
                                 ('ports', 'CE', "1'b0"),
                                 ('ports', 'CLEAR', "1'b0"),
                                 ('ports', 'CLK', "1'b0"),
                                 ('parameters', 'INIT', "1'b1")]:
            saved = deepcopy(n.cells[p])
            try:
                n.cells[p][part][key] = value
                with self.subTest(pin=key), self.assertRaises(ValueError):
                    fanout.audit(n, configuration)
            finally:
                n.cells[p] = saved
        saved = n.cells.pop(p)
        try:
            with self.assertRaises(ValueError):
                fanout.audit(n, configuration)
        finally:
            n.cells[p] = saved
        self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
