#!/usr/bin/env python3
"""Actual paired receipt source, queue/history lifecycle and bad-cone controls."""
from contextlib import contextmanager
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
from tools.workstation_task3_root_reset_audit import audit_root_startup
from tools.workstation_task3_receipt_audit import audit_direct_receipt


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class ActualPairedReceipt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected = os.environ.get('GW138K_TASK3_PAIRED_RECEIPT_STAGE')
        if not selected:
            raise unittest.SkipTest('explicit immutable paired M stage required; no cache fallback')
        cls.stage = Path(selected)
        cls.vg = cls.stage/'impl/gwsynthesis/custom_138k_integration.vg'
        cls.n = protocol_netlist(cls.vg.read_text(), mapping='synthesis')
        cls.root = audit_root_startup(cls.n, stage=cls.stage)
        cls.actual = audit_direct_receipt(cls.n, root=cls.root)
        cls.mutations, cls.failed = [], False
        cls.before = {str(p): sha(p) for p in (cls.vg,
            *(cls.stage/p for p in cls.root['source_sha256']),
            cls.stage/'rtl/tf_audio/workstation_tf_direct_runtime_service.sv',
            cls.stage/'rtl/workstation/workstation_runtime_audio.sv',
            cls.stage/'rtl/audio/workstation_ae350_pcm_owner.sv')}

    def tearDown(self):
        result = self._outcome.result
        self.__class__.failed |= bool(result.failures or result.errors)

    @classmethod
    def tearDownClass(cls):
        unchanged = cls.before == {p: sha(p) for p in cls.before}
        selected = os.environ.get('GW138K_TASK3_PAIRED_RECEIPT_EVIDENCE')
        if selected:
            files = ('tools/workstation_task3_receipt_audit.py',
                     'sim/test_workstation_task3_paired_receipt.py')
            Path(selected).write_text(json.dumps(dict(status='PASS' if unchanged and not cls.failed else 'FAIL',
                actual_input_sha256=cls.before, actual_receipt=cls.actual,
                mutations=cls.mutations, mutation_count=len(cls.mutations),
                original_inputs_unchanged=unchanged,
                audit_source_sha256={p: sha(ROOT/p) for p in files},
                full_tf_cdc_proven=False, physical_tail_event_semantics_proven=False,
                hardware_tested=False), indent=2)+'\n')
        assert unchanged, 'immutable actual paired inputs changed'

    @contextmanager
    def changed(self, path, part, key, value):
        target = self.n.cells[path][part]
        absent = object(); old = target.get(key, absent); target[key] = value
        try:
            yield
        finally:
            if old is absent:
                del target[key]
            else:
                target[key] = old

    def reject(self, label, path, part, key, value):
        with self.subTest(case=label), self.changed(path, part, key, value):
            with self.assertRaises(ValueError) as error:
                audit_direct_receipt(self.n, root=self.root)
        self.mutations.append(dict(case=label, rejected=True, error=str(error.exception)))

    def test_actual_source_and_queue_history_lifecycle(self):
        result = self.actual
        lifecycle = result['paired_source_abort_lifecycle']
        self.assertTrue(result['source_data_semantics_proven'])
        self.assertTrue(result['source_event_condition_semantics_proven'])
        self.assertIsNone(result['source_acceptance_condition_cut'])
        self.assertEqual(lifecycle['arbitrary_abort_or_data_cuts'], [])
        self.assertEqual(len(result['next_q']), 76)
        self.assertEqual(len(lifecycle['queue_next_q']), 34)
        self.assertEqual(len(lifecycle['history_snapshot_next_q']), 66)
        self.assertEqual(sorted(r['width'] for r in lifecycle['exact_inequality_comparisons']), [10,22,32,32])
        self.assertTrue(lifecycle['abort_priority_over_EOS_proven'])
        self.assertTrue(lifecycle['busy_preserves_queued_abort_proven'])
        self.assertFalse(result['full_tf_cdc_proven'])
        self.assertFalse(lifecycle['fault_producer_and_blocked_state_machine_semantics_proven'])

    def test_queue_kind_session_and_toggle_mutants(self):
        g = Graph(self.n); s='u_tf_audio'; r='u_managed/runtime'
        reg=lambda scope,stem,bit=None:g.register(scope,stem,bit)
        cases = (
            ('abort queue cleared before ACK', reg(s,'abort_queued'), 'ports','D',"1'b0"),
            ('abort queue enable suppressed', reg(s,'abort_queued'), 'ports','CE',"1'b0"),
            ('abort queue assertion removed', reg(s,'abort_queued'), 'ports','CLEAR',"1'b0"),
            ('abort queue INIT high', reg(s,'abort_queued'), 'parameters','INIT',"1'b1"),
            ('EOS priority/retention removed', reg(s,'eos_queued'), 'ports','D',"1'b0"),
            ('EOS enable suppressed', reg(s,'eos_queued'), 'ports','CE',"1'b0"),
            ('queued session bit0 wrong', reg(s,'queued_receipt_session',0), 'ports','D',"1'b0"),
            ('queued session bit31 not captured', reg(s,'queued_receipt_session',31), 'ports','CE',"1'b0"),
            ('queued session INIT high', reg(s,'queued_receipt_session',8), 'parameters','INIT',"1'b1"),
            ('held kind0 wrong', reg(s,'receipt_payload',0), 'ports','D',"1'b0"),
            ('held kind1 wrong', reg(s,'receipt_payload',1), 'ports','D',"1'b0"),
            ('held session31 wrong', reg(s,'receipt_payload',33), 'ports','D',"1'b0"),
            ('held payload overwritten separately', reg(s,'receipt_payload',12), 'ports','CE',"1'b1"),
            ('request no longer toggles', reg(s,'receipt_request'), 'ports','D',"1'b0"),
            ('request committed independently', reg(s,'receipt_request'), 'ports','CE',"1'b1"),
            ('panic snapshot D wrong', reg(r,'g_direct_tf.panic_q',9), 'ports','D',"1'b0"),
            ('cancel snapshot CE suppressed', reg(r,'g_direct_tf.cancel_q',0), 'ports','CE',"1'b0"),
            ('epoch snapshot reset removed', reg(r,'g_direct_tf.epoch_q',31), 'ports','CLEAR',"1'b0"),
            ('rate snapshot clock wrong', reg(r,'g_direct_tf.rate_q'), 'ports','CLK','clk_50m'),
            ('tail failure edge snapshot D wrong', reg(r,'g_direct_tf.tail_failed_q'), 'ports','D',"1'b0"),
        )
        for case in cases:
            self.reject(*case)

    def test_exact_abort_comparison_and_truth_table_mutants(self):
        g=Graph(self.n)
        for row in self.actual['paired_source_abort_lifecycle']['exact_inequality_comparisons']:
            p,port=g.drivers[row['actual_output']][0]
            self.assertEqual(port,'COUT')
            self.reject(row['id']+' NE operand removed',p,'ports','I0',"1'b0")
            self.reject(row['id']+' NE carry bypassed',p,'ports','CIN',"1'b1")
            self.reject(row['id']+' NE mode changed',p,'parameters','ALU_MODE','0')
        p,port=g.drivers[self.actual['source_ce']][0]
        self.assertRegex(self.n.cells[p]['kind'],'^LUT[1-6]$')
        width=int(self.n.cells[p]['kind'][3:])
        self.reject('source acceptance truth table disabled',p,'parameters','INIT',str(1<<width)+"'h0")


if __name__ == '__main__':
    unittest.main()
