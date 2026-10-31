#!/usr/bin/env python3
"""Role gates reject swept audio/video, shadow recorders and stale exceptions."""
from pathlib import Path
from types import SimpleNamespace
import copy
import sys
import unittest

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


if __name__ == '__main__':
    unittest.main()
