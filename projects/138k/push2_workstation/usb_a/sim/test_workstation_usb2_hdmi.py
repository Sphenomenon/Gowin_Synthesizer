"""D5 composition, explicit JTAG semantics and the PC monitor's live/stale states."""

from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ElementTree


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_usb2_hdmi as integration
from tools import workstation_hdmi_isolation as hdmi
from tools import workstation_usb2_hotplug as usb
from tools import workstation_pinout as pinout
from tools.capture_workstation_usb2_hdmi import decode, decode_csv
from tools.workstation_usb2_monitor import Monitor, demo_record, presentation
from tools.workstation_usb2_hdmi_audit import usb_primary_bindings
from tools.workstation_synthesis_netlist import SynthesisNetlist
from tools.stage_usb_firmware import sha
from test_workstation_pinout import fixture


def sample_bits(device='25k', connected=True):
    words = dict(reset_released=1, generic_midi=int(device != 'push'), gw25k=int(device == '25k'),
                 flags=0xfd if connected else 0x61, sof_count=123456,
                 telemetry=(3 << 192) | (0x04030201 << 160) | (5 << 128) | (6 << 96) |
                           (7 << 64) | (8 << 32) | (0x103 if connected else 0x101),
                 events=(90 << 82) | (12 << 50) | (2 << 18) | 0x12345,
                 fault_address=0, canceled_requests=9, instruction_address=0x200)
    bits = [int(bit) for name, _, width, _ in integration.FIELDS for bit in f'{words[name]:0{width}b}']
    sources = {}
    for source, bit in zip(integration.BIT_SOURCES, bits):
        if isinstance(source, str):
            if source in sources and sources[source] != bit:
                raise AssertionError('inconsistent test capture source')
            sources[source] = bit
        elif source != bit:
            raise AssertionError('test violates reconstructed constant')
    return [sources[source] for source in integration.SIGNALS]


def phy_bits(**words):
    layout = integration.observer_layout('phy')
    observed = dict(zip(integration.SIGNALS, sample_bits()))
    defaults = dict(reference_reset_released=1, reference_enabled=1, clock_supervisor_state=3,
                    heartbeat_reset_released=1, link_reset_released=1, source_reset_released=1,
                    destination_reset_released=1, link_source_released=1, link_destination_released=1,
                    raw_phy_ready=1)
    defaults.update(words)
    for name, signal, width, low in integration.PHY_FIELDS:
        for offset, bit in enumerate(reversed(range(low, low + width))):
            source = signal if width == 1 and low == 0 else f'{signal}[{bit}]'
            observed[source] = (defaults.get(name, 0) >> (width - offset - 1)) & 1
    return [observed[signal] for signal in layout['signals']]


