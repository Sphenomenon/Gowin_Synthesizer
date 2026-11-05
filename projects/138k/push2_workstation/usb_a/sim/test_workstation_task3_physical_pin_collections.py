#!/usr/bin/env python3
"""Check the physical selector repair against an explicit real Gowin probe."""
from pathlib import Path
import hashlib
import json
import os
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_custom_board_implementation import task3_pin_collections


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ActualPhysicalPins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stage = os.environ.get('GW138K_TASK3_PHYSICAL_PIN_STAGE')
        probe = os.environ.get('GW138K_TASK3_PHYSICAL_PIN_PROBE')
        if not stage or not probe:
            raise unittest.SkipTest('explicit actual source and Gowin physical probe required')
        cls.stage, cls.probe = Path(stage), Path(probe)
        vg = cls.stage/'impl/gwsynthesis/custom_138k_integration.vg'
        sdc = cls.stage/'constraints/custom_138k.sdc'
        cls.vg, cls.sdc = vg.read_text(), sdc.read_bytes()
        cls.inputs = {str(p): sha(p) for p in (vg, sdc,
            cls.probe/'physical.sdc', cls.probe/'custom_138k_integration.vg',
            ROOT/'tools/workstation_custom_board_implementation.py', Path(__file__))}
        cls.evidence = dict(rejections=[], routed_vector_arcs_verified=False,
            physical_CDC_accepted=False, routed_timing_verified=False, hardware_tested=False)

    def setUp(self):
        type(self).result = self._outcome.result

    @classmethod
    def tearDownClass(cls):
        unchanged = cls.inputs == {p: sha(Path(p)) for p in cls.inputs}
        target = os.environ.get('GW138K_TASK3_PHYSICAL_PIN_EVIDENCE')
        if target:
            path = Path(target)
            assert not path.exists(), 'never overwrite evidence'
            path.write_text(json.dumps(dict(cls.evidence, passed=cls.result.wasSuccessful() and unchanged,
                input_sha256=cls.inputs, inputs_unchanged=unchanged,
                negative_control_count=len(cls.evidence['rejections'])), indent=2)+'\n')
        assert unchanged, 'sealed source/probe or implementation changed during checks'

    def reject(self, label, payload=None, vg=None):
        with self.assertRaises(ValueError) as error:
            task3_pin_collections(self.sdc if payload is None else payload,
                                  self.vg if vg is None else vg)
        self.evidence['rejections'].append(dict(case=label, error=str(error.exception), rejected=True))

    def test_01_matches_actual_vendor_probe_and_retains_commands(self):
        adapted, receipt = task3_pin_collections(self.sdc, self.vg)
        self.assertEqual(adapted, (self.probe/'physical.sdc').read_bytes())
        self.assertEqual(self.inputs[str(self.stage/'impl/gwsynthesis/custom_138k_integration.vg')],
                         self.inputs[str(self.probe/'custom_138k_integration.vg')])
        log = (self.probe/'implementation.log').read_text()
        self.assertIn('Running placement', log)
        self.assertNotIn('TA2003', log)
        self.assertEqual(len(receipt['changes']), 17)
        scalar = [r for r in receipt['changes'] if r['kind'] == 'explicit_scalar_FF_Q']
        vector = [r for r in receipt['changes'] if r['kind'] == 'RAM16SDP4_vector_collection']
        self.assertEqual(len(scalar), 15)
        self.assertTrue(all(len(r['native_endpoints']) == 1 for r in scalar))
        self.assertEqual(len(vector), 2)
        self.assertTrue(all(len(r['native_endpoints']) == 27 and r['vector_width'] == 4 for r in vector))
        self.assertTrue(receipt['logical_native_endpoint_sets_unchanged'])
        self.assertTrue(receipt['non_query_bytes_unchanged'])
        self.assertFalse(receipt['clocks_or_budgets_or_exception_scope_relaxed'])
        self.evidence['positive'] = receipt

    def test_02_missing_broad_duplicate_and_unreviewed_selectors_reject(self):
        scalar = b'u_tf_audio/status_request_s[0-9]*/Q'
        ram = b'u_tf_audio/frames/frames_0/g_small_head.memory_g_small_head.memory_0_*_s/DO'
        self.reject('missing scalar query', self.sdc.replace(scalar, b'missing/Q'))
        self.reject('broader scalar query', self.sdc.replace(scalar, b'u_tf_audio/status_request_s*/Q'))
        self.reject('extra reviewed query', self.sdc+b'\nset_false_path -from [get_pins {'+scalar+b'}]\n')
        self.reject('unreviewed numeric class', self.sdc+b'\nset_false_path -from [get_pins {other_s[0-9]*/Q}]\n')
        self.reject('missing RAM vector', self.sdc.replace(ram, b'missing/DO'))
        self.reject('RAM already broadened without receipt', self.sdc.replace(ram, ram+b'*'))

    def test_03_changed_actual_cell_kind_and_vector_interface_reject(self):
        self.assertIn('RAM16SDP4', self.vg)
        self.reject('unsupported RAM kind', vg=self.vg.replace('RAM16SDP4', 'RAM16SDP2'))
        changed = re.sub(r'\.RAD\s*\(', '.RAD_EXTRA(', self.vg)
        self.assertNotEqual(changed, self.vg)
        self.reject('changed RAM vector interface', vg=changed)


if __name__ == '__main__':
    unittest.main()
