#!/usr/bin/env python3
"""Physical experiments preserve audited native inputs and deployment gates."""

from pathlib import Path
import copy
import json
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_custom_board_implementation as physical
from tools import workstation_pinout as pinout
from tools.stage_usb_firmware import sha
from test_workstation_pinout import fixture


class PhysicalPreparation(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / 'synthesis'
        self.output = self.base / 'physical'
        stage = self.source / 'workstation/Prj1'
        self.netlist = stage / f'impl/gwsynthesis/{physical.BASE}.vg'
        self.netlist.parent.mkdir(parents=True)
        self.netlist.write_text('audited native netlist\n')
        (stage / 'constraints').mkdir()
        for name in ('cst', 'sdc'):
            (stage / f'constraints/custom_138k.{name}').write_bytes(('unchanged ' + name + '\n').encode())
        metadata = dict(staged_input_sha256={
            f'constraints/custom_138k.{name}': sha(stage / f'constraints/custom_138k.{name}')
            for name in ('cst', 'sdc')}, remaining_gaps=['electrical', 'physical gates'])
        manifest = self.source / 'integration_inputs.json'
        manifest.write_text(json.dumps(metadata))
        self.audit = dict(identity='audited-parent', top_module=physical.TOP,
                          electrical_blocked=True, integration_inputs_sha256=sha(manifest),
                          netlist_sha256=sha(self.netlist))
        self.mock_audit = patch.object(physical, 'audit_synthesis', return_value=self.audit).start()
        self.addCleanup(patch.stopall)

    def test_acknowledgement_and_new_identity_are_required(self):
        with self.assertRaisesRegex(ValueError, 'acknowledgement'):
            physical.prepare(self.source, self.output, 'C1102501')
        self.mock_audit.assert_not_called()
        with self.assertRaisesRegex(ValueError, 'eight-hex'):
            physical.prepare(self.source, self.output, '85', True)
        self.assertFalse(self.output.exists())

    def test_parent_audit_failure_never_prepares_outputs(self):
        self.mock_audit.side_effect = ValueError('source drift')
        with self.assertRaisesRegex(ValueError, 'source drift'):
            physical.prepare(self.source, self.output, 'C1102501', True)
        self.assertFalse(self.output.exists())

    def test_drift_after_audit_is_rejected(self):
        self.netlist.write_text('changed netlist\n')
        with self.assertRaisesRegex(ValueError, 'input changed'):
            physical.prepare(self.source, self.output, 'C1102501', True)
        self.assertFalse(self.output.exists())

    def test_constraints_clocks_and_gates_are_not_relaxed(self):
        result = physical.prepare(self.source, self.output, 'c1102501', True)
        self.assertEqual(result['user_code'], '0xC1102501')
        self.assertEqual(sha(self.output / (physical.BASE + '.vg')), self.audit['netlist_sha256'])
        for name in ('cst', 'sdc'):
            self.assertEqual((self.output / f'physical.{name}').read_text(), 'unchanged ' + name + '\n')
        script = (self.output / 'run.tcl').read_text()
        self.assertIn('set_option -user_code C1102501\n', script)
        self.assertIn('set_option -bit_security 0\n', script)
        self.assertIn('set_option -secure_mode 0\n', script)
        self.assertIn('set_option -use_mspi_as_gpio 1\n', script)
        self.assertIn('set_option -use_cpu_as_gpio 1\n', script)
        self.assertIn(physical.BASE + '.vg', script)
        self.assertEqual(script.count('run pnr\n'), 1)
        self.assertNotIn('set_false_path', script)
        self.assertNotIn('create_clock', script)
        self.assertNotIn('openFPGALoader', script)
        self.assertTrue(result['electrical_blocked'])
        for key in ('deployment_allowed', 'release_ready', 'physical_gates_passed',
                    'timing_closed', 'sram_programmed', 'flash_programmed'):
            self.assertFalse(result[key])
        for name, expected in result['input_sha256'].items():
            self.assertEqual(sha(self.output / name), expected)

    def test_existing_output_and_parent_mutation_are_rejected(self):
        self.output.mkdir()
        with self.assertRaises(FileExistsError):
            physical.prepare(self.source, self.output, 'C1102501', True)
        with self.assertRaisesRegex(ValueError, 'parent candidate'):
            physical.prepare(self.source, self.source / 'physical', 'C1102501', True)

    def test_clear_nominal_voltage_domain_does_not_enable_deployment(self):
        self.audit['electrical_blocked'] = False
        with self.assertRaisesRegex(ValueError, 'acknowledgement'):
            physical.prepare(self.source, self.output, 'C1102501')
        result = physical.prepare(self.source, self.output, 'C1102501', True)
        self.assertFalse(result['electrical_blocked'])
        for key in ('deployment_allowed', 'release_ready', 'physical_gates_passed',
                    'hardware_tested', 'sram_programmed', 'flash_programmed'):
            self.assertFalse(result[key])

    def test_unknown_electrical_identity_is_rejected(self):
        for value in (None, 0, 1, 'false'):
            self.audit['electrical_blocked'] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'electrical identity'):
                physical.prepare(self.source, self.output, 'C1102501', True)
        self.assertFalse(self.output.exists())

    def bypass_inputs(self):
        profile, payloads, core = fixture()
        plan = pinout.resolve(profile, {role: pinout.Netlist(payload) for role, payload in payloads.items()}, core)
        payload = pinout.render_constraints(plan).replace('\n', '\r\n').encode()
        constraints = self.source / 'workstation/Prj1/constraints/custom_138k.cst'
        constraints.write_bytes(payload)
        plan_path = self.source / 'pinout/pinout.json'
        plan_path.parent.mkdir()
        plan_path.write_text(json.dumps(plan))
        manifest = self.source / 'integration_inputs.json'
        metadata = json.loads(manifest.read_text())
        metadata['pinout_sha256'] = sha(plan_path)
        metadata['staged_input_sha256']['constraints/custom_138k.cst'] = sha(constraints)
        manifest.write_text(json.dumps(metadata))
        self.audit['integration_inputs_sha256'] = sha(manifest)
        self.audit['electrical_blocked'] = False
        return plan, payload

    def test_ulpi_io_standard_does_not_supply_risk_or_board_authorization(self):
        self.bypass_inputs()
        with self.assertRaisesRegex(ValueError, 'acknowledgement'):
            physical.prepare(self.source, self.output, 'C1102501', ulpi_bypass_lvcmos33=True)
        self.mock_audit.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_ulpi_io_standard_preserves_locations_other_ports_sdc_and_source_bytes(self):
        plan, original = self.bypass_inputs()
        result = physical.prepare(self.source, self.output, 'C1102501', True, ulpi_bypass_lvcmos33=True)
        adapted = (self.output / 'physical.cst').read_bytes()
        expected = ''.join('IO_PORT "' + port + '" IO_TYPE=LVCMOS33;\n'
                           for port in plan['ports'] if port.startswith('usb2_ulpi_')).encode()
        self.assertEqual(adapted, original + expected)
        self.assertEqual(pinout.parse_locations(adapted.decode()), pinout.parse_locations(original.decode()))
        self.assertEqual((self.source / 'workstation/Prj1/constraints/custom_138k.cst').read_bytes(), original)
        self.assertEqual((self.output / 'physical.sdc').read_bytes(), b'unchanged sdc\n')
        self.assertEqual(result['parent_input_sha256']['physical.cst'], pinout.digest(original))
        self.assertEqual(result['ulpi_io_type_adaptation']['before_sha256'], pinout.digest(original))
        self.assertEqual(result['ulpi_io_type_adaptation']['after_sha256'], pinout.digest(adapted))
        self.assertEqual(len(result['ulpi_io_type_adaptation']['ports']), 12)
        self.assertEqual(sha(self.output / 'parent_pinout.json'), sha(self.source / 'pinout/pinout.json'))
        self.assertIn('offline physical experiment only', result['acknowledgement_scope'])
        self.assertNotIn('requested deployment', result['acknowledgement_scope'])
        for key in ('board_programming_authorized', 'deployment_allowed', 'release_ready',
                    'hardware_tested', 'sram_programmed', 'flash_programmed'):
            self.assertFalse(result[key])
        for key in ('actual_board_measured', 'full_electrical_acceptance', 'external_io_timing_complete'):
            self.assertFalse(result['ulpi_io_type_adaptation'][key])
        for name, expected_hash in result['input_sha256'].items():
            self.assertEqual(sha(self.output / name), expected_hash)

    def test_ulpi_io_standard_rejects_unreviewed_assembly_supply_or_acceptance_claims(self):
        plan, payload = self.bypass_inputs()
        variants = []
        changed = copy.deepcopy(plan)
        changed['ulpi_bypass'].pop('U4')
        variants.append(changed)
        for key, value in (('status', 'blocked'), ('actual_board_measured', True),
                           ('full_electrical_acceptance', True), ('findings', [{'code': 'unexpected'}])):
            changed = copy.deepcopy(plan)
            changed['electrical_check'][key] = value
            variants.append(changed)
        for key, value in (('nominal_mv', 1800), ('phy_side', 'A'), ('assembly', 'fitted'),
                           ('supply_node', 'U4.2'), ('supply_network', 'unreviewed_3V3')):
            changed = copy.deepcopy(plan)
            changed['electrical_check']['translators'][0][key] = value
            variants.append(changed)
        changed = copy.deepcopy(plan)
        changed['electrical_check']['translators'].append(copy.deepcopy(changed['electrical_check']['translators'][0]))
        variants.append(changed)
        for index, changed in enumerate(variants):
            with self.subTest(variant=index), self.assertRaisesRegex(ValueError, 'ULPI'):
                physical.ulpi_bypass_constraints(payload, changed)

    def test_ulpi_io_standard_rejects_location_drift_and_existing_overrides(self):
        plan, payload = self.bypass_inputs()
        variants = (payload.replace(b'IO_LOC "usb2_ulpi_stp" E17;\r\n', b''),
                    payload.replace(b'IO_LOC "usb2_ulpi_stp" E17;', b'IO_LOC "usb2_ulpi_stp" E16;'),
                    payload + b'IO_LOC "usb2_ulpi_extra" F17;\n',
                    payload + b'IO_PORT "usb2_ulpi_stp" IO_TYPE=LVCMOS18;\n')
        for index, changed in enumerate(variants):
            with self.subTest(variant=index), self.assertRaisesRegex(ValueError, 'ULPI'):
                physical.ulpi_bypass_constraints(changed, plan)

    def test_ulpi_io_standard_rejects_pinout_drift_before_output_creation(self):
        self.bypass_inputs()
        plan_path = self.source / 'pinout/pinout.json'
        plan_path.write_bytes(plan_path.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'input changed: parent_pinout.json'):
            physical.prepare(self.source, self.output, 'C1102501', True, ulpi_bypass_lvcmos33=True)
        self.assertFalse(self.output.exists())

    def test_physical_search_does_not_change_clocks_or_enable_protection(self):
        script = physical.implementation_script('C1102503', 1, 1, True)
        self.assertIn('set_option -place_option 1\n', script)
        self.assertIn('set_option -route_option 1\n', script)
        self.assertIn('set_option -replicate_resources 1\n', script)
        self.assertIn('set_option -bit_security 0\n', script)
        self.assertNotIn('set_false_path', script)
        with self.assertRaisesRegex(ValueError, 'algorithm'):
            physical.implementation_script('C1102503', 5, 0)

    def prepare_variant_parent(self):
        self.audit['identity'] = 'custom138k-native-integration-20261025-a18'
        physical.prepare(self.source, self.output, 'C1102501', True)
        adapter = runpy.run_path(str(ROOT / 'reports/workstation_physical_20261025/derive_physical.py'),
                                 run_name='physical_variant_test')
        return adapter['derive'], self.base / 'variant'

    def test_variant_keeps_all_audited_execution_inputs(self):
        derive, destination = self.prepare_variant_parent()
        result = derive(self.output, destination, 'C1102503', 1, 1, True)
        for name in (physical.BASE + '.vg', 'physical.cst', 'physical.sdc',
                     'parent_synthesis_audit.json', 'parent_integration_inputs.json'):
            self.assertEqual(sha(self.output / name), sha(destination / name))
        self.assertEqual(result['netlist_sha256'], self.audit['netlist_sha256'])
        self.assertEqual(result['parent_physical_identity'], 'custom138k-native-physical-C1102501')
        self.assertEqual(result['user_code'], '0xC1102503')
        self.assertFalse(result['bit_security'])
        self.assertFalse(result['deployment_allowed'])
        self.assertTrue(result['electrical_blocked'])
        for name, expected in result['input_sha256'].items():
            self.assertEqual(sha(destination / name), expected)

    def test_variant_rejects_drift_before_creating_outputs(self):
        derive, destination = self.prepare_variant_parent()
        (self.output / 'physical.sdc').write_text('relaxed clocks\n')
        with self.assertRaisesRegex(ValueError, 'input drifted'):
            derive(self.output, destination, 'C1102503', 1, 1, True)
        self.assertFalse(destination.exists())

    def test_hold_diagnostic_does_not_relax_constraints_or_signoff(self):
        derive, destination = self.prepare_variant_parent()
        result = derive(self.output, destination, 'C1102509', 2, 0, False, True)
        script = (destination / 'run.tcl').read_text()
        self.assertIn('set_option -correct_hold_violation 0\n', script)
        self.assertIn('set_option -timing_driven 1\n', script)
        for name in ('physical.cst', 'physical.sdc'):
            self.assertEqual(sha(self.output / name), sha(destination / name))
        self.assertTrue(result['hold_diagnostic_only'])
        self.assertTrue(result['full_timing_gates_required'])
        self.assertFalse(result['automatic_hold_repair'])
        self.assertFalse(result['deployment_allowed'])
        self.assertFalse(result['physical_gates_passed'])

    def test_variant_requires_a_new_identity(self):
        derive, destination = self.prepare_variant_parent()
        with self.assertRaisesRegex(ValueError, 'new physical UserCode'):
            derive(self.output, destination, 'C1102501', 1, 1, True)
        self.assertFalse(destination.exists())

    def prepare_ddr_floorplan_parent(self, include_minimum=True):
        self.audit['identity'] = 'custom138k-native-integration-20261025-a23'
        if include_minimum:
            source = self.source / 'workstation/Prj1/constraints/custom_138k.sdc'
            phy = 'u_memory/u_ddr3/gw3_top/u_ddr_phy_top'
            source.write_text(source.read_text() + f'set_min_delay 0.800 -from [get_pins {{{phy}/ddr_init_internal_r_s0/Q}}] -to [get_pins {{{phy}/wloadn_3_s0/D}}]\n')
            manifest = self.source / 'integration_inputs.json'
            metadata = json.loads(manifest.read_text())
            metadata['staged_input_sha256']['constraints/custom_138k.sdc'] = sha(source)
            manifest.write_text(json.dumps(metadata))
            self.audit['integration_inputs_sha256'] = sha(manifest)
        physical.prepare(self.source, self.output, 'C1102513', True)
        adapter = runpy.run_path(str(ROOT / 'reports/workstation_physical_20261025/derive_physical.py'),
                                 run_name='physical_floorplan_test')
        return adapter['derive'], self.base / 'floorplan'

    def test_ddr_floorplan_adds_only_placement_and_keeps_all_timing_gates(self):
        derive, destination = self.prepare_ddr_floorplan_parent()
        result = derive(self.output, destination, 'C1102514', 1, 1, False, ddr_hold_floorplan=True)
        self.assertEqual(sha(self.output / 'physical.sdc'), sha(destination / 'physical.sdc'))
        self.assertEqual(sha(self.output / (physical.BASE + '.vg')), sha(destination / (physical.BASE + '.vg')))
        self.assertEqual((destination / 'physical.cst').read_text(), (self.output / 'physical.cst').read_text() +
                         '\n' + result['ddr_hold_floorplan']['constraint'] + '\n')
        self.assertEqual(result['ddr_hold_floorplan']['region'], 'R[40:50]C[70:90]')
        self.assertTrue(result['automatic_hold_repair'])
        self.assertTrue(result['full_timing_gates_required'])
        self.assertFalse(result['clocks_or_exceptions_relaxed'])
        self.assertFalse(result['deployment_allowed'])
        for name, expected in result['input_sha256'].items():
            self.assertEqual(sha(destination / name), expected)

    def test_ddr_floorplan_rejects_missing_timing_policy_and_disabled_repair(self):
        derive, destination = self.prepare_ddr_floorplan_parent(include_minimum=False)
        with self.assertRaisesRegex(ValueError, 'source policy drifted'):
            derive(self.output, destination, 'C1102514', 1, 1, False, ddr_hold_floorplan=True)
        with self.assertRaisesRegex(ValueError, 'automatic repair'):
            derive(self.output, destination, 'C1102514', 1, 1, False, True, True)
        self.assertFalse(destination.exists())