class Observer(unittest.TestCase):
    def test_port_profile_retains_phy_layout_and_decodes_retry_evidence(self):
        physical = integration.observer_layout('phy')
        layout = integration.observer_layout('port')
        self.assertEqual(layout['signals'][:len(physical['signals'])], physical['signals'])
        self.assertEqual(layout['schema'], integration.PORT_SCHEMA)
        observed = dict(zip(physical['signals'], phy_bits(port_state=7)))
        observed.update(zip(integration.SIGNALS, sample_bits(connected=False)))
        words = dict(state_history=(1 << 13) | (1 << 18), failure_history=1 << 7,
                     attempts=12, last_failure=7, last_failure_state=13,
                     last_failure_function=0x50, received_peak=0, transmitted_peak=123456, sof_peak=0)
        for name, signal, width, low in integration.PORT_FIELDS:
            for bit in range(low, low + width):
                observed[f'{signal}[{bit}]'] = (words[name] >> (bit - low)) & 1
        sample = decode([observed[signal] for signal in layout['signals']], 'port')
        self.assertEqual(sample['port']['states_seen'], [13, 18])
        self.assertEqual(sample['port']['failures_seen'], [7])
        self.assertEqual(sample['port']['last_failure_state'], 13)
        self.assertEqual(sample['port']['last_failure_function'], 0x50)
        self.assertEqual(sample['port']['attempts'], 12)
        self.assertFalse(sample['enumeration_complete'])

    def test_unclocked_release_chains_are_not_misreported_as_initialization(self):
        signals = integration.observer_layout('phy')['signals']
        with tempfile.TemporaryDirectory(prefix='usb2-no-ulpi-clock-') as directory:
            path = Path(directory) / 'capture.csv'
            row = phy_bits(heartbeat_reset_released=0, source_reset_released=0, reference_enabled=0)
            path.write_text('time unit: us, ' + ', '.join(signals) + ',\n' +
                            ''.join(f'{index}, ' + ', '.join(map(str, row)) + ',\n' for index in range(8)))
            record = decode_csv(path, depth=8, profile='phy')
            self.assertEqual(record['last']['stage'], 'ulpi_clock_not_observed')
            self.assertTrue(record['phy_diagnostics']['ulpi_domains_still_in_reset'])
            self.assertIn('未观察到 ULPI 时钟', presentation(record)['stage'])
            self.assertFalse(presentation(record)['good'])

    def test_phy_profile_preserves_v1_and_adds_reference_and_snapshot_evidence(self):
        old = integration.observer_layout()
        self.assertEqual(old['signals'], integration.SIGNALS)
        self.assertEqual(old['sources'], integration.BIT_SOURCES)
        self.assertEqual(old['fields'], integration.FIELDS)
        extended = integration.observer_layout('phy')
        self.assertEqual(extended['signals'][:len(integration.SIGNALS)], integration.SIGNALS)
        self.assertNotEqual(extended['schema'], integration.SCHEMA)
        with self.assertRaises(ValueError):
            integration.observer_layout('guess')
        for stage, words in (('reference_reset', dict(reference_reset_released=0)),
                             ('host_disabled', dict(reference_enabled=0)),
                             ('ulpi_clock_failed', dict(clock_supervisor_state=4, clock_failure=1)),
                             ('ulpi_init_failed', dict(init_failure=3))):
            sample = decode(phy_bits(**words), 'phy')
            self.assertEqual(sample['stage'], stage)
            self.assertIsNone(sample['recognized_device'])
            self.assertFalse(sample['transaction_ready'])

    def test_phy_window_requires_snapshot_updates_and_counts_actual_clock_edges(self):
        signals = integration.observer_layout('phy')['signals']
        with tempfile.TemporaryDirectory(prefix='usb2-phy-decode-') as directory:
            path = Path(directory) / 'capture.csv'
            header = 'time unit: us, ' + ', '.join(signals) + ',\n'
            for toggling in (False, True):
                rows = [phy_bits(reference_heartbeat=int(toggling and index % 2),
                                 ulpi_heartbeat=index if toggling else 0,
                                 link_acknowledge=int(toggling and index % 2)) for index in range(8)]
                path.write_text(header + ''.join(f'{index}, ' + ', '.join(map(str, row)) + ',\n'
                                                  for index, row in enumerate(rows)))
                record = decode_csv(path, depth=8, profile='phy')
                self.assertEqual(record['phy_diagnostics']['reference_heartbeat_edges'], 7 if toggling else 0)
                self.assertEqual(record['phy_diagnostics']['link_snapshot_updates'], 7 if toggling else 0)
                self.assertEqual(record['last']['snapshot_observed'], toggling)
                self.assertEqual(presentation(record)['good'], toggling)
                self.assertEqual(record['last']['stage'], 'configured' if toggling else 'snapshot_unavailable')
                self.assertIn('快照更新', presentation(record)['detail'])
                with self.assertRaisesRegex(ValueError, 'trigger not observed'):
                    decode_csv(path, depth=8, profile='phy', trigger='clock-failure')
            rows = [phy_bits(clock_supervisor_state=4, clock_failure=1) for _ in range(8)]
            path.write_text(header + ''.join(f'{index}, ' + ', '.join(map(str, row)) + ',\n'
                                              for index, row in enumerate(rows)))
            result = decode_csv(path, depth=8, profile='phy', trigger='clock-failure')
            self.assertEqual(result['last']['stage'], 'ulpi_clock_failed')

    def test_decodes_real_owner_classification_not_just_phy_ready(self):
        for device in ('25k', 'push', 'generic_midi'):
            with self.subTest(device=device):
                result = decode(sample_bits(device))
                self.assertEqual(result['recognized_device'], device)
                self.assertTrue(result['enumeration_complete'])
                self.assertTrue(result['high_speed'])
                self.assertEqual(result['accepted_events'], 90)
                self.assertEqual(result['lifecycle_events'], 12)
                self.assertEqual(result['cancel_events'], 2)
                self.assertEqual(result['commands'], 6)
                self.assertEqual(result['instruction_address'], '0x00000200')
                self.assertEqual([result[name] for name in ('in_errors', 'duplicate_packets', 'naks', 'disconnects')],
                                 [1, 2, 3, 4])
        absent = decode(sample_bits(connected=False))
        self.assertTrue(absent['phy_ready'])
        self.assertFalse(absent['enumeration_complete'])
        self.assertIsNone(absent['recognized_device'])
        self.assertEqual(absent['stage'], 'waiting_for_link')
        stale = sample_bits()
        stale[integration.SIGNALS.index('u_usb/link_snapshot[4]')] = 0
        self.assertIsNone(decode(stale)['recognized_device'])
        self.assertFalse(decode(stale)['transaction_ready'])

    def test_binary_schema_depth_and_order_are_checked(self):
        values = sample_bits()
        for changed in (values[:-1], [2, *values[1:]]):
            with self.assertRaises(ValueError):
                decode(changed)
        with tempfile.TemporaryDirectory(prefix='usb2-hdmi-decode-') as directory:
            path = Path(directory) / 'capture.csv'
            header = 'Data:\ntime unit: us, ' + ', '.join(integration.SIGNALS) + ',\n'
            row = ', '.join(map(str, values))
            text = header + ''.join(f'{index}, {row},\n' for index in range(1024))
            path.write_text(text)
            result = decode_csv(path)
            self.assertEqual(result['recognized_devices'], ['25k'])
            self.assertEqual(result['samples'], 1024)
            for changed in (text.replace('0, ', '8, ', 1), text.rsplit('\n', 2)[0] + '\n',
                            text.replace(integration.SIGNALS[0], 'wrong', 1)):
                path.write_text(changed)
                with self.assertRaises(ValueError):
                    decode_csv(path)

    def test_monitor_never_keeps_green_after_failed_or_stale_read(self):
        record = demo_record(0)
        self.assertTrue(presentation(record)['good'])
        self.assertFalse(presentation(record, age=21)['good'])
        self.assertEqual(presentation(record, age=21)['device'], '未知（数据过期）')
        self.assertFalse(presentation(record, error='identity mismatch')['good'])
        self.assertEqual(presentation(record, error='identity mismatch')['device'], '未知')
        self.assertFalse(presentation()['good'])
        self.assertFalse(presentation(demo_record(4))['good'])

    @unittest.skipUnless(os.environ.get('DISPLAY'), 'desktop display required for Tk widget smoke')
    def test_actual_desktop_widgets_show_explicit_demo_and_device_state(self):
        window = tk.Tk()
        window.withdraw()
        monitor = Monitor(window, None, None, demo=True, interval=1)
        try:
            deadline = time.monotonic() + 2
            while monitor.record is None and time.monotonic() < deadline:
                window.update()
                time.sleep(.02)
            self.assertIn('模拟演示', window.title())
            self.assertEqual(monitor.device.cget('text'), '25K 键盘')
            self.assertIn('枚举与设备识别成功', monitor.stage.cget('text'))
            self.assertEqual(monitor.table.item('received_events')['values'][1], 2)
        finally:
            monitor.close()

    def test_gao_uses_cpu_clock_and_only_resolved_nonconstant_probes(self):
        document = ElementTree.fromstring(integration.gao_configuration('C11028E4'))
        core = document.find('AoCore')
        self.assertEqual(core.attrib['sample_clock'], 'u_usb/usb_clk')
        self.assertEqual(core.attrib['module_name'], integration.TOP)
        signals = [element.text for element in core.find('SignalList')]
        self.assertEqual(signals, list(integration.SIGNALS))
        self.assertEqual(len(signals), len(set(signals)))
        self.assertNotIn('u_usb/flags[0]', signals)
        self.assertNotIn('u_usb/telemetry[0]', signals)
        self.assertNotIn('u_usb/u_native_usb/host/instruction_address[0]', signals)
        self.assertEqual(core.find('Triggers/Trigger/SignalList/Signal').text, 'u_usb/usb_release[3]')

    def test_clock_failure_trigger_uses_the_existing_phy_fault_bit(self):
        with self.assertRaisesRegex(ValueError, 'requires the explicit phy'):
            integration.gao_configuration('C11028E6', 'owner', 'clock-failure')
        document = ElementTree.fromstring(integration.gao_configuration('C11028E6', 'phy', 'clock-failure'))
        core = document.find('AoCore')
        signals = [element.text for element in core.find('SignalList')]
        self.assertEqual(signals, list(integration.observer_layout('phy')['signals']))
        self.assertEqual(core.find('Triggers/Trigger/SignalList/Signal').text,
                         integration.USB_HOST + '/clock_failure[0]')


