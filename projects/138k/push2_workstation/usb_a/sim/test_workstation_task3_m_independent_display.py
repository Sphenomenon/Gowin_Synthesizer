#!/usr/bin/env python3
"""Independent M's actual mixed FF/RAM display proof and destructive controls."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_native_protocol_audit import (
    RAM_SCOPE, RAM_STEM, audit_demo_held_boundaries, audit_native_protocol,
    protocol_netlist, validate_native_protocol_sdc,
)
from tools.workstation_performance_reset import demo_held_handshake_constraints

PROFILE = 'm-task3-independent'
DISPLAY = 'u_managed/display'
HMI = 'u_video/u_applied_parameters_cdc'


class ActualIndependentDisplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected = os.environ.get('GW138K_TASK3_M_INDEPENDENT_CANDIDATE')
        if not selected:
            raise unittest.SkipTest('explicit actual candidate required; no cache fallback')
        cls.candidate = Path(selected)
        descriptor = json.loads((cls.candidate / 'workstation_profile.json').read_text())
        assert descriptor['profile'] == 'custom138k-workstation-task3-m-independent-ddr-map-v1'
        cls.stage = cls.candidate / 'workstation/Prj1'
        cls.vg = cls.stage / 'impl/gwsynthesis/custom_138k_integration.vg'
        cls.n = protocol_netlist(cls.vg.read_text(), mapping='synthesis')
        cls.result = audit_native_protocol(cls.n, profile=PROFILE)
        cls.result['demo_held_handshakes'] = audit_demo_held_boundaries(cls.n, cls.result)
        cls.sdc = (cls.stage / 'constraints/custom_138k.sdc').read_text()
        cls.cases = []

    @classmethod
    def tearDownClass(cls):
        evidence = os.environ.get('GW138K_TASK3_M_INDEPENDENT_DISPLAY_EVIDENCE')
        if evidence:
            Path(evidence).write_text(json.dumps(dict(
                profile=PROFILE, mapping='synthesis', candidate=str(cls.candidate),
                netlist_sha256=hashlib.sha256(cls.vg.read_bytes()).hexdigest(),
                sdc_sha256=hashlib.sha256(cls.sdc.encode()).hexdigest(),
                negative_controls=cls.cases, rejected_count=len(cls.cases),
                physical_cdc_accepted=False, hardware_tested=False), indent=2) + '\n')

    @contextmanager
    def changed(self, path, part, key, value):
        binding = self.n.cells[path][part]
        original = binding[key]
        binding[key] = value
        try:
            yield
        finally:
            binding[key] = original

    def reject_netlist(self, label, path, part, key, value, error):
        with self.changed(path, part, key, value):
            with self.assertRaisesRegex(ValueError, error) as caught:
                audit_native_protocol(self.n, profile=PROFILE)
        self.cases.append(dict(case=label, error=str(caught.exception), rejected=True))

    def validate(self, sdc):
        return validate_native_protocol_sdc(sdc, self.n, self.result,
            demo_held_handshakes=demo_held_handshake_constraints())

    def reject_sdc(self, label, sdc, error):
        with self.assertRaisesRegex(ValueError, error) as caught:
            self.validate(sdc)
        self.cases.append(dict(case=label, error=str(caught.exception), rejected=True))

    def test_exact_five_mailboxes_and_existing_bounds(self):
        self.assertEqual(self.result['mailbox_count'], 5)
        display = next(r for r in self.result['mailboxes'] if r['scope'] == DISPLAY)
        hmi = next(r for r in self.result['mailboxes'] if r['scope'] == HMI)
        self.assertEqual((display['held_ff_bits'], display['registered_ram_bits'], display['payload_bits']),
                         (132, 98, 230))
        self.assertEqual((hmi['held_ff_bits'], hmi['registered_ram_bits'], hmi['payload_bits']), (60, 0, 60))
        checked = self.validate(self.sdc)
        self.assertTrue(checked['independent_display_hmi_bounds_verified'])
        self.assertFalse(checked['direct_display_hmi_ff_bounds_verified'])
        self.assertEqual(len(checked['registered_ram_source_pins']), 3)
        self.assertEqual(len(checked['exact_98_registered_ram_capture_pins']), 98)
        self.assertFalse(self.result['physical_cdc_accepted'])

    def test_legacy_inventory_does_not_silently_accept_new_display(self):
        with self.assertRaisesRegex(ValueError, 'register bit inventory changed'):
            audit_native_protocol(self.n, profile='m-demo-core')

    def test_added_parameter_bits_have_exact_clock_enable_and_mapping(self):
        for scope, bit, adjacent in ((DISPLAY, 206, 207), (HMI, 3, 4)):
            held = f'{scope}/held_data_{bit}_s0'
            capture = f'{scope}/destination_data_{bit}_s0'
            with self.subTest(scope=scope):
                self.reject_netlist(scope + ' wrong held clock', held, 'ports', 'CLK', "1'b0", 'clock changed')
                self.reject_netlist(scope + ' busy overwrite CE', held, 'ports', 'CE', "1'b1", 'capture enable differs')
                self.reject_netlist(scope + ' payload alias', capture, 'ports', 'D',
                    self.n.cells[f'{scope}/held_data_{adjacent}_s0']['ports']['Q'], 'held payload bit mapping')

    def test_hmi_ack_capture_third_stage_and_first_stage_fanout(self):
        self.reject_netlist('HMI ACK capture detached', HMI + '/acknowledge_toggle_s0',
            'ports', 'CE', "1'b1", 'ACK must capture')
        self.reject_netlist('HMI request settled bypass', HMI + '/req_settled_s0', 'ports', 'D',
            self.n.cells[HMI + '/request_toggle_s2']['ports']['Q'], 'third request stage')
        self.reject_netlist('HMI first stage extra consumer', HMI + '/held_data_3_s0', 'ports', 'D',
            self.n.cells[HMI + '/ack_meta_s0']['ports']['Q'], 'first-stage fanout')

    def test_registered_ram_cannot_change_hold_clock_or_mode(self):
        ram = RAM_SCOPE + RAM_STEM + '0_s'
        for part, key, value in (('ports', 'CEB', "1'b1"), ('ports', 'CLKB', "1'b0"),
                                 ('parameters', 'READ_MODE', "1'b1")):
            with self.subTest(key=key):
                self.reject_netlist('RAM ' + key, ram, part, key, value, 'RAM read register')

    def test_registered_ram_has_exact_output_mapping(self):
        self.reject_netlist('RAM output alias', DISPLAY + '/destination_data_105_s0', 'ports', 'D',
            self.n.cells[DISPLAY + '/destination_data_106_s0']['ports']['D'], 'RAM payload destination fanout')

    def test_all_display_hmi_and_ram_lines_are_mandatory_once(self):
        lines = [line for line in self.sdc.splitlines()
                 if line.startswith(('set_max_delay ', 'set_false_path ')) and
                 any(s in line for s in (DISPLAY + '/', HMI + '/'))]
        self.assertEqual(len(lines), 14)
        for index, line in enumerate(lines):
            with self.subTest(line=index):
                self.reject_sdc(f'missing line {index}', self.sdc.replace(line + '\n', '', 1),
                                'missing, duplicated or changed')
                self.reject_sdc(f'duplicate line {index}', self.sdc + line + '\n',
                                'missing, duplicated or changed')

    def test_widened_selectors_and_weaker_overrides_fail(self):
        for scope in (DISPLAY, HMI):
            target = scope + '/destination_data_*_s*/D'
            line = next(s for s in self.sdc.splitlines()
                        if s.startswith('set_max_delay 20.000 ') and scope + '/held_data_' in s)
            self.reject_sdc(scope + ' widened capture', self.sdc.replace(line, line.replace(target, '*/D')),
                            'missing, duplicated or changed')
            self.reject_sdc(scope + ' weaker max_delay', self.sdc +
                f'set_max_delay 100.000 -to [get_pins {{{target}}}]\n', 'finite setup bound overridden')

    def test_no_setup_or_hold_cuts_to_later_stages_or_payload(self):
        for scope in (DISPLAY, HMI):
            for stem in ('req_sync', 'req_settled', 'ack_sync', 'destination_data_3'):
                for kind in ('', ' -hold'):
                    self.reject_sdc(scope + '/' + stem + kind, self.sdc +
                        f'set_false_path{kind} -to [get_pins {{{scope}/{stem}_s*/D}}]\n',
                        'later synchronizer/settled')


if __name__ == '__main__':
    unittest.main()
