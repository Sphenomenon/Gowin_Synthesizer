#!/usr/bin/env python3
"""Actual VG CPU-source reset inventory and opaque input-cone comparison."""
from pathlib import Path
import copy
import hashlib
import json
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_task3_m_cpu_source_boundary import (
    audit, CPU_BLACKBOX, OPAQUE_PINS, SCOPE, STATE_REFS)
from tools.workstation_task3_peripheral_releases_audit import (
    PAIRED_CPU_SOURCE_CLOSURE, PAIRED_CPU_DESTINATION_CLOSURE)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ActualCpuSourceBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = {}
        cls.actual = {}
        for label in ('BATCH', 'REFERENCE'):
            selected = os.environ.get('GW138K_TASK3_M_CPU_SOURCE_' + label + '_STAGE')
            if not selected:
                raise unittest.SkipTest('explicit actual batch and historical source-sealed stages required')
            stage = Path(selected).resolve()
            vg = stage / 'impl/gwsynthesis/custom_138k_integration.vg'
            cls.inputs[str(vg)] = sha(vg)
            cls.actual[label] = protocol_netlist(vg.read_text(), mapping='synthesis')
        cls.inputs.update({str(p): sha(p) for p in (
            Path(__file__), ROOT/'tools/workstation_task3_m_cpu_source_boundary.py',
            ROOT/'tools/workstation_task3_peripheral_releases_audit.py',
            ROOT/'tools/workstation_task3_m_paired_releases_audit.py')})
        cls.evidence = dict(positive=audit(cls.actual['BATCH'], reference=cls.actual['REFERENCE']),
                            rejections=[])

    def setUp(self):
        type(self).result = self._outcome.result

    @classmethod
    def tearDownClass(cls):
        unchanged = cls.inputs == {p: sha(p) for p in cls.inputs}
        target = os.environ.get('GW138K_TASK3_M_CPU_SOURCE_EVIDENCE')
        if target:
            path = Path(target)
            assert not path.exists(), 'never overwrite an existing evidence receipt'
            path.write_text(json.dumps(dict(cls.evidence,
                passed=cls.result.wasSuccessful() and unchanged,
                input_sha256=cls.inputs, inputs_unchanged=unchanged,
                negative_control_count=len(cls.evidence['rejections'])), indent=2) + '\n')
        assert unchanged, 'candidate or auditor changed during checks'

    def rejected_mutation(self, label, path, part, key, value, *, reference=False):
        n = self.actual['REFERENCE' if reference else 'BATCH']
        saved = copy.deepcopy(n.cells[path])
        try:
            n.cells[path][part][key] = value
            with self.assertRaises(ValueError) as error:
                audit(self.actual['BATCH'], reference=self.actual['REFERENCE'])
            self.evidence['rejections'].append(dict(case=label, rejected=True,
                                                    error=str(error.exception)))
        finally:
            n.cells[path] = saved

    def test_01_actual_boundary_and_explicit_limits(self):
        row = self.evidence['positive']
        self.assertEqual(row['FF_async_clear_count'], 403)
        self.assertTrue(row['complete_actual_FF_reset_endpoints_identical'])
        self.assertEqual([len(x['actual_named_inputs']) for x in row['opaque_CPU_input_cones']], [32, 42])
        for field in ('sequential_state_equivalence_proven', 'opaque_CPU_internal_pin_roles_proven',
                      'downstream_business_next_Q_proven',
                      'complete_destination_release_consumers_proven',
                      'whole_business_CDC_accepted', 'physical_CDC_accepted', 'hardware_tested'):
            self.assertFalse(row[field], field)
        self.assertEqual(PAIRED_CPU_SOURCE_CLOSURE,
                         'a4847d89534677bb0aab55b1bd2ee7cf0ef49b06a8b78f90b2f460d6ff6756d1')
        self.assertEqual(PAIRED_CPU_DESTINATION_CLOSURE,
                         'cbe5c18b92d425f53154665980cd894e3d58f10fb7a2b9ec220a606cb60b66c3')

    def test_02_reset_inventory_and_release_negatives(self):
        n = self.actual['BATCH']
        g = Graph(n)
        for scope, stem, bit in (
            ('u_runtime/u_cpu_cdc', 'held_data', 0),
            ('u_managed/control_cdc', 'request_toggle', None),
            (SCOPE, 'request_held', 0)):
            path = g.register(scope, stem, bit)
            for label, part, key, value in (
                ('INIT', 'parameters', 'INIT', "1'b1"),
                ('clock', 'ports', 'CLK', 'audio_clk'),
                ('CLEAR removed', 'ports', 'CLEAR', "1'b0")):
                self.rejected_mutation(scope + ' ' + label, path, part, key, value)
        for bit in (0, 1, 2):
            path = g.register(SCOPE, 'p_release', bit)
            for label, part, key, value in (
                ('CE', 'ports', 'CE', "1'b0"),
                ('INIT', 'parameters', 'INIT', "1'b1"),
                ('clock', 'ports', 'CLK', 'audio_clk')):
                self.rejected_mutation('release ' + str(bit) + ' ' + label,
                                       path, part, key, value)
        for bit in (1, 2):
            self.rejected_mutation('release shift bypass ' + str(bit),
                g.register(SCOPE, 'p_release', bit), 'ports', 'D', "1'b1")

    def test_03_actual_opaque_boolean_cone_negatives(self):
        n = self.actual['BATCH']
        g = Graph(n)
        for pin in OPAQUE_PINS['batch']:
            net = n.pin(CPU_BLACKBOX, pin)
            path, output = g.drivers[net][0]
            self.assertEqual(output, 'F')
            self.rejected_mutation(pin + ' LUT function', path, 'parameters', 'INIT',
                "8'hCB" if n.cells[path]['kind'] == 'LUT3' else "16'h0502")
            self.rejected_mutation(pin + ' direct bypass', CPU_BLACKBOX, 'ports', pin, "1'b0")
        for scope, stem, bit in (STATE_REFS[0], STATE_REFS[3], STATE_REFS[-1]):
            path = g.register(scope, stem, bit)
            self.rejected_mutation('named cone input INIT ' + path,
                                   path, 'parameters', 'INIT', "1'b1")
            self.rejected_mutation('named cone input clock ' + path,
                                   path, 'ports', 'CLK', 'audio_clk')
        self.rejected_mutation('CPU APB output width', CPU_BLACKBOX, 'ports', 'paddr', "1'b0")

    def test_04_reference_seal_and_extra_consumer_negatives(self):
        n = self.actual['REFERENCE']
        g = Graph(n)
        self.rejected_mutation('historical async reset removed',
            g.register('u_runtime/u_cpu_cdc', 'held_data', 0), 'ports', 'CLEAR', "1'b0", reference=True)
        n = self.actual['BATCH']
        g = Graph(n)
        path = 'audit_unreviewed_extra_consumer'
        n.cells[path] = dict(kind='DFFCE', parameters={}, ports=dict(
            Q='audit_extra_Q', D=n.pin(g.register(SCOPE, 'p_release', 2), 'Q'),
            CE="1'b1", CLEAR="1'b0", CLK='ram_clk'))
        n.scopes[path] = ''
        try:
            with self.assertRaises(ValueError) as error:
                audit(n, reference=self.actual['REFERENCE'])
            self.evidence['rejections'].append(dict(case='unreviewed final Q data consumer',
                                                    rejected=True, error=str(error.exception)))
        finally:
            del n.cells[path]
            del n.scopes[path]


if __name__ == '__main__':
    unittest.main()
