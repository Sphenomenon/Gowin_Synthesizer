#!/usr/bin/env python3
"""Actual batch MIDI root lifetime, exact selected SDC and negative controls."""
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
from tools.workstation_task3_root_reset_audit import audit_root_startup
from tools.workstation_task3_m_midi_release_sdc import (
    POLICY, ACTUAL_OWNER, STALE_SELECTOR, CORRECT_SELECTOR,
    audit_midi_release_sdc, project_midi_release_sdc, restore_midi_release_sdc)
from tools.workstation_task3_paired_board import adapt_constraints, restore_constraints


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ActualMidiRelease(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected = os.environ.get('GW138K_TASK3_MIDI_RELEASE_STAGE')
        if not selected:
            raise unittest.SkipTest('explicit actual batch stage required; no fallback')
        stage = Path(selected).resolve()
        vg = stage/'impl/gwsynthesis/custom_138k_integration.vg'
        sdc = stage/'constraints/custom_138k.sdc'
        cls.n = protocol_netlist(vg.read_text(), mapping='synthesis')
        cls.root = audit_root_startup(cls.n, stage=stage)
        cls.sdc = sdc.read_text()
        cls.installed_corrected = CORRECT_SELECTOR in cls.sdc
        if cls.installed_corrected:
            metadata = json.loads((stage.parents[1]/'integration_inputs.json').read_text())
            receipt = metadata['task3_paired_sdc']['M_MIDI_root_release']
            cls.stale = restore_midi_release_sdc(
                cls.sdc.removesuffix('\n# TASK3 paired LCD/F808 CDC physical endpoint review REQUIRED; no blanket exception.\n'), receipt)
            cls.projected, cls.receipt = project_midi_release_sdc(cls.stale)
        else:
            cls.stale = cls.sdc
            cls.projected, cls.receipt = project_midi_release_sdc(cls.sdc)
        cls.inputs = {str(p): sha(p) for p in (
            vg, sdc, stage/'Prj1.gprj', Path(__file__),
            ROOT/'tools/workstation_task3_m_midi_release_sdc.py',
            ROOT/'tools/workstation_task3_native_held.py',
            ROOT/'tools/workstation_task3_root_reset_audit.py',
            ROOT/'tools/workstation_task3_paired_board.py',
            ROOT/'tools/workstation_task3_paired_audit.py')}
        cls.evidence = dict(actual_stage=str(stage), rejections=[], installed_corrected=cls.installed_corrected)

    def setUp(self):
        type(self).result = self._outcome.result

    @classmethod
    def tearDownClass(cls):
        unchanged = cls.inputs == {p: sha(p) for p in cls.inputs}
        target = os.environ.get('GW138K_TASK3_MIDI_RELEASE_EVIDENCE')
        if target:
            path = Path(target)
            assert not path.exists(), 'never overwrite evidence'
            path.write_text(json.dumps(dict(cls.evidence, input_sha256=cls.inputs,
                inputs_unchanged=unchanged, passed=unchanged and cls.result.wasSuccessful(),
                negative_control_count=len(cls.evidence['rejections'])), indent=2)+'\n')
        assert unchanged, 'candidate or proof inputs changed during verification'

    def rejected(self, label, call):
        with self.assertRaises(ValueError) as error:
            call()
        self.evidence['rejections'].append(dict(case=label, error=str(error.exception), rejected=True))

    def test_01_actual_root_and_528_reset_consumers(self):
        proof = audit_midi_release_sdc(self.n, self.projected, root=self.root)
        self.assertTrue(proof['original_MIDI_reset_owner_and_SDC_target_verified'])
        self.assertEqual(proof['final_reset_consumer_count'], 528)
        self.assertTrue(proof['complete_final_reset_consumer_inventory_proven'])
        self.assertEqual(proof['boolean_assignments_proven'], 16)
        for key in ('whole_MIDI_handshake_proven', 'physical_recovery_removal_verified',
                    'routed_timing_verified', 'hardware_tested', 'deployment_allowed'):
            self.assertFalse(proof[key])
        self.evidence['actual_or_projected_positive'] = proof
        self.evidence['projection_receipt'] = self.receipt
        if self.installed_corrected:
            self.evidence['installed_positive'] = audit_midi_release_sdc(self.n, self.sdc, root=self.root)
        self.rejected('stale observer selector matches three pins but wrong lifetime',
            lambda: audit_midi_release_sdc(self.n, self.stale, root=self.root))

    def test_02_production_adapter_and_constraint_negatives(self):
        self.assertEqual(restore_midi_release_sdc(self.projected, self.receipt), self.stale)
        for label, value in (
            ('missing selector', self.projected.replace(CORRECT_SELECTOR, '')),
            ('broad root selector', self.projected.replace(CORRECT_SELECTOR, ACTUAL_OWNER+'/*/CLEAR')),
            ('functional state instead of release', self.projected.replace(CORRECT_SELECTOR, 'u_managed/midi_bytes/*/CLEAR')),
            ('duplicate corrected selector', self.projected+'\nset_false_path -to [get_pins {'+CORRECT_SELECTOR+'}]\n'),
            ('stale retained beside corrected', self.projected+'\nset_false_path -to [get_pins {'+STALE_SELECTOR+'}]\n')):
            self.rejected(label, lambda value=value: audit_midi_release_sdc(self.n, value, root=self.root))
        self.rejected('tampered inverse receipt', lambda: restore_midi_release_sdc(
            self.projected, dict(self.receipt, input_sha256='0'*64)))
        from tools.workstation_task3_tf_direct import restore_paired_release_constraints, adapt_paired_release_constraints
        # Construct the DIRECT parent through the actual reversible adapters.
        legacy = self.stale.removesuffix('\n# TASK3 paired LCD/F808 CDC physical endpoint review REQUIRED; no blanket exception.\n')
        from tools.workstation_task3_tf_direct import paired_release_constraint_mappings
        parent = legacy
        for before, after in reversed(paired_release_constraint_mappings()):
            self.assertEqual(parent.count(after), 1)
            parent = parent.replace(after, before, 1)
        selected, receipt = adapt_constraints(ROOT, parent, 'M', midi_release_policy=POLICY)
        self.assertEqual(restore_constraints(ROOT, selected, receipt), parent)
        self.assertIn(CORRECT_SELECTOR, selected)
        self.assertNotIn(STALE_SELECTOR, selected)
        self.assertEqual(selected.count('set_false_path'), parent.count('set_false_path'))
        old, old_receipt = adapt_constraints(ROOT, parent, 'M')
        self.assertIn(STALE_SELECTOR, old)
        self.assertNotIn('M_MIDI_root_release', old_receipt)
        for role, policy in (('W', POLICY), ('M', 'unreviewed')):
            self.rejected('wrong role/policy '+role+policy,
                lambda role=role, policy=policy: adapt_constraints(ROOT, parent, role, midi_release_policy=policy))

    def test_03_actual_netlist_and_provider_negatives(self):
        n, g = self.n, Graph(self.n)
        cases = []
        for bit in range(3):
            p = g.register(ACTUAL_OWNER, 'source_release', bit)
            cases.extend((str(bit)+' '+label, p, part, key, value) for label, part, key, value in (
                ('INIT', 'parameters', 'INIT', "1'b1"),
                ('clock', 'ports', 'CLK', 'clk_50m'),
                ('CE', 'ports', 'CE', "1'b0")))
        p = g.register('u_managed/midi_bytes', 'acknowledge_toggle')
        cases.extend((('functional clear removed', p, 'ports', 'CLEAR', "1'b0"),
                      ('missing existing PC reset', g.register('u_managed/pc_bytes', 'req_meta'), 'ports', 'CLEAR', "1'b0")))
        for label, p, part, key, value in cases:
            saved = copy.deepcopy(n.cells[p])
            try:
                n.cells[p][part][key] = value
                self.rejected(label, lambda: audit_midi_release_sdc(n, self.projected, root=self.root))
            finally:
                n.cells[p] = saved
        p = 'audit_unreviewed_midi_consumer'
        n.cells[p] = dict(kind='DFFCE', parameters={}, ports=dict(Q='audit_extra_q',
            D=n.pin(g.register(ACTUAL_OWNER, 'source_release', 2), 'Q'),
            CE="1'b1", CLEAR="1'b0", CLK='audio_clk'))
        n.scopes[p] = ''
        try:
            self.rejected('new final Q data bypass', lambda: audit_midi_release_sdc(n, self.projected, root=self.root))
        finally:
            del n.cells[p]; del n.scopes[p]
        for bad in ({}, dict(mapped_structure_verified=True, policy='unreviewed')):
            self.rejected('missing or wrong batch proof', lambda bad=bad: audit_midi_release_sdc(
                n, self.projected, root=dict(self.root, batch_mapped_structure=bad)))
        for label, patch in (
            ('unknown provider', dict(selected_provider='unreviewed')),
            ('opposite role', dict(selected_provider='rtl/workstation/workstation_profile_task3_w_paired_phone_batch.sv')),
            ('wrong root alias', dict(mapped_common_root_name=
                'terminal_ready' if self.root['mapped_common_root_name']=='reset_n' else 'reset_n')),
            ('inverted root', dict(common_root_output_polarity=0)),
            ('forged source binding', dict(source_sha256={})),
        ):
            self.rejected(label, lambda patch=patch: audit_midi_release_sdc(
                n, self.projected, root=dict(self.root, **patch)))


if __name__ == '__main__':
    unittest.main()
