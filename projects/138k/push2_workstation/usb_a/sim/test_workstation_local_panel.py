#!/usr/bin/env python3
"""Explicit LCD retirement, unchanged old providers and fail-closed netlist checks."""

from pathlib import Path
from unittest.mock import patch
import copy
import hashlib
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_board_peripherals import (
    LOCAL_PANEL_OUTPUTS, LOCAL_PANEL_SOURCE, LCD_SDC, audit_local_panel, local_panel_bundle)
from tools.workstation_custom_clocks import audit_clocks, clock_bundle


PROVIDERS_BEFORE = {
    'workstation_profile_r00_runtime.sv': '7e000a595fe1b89ffba529fee6b69cef8795d41eeb99fd34271d9b73ca88a074',
    'workstation_profile_no_cnn_runtime.sv': 'fb123586b2c2818d1b32110a82e91ac76bb81d25aa14914716ae57d93f4a401a',
    'workstation_profile_runtime.sv': '108dfc85bb096cef03a78a38d6d10aad83dd2c7deba2321a14c40273638abaa2',
    'workstation_custom_138k_top.sv': '2103f46e9155b5ebd0e996e06a1b400a42dbee8ead91a8eafc532b5e8acd2ffe',
}


def tokens(text):
    return re.sub(r'\s+', '', re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S))


