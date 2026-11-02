#!/usr/bin/env python3
"""Immutable actual paired root/release audits and destructive netlist controls."""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist, audit_native_protocol
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_task3_root_reset_audit import audit_root_startup, validate_root_publisher
from tools.workstation_task3_native_held import audit_direct_held_boundaries
from tools.workstation_task3_peripheral_releases_audit import audit_peripheral_releases
from tools.workstation_task3_m_paired_releases_audit import audit_paired_release_sdc, CHAINS
from tools.workstation_task3_tf_direct import (adapt_paired_release_constraints,
    restore_paired_release_constraints, paired_release_constraint_mappings)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ActualPairedReset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.actual, cls.before, cls.mutations, cls.failed = {}, {}, [], False
        for role in ('M', 'W'):
            selected = os.environ.get('GW138K_TASK3_PAIRED_' + role + '_STAGE')
            if not selected:
                raise unittest.SkipTest('explicit M/W sealed stages required; no cache fallback')
            stage = Path(selected)
            vg = stage / 'impl/gwsynthesis/custom_138k_integration.vg'
            n = protocol_netlist(vg.read_text(), mapping='synthesis')
            root = audit_root_startup(n, stage=stage)
            cls.actual[role] = dict(n=n, stage=stage, root=root)
            paths = [vg, stage/'constraints/custom_138k.sdc',
                     *(stage/p for p in root['source_sha256'])]
            cls.before.update({str(p): sha(p) for p in paths})
        m = cls.actual['M']
        original = (m['stage']/'constraints/custom_138k.sdc').read_text()
        if all(original.count(a) == 1 for a, b in paired_release_constraint_mappings()):
            cls.projected_sdc, cls.adaptation = adapt_paired_release_constraints(original)
            cls.actual_SDC_rebound = False
        else:
            cls.projected_sdc, cls.adaptation, cls.actual_SDC_rebound = original, None, True
        cls.original_sdc = original
        cls.release = audit_paired_release_sdc(m['n'], cls.projected_sdc, root=m['root'])

    def tearDown(self):
        result = self._outcome.result
        self.__class__.failed |= bool(result.failures or result.errors)

    @classmethod
    def tearDownClass(cls):
        assert cls.before == {p: sha(p) for p in cls.before}, 'immutable candidate inputs changed'
        selected = os.environ.get('GW138K_TASK3_PAIRED_RESET_EVIDENCE')
        if selected:
            Path(selected).write_text(json.dumps(dict(
                status='FAIL' if cls.failed else 'PASS', actual_inputs_sha256=cls.before,
                actual_root_proofs={role: row['root'] for role, row in cls.actual.items()},
                actual_installed_SDC_rebound=cls.actual_SDC_rebound,
                explicit_read_only_SDC_projection=cls.adaptation,
                actual_release_alias_and_query_proof=cls.release,
                actual_M_held_and_peripheral=getattr(cls, 'held_receipt', None),
                mutations=cls.mutations, mutation_count=len(cls.mutations),
                old_DIRECT_constraint_policy_changed=False,
                actual_candidates_mutated=False, physical_CDC_accepted=False,
                routed_timing_verified=False, hardware_tested=False), indent=2)+'\n')

    @contextmanager
    def changed(self, n, path, part, key, value):
        target = n.cells[path][part]
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

    def rejected(self, label, function):
        with self.assertRaises(ValueError) as error:
            function()
        self.mutations.append(dict(case=label, rejected=True, error=str(error.exception)))

    def test_actual_M_and_W_complete_root_startup(self):
        for role, row in self.actual.items():
            root = row['root']
            self.assertEqual(root['actual_state_bits'], 35)
            self.assertEqual(root['state_assignment_count'], 1 << 35)
            self.assertEqual(root['first_root_rise_clock_edge_from_zero_init'], 1026)
            self.assertEqual(root['mapped_common_root_name'], 'terminal_ready' if role == 'M' else 'reset_n')
            self.assertEqual(root['common_root_output_polarity'], 1)
            self.assertTrue(root['all_state_assignments_proven'])

    def test_actual_M_held_and_peripheral_resets(self):
        row = self.actual['M']
        native = audit_native_protocol(row['n'], profile='m-task3-direct', mapping='synthesis')
        held = audit_direct_held_boundaries(row['n'], native, root=row['root'])
        peripheral = audit_peripheral_releases(row['n'], root=row['root'])
        self.assertEqual(peripheral['release_register_count'], 12)
        self.assertEqual(peripheral['functional_register_count'], 1222)
        self.assertEqual(held['pc_actual_reset']['releases']['source']['stages'][-1],
                         'u_task3_m_pcm_commands/p_release_2_s0')
        self.__class__.held_receipt = dict(native_held=held, peripheral=peripheral,
            full_DIRECT_TF_CDC_accepted=False)

    def test_actual_root_mutants(self):
        for role, row in self.actual.items():
            n, stage, root = row['n'], row['stage'], row['root']
            p = root['root_register']
            for label, part, key, value in (
                ('zero INIT', 'parameters', 'INIT', "1'b1"),
                ('clock', 'ports', 'CLK', "1'b0"),
                ('root Q disconnected', 'ports', 'Q', 'audit_disconnected_root'),
                ('early rise enable', 'ports', 'CE', "1'b1"),
                ('startup reset removed', 'ports', 'RESET', "1'b0")):
                with self.subTest(role=role, case=label), self.changed(n, p, part, key, value):
                    self.rejected(role+' '+label, lambda: audit_root_startup(n, stage=stage))
            for label, patch in (
                ('wrong provider', dict(selected_provider='unreviewed')),
                ('wrong mapped alias', dict(mapped_common_root_name='preset_n')),
                ('wrong polarity', dict(common_root_output_polarity=0)),
                ('counter as common root', dict(root_register=Graph(n).register('u_reset','startup_count',0)))):
                self.rejected(role+' '+label,
                    lambda patch=patch: validate_root_publisher(n, Graph(n), dict(root, **patch)))

    def test_actual_release_chain_mutants(self):
        row = self.actual['M']; n, root = row['n'], row['root']; g = Graph(n)
        for config in CHAINS:
            label, scope, stem, bit, owner, release_stem, domain, cpu, expected_sha = config
            functional = g.register(scope, stem, bit)
            release = g.group(owner, release_stem, 3)
            for case, p, part, key, value in (
                ('CE disabled', release[0], 'ports', 'CE', "1'b0"),
                ('middle-stage bypass', release[1], 'ports', 'D', "1'b1"),
                ('assertion removed', release[2], 'ports', 'CLEAR', "1'b0"),
                ('wrong release INIT', release[0], 'parameters', 'INIT', "1'b1"),
                ('functional reset disconnected', functional, 'ports', 'CLEAR', "1'b0")):
                with self.subTest(chain=label, case=case), self.changed(n, p, part, key, value):
                    self.rejected(label+' '+case,
                        lambda: audit_paired_release_sdc(n, self.projected_sdc, root=root))
        owner = CHAINS[0][4]; p = g.group(owner, CHAINS[0][5], 3)[0]
        n.cells['audit_extra_consumer'] = dict(kind='DFFCE', parameters={'INIT':"1'b0"},
            ports=dict(Q='audit_extra_q', D=n.pin(p,'Q'), CLK='ram_clk', CLEAR="1'b0", CE="1'b1"))
        n.scopes['audit_extra_consumer'] = ''
        try:
            self.rejected('early release extra consumer',
                lambda: audit_paired_release_sdc(n, self.projected_sdc, root=root))
        finally:
            del n.cells['audit_extra_consumer']; del n.scopes['audit_extra_consumer']

    def test_SDC_exact_queries_and_inverse(self):
        n, root = self.actual['M']['n'], self.actual['M']['root']
        self.assertEqual(self.release['exact_installed_release_CLEAR_pins'], 12)
        if self.adaptation is not None:
            self.assertEqual(restore_paired_release_constraints(self.projected_sdc, self.adaptation),
                             self.original_sdc)
            self.rejected('frozen v4 stale SDC aliases',
                lambda: audit_paired_release_sdc(n, self.original_sdc, root=root))
            self.rejected('inverse wrong evidence', lambda: restore_paired_release_constraints(
                self.projected_sdc, dict(self.adaptation, added_exceptions=1)))
        for old, selected in paired_release_constraint_mappings():
            for label, replacement in (('omitted', ''), ('duplicated', selected+' '+selected),
                                       ('functional D cut', selected.removesuffix('/CLEAR')+'/D')):
                modified = self.projected_sdc.replace(selected, replacement)
                self.rejected(label+' '+selected,
                    lambda modified=modified: audit_paired_release_sdc(n, modified, root=root))


if __name__ == '__main__':
    unittest.main()
