"""Standalone PHY self-test preparation, simulated faults, and strict readback."""

from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_ulpi_selftest as selftest
from tools import workstation_pinout as pinout
from test_workstation_pinout import fixture


def bits(**updates):
    status = (0x061041 << 64) | (0x0004 << 48) | (0x0424 << 32) | (17 << 4) | 9
    words = dict(power_on_count=1023, reference_cycles=10, window_edges=600000, windows=3,
                 clock_seen=1, clock_flags=3, snapshot_valid=1, snapshot_updates=10, status=status, bus=0,
                 input_toggles=200000, input_high_cycles=250000)
    words.update(updates)
    return [int(bit) for name, _, width in selftest.FIELDS for bit in f'{words[name]:0{width}b}']


class Selftest(unittest.TestCase):
    def test_input_sampler_reports_sampled_transitions_not_an_unaliased_clock_frequency(self):
        result = selftest.decode(bits())
        self.assertTrue(result['input_sampler_present'])
        self.assertEqual(result['reference_sampled_transition_hz'], 20000000)
        self.assertEqual(result['reference_sampled_high_fraction'], 0.5)
        legacy = bits()[:len(selftest.LEGACY_SIGNALS)]
        self.assertTrue(selftest.decode(legacy)['passed'])
        self.assertFalse(selftest.decode(legacy)['input_sampler_present'])
        self.assertNotIn('reference_sampled_transition_hz', selftest.decode(legacy))

    def test_legacy_csv_remains_readable_but_mixed_schema_and_signal_layout_is_rejected(self):
        manifest = dict(schema=selftest.LEGACY_SCHEMA, signals=list(selftest.LEGACY_SIGNALS),
                        window_ref_cycles=500000, storage_depth=4)
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary)/'legacy.csv'
            rows = [bits(reference_cycles=index, snapshot_updates=index)[:len(selftest.LEGACY_SIGNALS)]
                    for index in range(4)]
            capture.write_text('time unit: us, ' + ', '.join(selftest.LEGACY_SIGNALS) + ',\n' +
                               ''.join(f'{index}, ' + ', '.join(map(str, row)) + ',\n'
                                       for index, row in enumerate(rows)))
            self.assertTrue(selftest.decode_csv(capture, manifest)['last']['passed'])
            with self.assertRaisesRegex(ValueError, 'observer layout'):
                selftest.decode_csv(capture, dict(manifest, schema=selftest.SCHEMA))

    def test_clock_pull_experiment_changes_only_the_existing_clock_io_property(self):
        physical = (b'IO_LOC "usb2_ulpi_clk" C18;\n'
                    b'IO_PORT "usb2_ulpi_clk" IO_TYPE=LVCMOS33;\n'
                    b'IO_PORT "usb2_ulpi_data[0]" IO_TYPE=LVCMOS33;\n')
        self.assertEqual(selftest.clock_pull_constraints(physical, None), physical)
        for mode in ('NONE', 'UP', 'DOWN'):
            with self.subTest(mode=mode):
                changed = selftest.clock_pull_constraints(physical, mode)
                self.assertEqual(changed.replace(f' PULL_MODE={mode}'.encode(), b''), physical)
                self.assertEqual(pinout.parse_locations(changed.decode()), {'usb2_ulpi_clk': ['C18']})
        for changed in (physical.replace(b'IO_TYPE=LVCMOS33;', b'IO_TYPE=LVCMOS18;'), physical + physical):
            with self.assertRaisesRegex(ValueError, 'anchor changed'):
                selftest.clock_pull_constraints(changed, 'UP')
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            selftest.clock_pull_constraints(physical, 'KEEPER')

    def test_decode_requires_clock_valid_snapshot_identity_controls_and_completed_scratch(self):
        self.assertTrue(selftest.decode(bits())['passed'])
        self.assertTrue(selftest.decode(bits())['scratch_patterns_verified'])
        for changed in (dict(power_on_count=0), dict(power_on_count=1022), dict(window_edges=0), dict(windows=0),
                        dict(clock_seen=0), dict(clock_flags=7), dict(snapshot_valid=0),
                        dict(status=0), dict(status=1), dict(status=(1 << 32) | 9)):
            with self.subTest(changed=changed):
                result = selftest.decode(bits(**changed))
                self.assertFalse(result['passed'])
                self.assertFalse(result['enumeration_tested'])
                self.assertFalse(result['hardware_acceptance'])
        result = selftest.decode(bits(clock_seen=0, window_edges=0, snapshot_valid=0, status=0, clock_flags=12))
        self.assertEqual(result['stage'], 'ulpi_clock_not_observed')
        self.assertEqual(result['clock_failure'], 1)

    def test_half_rate_clock_is_rejected_even_after_successful_register_initialization(self):
        for edges in (298594, 298664, 298772, 298668, 300000):
            with self.subTest(edges=edges):
                result = selftest.decode(bits(window_edges=edges))
                self.assertEqual(result['vendor_id'], 0x0424)
                self.assertEqual(result['product_id'], 0x0004)
                self.assertEqual(result['init_stage'], 17)
                self.assertEqual(result['init_failure'], 0)
                self.assertEqual(result['ulpi_hz'], edges * 100)
                self.assertEqual(result['stage'], 'ulpi_frequency_out_of_range')
                self.assertFalse(result['clock_frequency_ok'])
                self.assertFalse(result['passed'])
                self.assertFalse(result['enumeration_tested'])
                self.assertFalse(result['hardware_acceptance'])

    def test_gao_is_entirely_reference_clocked_and_has_no_cpu_or_hdmi(self):
        core = ElementTree.fromstring(selftest.gao_configuration('C11028F1')).find('AoCore')
        self.assertEqual(core.get('sample_clock'), 'clk_50m_d')
        self.assertEqual(core.get('module_name'), selftest.TOP)
        self.assertEqual([signal.text for signal in core.find('SignalList')], list(selftest.SIGNALS))
        self.assertEqual(core.find('Triggers/Trigger/SignalList/Signal').text, 'power_count_q[9]')
        self.assertNotIn('reset_n', selftest.SIGNALS)
        self.assertIn('clock_seen_q_1_Q', selftest.SIGNALS)
        self.assertIn('snapshot_valid_q_1_Q', selftest.SIGNALS)
        self.assertEqual(len(selftest.SIGNALS), len(set(selftest.SIGNALS)))
        self.assertEqual(len(selftest.SOURCES), 5)
        self.assertFalse(any('vendor/' in name for name in selftest.SOURCES))

    def test_ulpi_clock_constraint_retains_sixty_megahertz(self):
        self.assertIn('create_clock -name ulpi_60m -period 16.666667', selftest.timing_constraints())
        self.assertIn('-from [get_pins {ulpi_count_q_23_s*/Q}] -to [get_pins {gray_meta_q_23_s*/D}]',
                      selftest.timing_constraints())

    def test_prepare_uses_only_resolved_ulpi_ports_and_keeps_acceptance_false(self):
        profile, payloads, core = fixture()
        nets = {role: pinout.Netlist(payload) for role, payload in payloads.items()}
        plan = pinout.resolve(profile, nets, core)
        def prepare_pinout(root, directory, output):
            output.mkdir(parents=True)
            return output, plan
        with tempfile.TemporaryDirectory() as temporary, patch.object(selftest, 'prepare_pinout', prepare_pinout):
            output, manifest = selftest.prepare(ROOT, '/unused', Path(temporary)/'prepared', 'C11028F1')
            self.assertEqual(pinout.parse_locations((output/'selftest.cst').read_text()),
                             {port: plan['ports'][port]['balls'] for port in selftest.PORTS})
            self.assertEqual(plan['ports']['usb2_ulpi_clk']['balls'], ['C18'])
            self.assertEqual(manifest['electrical_check']['status'], 'no_voltage_domain_conflict_detected')
            self.assertFalse(manifest['electrical_check']['actual_board_measured'])
            self.assertFalse(manifest['full_electrical_acceptance'])
            self.assertEqual(tuple(manifest['source_paths']), selftest.SOURCES)
            self.assertNotIn('firmware', manifest)
            self.assertEqual(manifest['clock_input_pull'], 'vendor_default')
            with self.assertRaises(FileExistsError):
                selftest.prepare(ROOT, '/unused', output, 'C11028F1')
            for old in ('C11028D5', 'C11028E5', 'C11028E6', ''):
                with self.assertRaises(ValueError):
                    selftest.prepare(ROOT, '/unused', Path(temporary)/'other', old)

    def test_prepare_records_explicit_clock_pull_with_unchanged_sources_and_locations(self):
        profile, payloads, core = fixture()
        plan = pinout.resolve(profile, {role: pinout.Netlist(payload) for role, payload in payloads.items()}, core)
        with tempfile.TemporaryDirectory() as temporary, patch.object(selftest, 'prepare_pinout', return_value=(None, plan)):
            for mode in ('NONE', 'UP', 'DOWN'):
                output, manifest = selftest.prepare(ROOT, '/unused', Path(temporary)/mode, 'C11029F6', mode)
                self.assertEqual(manifest['clock_input_pull'], mode)
                self.assertEqual(tuple(manifest['source_paths']), selftest.SOURCES)
                self.assertEqual(pinout.parse_locations((output/'selftest.cst').read_text()),
                                 {port: plan['ports'][port]['balls'] for port in selftest.PORTS})
                self.assertIn(f'IO_PORT "usb2_ulpi_clk" IO_TYPE=LVCMOS33 PULL_MODE={mode};',
                              (output/'selftest.cst').read_text())

    def test_build_entry_rejects_clock_pull_without_selftest(self):
        result = subprocess.run([sys.executable, str(ROOT/'build.py'), '--ulpi-clock-pull', 'UP'],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--ulpi-clock-pull requires --ulpi-selftest', result.stderr)

    def test_external_probe_changes_only_clock_location_and_checks_the_passive_route(self):
        physical = (b'IO_LOC "usb2_ulpi_clk" C18;\n'
                    b'IO_LOC "usb2_ulpi_dir" F16;\n'
                    b'IO_PORT "usb2_ulpi_clk" IO_TYPE=LVCMOS33;\n')
        carrier = pinout.Netlist(b'$NETS\nBANK2_C17 ; FPC2.8 J1.15\n$END\n')
        changed = selftest.clock_probe_constraints(physical, carrier)
        self.assertEqual(changed.replace(b'C17;', b'C18;'), physical)
        for invalid in (physical + physical, physical.replace(b'C18;', b'C13;')):
            with self.assertRaisesRegex(ValueError, 'location anchor'):
                selftest.clock_probe_constraints(invalid, carrier)
        for route in (b'BANK2_C13 ; FPC2.8 J1.15', b'BANK2_C17 ; FPC2.8 J1.15 U99.1'):
            with self.assertRaisesRegex(ValueError, 'connectivity changed'):
                selftest.clock_probe_constraints(physical, pinout.Netlist(b'$NETS\n' + route + b'\n$END\n'))

    def test_external_probe_prepare_is_explicit_and_does_not_change_the_global_plan(self):
        profile, payloads, core = fixture()
        plan = pinout.resolve(profile, {role: pinout.Netlist(payload) for role, payload in payloads.items()}, core)
        carrier = pinout.Netlist(b'$NETS\nBANK2_C17 ; FPC2.8 J1.15\n$END\n')
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(selftest, 'prepare_pinout', return_value=(None, plan)), \
                patch.object(selftest, 'load_sources', return_value=({'carrier': carrier}, {})):
            output, manifest = selftest.prepare(ROOT, '/unused', Path(temporary)/'probe', 'C11029F9', clock_probe=True)
            expected = {port: plan['ports'][port]['balls'] for port in selftest.PORTS}
            expected['usb2_ulpi_clk'] = ['C17']
            self.assertEqual(pinout.parse_locations((output/'selftest.cst').read_text()), expected)
            self.assertEqual(manifest['port_locations'], expected)
            self.assertEqual(plan['ports']['usb2_ulpi_clk']['balls'], ['C18'])
            self.assertEqual(manifest['clock_input_pull'], 'NONE')
            self.assertEqual(manifest['clock_input_route']['mode'], 'external_probe')
            self.assertTrue(manifest['clock_input_route']['requires_amplifier_cable_disconnected'])
            self.assertEqual(tuple(manifest['source_paths']), selftest.SOURCES)
            for name in selftest.SOURCES:
                self.assertEqual((output/name).read_bytes(), (ROOT/name).read_bytes())

    def test_actual_pin_report_requires_the_selected_pin_input_mode_and_io_voltage(self):
        cells = ['usb2_ulpi_clk', '-', 'C17/2', 'Y', 'in', 'IOR26[B]', 'MGCLKC_1', 'LVCMOS33', 'OFF', 'NONE']
        def report(values):
            return '<table><tr>' + ''.join('<td>' + value + '</td>' for value in values) + '</tr></table>'
        binding = selftest.clock_pin_binding(report(cells), 'C17', 'NONE')
        self.assertEqual(binding['direction'], 'in')
        for index, invalid in ((2, 'C18/2'), (4, 'out'), (7, 'LVCMOS18'), (9, 'UP')):
            changed = list(cells)
            changed[index] = invalid
            with self.assertRaises(ValueError):
                selftest.clock_pin_binding(report(changed), 'C17', 'NONE')
        with self.assertRaisesRegex(ValueError, 'missing or duplicated'):
            selftest.clock_pin_binding(report(cells) + report(cells), 'C17', 'NONE')

    def test_build_entry_rejects_external_probe_without_selftest(self):
        result = subprocess.run([sys.executable, str(ROOT/'build.py'), '--ulpi-clock-probe'],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--ulpi-clock-probe requires --ulpi-selftest', result.stderr)

    def test_bad_layout_truncated_csv_and_stale_success_are_rejected(self):
        manifest = dict(window_ref_cycles=500000, storage_depth=4)
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary)/'capture.csv'
            header = 'time unit: us, ' + ', '.join(selftest.SIGNALS) + ',\n'
            def write(rows):
                capture.write_text(header + ''.join(f'{index}, ' + ', '.join(map(str,row)) + ',\n'
                                                   for index,row in enumerate(rows)))
            write([bits(reference_cycles=index, snapshot_updates=index) for index in range(4)])
            self.assertTrue(selftest.decode_csv(capture, manifest)['last']['passed'])
            write([bits()]*4)
            with self.assertRaisesRegex(ValueError, 'inactive'):
                selftest.decode_csv(capture, manifest)
            write([bits(reference_cycles=index) for index in range(4)])
            with self.assertRaisesRegex(ValueError, 'stale'):
                selftest.decode_csv(capture, manifest)
            write([bits()])
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                selftest.decode_csv(capture, manifest)
            with self.assertRaises(ValueError):
                selftest.decode([0])

    def test_build_entry_rejects_profile_mixing(self):
        for arguments in (['--ulpi-output', '/unused'], ['--ulpi-selftest'],
                          ['--ulpi-selftest', '--ulpi-output', '/unused', '--netlist-dir', '/unused',
                           '--user-code', 'C11028F1', '--current-workstation']):
            result = subprocess.run([sys.executable, str(ROOT/'build.py'), *arguments],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('error:', result.stderr)

    def test_vendor_csv_data_preamble_is_supported_without_relaxing_signal_layout(self):
        manifest = dict(window_ref_cycles=500000, storage_depth=4)
        header = 'time unit: us, ' + ', '.join(selftest.SIGNALS) + ',\n'
        rows = ''.join(f'{index}, ' + ', '.join(map(str, bits(reference_cycles=index, snapshot_updates=index)))
                       + ',\n' for index in range(4))
        with tempfile.TemporaryDirectory() as temporary:
            capture = Path(temporary) / 'capture.csv'
            for preamble in ('', 'Data:\n'):
                with self.subTest(preamble=preamble):
                    capture.write_text(preamble + header + rows)
                    self.assertTrue(selftest.decode_csv(capture, manifest)['last']['passed'])
            capture.write_text('Data:\n' + header.replace('power_count_q[9]', 'wrong_probe') + rows)
            with self.assertRaisesRegex(ValueError, 'layout changed'):
                selftest.decode_csv(capture, manifest)
            capture.write_text('Data:\n' + header + rows.replace('\n1, ', '\n0, ', 1))
            with self.assertRaisesRegex(ValueError, 'noncontiguous'):
                selftest.decode_csv(capture, manifest)

    def test_actual_rtl_good_missing_late_stopped_half_rate_clock_bad_identity_and_bad_scratch(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary)/'simulation'
            sources = [str(ROOT/name) for name in selftest.SOURCES]
            sources += [str(ROOT/'sim/usb2/usb3300_register_model.sv'),
                        str(ROOT/'sim/usb2/tb_workstation_ulpi_selftest.sv')]
            compilation = subprocess.run(['iverilog', '-g2012', '-s', 'tb_workstation_ulpi_selftest',
                                          '-o', str(executable), *sources], capture_output=True, text=True)
            self.assertEqual(compilation.returncode, 0, compilation.stderr)
            for scenario in range(7):
                with self.subTest(scenario=scenario):
                    result = subprocess.run(['vvp', str(executable), f'+SCENARIO={scenario}'],
                                            capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                    self.assertIn('PASS ULPI selftest', result.stdout)


if __name__ == '__main__':
    unittest.main()
