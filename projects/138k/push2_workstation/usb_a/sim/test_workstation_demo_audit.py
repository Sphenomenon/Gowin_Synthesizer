#!/usr/bin/env python3
"""Role gates reject swept audio/video, shadow recorders and stale exceptions."""
from pathlib import Path
from types import SimpleNamespace
import copy
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_demo_audit as audit
from tools.workstation_demo_policy import adapt_constraints
from tools.workstation_synthesis_netlist import SynthesisNetlist


def fixture(bluetooth=False):
    text = '''module workstation_custom_138k_top (clk,d,q);
input clk;
input d;
output q;
DFFCE live_0_s0 (.D(d),.Q(q),.CLK(clk),.CE(d),.CLEAR(d));
'''
    if bluetooth:
        text += 'ble u_bluetooth (.clk(clk),.d(d),.q(q));\n'
    text += 'endmodule\n'
    if bluetooth:
        text += '''module ble (clk,d,q);
input clk;
input d;
output q;
DFFCE rx_sync_0_s0 (.D(d),.Q(q),.CLK(clk),.CE(d),.CLEAR(d));
endmodule
'''
    return SynthesisNetlist(text, audit.TOP)


class OptionalReturnAuditor(unittest.TestCase):
    def test_old_policies_do_not_require_new_helper_but_v3_does(self):
        class PreparedBoundaryReached(Exception):
            pass
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in audit.AUDIT_SOURCES:
                if name in ('tools/workstation_w_return_mailbox_cdc.py',
                            'tools/workstation_bluetooth_ddr.py'):
                    continue
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('frozen auditor fixture\n')
            for policy in (None, 'independent-demo-runtime-timing-v1',
                           'independent-demo-runtime-timing-v2'):
                for role in ('M', 'W'):
                    metadata = {'demo_role': role}
                    if policy is not None:
                        metadata['demo_runtime_timing'] = {'policy': policy}
                    with self.subTest(policy=policy, role=role), patch.object(audit, 'verify_prepared',
                            side_effect=PreparedBoundaryReached):
                        with self.assertRaises(PreparedBoundaryReached):
                            audit.audit(root, root / 'candidate', metadata)
            metadata = {'demo_runtime_timing': {
                'policy': 'independent-demo-w-return-mailbox-timing-v3'}}
            with patch.object(audit, 'verify_prepared', side_effect=PreparedBoundaryReached):
                with self.assertRaisesRegex(FileNotFoundError, 'workstation_w_return_mailbox_cdc.py'):
                    audit.audit(root, root / 'candidate', metadata)
                (root / 'tools/workstation_w_return_mailbox_cdc.py').write_text('selected helper\n')
                with self.assertRaisesRegex(FileNotFoundError, 'workstation_bluetooth_ddr.py'):
                    audit.audit(root, root / 'candidate', metadata)
                (root / 'tools/workstation_bluetooth_ddr.py').write_text('selected source authority\n')
                with patch.object(audit, 'sha', wraps=audit.sha) as hashes:
                    with self.assertRaises(PreparedBoundaryReached):
                        audit.audit(root, root / 'candidate', metadata)
                    paths = {call.args[0].name for call in hashes.call_args_list}
                    self.assertTrue({'workstation_w_return_mailbox_cdc.py',
                                     'workstation_bluetooth_ddr.py'} <= paths)


