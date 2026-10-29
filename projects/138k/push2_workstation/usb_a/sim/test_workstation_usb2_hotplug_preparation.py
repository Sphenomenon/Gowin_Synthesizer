#!/usr/bin/env python3
"""Small board diagnostic composition, source identity and real UART framing."""

from pathlib import Path
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ElementTree


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_usb2_hotplug as diagnostic
from tools import workstation_pinout as pinout
from tools.stage_usb_firmware import sha
from test_workstation_pinout import fixture


class BoardSubset(unittest.TestCase):
    def setUp(self):
        profile, payloads, core = fixture()
        self.plan = pinout.resolve(profile, {role: pinout.Netlist(payload) for role, payload in payloads.items()}, core)

    def test_only_usb_and_debug_io_are_selected(self):
        payload, evidence = diagnostic.board_constraints(self.plan)
        locations = pinout.parse_locations(payload.decode())
        self.assertEqual(set(locations), set(diagnostic.PORTS))
        self.assertEqual(len(locations), 15)
        self.assertEqual(payload.count(b'IO_TYPE=LVCMOS33'), 12)
        self.assertEqual(locations['usb2_ulpi_clk'], ['C18'])
        self.assertNotIn(b'ddr_', payload)
        self.assertNotIn(b'tmds_', payload)
        self.assertTrue(evidence['locations_unchanged'])

    def test_bypass_and_voltage_evidence_are_required(self):
        for change in ('assembly', 'supply'):
            plan = copy.deepcopy(self.plan)
            if change == 'assembly':
                plan['ulpi_bypass']['U4'] = 'fitted'
            else:
                plan['electrical_check']['translators'][0]['supply_network'] = 'VDD_1V8'
            with self.subTest(change=change), self.assertRaises(ValueError):
                diagnostic.board_constraints(plan)

    def test_preparation_keeps_component_manifest_and_selects_only_small_dependencies(self):
        def resolved_pinout(root, directory, output):
            output.mkdir(parents=True)
            (output / 'pinout.json').write_text(json.dumps(self.plan))
            return output, self.plan

        with tempfile.TemporaryDirectory(prefix='usb2-hotplug-preparation-') as directory:
            output = Path(directory) / 'candidate'
            with patch.object(diagnostic, 'prepare_pinout', side_effect=resolved_pinout):
                prepared, metadata = diagnostic.prepare(ROOT, output, Path(directory) / 'netlists', 'C127E2F0')
            self.assertEqual(prepared, output)
            self.assertEqual(metadata['top_module'], diagnostic.TOP)
            self.assertEqual(metadata['clocks_hz'], dict(clk_50m=50000000, ulpi_60m=60000000,
                                                        usb_48m=48000000, audio_76m8=76800000))
            self.assertTrue(metadata['high_speed_allowed'])
            self.assertEqual(metadata['firmware_profile'], 'workstation')
            self.assertEqual(metadata['component_inputs_sha256'], sha(output / 'component/component_inputs.json'))
            component = json.loads((output / 'component/component_inputs.json').read_text())
            self.assertEqual(component['component'], 'workstation-input')
            self.assertTrue(component['business_firmware_selected'])
            self.assertEqual(sha(output / 'usb2_cpu.hex'), component['firmware']['rom_sha256'])
            fifo = 'support/' + diagnostic.FIFO_SOURCE
            self.assertIn(fifo, metadata['source_paths'])
            self.assertNotIn('component/' + diagnostic.COMPONENT_FIFO, metadata['source_paths'])
            self.assertEqual(metadata['event_fifo_transform'], 'existing_native_resource_timing_event_fifo')
            self.assertEqual(sha(output / fifo),
                             '2084bead34bf421610fd20489ece66601823b87f72887228be25de5374a956c6')
            self.assertNotEqual(sha(output / fifo), sha(output / 'component' / diagnostic.COMPONENT_FIFO))
            for name, expected in metadata['staged_input_sha256'].items():
                self.assertEqual(sha(output / name), expected, name)
            paths = [entry.attrib['path'] for entry in ElementTree.parse(output / 'usb2_hotplug.gprj').find('FileList')]
            self.assertTrue(all((output / name).is_file() for name in paths))
            self.assertEqual(paths[:-2], metadata['source_paths'])
            self.assertFalse(any('ddr3' in name or 'unified_oscillator' in name or 'workstation_hdmi' in name
                                 for name in metadata['source_paths']))
            constraints = (output / 'usb2_hotplug.sdc').read_text()
            self.assertEqual(constraints.count('create_clock '), 2)
            self.assertEqual(constraints.count('create_generated_clock '), 2)
            self.assertIn('u_native_usb/host/usb/bridge/', constraints)
            self.assertIn('u_native_usb/input_owner/events/', constraints)
            self.assertIn('u_diagnostic_link/', constraints)
            for stem, alias in (('source_release', 'u_native_usb/host/usb/bridge/ulpi_release_q'),
                                ('destination_release', 'u_native_usb/host/cpu_release_q')):
                self.assertIn(f'{{{alias}_1_s*/Q}}] -to [get_pins '
                              f'{{u_diagnostic_link/{stem}_2_s*/D}}] 2.000', constraints)
                self.assertNotIn(f'u_diagnostic_link/{stem}_0_s*/Q', constraints)
                self.assertNotIn(f'u_diagnostic_link/{stem}_1_s*/D', constraints)
            self.assertNotIn('set_clock_groups', constraints)
            self.assertNotIn('u_video/', constraints)
            self.assertTrue((output / 'implementation.tcl').read_text().endswith('run syn\nrun pnr\n'))
            self.assertIn('set_option -user_code C127E2F0', (output / 'implementation.tcl').read_text())
            with self.assertRaises(FileExistsError):
                diagnostic.prepare(ROOT, output, Path(directory) / 'netlists', 'C127E2F1')
            staged_uart = output / diagnostic.LIVE_SOURCES[1]
            staged_uart.write_bytes(staged_uart.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'staged input changed'):
                diagnostic.audit(ROOT, output)

    def test_missing_board_inputs_or_identity_fail_before_creating_output(self):
        with tempfile.TemporaryDirectory(prefix='usb2-hotplug-invalid-') as directory:
            for netlists, code in ((None, 'C127E201'), (Path(directory), None), (Path(directory), 'garbage')):
                output = Path(directory) / 'candidate'
                with self.subTest(code=code), self.assertRaises(ValueError):
                    diagnostic.prepare(ROOT, output, netlists, code)
                self.assertFalse(output.exists())

    def test_cli_requires_business_firmware_and_keeps_profiles_separate(self):
        with tempfile.TemporaryDirectory(prefix='usb2-hotplug-cli-') as directory:
            output = Path(directory) / 'candidate'
            common = [sys.executable, str(ROOT / 'build.py'), '--prepare-usb2-soc',
                      '--usb2-component', 'workstation-hotplug', '--usb2-soc-output', str(output)]
            for extra, message in (([], 'requires explicit --usb2-firmware-profile workstation'),
                                   (['--usb2-firmware-profile', 'workstation'], 'requires --netlist-dir'),
                                   (['--usb2-firmware-profile', 'workstation', '--current-workstation'],
                                    'cannot be mixed')):
                with self.subTest(extra=extra):
                    result = subprocess.run([*common, *extra], text=True, capture_output=True, timeout=30)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(message, result.stderr)
                    self.assertFalse(output.exists())


