#!/usr/bin/env python3
"""Actual M held capture/request next-Q proof and destructive controls.

Explicit source stage and synthesis VG are required; no cache fallback, EDA or
device operation. Mutants exist only in the parsed netlist, never its inputs.
This is a local commit proof, not full handshake or physical CDC acceptance.
"""
from contextlib import contextmanager, ExitStack
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
from tools.workstation_task3_root_reset_audit import audit_root_startup, M_PHONE_PROVIDER
from tools.workstation_task3_peripheral_releases_audit import (
    audit_peripheral_releases, audit_source_payload_commit)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ActualMHeldCommit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stage = os.environ.get('GW138K_TASK3_HELD_COMMIT_M_STAGE')
        vg = os.environ.get('GW138K_TASK3_HELD_COMMIT_M_VG')
        if not stage or not vg:
            raise unittest.SkipTest('explicit actual M stage and synthesis VG required; no fallback')
        cls.stage, cls.vg = Path(stage), Path(vg)
        cls.n = protocol_netlist(cls.vg.read_text(), mapping='synthesis')
        cls.root = audit_root_startup(cls.n, stage=cls.stage)
        if cls.root['selected_provider'] != M_PHONE_PROVIDER:
            raise AssertionError('actual phone-block M provider required')
        g = Graph(cls.n)
        cls.scopes = {}
        for name, width in (('performance', 380), ('cpu', 224)):
            scope = 'u_runtime/u_' + name + '_cdc'
            cls.scopes[scope] = dict(width=width,
                clear=cls.n.pin(g.register(scope, 'held_data', 0), 'CLEAR'),
                request=g.register(scope, 'request_toggle'))
        paths = [cls.vg, cls.stage/'Prj1.gprj',
                 *(cls.stage/p for p in cls.root['source_sha256'])]
        cls.before = {str(p): sha(p) for p in paths}
        cls.actual, cls.legacy, cls.mutations = {}, {}, []
        cls.failed, cls.next_rejection = False, None

    def tearDown(self):
        result = self._outcome.result
        self.__class__.failed |= bool(result.failures or result.errors)

    @classmethod
    def tearDownClass(cls):
        unchanged = cls.before == {p: sha(p) for p in cls.before}
        selected = os.environ.get('GW138K_TASK3_HELD_COMMIT_EVIDENCE')
        if selected:
            tools = ('workstation_task3_peripheral_releases_audit',
                     'workstation_runtime_pcm_cdc', 'workstation_recording_phase1_cdc',
                     'workstation_task3_root_reset_audit', 'workstation_native_protocol_audit')
            Path(selected).write_text(json.dumps(dict(
                status='FAIL' if cls.failed or not unchanged else 'PASS',
                mapping='synthesis', actual_input_sha256=cls.before,
                actual_auditor_source_sha256={name: sha(ROOT/'tools'/(name+'.py'))
                                             for name in tools},
                regression_source_sha256=sha(__file__),
                actual_local_commit_proofs=cls.actual,
                legacy_ce_mapping_proofs=cls.legacy,
                mutations=cls.mutations, mutation_count=len(cls.mutations),
                full_peripheral_audit_next_rejection=cls.next_rejection,
                historical_consumer_seals_changed=False,
                original_inputs_unchanged=unchanged, actual_candidates_mutated=False,
                complete_handshake_proven=False, physical_cdc_accepted=False,
                routed_timing_verified=False, hardware_tested=False), indent=2)+'\n')
        assert unchanged, 'actual candidate inputs changed'

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

    @contextmanager
    def added(self, scope, stem, cell):
        path = scope + '/' + stem
        self.assertNotIn(path, self.n.cells)
        self.n.cells[path], self.n.scopes[path] = cell, scope
        try:
            yield path
        finally:
            del self.n.cells[path]
            del self.n.scopes[path]

    def proof(self, scope):
        return audit_source_payload_commit(self.n, scope=scope, clear=self.scopes[scope]['clear'])

    def rejected(self, scope, label, function=None, message=None):
        with self.assertRaises(ValueError) as error:
            (function or (lambda: self.proof(scope)))()
        if message is not None:
            self.assertIn(message, str(error.exception))
        self.mutations.append(dict(scope=scope, case=label, rejected=True, error=str(error.exception)))
        return str(error.exception)

    def test_01_actual_reset_inclusive_commit_proofs(self):
        for scope, row in self.scopes.items():
            with self.subTest(scope=scope):
                proof = self.proof(scope)
                self.assertEqual(len(proof['held_registers']), row['width'])
                self.assertEqual(len(proof['named_register_q_inputs']), 19)
                self.assertEqual(proof['boolean_assignments'], 524288)
                self.assertFalse(proof['raw_request_payload_ce_equal'])
                self.assertTrue(proof['reset_before_enable'])
                self.assertTrue(proof['reset_inclusive_next_q_exact'])
                self.assertIn(proof['request_ce'], Graph(self.n).high)
                self.assertEqual(len(proof['source_payload_consumer_closure']['ff_endpoints']), row['width'])
                self.assertFalse(proof['complete_handshake_proven'])
                self.assertFalse(proof['physical_cdc_accepted'])
                self.actual[scope] = proof

    def test_02_legacy_identical_ce_mapping_remains_valid(self):
        # Rewrite the actual request only to the older physical encoding:
        # CE=payload_CE and D=~Q. Keep its real reset, clock and payload cone.
        for scope, row in self.scopes.items():
            request = row['request']
            first = Graph(self.n).register(scope, 'held_data', 0)
            inverse = dict(kind='INV', parameters={}, ports=dict(
                I=self.n.cells[request]['ports']['Q'], O='audit_legacy_inverse'))
            with self.added(scope, 'audit_legacy_inverse_s0', inverse), \
                 self.changed(request, 'ports', 'D', 'audit_legacy_inverse'), \
                 self.changed(request, 'ports', 'CE', self.n.cells[first]['ports']['CE']):
                proof = self.proof(scope)
                self.assertTrue(proof['raw_request_payload_ce_equal'])
                self.assertTrue(proof['reset_inclusive_next_q_exact'])
                self.legacy[scope] = proof

    def test_03_payload_commit_ce_mutants(self):
        for scope in self.scopes:
            held = self.proof(scope)['held_registers']
            for value in ("1'b0", "1'b1"):
                with self.subTest(scope=scope, all_ce=value), ExitStack() as stack:
                    for path in held:
                        stack.enter_context(self.changed(path, 'ports', 'CE', value))
                    self.rejected(scope, 'all payload CE '+value, message='commit CE is constant')
                with self.subTest(scope=scope, one_ce=value), \
                     self.changed(held[-1], 'ports', 'CE', value):
                    self.rejected(scope, 'one payload CE '+value, message='differing commit CE')
            with self.changed(held[-1], 'ports', 'CE', 'ack_sync'):
                self.rejected(scope, 'one payload wrong condition', message='differing commit CE')
            # A driven LUT constant must fail even though its net has a name.
            constant = dict(kind='LUT1', parameters=dict(INIT="2'h0"),
                            ports=dict(I0='ack_sync', F='audit_constant_ce'))
            with self.added(scope, 'audit_constant_ce_s0', constant), ExitStack() as stack:
                for path in held:
                    stack.enter_context(self.changed(path, 'ports', 'CE', 'audit_constant_ce'))
                self.rejected(scope, 'Boolean constant payload CE', message='Boolean constant')

    def test_04_request_control_and_xor_mutants(self):
        for scope, row in self.scopes.items():
            request = row['request']
            for pin, value, label in (
                    ('CE', "1'b0", 'disabled request CE'),
                    ('CE', 'ack_sync', 'wrong request CE condition'),
                    ('D', "1'b0", 'request D zero'),
                    ('D', "1'b1", 'request D one'),
                    ('D', 'request_toggle', 'request D holds'),
                    ('D', 'ack_sync', 'request D wrong state')):
                with self.subTest(scope=scope, case=label), self.changed(request, 'ports', pin, value):
                    self.rejected(scope, label, message='reset-inclusive next-Q changed')
            wrong_xor = dict(kind='LUT2', parameters=dict(INIT="4'h6"),
                             ports=dict(I0='request_toggle', I1='ack_sync', F='audit_wrong_xor'))
            with self.added(scope, 'audit_wrong_xor_s0', wrong_xor), \
                 self.changed(request, 'ports', 'D', 'audit_wrong_xor'):
                self.rejected(scope, 'request wrong XOR operand', message='reset-inclusive next-Q changed')
            with self.changed(request, 'ports', 'D', 'audit_absent_driver'):
                self.rejected(scope, 'request unknown D driver', message='driver absent/ambiguous')

    def test_05_register_reset_clock_init_and_primitive_mutants(self):
        for scope, row in self.scopes.items():
            held = Graph(self.n).register(scope, 'held_data', 0)
            for role, path in (('payload', held), ('request', row['request'])):
                for part, key, value, label, message in (
                        ('ports', 'CLK', "1'b0", 'clock', 'clock changed'),
                        ('ports', 'CLEAR', "1'b0", 'clear removed', 'CLEAR changed'),
                        ('ports', 'CLEAR', "1'b1", 'clear asserted', 'CLEAR changed'),
                        ('parameters', 'INIT', "1'b1", 'nonzero INIT', 'INIT'),
                        (None, 'kind', 'DFFRE', 'primitive', 'asynchronous clear FF')):
                    with self.subTest(scope=scope, role=role, case=label), \
                         self.changed(path, part, key, value):
                        self.rejected(scope, role+' '+label, message=message)
            with self.changed(held, 'ports', 'SET', "1'b0"):
                self.rejected(scope, 'payload extra set port', message='asynchronous clear FF')

    def test_06_exact_owner_inventory_and_consumer_mutants(self):
        self.rejected('unreviewed', 'unknown owner', function=lambda:
            audit_source_payload_commit(self.n, scope='u_runtime/u_other_cdc', clear="1'b0"),
            message='unreviewed source payload owner')
        for scope in self.scopes:
            g = Graph(self.n)
            held = g.register(scope, 'held_data', 0)
            captured = g.register(scope, 'destination_data', 0)
            extra = copy.deepcopy(self.n.cells[held])
            extra['ports']['Q'] = 'audit_extra_payload'
            with self.added(scope, 'held_data_999_s0', extra):
                self.rejected(scope, 'extra held bit', message='payload bit inventory changed')
            duplicate = copy.deepcopy(extra)
            with self.added(scope, 'held_data_0_s99', duplicate):
                self.rejected(scope, 'duplicate held bit', message='exact register missing/duplicate')
            original = self.n.cells.pop(held)
            try:
                self.rejected(scope, 'missing held bit', message='exact register missing/duplicate')
            finally:
                self.n.cells[held] = original
            with self.changed(captured, 'ports', 'D', "1'b0"):
                self.rejected(scope, 'corresponding captured D bypass', message='corresponding capture D changed')
            consumer = copy.deepcopy(extra)
            consumer['ports']['D'] = self.n.cells[held]['ports']['Q']
            with self.added(scope, 'audit_extra_consumer_s0', consumer):
                self.rejected(scope, 'extra FF held consumer', message='extra/bypassed consumer')
            opaque = dict(kind='AUDIT_OPAQUE', parameters={},
                          ports=dict(DI=self.n.cells[held]['ports']['Q']))
            with self.added(scope, 'audit_opaque_consumer_s0', opaque):
                self.rejected(scope, 'extra opaque held consumer', message='extra/bypassed consumer')
            # CLEAR is a real register-Q cone. Do not accept a new unknown cut
            # or allow another Q publisher to pass as an independent input.
            alias = copy.deepcopy(extra)
            alias['ports']['Q'] = self.n.cells[self.scopes[scope]['request']]['ports']['Q']
            with self.added(scope, 'audit_duplicate_request_publisher_s0', alias):
                self.rejected(scope, 'duplicate request Q publisher', message='multiple drivers')

    def test_07_full_audit_retains_historical_consumer_rejection(self):
        error = self.rejected('M', 'full audit historical consumer seal', function=lambda:
            audit_peripheral_releases(self.n, root=self.root),
            message='paired final release complete endpoint inventory changed')
        self.assertIn('u_task3_pair_link/config_cdc/p_release_2_s0', error)
        self.__class__.next_rejection = error


if __name__ == '__main__':
    unittest.main()
