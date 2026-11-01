#!/usr/bin/env python3
"""Actual task3 shared peripheral release proof and destructive controls.

Requires explicit candidate paths; does not launch EDA, change source inputs,
edit constraints, or operate a board.  No historical/cache fallback is used.
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
from tools.workstation_task3_peripheral_releases_audit import audit_peripheral_releases


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ActualTask3PeripheralReleases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected = os.environ.get('GW138K_TASK3_PERIPHERAL_VG')
        stage = os.environ.get('GW138K_TASK3_PERIPHERAL_STAGE')
        if not selected or not stage:
            raise unittest.SkipTest('explicit actual VG and sealed stage required; no fallback')
        cls.path, cls.stage = Path(selected), Path(stage)
        cls.mapping = os.environ.get('GW138K_TASK3_PERIPHERAL_MAPPING', 'synthesis')
        cls.n = protocol_netlist(cls.path.read_text(), mapping=cls.mapping)
        cls.root = audit_root_startup(cls.n, stage=cls.stage)
        cls.mutations, cls.positive, cls.failed = [], None, False
        cls.before = {str(path): sha(path) for path in (
            cls.path, cls.stage/'Prj1.gprj', cls.stage/ROOT_SOURCE,
            cls.stage/PROVIDER, cls.stage/TOP_SOURCE)}

    def tearDown(self):
        result = self._outcome.result
        self.__class__.failed |= bool(result.failures or result.errors)

    @classmethod
    def tearDownClass(cls):
        unchanged = cls.before == {path: sha(path) for path in cls.before}
        selected = os.environ.get('GW138K_TASK3_PERIPHERAL_EVIDENCE')
        if selected:
            paths = ('tools/workstation_task3_peripheral_releases_audit.py',
                     'sim/test_workstation_task3_peripheral_releases.py',
                     'tools/workstation_task3_root_reset_audit.py')
            Path(selected).write_text(json.dumps(dict(
                status='PASS' if unchanged and cls.positive and not cls.failed else 'FAIL',
                mapping=cls.mapping, actual_input_sha256=cls.before,
                audit_source_sha256={p: sha(ROOT/p) for p in paths},
                original_inputs_unchanged=unchanged,
                actual_peripheral_releases=cls.positive,
                mutations=cls.mutations, mutation_count=len(cls.mutations),
                root_startup_policy=cls.root['policy'],
                hardware_tested=False, physical_cdc_accepted=False), indent=2)+'\n')
        assert unchanged, 'actual source/netlist inputs drifted'

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

    def test_01_actual_chains_and_owned_clear_coverage(self):
        result = audit_peripheral_releases(self.n, root=self.root)
        self.assertEqual(result['release_register_count'], 12)
        self.assertEqual(result['functional_register_count'], 1222)
        self.assertEqual([s['functional_register_count'] for s in result['functional_scopes']], [767, 455])
        self.assertEqual([len(r['consumer_closures'][2]['ff_endpoints'])
                          for r in result['release_chains']], [410, 413, 315, 228])
        self.assertEqual([len(r['deferred_opaque_endpoints']) for r in result['release_chains']], [0, 0, 2, 0])
        self.assertTrue(all(r['all_32_reset_and_state_assignments_proven'] for r in result['release_chains']))
        self.assertFalse(result['opaque_cpu_reset_internal_logic_proven'])
        self.assertFalse(result['physical_cdc_accepted'])
        self.__class__.positive = result

    def test_02_actual_release_and_functional_mutants(self):
        actual = audit_peripheral_releases(self.n, root=self.root)
        cases = []
        for row in actual['release_chains']:
            label = row['id']
            r0, r1, r2 = row['registers']
            cases.extend((
                (label+' stage2 D bypasses stage1', r2, 'ports', 'D', self.n.cells[r0]['ports']['Q']),
                (label+' stage1 CE disabled', r1, 'ports', 'CE', "1'b0"),
                (label+' stage1 nonzero INIT', r1, 'parameters', 'INIT', "1'b1"),
                (label+' stage0 common clear removed', r0, 'ports', 'CLEAR', "1'b0"),
                (label+' stage2 wrong clock', r2, 'ports', 'CLK', "1'b0"),
            ))
        g = Graph(self.n)
        for name in ('performance', 'cpu'):
            scope = 'u_runtime/u_' + name + '_cdc'
            held = g.register(scope, 'held_data', 0)
            destination = g.register(scope, 'destination_data', 0)
            cases.extend((
                (name+' source payload clear removed', held, 'ports', 'CLEAR', "1'b0"),
                (name+' destination payload clear removed', destination, 'ports', 'CLEAR', "1'b0"),
                (name+' source payload INIT changed', held, 'parameters', 'INIT', "1'b1"),
                (name+' destination payload D disconnected', destination, 'ports', 'D', "1'b0"),
                (name+' source payload commit CE disconnected', held, 'ports', 'CE', "1'b0"),
                (name+' source payload synchronous reset primitive', held, None, 'kind', 'DFFRE'),
            ))
        for name, common in (('performance', 'u_tf_control_cdc/n6_s1'),
                             ('cpu', 'u_managed/control_cdc/n6_s1')):
            cases.extend((
                (name+' common root omitted', common, 'ports', 'I0', "1'b1"),
                (name+' common domain reset omitted', common, 'ports', 'I1', "1'b1"),
                (name+' common NAND polarity changed', common, 'parameters', 'INIT', "4'h8"),
            ))
        perf = actual['release_chains'][0]
        cases.extend((
            ('performance functional clear uses early release', perf['functional_clear_inverter'], 'ports', 'I',
             self.n.cells[perf['registers'][1]]['ports']['Q']),
            ('performance early release extra functional consumer',
             g.register('u_tf_control_cdc', 'ack_meta'), 'ports', 'D',
             self.n.cells[perf['registers'][0]]['ports']['Q']),
            ('cpu shared release extra opaque consumer', 'u_cpu/u_RiscV_AE350_SOC',
             'ports', 'rtc_tick', 'n8275_3'),
        ))
        for label, path, part, key, value in cases:
            with self.subTest(case=label), self.changed(path, part, key, value):
                with self.assertRaises(ValueError) as error:
                    audit_peripheral_releases(self.n, root=self.root)
            self.mutations.append(dict(case=label, rejected=True, error=str(error.exception)))
        self.assertEqual(len(cases), 41)

    def test_03_unverified_or_wrong_root_proof_rejected(self):
        for label, key, value in (
            ('root not proved', 'all_state_assignments_proven', False),
            ('wrong root Q', 'root_q', 'audio_reset_n'),
            ('wrong root policy', 'policy', 'legacy-global'),
        ):
            modified = dict(self.root, **{key: value})
            with self.subTest(case=label), self.assertRaises(ValueError) as error:
                audit_peripheral_releases(self.n, root=modified)
            self.mutations.append(dict(case=label, rejected=True, error=str(error.exception)))


if __name__ == '__main__':
    unittest.main()
