#!/usr/bin/env python3
"""Actual-VG destructive controls for the supplemental M CPU source review."""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_task3_m_cpu_source_review as owner
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph


class ActualMSourceReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stage = os.environ.get('GW138K_TASK3_CPU_SOURCE_STAGE')
        if not stage:
            raise unittest.SkipTest('explicit immutable v16 M stage required')
        cls.stage = Path(stage).resolve()
        cls.vg = cls.stage / 'impl/gwsynthesis/custom_138k_integration.vg'
        cls.source = owner.sources(cls.stage)
        bound = {**cls.source['root_binding']['source_sha256'], **owner.SOURCES}
        cls.before = {str(p): owner.sha(p) for p in
                      (cls.vg, cls.stage.parent.parent / 'workstation_profile.json',
                       *(cls.stage / rel for rel in bound))}
        cls.n = protocol_netlist(cls.vg.read_text(), mapping='synthesis')
        cls.g = Graph(cls.n)
        cls.rejections = []

    @classmethod
    def tearDownClass(cls):
        assert cls.before == {p: owner.sha(p) for p in cls.before}
        report = os.environ.get('GW138K_TASK3_CPU_SOURCE_TEST_RECEIPT')
        if report:
            path = Path(report)
            assert not path.exists()
            path.write_text(json.dumps(dict(input_sha256=cls.before,
                inputs_unchanged=True, rejected_mutations=cls.rejections,
                mutation_count=len(cls.rejections)), indent=2) + '\n')

    @contextmanager
    def cell(self, path):
        cell = self.n.cells[path]
        before = deepcopy(cell)
        try:
            yield cell
        finally:
            cell.clear()
            cell.update(before)

    def rejected(self, label):
        with self.subTest(case=label), self.assertRaises(ValueError):
            owner.review(self.n, source=self.source)
        self.rejections.append(label)

    def test_complete_named_state_and_external_APB_equations(self):
        proof = owner.review(self.n, source=self.source)
        self.assertEqual(proof['named_source_FF_CLEAR_count'], 403)
        self.assertEqual(proof['Boolean_assignments'], 1 << 42)
        self.assertTrue(proof['source_FF_clear_inventory_proven'])
        self.assertTrue(all(p['equation_proven'] and not p['treated_as_reset_input'] for p in
                            proof['external_APB_response_equations'].values()))
        self.assertFalse(proof['whole_CDC_accepted'])
        self.assertFalse(proof['selected_by_sealed_v16_auditor'])

    def test_source_FF_semantics_and_boundary_mutations(self):
        path = self.g.register(owner.STREAM, 'held_data', 0)
        for field, value in (('CLK', 'clk_50m'), ('CLEAR', "1'b0")):
            with self.cell(path) as cell:
                cell['ports'][field] = value
                self.rejected('source FF ' + field)
        with self.cell(path) as cell:
            cell['parameters']['INIT'] = "1'b1"
            self.rejected('source FF nonzero INIT')
        with self.cell(path) as cell:
            cell['kind'] = 'DFFSE'
            self.rejected('source FF wrong primitive')
        release = self.g.register(owner.CONFIG, 'p_release', 2)
        top_ff = next(p for p in self.g.regs if self.n.scopes[p] == '')
        with self.cell(top_ff) as cell:
            cell['ports']['D'] = self.n.pin(release, 'Q')
            self.assertEqual(self.n.pin(top_ff, 'D'), self.n.pin(release, 'Q'))
            self.rejected('release reaches extra D consumer')
        for extra in (owner.STREAM + '/held_data_224_s0', 'unexpected_source_reset_s0'):
            self.n.cells[extra] = deepcopy(self.n.cells[path])
            self.n.cells[extra]['ports']['Q'] = extra + '_q'
            self.n.scopes[extra] = self.n.scopes[path]
            try:
                self.rejected('extra source FF ' + extra)
            finally:
                del self.n.cells[extra]
                del self.n.scopes[extra]

    def test_opaque_inputs_and_mux_truth_mutations(self):
        with self.cell(owner.CPU_BLACKBOX) as cell:
            cell['ports']['unexpected_release'] = cell['ports'][owner.OPAQUE_INPUTS['ready']]
            self.rejected('extra opaque consumer')
        with self.cell(owner.CPU_BLACKBOX) as cell:
            a, b = owner.OPAQUE_INPUTS.values()
            cell['ports'][a], cell['ports'][b] = cell['ports'][b], cell['ports'][a]
            self.rejected('swapped opaque ready and error')
        for pin in owner.OPAQUE_INPUTS.values():
            net = self.n.pin(owner.CPU_BLACKBOX, pin)
            path, _ = self.g.drivers[net][0]
            with self.cell(path) as cell:
                width = int(cell['kind'][3:])
                old = int(cell['parameters']['INIT'].split("'h")[1], 16)
                cell['parameters']['INIT'] = f"{1 << width}'h{old ^ ((1 << (1 << width))-1):X}"
                self.rejected('inverted APB output truth table ' + pin)

    def test_external_bus_cuts_and_source_policy_mutations(self):
        wrapper = self.n.frames['u_cpu']['kind']
        for port in ('paddr', 'pstrb', 'psel'):
            old = self.n.directions[wrapper][port]
            try:
                self.n.directions[wrapper][port] = 'input'
                self.rejected('CPU bus cut has wrong direction ' + port)
            finally:
                self.n.directions[wrapper][port] = old
        for key, value in (('profile', 'custom138k-workstation-task3-w-paired-checkpoint-v16'),
                           ('reviewed_source_sha256', {})):
            source = dict(self.source, **{key: value})
            with self.subTest(case=key), self.assertRaises(ValueError):
                owner.review(self.n, source=source)
            self.rejections.append('source policy ' + key)


if __name__ == '__main__':
    unittest.main()
