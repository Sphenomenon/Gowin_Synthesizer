#!/usr/bin/env python3
"""Strict receipt shape: actual old candidate rejection and new actual audit.

Old evidence cannot stand in for a new-shape positive run. Neither candidate
is inferred from a cache, and no mocked positive VG is constructed.
"""
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
from tools.workstation_task3_root_reset_audit import (
    audit_root_startup, ROOT_SOURCE, PROVIDER, TOP_SOURCE)
from tools.workstation_task3_receipt_audit import audit_direct_receipt


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class OldActualReceiptRejected(unittest.TestCase):
    def test_old_actual_candidate_requires_real_local_receiver(self):
        selected = os.environ.get('GW138K_TASK3_RECEIPT_OLD_VG')
        stage = os.environ.get('GW138K_TASK3_RECEIPT_OLD_STAGE')
        if not selected or not stage:
            self.skipTest('explicit old actual VG/stage required; no fallback')
        stage, selected = Path(stage), Path(selected)
        before = {str(p): sha(p) for p in (selected, stage/'Prj1.gprj',
            stage/ROOT_SOURCE, stage/PROVIDER, stage/TOP_SOURCE)}
        n = protocol_netlist(selected.read_text(), mapping='synthesis')
        root = audit_root_startup(n, stage=stage)
        with self.assertRaisesRegex(ValueError, 'missing required receipt_local') as error:
            audit_direct_receipt(n, root=root)
        self.assertEqual(before, {path: sha(path) for path in before})
        evidence = os.environ.get('GW138K_TASK3_RECEIPT_OLD_EVIDENCE')
        if evidence:
            Path(evidence).write_text(json.dumps(dict(
                status='EXPECTED_OLD_SHAPE_REJECTION_CONFIRMED', actual_input_sha256=before,
                error=str(error.exception), actual_positive_verified=False,
                no_mocked_positive_netlist=True,
                audit_source_sha256={p: sha(ROOT/p) for p in (
                    'tools/workstation_task3_receipt_audit.py', 'sim/test_workstation_task3_receipt.py')},
                new_candidate_requires_separate_actual_netlist_run=True,
                hardware_tested=False), indent=2)+'\n')


