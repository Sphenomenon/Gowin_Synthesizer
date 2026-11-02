"""Independent BLE source selection and live endpoint preservation."""
from pathlib import Path
import copy
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_profile as profile
from tools.workstation_demo_policy import adapt_constraints, verify_constraints, BLE_POLICY
from tools.workstation_demo_audit import audit_ble_business
from tools.workstation_synthesis_netlist import SynthesisNetlist


def ble_netlist_fixture():
    text = '''module workstation_custom_138k_top (src,dst,valid,error,rate,pcm,seq,epoch);
input src;
input dst;
input valid;
input error;
input rate;
input [31:0] pcm;
input [31:0] seq;
input [31:0] epoch;
managed u_managed (.mclk_o(src),.frame_valid_o(valid),.frame_error_o(error),.frame_44k1_o(rate),
 .frame_pcm_o(pcm),.frame_sequence_o(seq),.frame_epoch_o(epoch));
cdc u_ble_pcm_cdc (.source_clk(src),.destination_clk(dst),.source_valid(valid),.source_data({rate,error,epoch,seq,pcm}));
workstation_bluetooth u_bluetooth ();
endmodule
module managed (mclk_o,frame_valid_o,frame_error_o,frame_44k1_o,frame_pcm_o,frame_sequence_o,frame_epoch_o);
output mclk_o;
output frame_valid_o;
output frame_error_o;
output frame_44k1_o;
output [31:0] frame_pcm_o;
output [31:0] frame_sequence_o;
output [31:0] frame_epoch_o;
endmodule
module cdc (source_clk,destination_clk,source_valid,source_data);
input source_clk;
input destination_clk;
input source_valid;
input [97:0] source_data;
'''
    for stem, clock in (('held_data', 'source_clk'), ('destination_data', 'destination_clk')):
        for bit in range(98):
            data = f'source_data[{bit}]' if stem == 'held_data' else f'q_held_data_{bit}'
            text += f'DFFCE {stem}_{bit}_s0 (.CLK({clock}),.D({data}),.Q(q_{stem}_{bit}));\n'
    text += '''endmodule
module workstation_bluetooth ();
bt_verilog_core u_core ();
endmodule
module bt_verilog_core ();
bt_h5_transport transport ();
bt_hci_init initializer ();
bt_gatt application ();
endmodule
module bt_gatt ();
ble_protocol_command command_endpoint ();
endmodule
module ble_protocol_command ();
ble_recording recording ();
endmodule
'''
    for kind in ('bt_h5_transport', 'bt_hci_init', 'ble_recording'):
        text += f'module {kind} ();\nendmodule\n'
    return text