def preprocess(provider):
    with tempfile.TemporaryDirectory(prefix='local-panel-provider-') as directory:
        output = Path(directory) / 'preprocessed.sv'
        result = subprocess.run(['iverilog', '-g2012', '-E', '-I', str(ROOT), '-o', str(output),
            str(ROOT / 'rtl/workstation' / provider)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return output.read_text()


def static_fixture():
    declarations, buffers = [], []
    for port, width in LOCAL_PANEL_OUTPUTS.items():
        declarations.append(f'output [{width-1}:0] {port};' if width > 1 else f'output {port};')
        for index in range(width):
            bit = f'{port}[{index}]' if width > 1 else port
            buffers.append(f'OBUF {port}_{index}_obuf (\n.I(GND), .O({bit})\n);')
    return ('module workstation_custom_138k_top (\n);\n' + '\n'.join(declarations) +
            '\nGND ground (\n.G(GND)\n);\n' + '\n'.join(buffers) + '\nendmodule\n')


LIVE_FIXTURE = '''module workstation_custom_138k_top (
);
local_lcd u_lcd (
);
endmodule
module local_lcd (
);
lcd_pll u_pll (
);
mailbox u_feedback (
);
endmodule
module lcd_pll (
);
PLL PLL_inst (
);
endmodule
module mailbox (
);
endmodule
'''


class LocalPanel(unittest.TestCase):
    def test_existing_provider_tokens_are_unchanged(self):
        # Captured from 483aba48 before introducing the optional branch.
        for provider, expected in PROVIDERS_BEFORE.items():
            with self.subTest(provider=provider):
                self.assertEqual(hashlib.sha256(tokens(preprocess(provider)).encode()).hexdigest(), expected)

    def test_new_provider_replaces_only_lcd_instance_and_does_not_leak_macro(self):
        original = preprocess('workstation_profile_r00_runtime.sv')
        selected = preprocess('workstation_profile_r00_no_local_panel.sv')
        parked = "assign lcd_r=5'd0,lcd_g=6'd0,lcd_b=5'd0;\n" + \
                 "assign lcd_pclk=1'b0,lcd_hsync=1'b0,lcd_vsync=1'b0,lcd_de=1'b0,lcd_bl=1'b0;"
        expected, count = re.subn(r'workstation_lcd\s+u_lcd\s*\(.*?\);', parked, original, flags=re.S)
        self.assertEqual(count, 1)
        self.assertEqual(tokens(selected), tokens(expected))
        self.assertNotIn('u_lcd', selected)
        self.assertIn(".input_attached(1'b0)", selected)
        with tempfile.TemporaryDirectory(prefix='local-panel-macro-') as directory:
            source = Path(directory) / 'scope.sv'
            output = Path(directory) / 'scope.preprocessed.sv'
            source.write_text('`include "rtl/workstation/workstation_profile_r00_no_local_panel.sv"\n'
                '`ifdef WORKSTATION_NO_LOCAL_PANEL\nmodule leaked_local_panel_macro(); endmodule\n`endif\n')
            subprocess.run(['iverilog', '-g2012', '-E', '-I', str(ROOT), '-o', str(output), str(source)],
                           capture_output=True, text=True, check=True, timeout=30)
            self.assertNotIn('leaked_local_panel_macro', output.read_text())

    def test_actual_selected_top_keeps_all_lcd_pins_low_while_reference_clocks_run(self):
        # Unresolved owners are black boxes for this composition-only test.
        # The real top must independently park every local-panel output.
        with tempfile.TemporaryDirectory(prefix='local-panel-pins-') as directory:
            stage = Path(directory)
            source = stage / 'tb.sv'
            binary = stage / 'simulation'
            source.write_text('''module tb;
reg clk_50m=0,clk_12m288=0,clk_16m9344=0;
always #10 clk_50m=~clk_50m;
always #41 clk_12m288=~clk_12m288;
always #30 clk_16m9344=~clk_16m9344;
wire [4:0] lcd_r,lcd_b;
wire [5:0] lcd_g;
wire lcd_pclk,lcd_hsync,lcd_vsync,lcd_de,lcd_bl;
workstation_custom_138k_top dut (
 .clk_50m(clk_50m),.clk_12m288(clk_12m288),.clk_16m9344(clk_16m9344),
 .lcd_r(lcd_r),.lcd_g(lcd_g),.lcd_b(lcd_b),.lcd_pclk(lcd_pclk),
 .lcd_hsync(lcd_hsync),.lcd_vsync(lcd_vsync),.lcd_de(lcd_de),.lcd_bl(lcd_bl)
);
initial begin
 repeat(1000) begin
  #7;
  if ({lcd_r,lcd_g,lcd_b,lcd_pclk,lcd_hsync,lcd_vsync,lcd_de,lcd_bl} !== 21'd0)
   $fatal(1,"local panel output changed while disabled");
 end
 $display("PASS disabled local panel pins");
 $finish;
end
endmodule
''')
            result = subprocess.run(['iverilog', '-g2012', '-i', '-s', 'tb', '-I', str(ROOT),
                '-o', str(binary), str(source),
                str(ROOT / 'rtl/workstation/workstation_profile_r00_no_local_panel.sv')],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run(['vvp', str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS disabled local panel pins', result.stdout)

    def test_clock_and_cdc_selection_retire_only_lcd(self):
        self.assertEqual(local_panel_bundle()['sources'], [LOCAL_PANEL_SOURCE])
        self.assertEqual(local_panel_bundle()['sdc'], LCD_SDC)
        retired = local_panel_bundle(False)
        self.assertEqual(retired['sources'], [])
        self.assertEqual(retired['sdc'], '')
        self.assertEqual(retired['retired_sources'], [LOCAL_PANEL_SOURCE])
        self.assertEqual(retired['retired_clocks'], ['lcd_pixel31m5'])
        self.assertFalse(retired['touch_input_selected'])
        for mode in ('1080p60', '720p30', '720p60'):
            with self.subTest(mode=mode):
                original = clock_bundle(ROOT, mode)
                selected = clock_bundle(ROOT, mode, local_panel_enabled=False)
                omitted = [line for line in original['sdc'].splitlines(keepends=True) if 'lcd_pixel31m5' in line]
                self.assertEqual(len(omitted), 1)
                self.assertEqual(selected['sdc'], original['sdc'].replace(omitted[0], ''))
                self.assertEqual(selected['plan']['primary'], original['plan']['primary'])
                self.assertEqual(selected['plan']['generated'], [entry for entry in original['plan']['generated']
                                  if entry['name'] != 'lcd_pixel31m5'])
                self.assertEqual(selected['source_sha256'], original['source_sha256'])

    def test_disabled_panel_still_validates_reviewed_plan_and_boolean_selection(self):
        changed = copy.deepcopy(clock_bundle(ROOT)['plan'])
        next(entry for entry in changed['generated'] if entry['name'] == 'lcd_pixel31m5')['frequency_hz'] = 1
        with patch('tools.workstation_custom_clocks.json.loads', return_value=changed):
            with self.assertRaisesRegex(ValueError, 'frequency or target inventory'):
                clock_bundle(ROOT, local_panel_enabled=False)
        for value in (0, 1, None, 'false'):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'must be boolean'):
                    local_panel_bundle(value)
                with self.assertRaisesRegex(ValueError, 'must be boolean'):
                    clock_bundle(ROOT, local_panel_enabled=value)

    def test_static_output_audit_rejects_active_missing_or_wrong_width_pins(self):
        source = static_fixture()
        evidence = audit_local_panel(source, local_panel_enabled=False)
        self.assertEqual(len(evidence['static_output_bits']), 21)
        self.assertFalse(evidence['hierarchy_present'])
        self.assertFalse(evidence['physical_panel_verified'])
        mutations = (
            (source.replace('.I(GND), .O(lcd_bl)', ".I(1'b1), .O(lcd_bl)"), 'not static low'),
            (source.replace('.O(lcd_pclk)', '.O(another_pin)'), 'not static low'),
            (source.replace('output [5:0] lcd_g;', 'output [4:0] lcd_g;'), 'output port changed'),
            (source.replace('OBUF lcd_bl_0_obuf', 'OBUF extra_bl (\n.I(GND),.O(lcd_bl)\n);\nOBUF lcd_bl_0_obuf'),
             'not static low'),
            (source.replace('GND ground', 'PLL u_lcd (\n);\nGND ground'), 'hierarchy remains'),
        )
        for changed, message in mutations:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                audit_local_panel(changed, local_panel_enabled=False)

    def test_enabled_audit_requires_real_lcd_pll_and_feedback_owner(self):
        self.assertTrue(audit_local_panel(LIVE_FIXTURE)['hierarchy_present'])
        for old in ('local_lcd u_lcd', 'mailbox u_feedback', 'PLL PLL_inst'):
            with self.subTest(missing=old), self.assertRaisesRegex(ValueError, 'owner, PLL or feedback'):
                audit_local_panel(LIVE_FIXTURE.replace(old, 'unselected unused'))

    def test_clock_audit_rejects_disabled_hierarchy_before_accepting_clock_inventory(self):
        with tempfile.TemporaryDirectory(prefix='local-panel-clock-audit-') as directory:
            stage = Path(directory)
            (stage / 'constraints').mkdir()
            (stage / 'constraints/custom_138k.sdc').write_text(clock_bundle(ROOT, local_panel_enabled=False)['sdc'])
            with self.assertRaisesRegex(ValueError, 'hierarchy remains'):
                audit_clocks(ROOT, stage, LIVE_FIXTURE, local_panel_enabled=False)
            with self.assertRaisesRegex(ValueError, 'constraint remains'):
                audit_clocks(ROOT, stage, static_fixture(), extra_sdc=LCD_SDC, local_panel_enabled=False)


if __name__ == '__main__':
    unittest.main()
