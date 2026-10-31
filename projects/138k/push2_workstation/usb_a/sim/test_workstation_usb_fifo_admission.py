#!/usr/bin/env python3
"""Real complete-workstation USB packet CEA correlation regression; no EDA."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_runtime_pcm_cdc import PcmNetlist, Graph, TOP
from tools.workstation_synthesis_netlist import SynthesisNetlist
from tools.workstation_usb_fifo_reset import audit_synthesis, _expanded_admission_proof

SOURCES = ('tools/workstation_usb_fifo_reset.py', 'tools/workstation_runtime_pcm_cdc.py',
    'tools/workstation_synthesis_netlist.py', 'tools/workstation_recording_phase1_cdc.py',
    'sim/test_workstation_usb_fifo_admission.py')


class ActualAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get('GW138K_USB_FIFO_ADMISSION_NETLIST')
        if not path:
            raise unittest.SkipTest('explicit actual GW138K_USB_FIFO_ADMISSION_NETLIST required')
        cls.path = Path(path)
        cls.original = cls.path.read_bytes()
        cls.n = PcmNetlist(cls.original.decode(), TOP)
        cls.gate = audit_synthesis(cls.n)
        cls.rows = []
        cls.source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                             for name in SOURCES}

    @classmethod
    def tearDownClass(cls):
        if cls.path.read_bytes() != cls.original:
            raise AssertionError('sealed actual candidate netlist changed')
        if audit_synthesis(cls.n) != cls.gate:
            raise AssertionError('actual-object mutant restoration changed baseline proof')
        if cls.source_hashes != {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                 for name in SOURCES}:
            raise AssertionError('auditor source changed during actual-netlist regression')
        output = os.environ.get('GW138K_USB_FIFO_ADMISSION_EVIDENCE')
        if output:
            Path(output).write_text(json.dumps(dict(actual_netlist=str(cls.path),
                netlist_sha256=hashlib.sha256(cls.original).hexdigest(),
                audit_sources_sha256=cls.source_hashes, baseline=cls.gate,
                mutations=cls.rows, expected_negative_controls=19,
                all_rejected=len(cls.rows) == 19 and all(row['rejected'] for row in cls.rows),
                original_candidate_netlist_unchanged=True, complete_workstation_gate_accepted=False,
                PNR=False, hardware_tested=False), indent=2) + '\n')

    def test_exact_expansion_and_full_source_consumer_inventory(self):
        gate = self.gate
        proof = gate['admission_function']
        self.assertEqual(proof['method'], 'exact_complete_shared_INV_LUT_BDD')
        self.assertEqual(proof['actual_CEA_q0_cofactor'], 0)
        self.assertEqual(proof['actual_INV_LUT_count'], len(proof['actual_INV_LUT_equations']))
        self.assertIn(proof['final_release_Q'], proof['terminal_inputs'])
        self.assertTrue(all(value['independently_arbitrary'] for value in proof['terminal_inputs'].values()))
        self.assertTrue(proof['no_sequential_reachability_assumptions'])
        self.assertEqual(gate['actual_write_state_registers'], 13)
        closure = proof['final_release_complete_source_consumers']
        self.assertEqual(set(closure['ff_endpoints'].values()), {gate['usb_clock']})
        self.assertEqual(set(closure['primitive_endpoints']), {gate['actual_memory_write_pin']})
        self.assertFalse(closure['top_output_endpoints'])

    def reject_change(self, name, cell, field, key, value):
        target = self.n.cells[cell][field]
        existed, original = key in target, target.get(key)
        target[key] = value
        try:
            try:
                audit_synthesis(self.n)
            except ValueError as error:
                self.rows.append(dict(name=name, kind='parsed_complete_actual_netlist_mutant',
                                      rejected=True, error=str(error)))
            else:
                self.rows.append(dict(name=name, kind='parsed_complete_actual_netlist_mutant', rejected=False))
                self.fail('complete actual-netlist mutant accepted: ' + name)
        finally:
            if existed:
                target[key] = original
            else:
                del target[key]

    def test_full_actual_reset_CEA_increment_and_correlation_negative_controls(self):
        g, n, gate = Graph(self.n), self.n, self.gate
        memory = gate['actual_memory_write_pin'].rsplit('/', 1)[0]
        release0, release1 = (gate['release_registers'][i] for i in (0, 1))
        q = n.pin(release1, 'Q')
        producer = gate['write_groups']['produce_w_bin'][0]
        cea = g.drivers[n.pin(memory, 'CEA')][0][0]
        q_gates = [cell for cell, value in gate['admission_function']['actual_INV_LUT_equations'].items()
                   if q in value['inputs'].values()]
        self.assertEqual(len(q_gates), 1)
        guard = q_gates[0]
        guard_pin = next(pin for pin in n.cells[guard]['ports'] if n.pin(guard, pin) == q)
        self.assertEqual(n.cells[guard]['parameters']['INIT'], "16'hD000")
        reconvergent = next(cell for cell, value in gate['admission_function']['actual_INV_LUT_equations'].items()
                           if value['kind'] == 'LUT2' and value['output'].endswith('/\\$1_4'))
        increment = gate['pointer_increment_function']
        self.assertEqual(increment.get('kind'), 'ALU')
        adder = increment['primitive']
        cases = [
            ('producer_reset_bypass', producer, 'ports', 'CLEAR', "1'b0"),
            ('producer_wrong_clock', producer, 'ports', 'CLK', gate['audio_clock']),
            ('release_wrong_clock', release0, 'ports', 'CLK', gate['audio_clock']),
            ('release_second_bypass', release1, 'ports', 'D', n.cells[release0]['ports']['D']),
            ('memory_CEA_bypass', memory, 'ports', 'CEA', "1'b1"),
            ('actual_CEA_truth_all_one', cea, 'parameters', 'INIT', "16'hFFFF"),
            ('actual_CEA_truth_all_zero', cea, 'parameters', 'INIT', "16'h0000"),
            ('guard_truth_release_bypassed', guard, 'parameters', 'INIT', "16'hD0D0"),
            ('guard_release_input_tied_high', guard, 'ports', guard_pin, "1'b1"),
            ('actual_reconvergent_NOR_truth_removed', reconvergent, 'parameters', 'INIT', "4'h0"),
            ('unreviewed_actual_LUT_input', reconvergent, 'ports', 'BAD', n.cells[release1]['ports']['Q']),
            ('adder_mode', adder, 'parameters', 'ALU_MODE', '1'),
            ('adder_carry', adder, 'ports', 'CIN', "1'b1"),
            ('adder_operand', adder, 'ports', 'I1', "1'b0"),
        ]
        for case in cases:
            with self.subTest(case=case[0]):
                self.reject_change(*case)

    def test_extra_cross_domain_opaque_export_and_wrong_source_rejected(self):
        n, gate = self.n, self.gate
        release0, release1 = (gate['release_registers'][i] for i in (0, 1))
        memory = gate['actual_memory_write_pin'].rsplit('/', 1)[0]
        contract = gate['admission_function']['contract']
        with self.assertRaises(ValueError):
            _expanded_admission_proof(n, Graph(n), memory, n.pin(release0, 'Q'), contract)
        self.rows.append(dict(name='wrong_first_release_source_Q', rejected=True))
        source_scope = n.scopes[release1]
        extra = source_scope + '/unreviewed_extra_s0'
        for kind in ('DFFCE', 'UNREVIEWED_RAM'):
            c = copy.deepcopy(n.cells[release1])
            c['kind'] = kind
            c['ports']['D'] = c['ports']['Q']
            c['ports']['Q'] = 'unreviewed_extra_Q'
            c['ports']['CLK'] = n.cells[gate['write_groups']['produce_w_bin'][0]]['ports']['CLK']
            if kind == 'DFFCE':
                # A newly connected FF without the actual USB clock must
                # fail the complete consumer inventory, even if it is inert.
                c['ports']['CLK'] = "1'b0"
            else:
                c['ports'] = {'IN': c['ports']['D'], 'CLK': c['ports']['CLK']}
            n.cells[extra], n.scopes[extra] = c, source_scope
            try:
                with self.assertRaises(ValueError):
                    audit_synthesis(n)
                self.rows.append(dict(name='extra_final_Q_consumer_' + kind, rejected=True))
            finally:
                del n.cells[extra]
                del n.scopes[extra]
        n.directions[TOP]['unreviewed_export'] = 'output'
        n.buffers[TOP]['unreviewed_export'] = n.pin(release1, 'Q')
        try:
            with self.assertRaises(ValueError):
                audit_synthesis(n)
            self.rows.append(dict(name='extra_final_Q_top_output', rejected=True))
        finally:
            del n.directions[TOP]['unreviewed_export']
            del n.buffers[TOP]['unreviewed_export']
        with self.assertRaisesRegex(ValueError, 'strict complete named-port inventory'):
            audit_synthesis(SynthesisNetlist(self.original.decode(), TOP))
        self.rows.append(dict(name='strict_named_port_inventory_absent', rejected=True))


if __name__ == '__main__':
    unittest.main()