class BleDemo(unittest.TestCase):
    def test_independent_owner_and_actual_final_pcm_compilation(self):
        spec = profile.specification(profile.BLE_DEMO_NAME)
        self.assertTrue(spec['retain_bluetooth'])
        self.assertFalse(spec.get('recording_enabled', False))
        self.assertFalse(spec.get('business_owner_enabled', False))
        self.assertFalse(spec.get('hci_shared_owner_enabled', False))
        self.assertFalse(spec.get('worker_audio_only', False))
        with tempfile.TemporaryDirectory(prefix='ble-demo-preprocess-') as directory:
            output = Path(directory) / 'selected.sv'
            subprocess.run(['iverilog', '-g2012', '-grelative-include', '-E', '-I', str(ROOT),
                '-o', str(output), str(ROOT / spec['provider'])],
                cwd=ROOT, capture_output=True, text=True, check=True, timeout=30)
            selected = output.read_text()
        self.assertIn('workstation_bluetooth #(.EXTERNAL_SEAL_PROTOCOL(1)) u_bluetooth', selected)
        self.assertIn('gw138k_stream_cdc #(.WIDTH(98)) u_ble_pcm_cdc', selected)
        self.assertIn('assign ble_frame_pcm=physical_frame_pcm', selected)
        self.assertIn('!ble_frame44 && !ble_frame_error && ble_frame_epoch==rate_epoch', selected)
        self.assertNotIn('workstation_recording_runtime u_recording', selected)
        self.assertNotIn('workstation_tf_runtime_service u_tf_audio', selected)
        self.assertNotIn('SESSION_ONLY_PAIRING(1)', selected)
        self.assertIn('module workstation_custom_138k_top', selected)
        self.assertIn('u_runtime_display', selected)

    def test_live_ble_constraints_retained_with_local_recorder_and_tf_absent(self):
        source = ('set_false_path -to [get_pins {u_bluetooth/u_core/uart/rx_meta/D '
                  'u_recording/commands/req_meta/D u_native_usb/input_owner/meta/D}]\n'
                  'set_max_delay 10.000 -from [get_regs {u_ble_pcm_cdc/held_data*}] '
                  '-to [get_regs {u_ble_pcm_cdc/destination_data*}]\n'
                  'set_max_delay 13.020 -to [get_pins {u_tf_audio/frames/meta/D}]\n')
        selected, evidence = adapt_constraints(source, 'M', retain_bluetooth=True)
        self.assertEqual(evidence['policy'], BLE_POLICY)
        self.assertIn('u_bluetooth/u_core/uart/rx_meta/D', selected)
        self.assertIn('u_ble_pcm_cdc/held_data*', selected)
        self.assertIn('u_ble_pcm_cdc/destination_data*', selected)
        self.assertIn('u_native_usb/input_owner/meta/D', selected)
        self.assertNotIn('u_recording/', selected)
        self.assertNotIn('u_tf_audio/', selected)
        self.assertEqual(source, verify_constraints(selected, evidence, 'M', retain_bluetooth=True))
        with self.assertRaisesRegex(ValueError, 'retention'):
            verify_constraints(selected, evidence, 'M')
        with self.assertRaisesRegex(ValueError, 'retention'):
            regular, regular_evidence = adapt_constraints(source, 'M')
            verify_constraints(regular, regular_evidence, 'M', retain_bluetooth=True)
        with self.assertRaises(ValueError):
            verify_constraints(selected.replace('10.000', '100.000'), evidence, 'M', retain_bluetooth=True)
        forged = copy.deepcopy(evidence)
        forged['retired_prefixes'].append('u_bluetooth/')
        with self.assertRaises(ValueError):
            verify_constraints(selected, forged, 'M', retain_bluetooth=True)
        with self.assertRaises(ValueError):
            adapt_constraints(source, 'W', retain_bluetooth=True)

    def test_existing_m_and_w_policies_keep_their_original_selection(self):
        source = ('set_max_delay 10 -from [get_regs {u_ble_pcm_cdc/held_data*}] '
                  '-to [get_regs {u_ble_pcm_cdc/destination_data*}]\n')
        self.assertEqual(adapt_constraints(source, 'M')[0], '')
        self.assertEqual(adapt_constraints(source, 'W')[0], source)
        self.assertNotIn('retain_bluetooth', profile.specification(profile.M_DEMO_NAME))
        self.assertNotIn('retain_bluetooth', profile.specification(profile.W_DEMO_NAME))

    def test_ble_gate_rejects_competing_owner_missing_ram_and_changed_final_pcm(self):
        source = ble_netlist_fixture()
        rows = {'u_bluetooth/u_core/application/command_endpoint/recording': {'Bsram': 32}}
        clocks = {'clocks': {'clk_50m': {'net': 'dst'}}}
        def gate(text=source, selected_rows=rows):
            return audit_ble_business(SynthesisNetlist(text, 'workstation_custom_138k_top'), selected_rows, clocks)
        proof = gate()
        self.assertTrue(proof['exact_completed_frame_payload_verified'])
        self.assertFalse(proof['hardware_non_silent_capture_verified'])
        for label, changed in (
                ('swapped completed-frame fields', source.replace('{rate,error,epoch,seq,pcm}', '{rate,error,epoch,pcm,seq}')),
                ('wrong sample-valid', source.replace('.source_valid(valid)', '.source_valid(error)')),
                ('wrong held-data clock', source.replace('held_data_0_s0 (.CLK(source_clk)', 'held_data_0_s0 (.CLK(destination_clk)')),
                ('missing payload bit', source.replace('DFFCE destination_data_97_s0', 'DFFCE unexpected_97_s0')),
                ('second HCI initializer', source.replace('bt_hci_init initializer ();', 'bt_hci_init initializer ();\nbt_hci_init shadow_initializer ();'))):
            with self.subTest(case=label), self.assertRaises(ValueError):
                gate(changed)
        with self.assertRaisesRegex(ValueError, 'RAM missing'):
            gate(selected_rows={next(iter(rows)): {'Bsram': 31}})


@unittest.skipUnless(os.environ.get('GW138K_BLE_REFERENCE_VG'),
                     'Set GW138K_BLE_REFERENCE_VG for the real stereo inventory qualification controls')