class VisibleConstraints(unittest.TestCase):
    def setUp(self):
        self.netlist = fixture()
        self.sdc = ('create_clock -name test -period 20 [get_ports {clk}]\n'
                    'set_false_path -to [get_pins {live_0_s0/D}]\n')

    def test_every_live_selector_resolves_without_promoting_STA(self):
        result = audit.audit_sdc_selectors(self.sdc, self.netlist)
        self.assertTrue(result['all_visible_selector_members_resolved'])
        self.assertFalse(result['tool_Tcl_resolution_verified'])
        self.assertFalse(result['routed_CDC_or_STA_accepted'])

    def test_a_live_member_does_not_hide_an_empty_mixed_member(self):
        with self.assertRaisesRegex(ValueError, 'retired.*/D'):
            audit.audit_sdc_selectors(self.sdc.replace('live_0_s0/D', 'live_0_s0/D retired*/D'), self.netlist)

    def test_unreviewed_whole_clock_cut_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'whole-clock'):
            audit.audit_sdc_selectors(self.sdc +
                'set_false_path -from [get_clocks {test}] -to [get_clocks {test}]\n', self.netlist)

    def test_opaque_defer_needs_the_actual_encrypted_boundary(self):
        with self.assertRaisesRegex(ValueError, 'encrypted DDR boundary'):
            audit.audit_sdc_selectors(self.sdc +
                'set_false_path -to [get_pins {u_memory/u_ddr3/gw3_top/missing/D}]\n', self.netlist)

    def test_retirement_cannot_erase_a_live_bluetooth_endpoint(self):
        selected, record = adapt_constraints(self.sdc +
            'set_false_path -to [get_pins {u_bluetooth/rx_sync_0_s*/D}]\n', 'M')
        with self.assertRaisesRegex(ValueError, 'still has live endpoints'):
            audit.audit_constraint_retirement(selected, record, 'M', fixture(bluetooth=True))

    def test_rebinding_requires_old_absent_and_new_actual_pin_present(self):
        old = 'u_managed/runtime/cpu_pcm/switch_inhibit_compute'
        new = 'u_managed/runtime/cpu_pcm.switch_inhibit_compute'
        source = 'set_false_path -to [get_pins {' + old + '*/CLEAR}]\n'
        selected, evidence = adapt_constraints(source, 'W')
        n = SimpleNamespace(cells={new + '_0_s0': dict(kind='DFFPE', ports={'PRESET': 'rst'})},
                            directions={audit.TOP: {}})
        result = audit.audit_constraint_retirement(selected, evidence, 'W', n)
        self.assertTrue(result['every_rebound_selector_verified'])
        self.assertEqual(next(iter(result['rebound_selectors'].values()))['matched'], 1)
        n.cells[old + '_0_s0'] = dict(kind='DFFCE', ports={'CLEAR': 'rst'})
        with self.assertRaisesRegex(ValueError, 'source selector still has live'):
            audit.audit_constraint_retirement(selected, evidence, 'W', n)
        n.cells.clear()
        with self.assertRaisesRegex(ValueError, 'replacement has no live'):
            audit.audit_constraint_retirement(selected, evidence, 'W', n)

    def test_retirement_cannot_hide_a_live_member_in_the_actual_generate_scope(self):
        source = 'set_false_path -to [get_pins {u_managed/pcm_apb/commands/p_release*/CLEAR}]\n'
        selected, evidence = adapt_constraints(source, 'W')
        n = SimpleNamespace(cells={'u_managed/pcm_apb.commands/p_release_0_s0':
            dict(kind='DFFCE', ports={'CLEAR': 'rst'})}, directions={audit.TOP: {}})
        with self.assertRaisesRegex(ValueError, 'live rebound endpoints'):
            audit.audit_constraint_retirement(selected, evidence, 'W', n)


class RoleFeatures(unittest.TestCase):
    def setUp(self):
        self.rows = {p: dict(Bsram=40) for p in
                     {*audit.COMMON_FEATURES.values(), *audit.M_FEATURES.values()}}

    def test_vector_ROM_and_spectrum_storage_cannot_be_swept(self):
        for feature in ('vector', 'hdmi_spectrum'):
            changed = copy.deepcopy(self.rows)
            path = audit.M_FEATURES.get(feature, audit.COMMON_FEATURES.get(feature))
            changed[path]['Bsram'] = 0
            with self.subTest(feature=feature), self.assertRaises(ValueError):
                audit.audit_features('M', changed, SimpleNamespace(cells={}))

    def test_M_cannot_retain_a_second_role_owner(self):
        with self.assertRaisesRegex(ValueError, 'retired hierarchy'):
            audit.audit_features('M', dict(self.rows, u_bluetooth=dict(Bsram=32)), SimpleNamespace(cells={}))

    def test_W_has_one_real_PCM_recording_object_and_no_local_recorder(self):
        rows = {p: self.rows[p] for p in audit.COMMON_FEATURES.values()}
        cells = {str(i): dict(kind=kind) for i, kind in enumerate((
            'workstation_ae350_pcm_owner', 'workstation_ble_record_data_engine',
            'workstation_ble_raw_ddr_store', 'workstation_hci_native_transport'))}
        self.assertTrue(audit.audit_features('W', rows, SimpleNamespace(cells=cells))['role_retirement_verified'])
        for kind in ('workstation_ble_raw_ddr_store', 'workstation_recording_service',
                     'workstation_runtime_oscillator_engine', 'ble_recording'):
            changed = dict(cells, hidden=dict(kind=kind))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                audit.audit_features('W', rows, SimpleNamespace(cells=changed))

    def test_all_32_voice_states_must_reach_synthesis(self):
        cells = {}
        for stem, width in (('sample_envelope_q18', 18), ('envelope_state', 3), ('expression_gain_q8', 8)):
            cells.update({audit.ENGINES + '/oscillator/' + stem + f'[{voice}]_{bit}_s0': dict(kind='DFFCE')
                          for voice in range(32) for bit in range(width)})
        self.assertEqual(audit.audit_m_voice_storage(SimpleNamespace(cells=cells))['voices'], 32)
        cells.pop(audit.ENGINES + '/oscillator/envelope_state[31]_2_s0')
        with self.assertRaisesRegex(ValueError, '32-voice storage swept'):
            audit.audit_m_voice_storage(SimpleNamespace(cells=cells))


