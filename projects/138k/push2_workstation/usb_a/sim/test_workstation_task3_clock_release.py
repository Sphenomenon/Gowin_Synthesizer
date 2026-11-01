#!/usr/bin/env python3
"""Real DIRECT VG positives and destructive monitor-release controls."""
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
from tools.workstation_task3_clock_release_audit import audit_clock_monitor_release


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class ActualClockRelease(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        vg = os.environ.get('GW138K_TASK3_CLOCK_RELEASE_VG')
        stage = os.environ.get('GW138K_TASK3_CLOCK_RELEASE_STAGE')
        if not vg or not stage:
            raise unittest.SkipTest('explicit actual DIRECT VG/stage required; no synthetic positive')
        cls.path, cls.stage = Path(vg), Path(stage)
        cls.before = {str(p): sha(p) for p in (cls.path, cls.stage/'Prj1.gprj',
            cls.stage/'rtl/audio/workstation_audio_clock_monitor.sv')}
        cls.n = protocol_netlist(cls.path.read_text(), mapping='synthesis')
        cls.root = audit_root_startup(cls.n, stage=cls.stage)
        cls.domains = [('reference_48_monitor', 'clk_12m288'),
                       ('reference_44_monitor', 'clk_16m9344'),
                       ('selected_monitor', cls.n.pin('u_managed/runtime/clocks/selector', 'CLKOUT'))]
        cls.positive, cls.mutations = [], []

    @classmethod
    def tearDownClass(cls):
        unchanged = cls.before == {p: sha(p) for p in cls.before}
        evidence = os.environ.get('GW138K_TASK3_CLOCK_RELEASE_EVIDENCE')
        if evidence:
            Path(evidence).write_text(json.dumps(dict(
                passed=unchanged and len(cls.positive)==3 and len(cls.mutations)==18,
                actual_input_sha256=cls.before, inputs_unchanged=unchanged,
                actual_monitors=cls.positive, mutations_rejected=cls.mutations,
                auditor_sha256=sha(ROOT/'tools/workstation_task3_clock_release_audit.py'),
                test_sha256=sha(__file__), full_CDC_accepted=False,
                hardware_tested=False, reset_recovery_removal_accepted=False), indent=2)+'\n')
        assert unchanged, 'candidate changed during audit'

    @contextmanager
    def changed(self, p, part, key, value):
        target = self.n.cells[p][part]
        missing = object()
        old = target.get(key, missing)
        target[key] = value
        try:
            yield
        finally:
            if old is missing:
                del target[key]
            else:
                target[key] = old

    def check(self, name, clock):
        return audit_clock_monitor_release(self.n, stage=self.stage, name=name,
                                          source_clock=clock, root=self.root)

    def test_01_actual_all_arbitrary_state_next_q(self):
        for name, clock in self.domains:
            result = self.check(name, clock)
            self.assertEqual(len(result['exact_next_q']), 6)
            self.assertEqual(result['arbitrary_state_assignments'], 256)
            self.assertFalse(result['exception_added'])
            self.positive.append(result)

    def test_02_destructive_release_controls(self):
        g = Graph(self.n)
        for name, clock in self.domains:
            scope = 'u_managed/runtime/clocks/' + name
            startup = g.group(scope, 'startup_source', 2)
            pre = g.group(scope, 'source_reset_pre', 3)
            release = g.register(scope, 'source_reset_n')
            cases = [
                ('qualification removed', pre[1], 'ports', 'D', self.n.cells[pre[0]]['ports']['Q']),
                ('first pre disconnected', pre[0], 'ports', 'D', "1'b0"),
                ('root assertion removed', pre[2], 'ports', 'CLEAR', "1'b0"),
                ('startup CE disabled', startup[1], 'ports', 'CE', "1'b0"),
                ('opposite edge bypassed', release, 'ports', 'CLK', self.n.cells[pre[0]]['ports']['CLK']),
                ('nonzero startup INIT', startup[0], 'parameters', 'INIT', "1'b1"),
            ]
            for label, p, part, key, value in cases:
                with self.changed(p, part, key, value):
                    with self.assertRaises(ValueError):
                        self.check(name, clock)
                self.mutations.append(name + ': ' + label)


if __name__ == '__main__':
    unittest.main()