class ActualBleStereoQualification(unittest.TestCase):
    def test_independent_ble_identity_and_revision_are_required_for_stereo_inventory(self):
        from tools.workstation_native_protocol_audit import audit_native_protocol, protocol_netlist
        text = Path(os.environ['GW138K_BLE_REFERENCE_VG']).read_text()
        netlist = protocol_netlist(text, mapping='synthesis')
        selected = dict(profile='m-demo-core', connected_xy=True, stereo_xy=True,
            profile_revision=1, profile_identity=profile.BLE_DEMO_NAME,
            xy_axes_policy='ordinary_mid_side_vector_direct_v1')
        result = audit_native_protocol(netlist, **selected)
        self.assertGreater(result['mailbox_count'], 0)
        for label, changed in (
                ('missing independent identity', dict(profile_identity=None)),
                ('M identity with BLE revision', dict(profile_identity=profile.M_DEMO_NAME)),
                ('wrong BLE revision', dict(profile_revision=4)),
                ('unspecified BLE revision', dict(profile_revision=None)),
                ('wrong role', dict(profile='w-demo-audio')),
                ('missing axes policy', dict(xy_axes_policy=None))):
            with self.subTest(case=label), self.assertRaises(ValueError):
                audit_native_protocol(netlist, **dict(selected, **changed))


@unittest.skipUnless(os.environ.get('GW138K_BLE_ACTUAL_VG'),
                     'Set GW138K_BLE_ACTUAL_VG for the actual BLE implementation controls')
class ActualBleMappedPcm(unittest.TestCase):
    def test_actual_mapped_completed_pcm_bit_delivery_and_negative_controls(self):
        import xml.etree.ElementTree as ET
        from tools.workstation_demo_audit import hierarchy_counts
        vg = Path(os.environ['GW138K_BLE_ACTUAL_VG'])
        netlist = SynthesisNetlist(vg.read_text(), 'workstation_custom_138k_top')
        _, rows = hierarchy_counts(ET.parse(vg.with_name('custom_138k_integration_syn_rsc.xml')).getroot())
        clocks = {'clocks': {'clk_50m': {'net': netlist.pin('clk_50m_ibuf', 'I')}}}
        def gate():
            return audit_ble_business(netlist, rows, clocks)
        proof = gate()
        self.assertTrue(proof['mapped_port_inventory'])
        self.assertTrue(proof['exact_payload_D_Q_delivery_verified'])
        for label, path, port, value in (
                ('wrong source PCM bit', 'u_ble_pcm_cdc/held_data_0_s0', 'D', 'physical_frame_pcm[1]'),
                ('wrong delivered PCM bit', 'u_ble_pcm_cdc/destination_data_0_s0', 'D', 'held_data[1]'),
                ('wrong source clock', 'u_ble_pcm_cdc/held_data_0_s0', 'CLK', 'clk_50m_d'),
                ('wrong epoch identity', 'u_managed', 'physical_frame_epoch', 'physical_frame_sequence[31:0]'),
                ('wrong source valid', 'u_ble_pcm_cdc', 'physical_frame_valid', 'physical_frame_error')):
            ports = netlist.cells[path]['ports']
            original = ports[port]
            try:
                ports[port] = value
                with self.subTest(case=label), self.assertRaises(ValueError):
                    gate()
            finally:
                ports[port] = original
        owner = 'u_bluetooth/u_core/initializer'
        netlist.cells['shadow_initializer'] = copy.deepcopy(netlist.cells[owner])
        try:
            with self.assertRaisesRegex(ValueError, 'unique owner'):
                gate()
        finally:
            del netlist.cells['shadow_initializer']
        path = 'u_ble_pcm_cdc/held_data_97_s0'
        missing = netlist.cells.pop(path)
        try:
            with self.assertRaisesRegex(ValueError, 'inventory changed'):
                gate()
        finally:
            netlist.cells[path] = missing
        recorder = 'u_bluetooth/u_core/application/command_endpoint/recording'
        original = rows[recorder]['Bsram']
        try:
            rows[recorder]['Bsram'] = 31
            with self.assertRaisesRegex(ValueError, 'PCM RAM missing'):
                gate()
        finally:
            rows[recorder]['Bsram'] = original
        self.assertEqual(gate(), proof)


if __name__ == '__main__':
    unittest.main()