class Worker25kFeedback(unittest.TestCase):
    def setUp(self):
        prefix = self.prefix = 'u_native_usb/input_owner/feedback/'
        self.cells = {}
        def ff(stem, clock, q, d, ce='always'):
            self.cells[prefix + stem + '_s0'] = dict(kind='DFFCE',
                ports=dict(CLK=clock, Q=q, D=d, CE=ce, CLEAR='reset'))
        ff('request_toggle', 'audio', 'request', 'new_request', 'source_capture')
        ff('acknowledge_toggle', 'usb', 'ack', 'settled', 'destination_capture')
        for stem, clock, q, d in (
            ('req_meta', 'usb', 'meta', 'request'), ('req_sync', 'usb', 'sync', 'meta'),
            ('req_settled', 'usb', 'settled', 'sync'), ('ack_meta', 'audio', 'ameta', 'ack'),
            ('ack_sync', 'audio', 'async', 'ameta')):
            ff(stem, clock, q, d)
        for stem, clock in (('source_release', 'audio'), ('destination_release', 'usb')):
            for bit in range(3):
                ff(stem + '_' + str(bit), clock, stem + str(bit), stem + str(bit - 1))
        bits = {*range(32, 35), *range(37, 42), *range(56, 64), *range(132, 196),
                *range(224, 245), 276, *range(278, 288)}
        for bit in bits:
            ff('held_data_' + str(bit), 'audio', 'payload' + str(bit), 'input' + str(bit), 'source_capture')
            ff('destination_data_' + str(bit), 'usb', 'result' + str(bit), 'payload' + str(bit), 'destination_capture')
        self.n = SimpleNamespace(cells=self.cells,
            pin=lambda p, pin: self.cells[p]['ports'][pin])
        self.clocks = dict(clocks=dict(audio_76m8=dict(net='audio'), usb_48m=dict(net='usb')))

    def test_live_parameter_payload_and_handshake_pass_without_a_Push_pulse(self):
        result = audit.audit_worker_feedback(self.n, self.clocks)
        self.assertEqual(len(result['live_payload_bits']), 112)
        self.assertEqual((result['source_registers'], result['destination_registers']), (118, 119))
        self.assertFalse(result['physical_timing_verified'])

    def test_missing_payload_bit_is_rejected(self):
        self.cells.pop(self.prefix + 'held_data_132_s0')
        with self.assertRaisesRegex(ValueError, 'bitmap changed'):
            audit.audit_worker_feedback(self.n, self.clocks)

    def test_payload_mutation_or_capture_clock_change_is_rejected(self):
        path = self.prefix + 'destination_data_132_s0'
        self.cells[path]['ports']['D'] = 'unheld'
        with self.assertRaisesRegex(ValueError, 'immutable payload'):
            audit.audit_worker_feedback(self.n, self.clocks)
        self.cells[path]['ports']['D'] = 'payload132'
        self.cells[path]['ports']['CLK'] = 'audio'
        with self.assertRaisesRegex(ValueError, 'clock changed'):
            audit.audit_worker_feedback(self.n, self.clocks)

    def test_handshake_bypass_or_missing_reset_stage_is_rejected(self):
        path = self.prefix + 'ack_sync_s0'
        self.cells[path]['ports']['D'] = 'ack'
        with self.assertRaisesRegex(ValueError, 'direct stage changed'):
            audit.audit_worker_feedback(self.n, self.clocks)
        self.cells[path]['ports']['D'] = 'ameta'
        self.cells.pop(self.prefix + 'destination_release_1_s0')
        with self.assertRaisesRegex(ValueError, 'reset release inventory'):
            audit.audit_worker_feedback(self.n, self.clocks)


if __name__ == '__main__':
    unittest.main()
