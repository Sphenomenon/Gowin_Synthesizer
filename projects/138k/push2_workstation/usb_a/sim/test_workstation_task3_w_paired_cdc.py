#!/usr/bin/env python3
"""Actual paired W retained handshakes and destructive graph/SDC controls.

Set GW138K_TASK3_PAIRED_W to an immutable synthesized candidate. An explicitly
selected proposed SDC may be supplied with GW138K_TASK3_W_CDC_SDC; the candidate
and its installed constraints are never rewritten.
"""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph
from tools import workstation_task3_paired_board as common
from tools.workstation_task3_w_paired_cdc_audit import (
    audit_boundary, audit_held, audit_retirements, validate_held_sdc, _mailboxes, _held_resets)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ActualPairedW(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected = os.environ.get('GW138K_TASK3_PAIRED_W')
        if not selected:
            raise unittest.SkipTest('explicit actual W candidate required; no cache fallback')
        cls.candidate = Path(selected)
        cls.stage = cls.candidate / 'workstation/Prj1'
        cls.vg = cls.stage / 'impl/gwsynthesis/custom_138k_integration.vg'
        cls.n = protocol_netlist(cls.vg.read_text(), mapping='synthesis')
        cls.metadata = json.loads((cls.candidate / 'integration_inputs.json').read_text())
        installed = cls.stage / 'constraints/custom_138k.sdc'
        override = os.environ.get('GW138K_TASK3_W_CDC_SDC')
        cls.sdc = Path(override).read_text() if override else common.restore_constraints(cls.stage, installed.read_text())
        cls.boundary = audit_boundary(cls.n, cls.sdc)
        cls.held = audit_held(cls.stage, cls.sdc, cls.metadata, cls.n)
        cls.native = cls.held['actual_native_protocol']
        cls.root = cls.held['actual_root_startup']
        cls.before = {str(path): sha(path) for path in (
            cls.vg, installed, cls.candidate / 'integration_inputs.json', cls.stage / 'Prj1.gprj',
            *(cls.stage / relative for relative in cls.root['source_sha256']))}
        cls.mutations, cls.failed = [], False

    @classmethod
    def tearDownClass(cls):
        assert cls.before == {path: sha(path) for path in cls.before}, 'frozen actual inputs changed'
        evidence = os.environ.get('GW138K_TASK3_W_CDC_EVIDENCE')
        if evidence:
            Path(evidence).write_text(json.dumps(dict(status='FAIL' if cls.failed else 'PASS',
                actual_inputs_sha256=cls.before, actual_boundary=cls.boundary,
                actual_held=cls.held, mutations=cls.mutations, mutation_count=len(cls.mutations),
                source_implementation_only=True, routed_timing_verified=False,
                physical_cdc_accepted=False, hardware_tested=False), indent=2) + '\n')

    def tearDown(self):
        result = self._outcome.result
        self.__class__.failed |= bool(result.errors or result.failures)

    @contextmanager
    def change(self, path, part, key, value):
        old = deepcopy(self.n.cells[path])
        self.n.cells[path][part][key] = value
        try:
            yield
        finally:
            self.n.cells[path].clear()
            self.n.cells[path].update(old)

    def reject_graph(self, label, path, part, key, value, gate):
        with self.change(path, part, key, value), self.assertRaises(ValueError) as error:
            gate()
        self.mutations.append(dict(case=label, rejected=True, error=str(error.exception)))

    def test_actual_retained_inventories(self):
        self.assertEqual(self.boundary['inventory_role'], 'W')
        self.assertEqual(len(self.boundary['queue_source_closure']['ff_endpoints']), 139)
        self.assertEqual([row['payload_bits'] for row in self.native['mailboxes']], [8, 32])
        self.assertEqual(self.native['installed_local_sdc']['exact_required_lines'], 28)
        self.assertEqual(self.root['actual_state_bits'], 35)
        self.assertTrue(self.native['paired_constraint_retirement_and_rebinding']['retired_registers_and_owners_absent'])
        self.assertFalse(self.native['physical_cdc_accepted'])

    def test_real_mailbox_destructive_controls(self):
        g = Graph(self.n)
        r = lambda scope, stem, bit=None: g.register(scope, stem, bit)
        pc, health = 'u_managed/pc_bytes', 'u_managed/health_snapshot'
        first = r(pc, 'req_meta')
        cases = (
            ('PC first clock', first, 'ports', 'CLK', 'clk_50m'),
            ('PC second bypass', r(pc, 'req_sync'), 'ports', 'D', self.n.cells[first]['ports']['D']),
            ('PC first extra consumer', r(pc, 'drop_count', 0), 'ports', 'D', self.n.cells[first]['ports']['Q']),
            ('PC source overwrite CE', r(pc, 'held_data', 0), 'ports', 'CE', "1'b1"),
            ('PC payload bit mapping', r(pc, 'destination_data', 3), 'ports', 'D', "1'b0"),
            ('PC third bypass', r(pc, 'req_settled'), 'ports', 'D', "1'b0"),
            ('health payload bit mapping', r(health, 'destination_data', 63), 'ports', 'D', "1'b0"),
            ('health returned ACK clock', r(health, 'ack_meta'), 'ports', 'CLK', 'clk_50m'),
            ('health capture CE', r(health, 'destination_data', 32), 'ports', 'CE', "1'b1"),
        )
        for case in cases:
            with self.subTest(case=case[0]):
                self.reject_graph(*case, lambda: _mailboxes(self.n, Graph(self.n)))

    def test_actual_fault_fifo_destructive_controls(self):
        from tools.workstation_demo_boundary_cdc import E, U
        g = Graph(self.n)
        r = lambda scope, stem, bit=None: g.register(scope, stem, bit)
        cases = (
            ('DMA fault first D disconnected', r(E, 'dma_fault_meta'), 'ports', 'D', "1'b0"),
            ('DMA fault receiver clock', r(E, 'dma_fault_sync'), 'ports', 'CLK', 'memory_clk'),
            ('USB queue first-edge bypass', r(U, 'queue_release', 0), 'ports', 'D', "1'b0"),
            ('W queue tail consumer removed', r('u_managed/events/queue', 'tail'), 'ports', 'CE', "1'b0"),
        )
        for case in cases:
            with self.subTest(case=case[0]):
                self.reject_graph(*case, lambda: audit_boundary(self.n, self.sdc))

    def test_real_local_reset_controls(self):
        g = Graph(self.n)
        r = lambda scope, stem, bit=None: g.register(scope, stem, bit)
        pc, health = 'u_managed/pc_bytes', 'u_managed/health_snapshot'
        resets = self.native['retained_held_handshakes']
        source = resets['mailbox_resets'][pc]['releases']['source']['stages']
        apb = resets['apb_resets']['source']['release']
        cases = (
            ('shared source release INIT', source[0], 'parameters', 'INIT', "1'b1"),
            ('shared source third bypass', source[2], 'ports', 'D', "1'b1"),
            ('PC payload assertion removed', r(pc, 'destination_data', 7), 'ports', 'CLEAR', "1'b0"),
            ('health payload assertion removed', r(health, 'held_data', 63), 'ports', 'CLEAR', "1'b0"),
            ('APB merged source release bypass', apb[1], 'ports', 'D', "1'b1"),
            ('APB payload INIT', r('u_managed/control_cdc', 'response_held', 32), 'parameters', 'INIT', "1'b1"),
        )
        for case in cases:
            with self.subTest(case=case[0]):
                self.reject_graph(*case, lambda: _held_resets(self.n, Graph(self.n), self.native, self.root))

    def test_retirement_and_merge_controls(self):
        g = Graph(self.n)
        cases = (
            ('retired media source no longer zero', g.register('u_managed/media_stop', 'request_compute', 0), 'ports', 'D', "1'b1"),
            ('rebound startup clock', g.register('u_managed/runtime', 'startup_memory', 0), 'ports', 'CLK', 'clk_50m'),
            ('CNN merged first D disconnected', g.register('u_task3_media/cnn_stream/task_service', 'backend_meta'), 'ports', 'D', "1'b0"),
            ('CNN merged second bypass', g.register('u_task3_media/cnn_stream/task_service/cnn', 'model_memory_ready'), 'ports', 'D', "1'b0"),
            ('CNN memory ready gate source', 'u_task3_media/memory/ddr_client_ready_s', 'ports', 'I3', "1'b1"),
        )
        for case in cases:
            with self.subTest(case=case[0]):
                self.reject_graph(*case, lambda: audit_retirements(self.n))
        revived = 'u_managed/runtime/serial_epoch_4_s0'
        template = g.register('u_managed/runtime', 'serial_epoch', 0)
        self.n.cells[revived] = deepcopy(self.n.cells[template])
        self.n.scopes[revived] = self.n.scopes[template]
        try:
            with self.assertRaises(ValueError) as error:
                audit_retirements(self.n)
            self.mutations.append(dict(case='retired epoch endpoint revived', rejected=True, error=str(error.exception)))
        finally:
            del self.n.cells[revived]
            del self.n.scopes[revived]

    def test_later_stages_and_finite_bounds_remain_protected(self):
        variants = (
            ('later-D cut', self.sdc + 'set_false_path -to [get_pins {u_managed/pc_bytes/req_settled_s*/D}]\n'),
            ('later-register cut', self.sdc + 'set_false_path -to [get_regs {u_managed/health_snapshot/req_sync_s*}]\n'),
            ('PC13ns bound weakened', self.sdc.replace('set_max_delay 13.020 -from [get_pins {u_managed/pc_bytes/', 'set_max_delay 30.000 -from [get_pins {u_managed/pc_bytes/')),
            ('health2ns bound weakened', self.sdc.replace('set_max_delay 2.000 -from [get_pins {u_managed/health_snapshot/req_meta_', 'set_max_delay 10.000 -from [get_pins {u_managed/health_snapshot/req_meta_')),
            ('weaker override', self.sdc + 'set_max_delay 80.000 -to [get_pins {u_managed/health_snapshot/destination_data_*_s*/D}]\n'),
            ('whole-clock cut', self.sdc + 'set_false_path -from [get_clocks {clk_50m}] -to [get_clocks {audio_clk}]\n'),
        )
        for label, changed in variants:
            with self.subTest(case=label), self.assertRaises(ValueError) as error:
                validate_held_sdc(changed, self.n, self.native)
            self.mutations.append(dict(case=label, rejected=True, error=str(error.exception)))


if __name__ == '__main__':
    unittest.main()