class ActualNewReceipt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected = os.environ.get('GW138K_TASK3_RECEIPT_VG')
        stage = os.environ.get('GW138K_TASK3_RECEIPT_STAGE')
        if not selected or not stage:
            raise unittest.SkipTest('explicit new actual VG/stage required; no mocked positive or fallback')
        cls.path, cls.stage = Path(selected), Path(stage)
        cls.mapping = os.environ.get('GW138K_TASK3_RECEIPT_MAPPING', 'synthesis')
        cls.n = protocol_netlist(cls.path.read_text(), mapping=cls.mapping)
        cls.root = audit_root_startup(cls.n, stage=cls.stage)
        cls.positive, cls.mutations, cls.failed = None, [], False
        cls.before = {str(p): sha(p) for p in (cls.path, cls.stage/'Prj1.gprj',
            cls.stage/ROOT_SOURCE, cls.stage/PROVIDER, cls.stage/TOP_SOURCE,
            cls.stage/'rtl/tf_audio/workstation_tf_direct_runtime_service.sv')}

    def tearDown(self):
        result = self._outcome.result
        self.__class__.failed |= bool(result.failures or result.errors)

    @classmethod
    def tearDownClass(cls):
        unchanged = cls.before == {p: sha(p) for p in cls.before}
        evidence = os.environ.get('GW138K_TASK3_RECEIPT_EVIDENCE')
        if evidence:
            Path(evidence).write_text(json.dumps(dict(
                status='PASS' if unchanged and cls.positive and not cls.failed else 'FAIL',
                selected_vg=str(cls.path), selected_stage=str(cls.stage), mapping=cls.mapping,
                actual_input_sha256=cls.before, original_inputs_unchanged=unchanged,
                actual_receipt=cls.positive, mutations=cls.mutations, mutation_count=len(cls.mutations),
                audit_source_sha256={p: sha(ROOT/p) for p in (
                    'tools/workstation_task3_receipt_audit.py', 'sim/test_workstation_task3_receipt.py')},
                source_data_semantics_proven=False, physical_event_semantics_proven=False,
                full_tf_cdc_proven=False, physical_tail_proven=False,
                hardware_tested=False), indent=2)+'\n')
        assert unchanged, 'actual candidate/source inputs drifted'

    @contextmanager
    def changed(self, path, part, key, value):
        target = self.n.cells[path] if part is None else self.n.cells[path][part]
        absent = object()
        old = target.get(key, absent)
        target[key] = value
        try:
            yield
        finally:
            if old is absent:
                del target[key]
            else:
                target[key] = old

    def test_01_actual_new_mailbox_and_all_next_q(self):
        result = audit_direct_receipt(self.n, root=self.root)
        self.assertEqual(result['register_count'], 76)
        self.assertEqual(len(result['source_pins']), 34)
        self.assertEqual(len(result['capture_pins']), 34)
        self.assertEqual(len(result['next_q']), 76)
        self.assertEqual(len({p['register'] for p in result['next_q']}), 76)
        self.assertTrue(result['all_reset_inclusive_next_q_proven'])
        self.assertEqual(len(result['chains']), 2)
        self.assertFalse(result['source_data_semantics_proven'])
        self.assertFalse(result['source_event_condition_semantics_proven'])
        self.assertFalse(result['full_tf_cdc_proven'])
        self.assertFalse(result['physical_tail_proven'])
        self.__class__.positive = result

    def test_02_actual_receipt_destructive_controls(self):
        result = audit_direct_receipt(self.n, root=self.root)
        g, n = Graph(self.n), self.n
        local = g.group('u_tf_audio', 'receipt_local', 34)
        payload = g.group('u_tf_audio', 'receipt_payload', 34)
        req = g.register('u_tf_audio', 'receipt_request')
        seen = g.register('u_tf_audio', 'receipt_seen')
        capture = g.register('u_tf_audio', 'receipt_capture')
        dispatch = g.register('u_tf_audio', 'receipt_dispatch')
        consumer = g.register('u_tf_audio', 'restart_q')
        eos_queued = g.register('u_tf_audio', 'eos_queued')
        ce_gate = g.drivers[result['source_ce']][0][0]
        self.assertRegex(n.cells[ce_gate]['kind'], '^LUT[1-6]$')
        zero_init = str(1 << int(n.cells[ce_gate]['kind'][3:])) + "'h0"
        common_gate = g.drivers[result['common_clear']][0][0]
        cases = [
            ('local0 D disconnected', local[0], 'ports', 'D', "1'b0"),
            ('local33 CE disconnected', local[33], 'ports', 'CE', "1'b0"),
            ('local17 CLEAR disconnected', local[17], 'ports', 'CLEAR', "1'b0"),
            ('local8 INIT changed', local[8], 'parameters', 'INIT', "1'b1"),
            ('local31 clock changed', local[31], 'ports', 'CLK', 'audio_clk'),
            ('held payload CE disconnected', payload[2], 'ports', 'CE', "1'b0"),
            ('held payload CLEAR disconnected', payload[30], 'ports', 'CLEAR', "1'b0"),
            ('held payload INIT changed', payload[19], 'parameters', 'INIT', "1'b1"),
            ('held payload clock changed', payload[3], 'ports', 'CLK', 'clk_50m_d'),
            ('held payload reaches business D', consumer, 'ports', 'D', n.cells[payload[5]]['ports']['Q']),
            ('request D no longer toggles', req, 'ports', 'D', "1'b0"),
            ('request commit CE disconnected', req, 'ports', 'CE', "1'b0"),
            ('request INIT changed', req, 'parameters', 'INIT', "1'b1"),
            ('seen D disconnected', seen, 'ports', 'D', "1'b0"),
            ('seen CE disconnected', seen, 'ports', 'CE', "1'b0"),
            ('capture D disconnected', capture, 'ports', 'D', "1'b0"),
            ('capture CE disconnected', capture, 'ports', 'CE', "1'b0"),
            ('dispatch D disconnected', dispatch, 'ports', 'D', "1'b0"),
            ('dispatch CE disconnected', dispatch, 'ports', 'CE', "1'b0"),
            ('source acceptance truth table changed', ce_gate, 'parameters', 'INIT', zero_init),
            ('payload0 event condition replaced by constant', payload[0], 'ports', 'D', "1'b1"),
            ('common root assertion removed', common_gate, 'ports', 'I', "1'b1"),
            ('request extra remote business consumer', consumer, 'ports', 'D', n.cells[req]['ports']['Q']),
            ('seen extra remote source consumer', eos_queued, 'ports', 'D', n.cells[seen]['ports']['Q']),
        ]
        for chain in result['chains']:
            first, second = (pin.rsplit('/',1)[0] for pin in (chain['first'], chain['second']))
            cases.extend((
                (chain['id']+' first D bypass', first, 'ports', 'D', "1'b1"),
                (chain['id']+' second D bypass', second, 'ports', 'D', "1'b1"),
                (chain['id']+' first CE changed', first, 'ports', 'CE', "1'b0"),
                (chain['id']+' second root CLEAR removed', second, 'ports', 'CLEAR', "1'b0"),
                (chain['id']+' first extra consumer', consumer, 'ports', 'D', n.cells[first]['ports']['Q']),
            ))
        for label, path, part, key, value in cases:
            with self.subTest(case=label), self.changed(path, part, key, value):
                with self.assertRaises(ValueError) as error:
                    audit_direct_receipt(n, root=self.root)
            self.mutations.append(dict(case=label, rejected=True, error=str(error.exception)))
        self.assertEqual(len(cases), 34)

    def test_03_root_proof_interface_controls(self):
        for label, key, value in (
            ('unverified root', 'all_state_assignments_proven', False),
            ('wrong root Q', 'root_q', 'audio_reset_n'),
            ('wrong root policy', 'policy', 'legacy-global'),
        ):
            with self.subTest(case=label), self.assertRaises(ValueError) as error:
                audit_direct_receipt(self.n, root=dict(self.root, **{key: value}))
            self.mutations.append(dict(case=label, rejected=True, error=str(error.exception)))


if __name__ == '__main__':
    unittest.main()
