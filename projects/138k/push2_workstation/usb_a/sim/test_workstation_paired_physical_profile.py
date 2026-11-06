"""A paired PLL selection must bind source, profile, synthesis and exact SDC."""
from pathlib import Path
import copy
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

USB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(USB))
sys.path.insert(0, str(USB / 'tools'))
from tools import workstation_custom_board_implementation as prepare
from tools import workstation_task3_paired_audit as paired
from workstation_physical_pll_audit import physical_snapshot, source_context, verify_unchanged, sha


class PairedPhysicalProfile(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'source'
        self.stage = self.source / 'workstation/Prj1'
        self.physical = self.base / 'physical'
        name = 'custom138k-workstation-task3-m-paired-checkpoint-v17'
        role, identity, unused = paired.PROFILES[name]
        candidate = name + '-fixture'
        files = {
            'constraints/custom_138k.cst': 'IO_LOC "clk_50m" V22;\n',
            'constraints/custom_138k.sdc': '# unchanged clocks and exceptions\n',
            'impl/gwsynthesis/custom_138k_integration.vg':
                'module workstation_custom_138k_top(clk_50m);\ninput clk_50m;\nendmodule\n',
            'impl/gwsynthesis/custom_138k_integration_syn_rsc.xml': '<resources/>\n',
        }
        for relative, text in files.items():
            self.write(self.stage / relative, text)
        self.write(self.source / 'synthesis.log', 'GowinSynthesis finish\n')
        self.write(self.source / 'parent_prepare_metadata.json', '{}')
        self.write(self.source / 'pinout/pinout.json', '{}')
        self.write(self.source / 'workstation/resource_rework_overlays.json', '{}')
        closure = {'constraints/custom_138k.' + ext: sha(self.stage / ('constraints/custom_138k.' + ext))
                   for ext in ('cst', 'sdc')}
        self.profile = dict(candidate_identity=candidate, staged_input_sha256=closure,
                            resource_overlays_sha256=sha(self.source / 'workstation/resource_rework_overlays.json'))
        self.write_json(self.source / 'workstation_profile.json', self.profile)
        self.parent = dict(identity=identity, top_module=prepare.TOP, remaining_gaps=['full CDC', 'timing'],
            staged_input_sha256=closure, ae350_firmware=dict(evidence_directory='firmware', artifacts_sha256={}),
            parent_prepare_metadata_sha256=sha(self.source / 'parent_prepare_metadata.json'),
            pinout_sha256=sha(self.source / 'pinout/pinout.json'),
            workstation_profile=dict(name=name, artifact='workstation_profile.json',
                artifact_sha256=sha(self.source / 'workstation_profile.json'), candidate_identity=candidate),
            local_panel=dict(enabled=False, sources=[], sdc='', touch_input_selected=False,
                output_behavior='all_21_lcd_output_bits_static_low_backlight_off'))
        self.write_json(self.source / 'integration_inputs.json', self.parent)
        self.audit = dict(identity=identity, top_module=prepare.TOP, paired_role=role,
            candidate_identity=candidate, electrical_blocked=True,
            validation_stage='task3_paired_synthesis_only', source_policy='immutable_prepared_closure',
            audit_source_seal_before_and_after=True,
            integration_inputs_sha256=sha(self.source / 'integration_inputs.json'),
            netlist_sha256=sha(self.stage / 'impl/gwsynthesis/custom_138k_integration.vg'),
            resource_report_sha256=sha(self.stage / 'impl/gwsynthesis/custom_138k_integration_syn_rsc.xml'),
            synthesis_log_sha256=sha(self.source / 'synthesis.log'),
            gates={key: dict(passed=True) for key in ('feature_structure', 'port_coverage',
                   'visible_SDC_members', 'constraint_retirement_and_rebinding')})
        # Complete CPU/TF gates may still fail: this selects only PLL evidence.
        self.audit['gates']['M_paired_release_CDC'] = dict(passed=False)
        self.reference = self.stage / 'constraints/custom_138k.cst'
        self.addCleanup(patch.stopall)
        patch.object(prepare, 'audit_synthesis', return_value=self.audit).start()
        self.verified = patch.object(paired, 'verify_prepared',
            side_effect=lambda source, parent: ('M', self.profile, self.stage, {})).start()

    @staticmethod
    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def write_json(self, path, data):
        self.write(path, json.dumps(data))

    def prepared(self, standard=False):
        if standard:
            return prepare.prepare(self.source, self.physical, 'D21106ED', True)
        return prepare.prepare_reference(self.source, self.physical, 'D21106ED',
            self.reference, sha(self.reference), place_option=3)

    def context(self, inputs):
        self.write_json(self.physical / 'physical_inputs.json', inputs)
        unused, snapshot = physical_snapshot(self.physical)
        result = source_context(self.physical, inputs, snapshot)
        verify_unchanged(snapshot)
        return result

    def reseal(self, inputs, name, data):
        self.write_json(self.physical / name, data)
        inputs['input_sha256'][name] = sha(self.physical / name)

    def test_reference_preparation_seals_actual_profile_and_selects_no_panel(self):
        inputs = self.prepared()
        stage, parent, panel, selection = self.context(inputs)
        self.assertEqual(stage, self.stage)
        self.assertFalse(panel)
        self.assertEqual(selection['policy'], 'sealed_immutable_paired_profile_source')
        self.assertFalse(selection['acceptance_inherited'])
        self.assertEqual(selection['paired_role'], 'M')
        self.assertEqual(inputs['parent_candidate_identity'], self.profile['candidate_identity'])
        self.assertEqual(sha(self.physical / 'parent_workstation_profile.json'),
                         self.parent['workstation_profile']['artifact_sha256'])
        for key in ('deployment_allowed', 'hardware_tested', 'release_ready', 'timing_closed'):
            self.assertFalse(inputs[key])

    def test_standard_preparation_uses_the_same_seal(self):
        self.assertFalse(self.context(self.prepared(standard=True))[2])

    def test_preparer_rejects_role_profile_or_artifact_linkage_before_output(self):
        for field, value in (('paired_role', 'W'), ('candidate_identity', 'other'),
                             ('identity', 'other'), ('validation_stage', 'synthesis_only'),
                             ('source_policy', 'mutable'), ('audit_source_seal_before_and_after', False)):
            with self.subTest(field=field), patch.dict(self.audit, {field: value}), self.assertRaises(ValueError):
                self.prepared()
            self.assertFalse(self.physical.exists())

    def test_profile_or_synthesis_audit_cannot_be_omitted_from_seal(self):
        inputs = self.prepared()
        for name in ('parent_workstation_profile.json', 'parent_synthesis_audit.json'):
            changed = copy.deepcopy(inputs)
            del changed['input_sha256'][name]
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'not sealed'):
                self.context(changed)

    def test_resealed_role_candidate_and_parent_identity_cannot_be_substituted(self):
        inputs = self.prepared()
        for field in ('paired_role', 'parent_candidate_identity', 'parent_identity'):
            changed = copy.deepcopy(inputs); changed[field] = 'other'
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.context(changed)

    def test_resealed_profile_swap_still_must_equal_the_source(self):
        inputs = self.prepared()
        self.reseal(inputs, 'parent_workstation_profile.json', dict(self.profile, candidate_identity='other'))
        with self.assertRaisesRegex(ValueError, 'copied metadata differs'):
            self.context(inputs)

    def test_resealed_false_source_gate_and_wrong_synthesis_scope_are_rejected(self):
        inputs = self.prepared()
        for gate in self.audit['gates']:
            if gate == 'M_paired_release_CDC':
                continue
            changed = copy.deepcopy(self.audit); changed['gates'][gate]['passed'] = False
            self.reseal(inputs, 'parent_synthesis_audit.json', changed)
            with self.subTest(gate=gate), self.assertRaisesRegex(ValueError, 'source linkage differs'):
                self.context(inputs)
        changed = dict(self.audit, validation_stage='demo_full_profile_synthesis_only')
        self.reseal(inputs, 'parent_synthesis_audit.json', changed)
        with self.assertRaisesRegex(ValueError, 'source linkage differs'):
            self.context(inputs)

    def test_resealed_physical_sdc_and_vg_must_match_synthesis(self):
        inputs = self.prepared()
        for name in ('physical.sdc', 'custom_138k_integration.vg'):
            original = (self.physical / name).read_bytes()
            (self.physical / name).write_bytes(original + b'\n')
            inputs['input_sha256'][name] = sha(self.physical / name)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'physical/synthesis input differs'):
                self.context(inputs)
            (self.physical / name).write_bytes(original)
            inputs['input_sha256'][name] = sha(self.physical / name)

    def test_missing_or_invalid_pair_role_cannot_borrow_demo_or_legacy_contract(self):
        inputs = self.prepared()
        for field in ('paired_role',):
            changed = copy.deepcopy(inputs); changed.pop(field)
            with self.assertRaises(ValueError):
                self.context(changed)
        changed = copy.deepcopy(inputs); changed['paired_role'] = None
        with self.assertRaises(ValueError):
            self.context(changed)
        for field, value in (('source', dict(synthesis={})), ('demo_role', 'M')):
            changed = copy.deepcopy(inputs); changed[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'competing physical source evidence'):
                self.context(changed)


class ActualPairedContext(unittest.TestCase):
    def test_actual_selected_source_and_exact_physical_pin_collections(self):
        selected = os.environ.get('GW138K_PAIRED_PLL_PHYSICAL')
        if not selected:
            self.skipTest('explicit prepared paired physical candidate required')
        physical = Path(selected)
        inputs, snapshot = physical_snapshot(physical)
        stage, parent, panel, selection = source_context(physical, inputs, snapshot)
        self.assertFalse(panel)
        self.assertFalse(selection['acceptance_inherited'])
        self.assertEqual(selection['candidate_identity'], inputs['parent_candidate_identity'])
        for key, value in (('paired_role', 'W'), ('parent_candidate_identity', 'other'),
                           ('task3_pin_adaptation', None)):
            changed = copy.deepcopy(inputs); changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                source_context(physical, changed, {})
        changed = copy.deepcopy(inputs)
        changed['task3_pin_adaptation']['output_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            source_context(physical, changed, {})
        verify_unchanged(snapshot)


if __name__ == '__main__':
    unittest.main()