class Composition(unittest.TestCase):
    def test_primary_clock_aliases_must_resolve_through_actual_parent_buffers(self):
        source = '''module child (clk_50m_d, usb2_ulpi_clk_d);
input clk_50m_d;
input usb2_ulpi_clk_d;
endmodule
module top (clk_50m, usb2_ulpi_clk);
input clk_50m;
input usb2_ulpi_clk;
  IBUF reference_buffer (
    .I(clk_50m), .O(buffered)
);
  child u_usb (
    .clk_50m_d(buffered), .usb2_ulpi_clk_d(usb2_ulpi_clk)
);
endmodule
'''
        self.assertEqual(usb_primary_bindings(SynthesisNetlist(source, 'top')),
                         dict(clk_50m='clk_50m_d', ulpi_60m='usb2_ulpi_clk_d'))
        changed = source.replace('.clk_50m_d(buffered)', '.clk_50m_d(usb2_ulpi_clk)')
        with self.assertRaisesRegex(ValueError, 'not bound to its board input'):
            usb_primary_bindings(SynthesisNetlist(changed, 'top'))

    def test_successful_tool_without_actual_outputs_is_a_failed_build(self):
        with tempfile.TemporaryDirectory(prefix='usb2-hdmi-missing-outputs-') as directory:
            output = Path(directory)
            (output / 'inputs.json').write_text(json.dumps(dict(identity='unit-test', input_sha256={})))
            with patch.object(integration.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
                result = integration.build(output)
            self.assertEqual(result['tool_returncode'], 0)
            self.assertEqual(result['returncode'], 1)
            self.assertIn('impl/pnr/ao_0.fs', result['missing_outputs'])

    def test_only_internal_selectors_are_prefixed_including_registers(self):
        text = ('create_clock -name clk_50m -period 20 [get_ports {clk_50m}]\n'
                'set_max_delay 2 -from [get_regs {u_video/count*}] -to [get_pins {u_video/meta*/D}]\n'
                'set_false_path -from [get_clocks clk_50m] -to [get_nets counter]\n')
        result = integration.prefixed_constraints(text, 'u_hdmi/')
        self.assertIn('[get_regs {u_hdmi/u_video/count*}]', result)
        self.assertIn('[get_pins {u_hdmi/u_video/meta*/D}]', result)
        self.assertIn('[get_nets u_hdmi/counter]', result)
        self.assertIn('[get_ports {clk_50m}]', result)
        self.assertIn('[get_clocks clk_50m]', result)

    def test_nonidentical_module_collision_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='usb2-hdmi-collision-') as directory:
            output = Path(directory)
            for name, text in (('hdmi/a.v', 'module shared(); endmodule\n'),
                               ('usb/b.v', 'module shared(input changed); endmodule\n')):
                target = output / name
                target.parent.mkdir()
                target.write_text(text)
            with self.assertRaisesRegex(ValueError, 'nonidentical RTL module collision'):
                integration.source_composition(output, dict(enabled_inputs=['a.v']), dict(source_paths=['b.v']))

    def test_wrong_d5_identity_and_cli_mixing_fail_before_output(self):
        with tempfile.TemporaryDirectory(prefix='usb2-hdmi-invalid-') as directory:
            base = Path(directory)
            (base / 'inputs.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'accepted C11028D5'):
                integration.validate_d5(base)
            result = subprocess.run([sys.executable, str(ROOT / 'build.py'), '--usb2-hdmi-baseline', str(base)],
                                    text=True, capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires --prepare-usb2-soc', result.stderr)
            result = subprocess.run([sys.executable, str(ROOT / 'build.py'), '--usb2-observer-profile', 'phy'],
                                    text=True, capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires --usb2-hdmi-baseline', result.stderr)

    def test_real_preparation_composes_unchanged_child_inputs_and_preserves_d5(self):
        profile, payloads, core = fixture()
        plan = pinout.resolve(profile, {role: pinout.Netlist(payload) for role, payload in payloads.items()}, core)

        def resolved(root, directory, output):
            output.mkdir(parents=True)
            (output / 'pinout.json').write_text(json.dumps(plan))
            return output, plan

        with tempfile.TemporaryDirectory(prefix='usb2-hdmi-prepare-') as directory:
            base = Path(directory)
            with patch.object(hdmi, 'prepare_pinout', side_effect=resolved), \
                    patch.object(usb, 'prepare_pinout', side_effect=resolved):
                _, reference = hdmi.prepare(ROOT, base / 'netlists', base / 'reference', 'C11028D5')
                reference = json.loads((base / 'reference/inputs.json').read_text())
                with patch.object(integration, 'validate_d5', return_value=reference):
                    output, manifest = integration.prepare(ROOT, base / 'candidate', base / 'netlists',
                                                           'C11028EF', base / 'reference')
                    status_output, status_manifest = integration.prepare(
                        ROOT, base / 'with-status', base / 'netlists', 'C1110201',
                        base / 'reference', usb_status=True)
            self.assertEqual(manifest['top_module'], integration.TOP)
            self.assertTrue(manifest['hdmi_implementation_byte_identical'])
            self.assertEqual(len(manifest['identical_duplicate_sources_omitted']), 3)
            for name in (*reference['enabled_inputs'], 'display.cst', 'display.sdc'):
                self.assertEqual(sha(output / 'hdmi' / name), sha(base / 'reference' / name))
            for name, expected in manifest['input_sha256'].items():
                self.assertEqual(sha(output / name), expected, name)
            self.assertEqual(sha(output / 'src/memory/ddr_address_map.vh'),
                             sha(output / 'hdmi/src/memory/ddr_address_map.vh'))
            constraints = (output / 'integration.sdc').read_text()
            self.assertEqual(constraints.count('create_clock -name clk_50m '), 1)
            self.assertNotIn('get_regs {u_display/', constraints)
            self.assertNotIn('get_regs {u_native_usb/', constraints)
            self.assertIn('get_regs {u_hdmi/u_display/', constraints)
            self.assertIn('get_regs {u_usb/u_native_usb/', constraints)
            self.assertIn('u_usb/u_native_usb/host/usb/bridge/', constraints)
            self.assertFalse(status_manifest['hdmi_implementation_byte_identical'])
            self.assertTrue(status_manifest['usb_status_panel'])
            for name in reference['enabled_inputs']:
                self.assertEqual(sha(status_output / 'hdmi' / name), sha(base / 'reference' / name))
            self.assertIn('status/hdmi_display.v', status_manifest['enabled_inputs'])
            self.assertNotIn('hdmi/src/video/hdmi_display.v', status_manifest['enabled_inputs'])
            self.assertIn('status/workstation_usb2_hotplug_top.sv', status_manifest['enabled_inputs'])
            self.assertNotIn('usb/rtl/workstation/workstation_usb2_hotplug_top.sv', status_manifest['enabled_inputs'])
            self.assertNotIn('`define WORKSTATION_USB_STATUS_SOURCE\n',
                (output / 'usb/rtl/workstation/workstation_usb2_hotplug_top.sv').read_text())
            self.assertIn('`define WORKSTATION_USB_STATUS_SOURCE\n',
                (status_output / 'status/workstation_usb2_hotplug_top.sv').read_text())
            original_renderer=(status_output / 'hdmi/src/video/feedback_renderer.v').read_text()
            adapted_renderer=(status_output / 'status/feedback_renderer.v').read_text()
            self.assertEqual(sorted(original_renderer.splitlines()),sorted(adapted_renderer.splitlines()))
            self.assertIn('u_usb_status/u_status_cdc', (status_output / 'integration.sdc').read_text())
            self.assertIn('u_usb_status/status_release_q_0_s*/Q', (status_output / 'integration.sdc').read_text())
            self.assertIn('u_usb_status/status_release_q_2_s*/D', (status_output / 'integration.sdc').read_text())
            self.assertEqual(integration.constraints(status_output, True),
                ((status_output / 'integration.cst').read_text(), (status_output / 'integration.sdc').read_text()))
            self.assertIn('`define HDMI_USB_STATUS', (status_output / 'hdmi_isolation_config.vh').read_text())
            for name, expected in status_manifest['input_sha256'].items():
                self.assertEqual(sha(status_output / name), expected, name)
            if shutil.which('iverilog'):
                # Elaborate selected first-party wiring; encrypted vendor/IP
                # implementations are black boxes for this open-source tool.
                result = subprocess.run(['iverilog', '-g2012', '-i', '-s', integration.TOP,
                    '-I', str(status_output), '-o', str(status_output / 'elaboration'),
                    *(str(status_output / name) for name in status_manifest['enabled_inputs']
                      if '/vendor/' not in name)],
                    cwd=status_output, capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            # Drift at a wiring anchor must fail instead of silently dropping the panel.
            path = status_output / 'hdmi/src/video/hdmi_display.v'
            path.write_text(path.read_text().replace('    ddr_frame_writer u_writer (', '    ddr_frame_writer renamed ('))
            with self.assertRaises(ValueError):
                integration.status_panel_sources(ROOT, status_output, manifest['enabled_inputs'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