class DiagnosticUart(unittest.TestCase):
    def test_actual_uart_transmits_atomic_snapshot_as_sixteen_hex_words(self):
        self.assertIsNotNone(shutil.which('iverilog'))
        words = [0x12345678 + index * 0x01010101 for index in range(16)]
        report = ''.join(f'{word:08X}' for word in words)
        expected = ('U2 ' + ' '.join(f'{word:08X}' for word in words) + '\r\n').encode()
        bench = '''`timescale 1ns/1ps
module tb;
reg clk=0, reset_n=0;
always #5 clk=~clk;
reg [511:0] report_data=512'hPAYLOAD;
wire serial;
workstation_usb2_diagnostic_uart #(.CLOCK_HZ(100),.BAUD(25),.REPORT_CYCLES(16)) dut (
 .clk(clk),.reset_n(reset_n),.report_i(report_data),.uart_tx_o(serial));
integer byte_index, bit_index;
reg [7:0] character;
reg [8*LENGTH-1:0] expected=8*LENGTH'hEXPECTED;
initial begin
 #21; reset_n=1;
 wait(dut.busy_q); @(negedge clk); report_data=0;
 for(byte_index=0;byte_index<LENGTH;byte_index=byte_index+1) begin
  @(negedge serial); #60;
  for(bit_index=0;bit_index<8;bit_index=bit_index+1) begin
   character[bit_index]=serial; #40;
  end
  if(serial!==1) $fatal(1,"UART stop bit");
  if(character!==expected[8*(LENGTH-1-byte_index)+:8])
   $fatal(1,"UART character %0d got %02x expected %02x",byte_index,character,expected[8*(LENGTH-1-byte_index)+:8]);
 end
 $display("PASS atomic diagnostic UART"); $finish;
end
initial begin #200000; $fatal(1,"UART timeout"); end
endmodule
'''.replace('PAYLOAD', report).replace('LENGTH', str(len(expected))).replace('EXPECTED', expected.hex())
        bench = bench.replace('8*' + str(len(expected)) + "'h", str(8 * len(expected)) + "'h")
        with tempfile.TemporaryDirectory(prefix='usb2-diagnostic-uart-') as directory:
            stage = Path(directory)
            (stage / 'tb.sv').write_text(bench)
            compilation = subprocess.run(['iverilog', '-g2012', '-s', 'tb', '-o', str(stage / 'simulation'),
                                          str(stage / 'tb.sv'), str(ROOT / diagnostic.LIVE_SOURCES[1]),
                                          str(ROOT / 'vendor/usb_host_fs_8fc3/src/simpleuart.v')],
                                         capture_output=True, text=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stderr)
            execution = subprocess.run(['vvp', str(stage / 'simulation')], capture_output=True, text=True, timeout=30)
            self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
            self.assertIn('PASS atomic diagnostic UART', execution.stdout)


if __name__ == '__main__':
    unittest.main()
