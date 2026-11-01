#!/usr/bin/env python3
"""Explicit actual-candidate TF startup/release next-Q and negative controls.

No source/candidate mutation, fallback candidate, EDA, SDC or board operation.
Running this on v4 provides only v4 local evidence; v6 needs a separate run.
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
from tools.workstation_task3_tf_startup_audit import audit_tf_startup_releases


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ActualTask3TfStartup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected = os.environ.get('GW138K_TASK3_TF_STARTUP_VG')
        stage = os.environ.get('GW138K_TASK3_TF_STARTUP_STAGE')
        if not selected or not stage:
            raise unittest.SkipTest('explicit actual VG and sealed stage required; no fallback')
        cls.path, cls.stage = Path(selected), Path(stage)
        cls.mapping = os.environ.get('GW138K_TASK3_TF_STARTUP_MAPPING', 'synthesis')
        cls.n = protocol_netlist(cls.path.read_text(), mapping=cls.mapping)
        cls.root = audit_root_startup(cls.n, stage=cls.stage)
        cls.mutations, cls.traces, cls.positive, cls.failed = [], [], None, False
        cls.before = {str(path): sha(path) for path in (
            cls.path, cls.stage/'Prj1.gprj', cls.stage/ROOT_SOURCE,
            cls.stage/PROVIDER, cls.stage/TOP_SOURCE,
            cls.stage/'rtl/tf_audio/workstation_tf_direct_runtime_service.sv')}

    def tearDown(self):
        result = self._outcome.result
        self.__class__.failed |= bool(result.failures or result.errors)

    @classmethod
    def tearDownClass(cls):
        unchanged = cls.before == {path: sha(path) for path in cls.before}
        selected = os.environ.get('GW138K_TASK3_TF_STARTUP_EVIDENCE')
        if selected:
            paths = ('tools/workstation_task3_tf_startup_audit.py',
                     'sim/test_workstation_task3_tf_startup.py',
                     'tools/workstation_task3_root_reset_audit.py')
            Path(selected).write_text(json.dumps(dict(
                status='PASS' if unchanged and cls.positive and not cls.failed else 'FAIL',
                mapping=cls.mapping, actual_input_sha256=cls.before,
                selected_stage=str(cls.stage), selected_vg=str(cls.path),
                candidate_scope='only the explicit actual input hashes; another candidate requires a new run',
                audit_source_sha256={p: sha(ROOT/p) for p in paths},
                original_inputs_unchanged=unchanged, actual_tf_startup=cls.positive,
                temporal_actual_cell_traces=cls.traces,
                mutations=cls.mutations, mutation_count=len(cls.mutations),
                tf_source_binding_proven=False, full_tf_cdc_proven=False,
                physical_tail_proven=False, hardware_tested=False), indent=2)+'\n')
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

    def test_01_actual_five_state_next_q_and_early_closures(self):
        result = audit_tf_startup_releases(self.n, root=self.root)
        self.assertEqual(result['register_count'], 10)
        self.assertEqual([r['reset_and_state_assignment_count'] for r in result['chains']], [128, 128])
        self.assertTrue(all(r['all_state_assignments_proven'] for r in result['chains']))
        self.assertFalse(result['full_tf_cdc_proven'])
        self.assertFalse(result['physical_tail_proven'])
        self.assertFalse(result['readiness_state_transition_logic_proven'])
        self.__class__.positive = result

    def test_02_actual_cell_start_and_runtime_drop_edges(self):
        result = audit_tf_startup_releases(self.n, root=self.root)
        g, n = Graph(self.n), self.n
        for chain in result['chains']:
            registers = chain['registers']
            state = {n.pin(p, 'Q'): 0 for p in registers}

            def update(root_value, guard_value):
                assignment = dict(state, **{result['root_q']: root_value,
                                           result['readiness_q']: guard_value})
                state.update({n.pin(p, 'Q'): 0 if g.value(n.pin(p, 'CLEAR'), assignment) else
                    g.value(n.pin(p, 'D'), assignment) if g.value(n.pin(p, 'CE'), assignment) else
                    assignment[n.pin(p, 'Q')] for p in registers})
                return [state[n.pin(p, 'Q')] for p in registers]

            started = [update(1, 1) for _ in range(5)]
            self.assertEqual(started, [[1,0,0,0,0], [1,1,0,0,0], [1,1,1,0,0],
                                       [1,1,1,1,0], [1,1,1,1,1]])
            dropped = [update(1, 0) for _ in range(3)]
            self.assertEqual(dropped, [[0,1,1,1,1], [0,0,1,1,1], [0,0,0,0,0]])
            for _ in range(5):
                update(1, 1)
            asserted = update(0, 1)
            self.assertEqual(asserted, [0,0,0,0,0])
            self.traces.append(dict(id=chain['id'], state_order=registers,
                runtime_high_from_zero=started, runtime_low_from_released=dropped,
                root_assertion_effective_next_q=asserted,
                edge_counts_are_local_clock_edges=True, analog_or_physical_timing_proven=False))

    def test_03_actual_startup_release_mutants(self):
        actual = audit_tf_startup_releases(self.n, root=self.root)
        g = Graph(self.n)
        local_consumer = g.register('u_tf_audio', 'restart_q')
        common_gate = g.drivers[actual['common_clear']][0][0]
        runtime_gate = g.drivers[actual['runtime_reset_n']][0][0]
        cases = []
        for chain in actual['chains']:
            label = chain['id']
            s0, s1 = chain['startup_registers']
            r0, r1, r2 = chain['release_registers']
            cases.extend((
                (label+' startup0 INIT', s0, 'parameters', 'INIT', "1'b1"),
                (label+' startup1 clock', s1, 'ports', 'CLK', "1'b0"),
                (label+' release0 CE', r0, 'ports', 'CE', "1'b0"),
                (label+' release1 common CLEAR', r1, 'ports', 'CLEAR', "1'b0"),
                (label+' release2 synchronous primitive', r2, None, 'kind', 'DFFRE'),
                (label+' startup0 runtime input bypass', s0, 'ports', 'D', "1'b1"),
                (label+' startup1 first stage bypass', s1, 'ports', 'D', "1'b1"),
                (label+' release0 startup gate bypass', r0, 'ports', 'D', "1'b1"),
                (label+' release1 startup clear omitted', r1, 'ports', 'D', self.n.cells[r0]['ports']['Q']),
                (label+' release2 startup clear omitted', r2, 'ports', 'D', self.n.cells[r1]['ports']['Q']),
            ))
            for path in (s0, s1, r0, r1):
                cases.append((label+' early extra consumer '+path.rsplit('/',1)[1],
                    local_consumer, 'ports', 'D', self.n.cells[path]['ports']['Q']))
        cases.extend((
            ('common CLEAR replaced by runtime reset', common_gate, 'ports', 'I', 'runtime_reset_n'),
            ('runtime reset root omitted', runtime_gate, 'ports', 'I0', "1'b1"),
            ('runtime reset guard omitted', runtime_gate, 'ports', 'I1', "1'b1"),
            ('runtime reset AND polarity changed', runtime_gate, 'parameters', 'INIT', "4'h7"),
        ))
        for label, path, part, key, value in cases:
            with self.subTest(case=label), self.changed(path, part, key, value):
                with self.assertRaises(ValueError) as error:
                    audit_tf_startup_releases(self.n, root=self.root)
            self.mutations.append(dict(case=label, rejected=True, error=str(error.exception)))
        self.assertEqual(len(cases), 32)

    def test_04_root_proof_interface_mutants(self):
        for label, key, value in (
            ('unproved root', 'all_state_assignments_proven', False),
            ('wrong root Q', 'root_q', 'audio_reset_n'),
            ('wrong root policy', 'policy', 'legacy-global'),
        ):
            with self.subTest(case=label), self.assertRaises(ValueError) as error:
                audit_tf_startup_releases(self.n, root=dict(self.root, **{key: value}))
            self.mutations.append(dict(case=label, rejected=True, error=str(error.exception)))


if __name__ == '__main__':
    unittest.main()