class ExperimentalTimingAuthorization(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        adapter = runpy.run_path(str(ROOT / 'reports/workstation_physical_20261025/prepare_deployment.py'),
                                 run_name='experimental_deployment_test')
        self.verify = adapter['verify_timing_authorization']
        self.inputs = dict(identity='test-candidate', user_code='0xC1102515')
        (self.base / 'physical_inputs.json').write_text(json.dumps(self.inputs))
        bitstream = self.base / 'impl/pnr/custom_138k_integration.fs'
        bitstream.parent.mkdir(parents=True)
        bitstream.write_text('exact candidate bytes\n')
        self.timing = dict(global_worst_ns=dict(setup=-0.568, hold=0.155, recovery=2.981, removal=0.250),
                           pulse_width_violations=[])
        self.record = dict(physical_identity=self.inputs['identity'], user_code=self.inputs['user_code'],
                           physical_inputs_sha256=sha(self.base / 'physical_inputs.json'),
                           bitstream_sha256=sha(bitstream), sram_and_flash_authorized=True,
                           setup_only_exception=True, user_statement='accepted setup slack',
                           deployment_request='program SRAM and Flash')
        self.authorization = self.base / 'authorization.json'
        self.save()

    def save(self):
        report = self.base / 'timing-audit.json'
        report.write_text(json.dumps(self.timing))
        self.record['timing_audit_sha256'] = sha(report)
        self.authorization.write_text(json.dumps(self.record))

    def test_exact_authorization_preserves_failed_sta(self):
        result = self.verify(self.authorization, self.base, self.inputs)
        self.assertEqual(result['sha256'], sha(self.authorization))
        self.assertEqual(json.loads((self.base / 'timing-audit.json').read_text()), self.timing)

    def test_authorization_does_not_transfer_to_changed_inputs(self):
        for field in ('physical_identity', 'user_code', 'physical_inputs_sha256',
                      'timing_audit_sha256', 'bitstream_sha256', 'sram_and_flash_authorized'):
            with self.subTest(field=field):
                changed = dict(self.record, **{field: 'changed'})
                self.authorization.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, 'exact candidate'):
                    self.verify(self.authorization, self.base, self.inputs)

    def test_worse_setup_other_violations_and_missing_request_are_rejected(self):
        for kind in ('setup', 'hold', 'recovery', 'removal', 'pulse', 'request'):
            with self.subTest(kind=kind):
                self.timing['global_worst_ns'] = dict(setup=-0.568, hold=0.155, recovery=2.981, removal=0.250)
                self.timing['pulse_width_violations'] = []
                self.record['deployment_request'] = 'program SRAM and Flash'
                if kind in self.timing['global_worst_ns']:
                    self.timing['global_worst_ns'][kind] = -0.569
                elif kind == 'pulse':
                    self.timing['pulse_width_violations'] = ['pulse width failure']
                else:
                    self.record['deployment_request'] = ''
                self.save()
                with self.assertRaisesRegex(ValueError, 'setup violation'):
                    self.verify(self.authorization, self.base, self.inputs)


if __name__ == '__main__':
    unittest.main()
