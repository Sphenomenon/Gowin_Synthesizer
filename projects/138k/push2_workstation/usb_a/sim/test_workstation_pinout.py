#!/usr/bin/env python3
"""Portable pin-relocation regressions; no external netlists, toolchain or board."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_pinout as pinout


AUDIO_BALLS = ['A16', 'B16', 'A15', 'D17', 'C17', 'B15', 'A14', 'A13', 'B13', 'C13']
ULPI_BALLS = ['A21', 'B21', 'A20', 'B20', 'A19', 'A18', 'B18', 'B17', 'C18', 'F16', 'D16', 'E17']
HDMI_BALLS = [['J14', 'H14'], ['J15', 'H15'], ['K17', 'J17'], ['G15', 'G16']]
RESERVED_BALLS = ['AB15', 'Y16', 'K18', 'J19', 'U9', 'U10', 'U11', 'V13', 'V12', 'U13', 'T13', 'R13', 'U8']


def fixture():
    profile = json.loads((ROOT / pinout.PROFILE_PATH).read_text())
    networks = {role: {} for role in profile['sources']}

    def connect(role, name, *nodes):
        networks[role].setdefault(name, []).extend(nodes)

    for channel, ball in zip(profile['audio'], AUDIO_BALLS):
        connect('carrier', 'BANK2_' + ball, 'FPC2.' + str(channel['pin']))
        if 'array' in channel:
            near, far = channel['array']
            connect('amplifier', 'P' + str(channel['pin']), 'FPC1.' + str(channel['pin']), near)
            connect('amplifier', 'DAC_' + channel['port'], far, channel['dac'])
        else:
            connect('amplifier', 'DAC_' + channel['port'], 'FPC1.' + str(channel['pin']),
                    channel['dac'], *channel.get('additional_nodes', []))
    for pin in (1, 2, 3, 4, 5, 6, 7, 18, 19, 20, 21, 22, 23, 24):
        supply = '+12V' if pin in (1, 2, 23, 24) else '+5V' if pin in (5, 20) else 'GND'
        connect('carrier', supply, 'FPC2.' + str(pin))
        connect('amplifier', 'INPUT_12V' if supply == '+12V' else supply, 'FPC1.' + str(pin))
    for channel, ball in zip(profile['ulpi'], ULPI_BALLS):
        connect('carrier', 'PHY_' + channel['phy'].replace('.', '_'), channel['phy'], channel['bridge'][0])
        connect('carrier', 'BANK2_' + ball, channel['bridge'][1])
    connect('carrier', 'GND', 'U2.9')
    for node, supply in {'U4.2': 'VDD_1V8', 'U4.19': '3V3_USB3300', 'U4.10': 'VDD_1V8',
                         'U5.1': 'VDD_1V8', 'U5.14': '3V3_USB3300', 'U5.8': 'VDD_1V8'}.items():
        connect('carrier', supply, node)
    for node, ball in zip(profile['tf_spi'].values(), ['AA15', 'W14', 'V15', 'W15']):
        connect('carrier', 'BANK5_' + ball, node)
    for channel, balls in zip(profile['hdmi_pairs'], HDMI_BALLS):
        for index, (native, ball) in enumerate(zip(channel['native_nodes'], balls)):
            connect('carrier', 'BANK3_' + ball, native)
            capacitor, terminal = native.split('.')
            far = capacitor + '.' + str(3 - int(terminal))
            connect('carrier', 'HDMI_' + capacitor, far, channel['connector_nodes'][1 - index])
    connect('carrier', 'BANK3_K13', 'R19.2')
    connect('carrier', 'BANK3_K14', 'R21.1')
    connect('carrier', 'CEC', 'R21.2', 'USB3.13')
    for channel in profile['bluetooth']:
        pin = channel['pin']
        connect('carrier', 'BANK5_T14' if pin == 5 else channel['signal'], 'FPC3.' + str(pin))
        connect('bluetooth', channel['signal'], 'FPC1.' + str(25 - pin), channel['module'])
    for node, name in {'J2.2':'BANK4_Y22', 'J2.3':'BANK4_Y21', 'J2.56':'BANK5_T14',
                       'J2.57':'DIP_SWITCH_0_BANK5_V13', 'J2.77':'BANK5_W14', 'J2.78':'BANK5_V15',
                       'J2.79':'BANK5_W15', 'J2.100':'BANK4_W22', 'J2.58':'UART_TX',
                       'J2.59':'BT_DIS#', 'J2.71':'WL_DIS#'}.items():
        connect('carrier', name, node)
    for pin in (1, 2, 3, 4, 21, 22, 23, 24):
        supply = '+5V' if pin in (1, 2, 23, 24) else 'GND'
        connect('carrier', supply, 'FPC3.' + str(pin))
        connect('bluetooth', supply, 'FPC1.' + str(25 - pin))
    for node, ball in zip(profile['reserved_nodes'], RESERVED_BALLS):
        connect('carrier', 'BANK10_' + ball, node)

    payloads = {}
    for role, entries in networks.items():
        text = '$PACKAGES\n$A_PROPERTIES\n$NETS\n'
        text += ''.join("'" + name + "' ; " + ' '.join(nodes) + '\n' for name, nodes in entries.items())
        payloads[role] = (text + '$SCHEDULE\n$END\n').replace('\n', '\r\n').encode()
        profile['sources'][role]['sha256'] = pinout.digest(payloads[role])
    core = 'IO_LOC "clk_50m" V22;\nIO_LOC "debug_uart_tx" U15;\nIO_LOC "pc_uart_rx_i" V14;\n'
    core += 'IO_LOC "ddr_addr[0]" D1;\nIO_PORT "ddr_addr[0]" IO_TYPE=SSTL15 BANK_VCCIO=1.5;\n'
    core += 'IO_LOC "ddr_dqs[0]" Y3,AA3;\nIO_PORT "ddr_dqs[0]" IO_TYPE=SSTL15D BANK_VCCIO=1.5;\n'
    for channel, balls in zip(profile['hdmi_pairs'], HDMI_BALLS):
        core += 'IO_LOC "' + channel['port'] + '" ' + ','.join(balls) + ';\n'
    core += 'IO_LOC "pa_en" AB16;\nIO_LOC "usb1_dp" H13;\n'
    return profile, payloads, core


class NetlistParsing(unittest.TestCase):
    def test_quotes_unquoted_names_comma_continuation_and_crlf(self):
        nets = pinout.Netlist(b"$NETS\r\n'BANK2_A16' ; FPC2.10 ,\r\n J1.18\r\nP9 ; RN1.2 FPC1.10\r\n$SCHEDULE\r\n")
        self.assertEqual(nets.ball('FPC2.10', 2), 'A16')
        self.assertEqual(nets.same('FPC2.10', 'J1.18'), 'BANK2_A16')
        self.assertEqual(nets.network('RN1.2'), 'P9')

    def test_missing_duplicate_and_malformed_input_fail(self):
        samples = [b'$NETS\n', b'$NETS\nA ; U1.1\nA ; U2.1\n$END\n',
                   b'$NETS\nA ; U1.1\nB ; U1.1\n$END\n',
                   b'$NETS\nU1.1\n$END\n', b'$NETS\nA ; wrong\n$END\n']
        for payload in samples:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                pinout.Netlist(payload)

    def test_missing_or_wrong_bank_is_not_inferred_from_other_net(self):
        nets = pinout.Netlist(b'$NETS\nOTHER ; U1.1\nBANK3_A16 ; U1.2\n$END\n')
        for node in ['U1.1', 'U1.2', 'U1.3']:
            with self.subTest(node=node), self.assertRaises(ValueError):
                nets.ball(node, 2)


class UlpiElectricalPreflight(unittest.TestCase):
    def setUp(self):
        self.profile, payloads, self.core = fixture()
        self.carrier = pinout.Netlist(payloads['carrier'])

    def test_locked_board_reports_stp_and_both_input_domain_conflicts(self):
        check = pinout.check_ulpi_electrical(self.carrier)
        self.assertEqual(check['status'], 'blocked')
        self.assertEqual([entry['code'] for entry in check['findings']],
                         ['ULPI_PHY_OUTPUT_DOMAIN', 'ULPI_PHY_OUTPUT_DOMAIN', 'ULPI_STP_HIGH_LEVEL'])
        self.assertEqual([entry['nominal_mv'] for entry in check['translators']], [1800, 1800])
        stp = check['findings'][-1]
        self.assertEqual((stp['driver_node'], stp['receiver_node']), ('U5.3', 'U2.13'))
        self.assertLess(stp['driver_supply_mv'], stp['receiver_vih_min_mv'])
        self.assertFalse(check['actual_board_measured'])

    def test_same_voltage_domain_does_not_grant_electrical_or_deployment_acceptance(self):
        for node in ('U4.2', 'U5.1'):
            self.carrier.nodes[node] = '3V3_USB3300'
        check = pinout.check_ulpi_electrical(self.carrier)
        self.assertEqual(check['status'], 'no_voltage_domain_conflict_detected')
        self.assertFalse(check['full_electrical_acceptance'])
        profile, payloads, core = fixture()
        with patch.object(pinout, 'check_ulpi_electrical', return_value=check):
            plan = pinout.resolve(profile, {role: pinout.Netlist(payload) for role, payload in payloads.items()}, core)
        self.assertFalse(plan['synthesis_allowed'])
        self.assertFalse(plan['hardware_accepted'])
        self.assertFalse(plan['flash_deployed'])

    def test_unknown_supply_is_not_guessed_from_network_name(self):
        self.carrier.nodes['U5.1'] = 'UNREVIEWED_3V3'
        check = pinout.check_ulpi_electrical(self.carrier)
        self.assertEqual(check['status'], 'blocked')
        self.assertIn('ULPI_UNKNOWN_SUPPLY', [entry['code'] for entry in check['findings']])
        self.assertIsNone(check['translators'][1]['nominal_mv'])

    def test_missing_supply_node_is_not_treated_as_compatible(self):
        del self.carrier.nodes['U5.1']
        with self.assertRaisesRegex(ValueError, 'missing netlist node'):
            pinout.check_ulpi_electrical(self.carrier)


class BoardResolution(unittest.TestCase):
    def setUp(self):
        self.profile, self.payloads, self.core = fixture()

    def test_different_phy_model_requires_new_electrical_review(self):
        self.profile['electrical_evidence']['component_models']['U2'] = 'UNREVIEWED_PHY'
        with self.assertRaisesRegex(ValueError, 'unreviewed USB2 device models'):
            pinout.resolve(self.profile, {role: pinout.Netlist(payload) for role, payload in self.payloads.items()}, self.core)

    def resolve(self, payloads=None, profile=None, core=None):
        netlists = {role: pinout.Netlist(payload) for role, payload in (payloads or self.payloads).items()}
        return pinout.resolve(profile or self.profile, netlists, self.core if core is None else core)

    def test_audio_and_usb2_use_distinct_new_locations(self):
        plan = self.resolve()
        expected = {'hp_bck': 'A16', 'hp_ws': 'B16', 'hp_din': 'A15', 'dac_mclk': 'D17',
                    'dac_pdn_n': 'C17', 'amp_fpga_det': 'C13', 'usb2_ulpi_data[7]': 'B17',
                    'sd_mosi': 'W14'}
        for port, ball in expected.items():
            self.assertEqual(plan['ports'][port]['balls'], [ball])
        self.assertFalse(plan['synthesis_allowed'])
        self.assertIsNone(plan['bitstream_sha256'])
        self.assertTrue(plan['assumptions'])

    def test_core_electrical_constraints_are_preserved_and_old_dock_ports_retired(self):
        plan = self.resolve()
        text = pinout.render_constraints(plan)
        self.assertIn('IO_PORT "ddr_addr[0]" IO_TYPE=SSTL15 BANK_VCCIO=1.5;', text)
        self.assertIn('IO_LOC "ddr_dqs[0]" Y3,AA3;', text)
        self.assertNotIn('"pa_en"', text)
        self.assertNotIn('"usb1_dp"', text)
        self.assertNotIn('"hdmi_tx_en"', text)
        self.assertEqual(pinout.parse_locations(text), {port: entry['balls'] for port, entry in plan['ports'].items()})

    def test_hdmi_keeps_native_legal_pairs_and_reports_four_pending_inversions(self):
        plan = self.resolve()
        for pair, balls in zip(plan['hdmi_polarity'], HDMI_BALLS):
            self.assertEqual(pair['native_balls'], balls)
            self.assertTrue(pair['invert_serialized_lane'])
            self.assertFalse(pair['implemented'])

    def test_hdmi_native_pair_drift_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'differential pair drifted'):
            self.resolve(core=self.core.replace('J14,H14', 'H14,J14'))

    def test_bluetooth_reverse_cable_and_uart_direction_are_explicit(self):
        entries = self.resolve()['bluetooth_cable']
        self.assertEqual(len(entries), 15)
        self.assertEqual(entries[0]['signal'], 'UART_RX')
        self.assertEqual((entries[0]['carrier_pin'], entries[0]['module_pin']), (5, 20))
        self.assertEqual(entries[0]['carrier_network'], 'BANK5_T14')

    def test_stale_mclk_bank_alias_does_not_control_location(self):
        payloads = dict(self.payloads)
        payloads['amplifier'] = payloads['amplifier'].replace(b'DAC_dac_mclk', b'AK_MCLK_BANK2_B17')
        self.assertEqual(self.resolve(payloads)['ports']['dac_mclk']['balls'], ['D17'])

    def test_missing_or_disconnected_audio_node_fails(self):
        for replacement in (b'U1.99', b'RN1.99'):
            payloads = dict(self.payloads)
            original = b'U1.3' if replacement == b'U1.99' else b'RN1.2'
            payloads['amplifier'] = payloads['amplifier'].replace(original + b'\r', replacement + b'\r')
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                self.resolve(payloads)

    def test_alternative_resistor_pairing_requires_explicit_profile_change(self):
        profile = copy.deepcopy(self.profile)
        profile['audio'][0]['array'] = ['RN1.2', 'RN1.6']
        with self.assertRaisesRegex(ValueError, 'undeclared resistor-array pairing'):
            self.resolve(profile=profile)

    def test_stale_ball_collision_is_rejected(self):
        payloads = dict(self.payloads)
        payloads['carrier'] = payloads['carrier'].replace(b"'BANK2_D17'", b"'ALT_BANK2_B17'", 1)
        with self.assertRaisesRegex(ValueError, 'ball collision'):
            self.resolve(payloads)

    def test_assignment_cannot_consume_reserved_configuration_pin(self):
        profile = copy.deepcopy(self.profile)
        profile['reserved_nodes'].append('FPC2.10')
        with self.assertRaisesRegex(ValueError, 'reserved board function'):
            self.resolve(profile=profile)

    def test_changed_supply_or_phy_reset_wiring_is_rejected(self):
        for role, original, replacement in [('carrier', b'U2.9', b'U2.99'),
                                             ('amplifier', b'INPUT_12V', b'+3V3'),
                                             ('carrier', b'3V3_USB3300', b'+1V8'),
                                             ('bluetooth', b'BT_DIS#', b'WRONG')]:
            payloads = dict(self.payloads)
            payloads[role] = payloads[role].replace(original, replacement)
            with self.subTest(original=original), self.assertRaises(ValueError):
                self.resolve(payloads)


class PreparationAndCli(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / 'root'
        self.inputs = self.directory / 'inputs'
        self.inputs.mkdir()
        self.profile, payloads, self.core = fixture()
        profile_path = self.root / pinout.PROFILE_PATH
        profile_path.parent.mkdir(parents=True)
        profile_path.write_text(json.dumps(self.profile))
        (self.root / 'build.py').write_text('pass\n')
        for role, source in self.profile['sources'].items():
            (self.inputs / source['filename']).write_bytes(payloads[role])
        baseline = SimpleNamespace(read_bytes=lambda name: self.core.encode(), evidence=lambda: {'name': 'fixture'})
        self.baseline_patch = patch.object(pinout, 'load_baseline', return_value=baseline)
        self.baseline_patch.start()
        self.addCleanup(self.baseline_patch.stop)

    def test_emitted_constraints_and_metadata_are_bound_and_never_release_ready(self):
        output, plan = pinout.prepare(self.root, self.inputs, self.directory / 'output')
        payload = (output / 'custom_138k.locations.cst').read_bytes()
        self.assertEqual(plan['constraints_sha256'], pinout.digest(payload))
        self.assertEqual(json.loads((output / 'pinout.json').read_text()), plan)
        self.assertFalse(plan['synthesis_allowed'])
        self.assertFalse(plan['hardware_accepted'])
        self.assertFalse(plan['sram_deployed'])
        self.assertFalse(plan['flash_deployed'])
        self.assertEqual(set(plan['source_inputs']), {'carrier', 'amplifier', 'bluetooth'})
        self.assertEqual(set(plan['recipe_inputs']), {
            pinout.PROFILE_PATH.as_posix(), 'tools/workstation_pinout.py',
            'tools/workstation_baselines.py', 'build.py'})
        self.assertFalse((self.root / 'LATEST_BUILD.txt').exists())

    def test_modified_or_missing_source_fails_before_creating_output(self):
        source = self.inputs / self.profile['sources']['carrier']['filename']
        original = source.read_bytes()
        output = self.directory / 'output'
        source.write_bytes(original + b'\n')
        with self.assertRaisesRegex(ValueError, 'input drifted'):
            pinout.prepare(self.root, self.inputs, output)
        self.assertFalse(output.exists())
        source.unlink()
        with self.assertRaisesRegex(ValueError, 'missing or escaping'):
            pinout.prepare(self.root, self.inputs, output)
        self.assertFalse(output.exists())

    def test_existing_output_and_input_directory_are_not_overwritten(self):
        output = self.directory / 'output'
        output.mkdir()
        sentinel = output / 'user-work'
        sentinel.write_text('keep')
        with self.assertRaises(FileExistsError):
            pinout.prepare(self.root, self.inputs, output)
        self.assertEqual(sentinel.read_text(), 'keep')
        with self.assertRaisesRegex(ValueError, 'inside netlist inputs'):
            pinout.prepare(self.root, self.inputs, self.inputs / 'output')
        self.assertFalse((self.inputs / 'output').exists())

    def test_parent_traversal_and_escaping_symlink_sources_are_rejected(self):
        profile = copy.deepcopy(self.profile)
        profile['sources']['carrier']['filename'] = '../outside.tel'
        with self.assertRaisesRegex(ValueError, 'basename'):
            pinout.load_sources(profile, self.inputs)
        path = self.inputs / self.profile['sources']['carrier']['filename']
        external = self.directory / 'external.tel'
        external.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'escaping'):
            pinout.load_sources(self.profile, self.inputs)

    def test_cli_rejects_synthesis_and_workstation_profile_mixing(self):
        flags = ['--prepare-only', '--synthesis-only', '--current-workstation', '--cnn-timing85',
                 '--resource-rework', '--resource-timing', '--replicate-resources']
        for flag in flags:
            command = [sys.executable, str(ROOT / 'build.py'), '--prepare-pinout', 'custom-138k',
                       '--netlist-dir', str(self.inputs), flag]
            result = subprocess.run(command, text=True, capture_output=True)
            with self.subTest(flag=flag):
                self.assertEqual(result.returncode, 2)
                self.assertIn('cannot be mixed', result.stderr)

    def test_cli_requires_explicit_inputs_and_rejects_orphan_output_options(self):
        for flags in [['--prepare-pinout', 'custom-138k'], ['--netlist-dir', str(self.inputs)],
                      ['--pinout-output', str(self.directory / 'output')]]:
            result = subprocess.run([sys.executable, str(ROOT / 'build.py'), *flags], text=True, capture_output=True)
            with self.subTest(flags=flags):
                self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
