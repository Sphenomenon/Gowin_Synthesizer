#!/usr/bin/env python3
"""Reviewed runtime CDC endpoints and deliberate actual-VG corruptions; no EDA."""

from pathlib import Path
import json
import os
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_runtime_cdc import (
    GRAY, GRAY_MSB_ALIASES, audit_runtime_cdc, runtime_cdc_bundle, run_audit, validate_installed_constraints,
)
from tools.workstation_runtime_clock_audit import VG_RELATIVE, audit_runtime_clocks, file_sha
from tools.workstation_synthesis_netlist import IDENTIFIER, SynthesisNetlist
from tools.workstation_runtime_profile import shared_constraints


class RuntimeCdcPolicy(unittest.TestCase):
    def test_source_period_limits_and_explicit_partial_scope(self):
        b = runtime_cdc_bundle(ROOT)
        self.assertEqual(len(GRAY), 21)
        self.assertEqual(sum(g['width'] for g in b['gray_groups']), 400)
        self.assertEqual(len(b['sdc'].splitlines()), 43)
        self.assertEqual(sum(bool(g['registered_msb_alias']) for g in b['gray_groups']), 10)
        self.assertNotIn('get_clocks', b['sdc'])
        for g in b['gray_groups']:
            self.assertLessEqual(g['max_delay_ns'], g['source_period_ns'])
            self.assertGreater(g['max_delay_ns'], 0)
            self.assertFalse(g['setup_false_path'])
            if g['source_domain'] == 'selected':
                self.assertEqual(g['max_delay_ns'], 59.051)
        self.assertFalse(b['remaining_inventory_complete'])
        self.assertFalse(b['constraints_complete'])
        self.assertFalse(b['physical_cdc_accepted'])

    def test_legacy_run_selector_is_removed_only_in_reviewed_shape(self):
        line = 'set_false_path -to [get_pins {tf_run_meta*/D}]\n'
        selected = shared_constraints(line)
        self.assertEqual(selected['sdc'], '')
        self.assertEqual(selected['omitted'][0]['removed_selectors'], ['tf_run_meta*/D'])
        with self.assertRaisesRegex(ValueError, 'unsupported legacy TF run'):
            shared_constraints('set_false_path -to [get_pins {tf_run_meta*/D another/D}]\n')


class ActualRuntimeCdc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get('GW138K_RUNTIME_CDC_STAGE') or not os.environ.get('GW138K_RUNTIME_CDC_PROCESS'):
            raise unittest.SkipTest('select a sealed runtime VG/process with GW138K_RUNTIME_CDC_STAGE/PROCESS; no EDA fallback')
        cls.stage = Path(os.environ['GW138K_RUNTIME_CDC_STAGE'])
        cls.process = Path(os.environ['GW138K_RUNTIME_CDC_PROCESS'])
        cls.text = (cls.stage / VG_RELATIVE).read_text()
        cls.netlist = SynthesisNetlist(cls.text, 'workstation_custom_138k_top')
        cls.clocks = audit_runtime_clocks(ROOT, cls.stage, cls.text)
        cls.mutations = []

    @classmethod
    def tearDownClass(cls):
        if os.environ.get('GW138K_RUNTIME_CDC_TEST_EVIDENCE'):
            p = Path(os.environ['GW138K_RUNTIME_CDC_TEST_EVIDENCE'])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(dict(schema=1, vg_sha256=file_sha(cls.stage / VG_RELATIVE),
                mutations=cls.mutations, mutation_count=len(cls.mutations), eda_invoked=False,
                hardware_operated=False, constraints_complete=False, physical_cdc_accepted=False), indent=2) + '\n')

    def change(self, path, *, port=None, parameter=None, value=None, append=''):
        scope = self.netlist.scopes[path]
        module = self.netlist.frames[scope]['kind']
        blocks = list(re.finditer(r'^module\s+(' + IDENTIFIER + r')\s*\(.*?^endmodule\b', self.text, re.M | re.S))
        block = next(m for m in blocks if m[1].removeprefix('\\') == module)
        original = block[0]
        # Promoted primitives may have an escaped label containing slashes.
        label = path[len(scope) + 1:] if scope else path
        changed = original
        if port:
            # Gowin may write the module port-list terminator as ")\n;".
            # Starting after the first literal ");" would skip its first cell.
            body_start = re.match(r'^module\s+' + IDENTIFIER + r'\s*\(.*?\)\s*;', original, re.S).end()
            instances = list(re.finditer(r'^[ \t]*(' + IDENTIFIER + r')[ \t]+(' + IDENTIFIER +
                r')[ \t]*\((.*?)^[ \t]*\);', original[body_start:], re.M | re.S))
            c = next(c for c in instances if c[2].removeprefix('\\') == label)
            replacement, count = re.subn(r'(\.' + re.escape(port) + r'\()\s*[^()]*?(\))',
                                         lambda p: p[1] + value + p[2], c[0])
            self.assertEqual(count, 1)
            changed = original[:body_start + c.start()] + replacement + original[body_start + c.end():]
        elif parameter:
            rx = r'(defparam\s+(?:\\)?' + re.escape(label) + r'\s*\.' + parameter + r'\s*=\s*)[^;]+;'
            changed, count = re.subn(rx, lambda p: p[1] + value + ';', original)
            self.assertEqual(count, 1)
        if append:
            changed = changed.removesuffix('endmodule') + append + '\nendmodule'
        return self.text[:block.start()] + changed + self.text[block.end():]

    def reject(self, label, text, message):
        with self.assertRaisesRegex(ValueError, message) as e:
            audit_runtime_cdc(ROOT, text, self.clocks)
        self.mutations.append(dict(case=label, rejected=True, error=str(e.exception)))

    def test_sealed_actual_400_bits_and_shared_reset_chains(self):
        result = run_audit(ROOT, self.stage, self.process, endpoint_development=True)
        self.assertEqual(result['gray_group_count'], 21)
        self.assertEqual(result['gray_first_stage_bits'], 400)
        self.assertEqual(len(result['ble_reset_aliases']), 2)
        self.assertTrue(result['source_seal_before_and_after'])
        self.assertFalse(result['candidate_constraints_installed'])
        self.assertTrue(result['endpoint_development_only'])
        for group in result['gray_groups']:
            if group['id'] in GRAY_MSB_ALIASES:
                self.assertRegex(group['paths'][-1]['source'], '/' + GRAY_MSB_ALIASES[group['id']] +
                                 '_' + str(group['width'] - 1) + r'_s\d+$')
        for key in ('remaining_inventory_complete', 'held_payload_complete', 'fifo_payload_complete',
                    'single_bit_complete', 'reset_inventory_complete', 'constraints_complete',
                    'routed_propagation_verified', 'physical_cdc_accepted', 'sta_verified',
                    'hardware_tested', 'release_ready', 'deployment_allowed'):
            self.assertFalse(result[key])

    def test_wrong_gray_bit_is_rejected(self):
        self.reject('Gray swapped source bit', self.change('u_runtime_memory_guard/gray_meta_0_s0',
                    port='D', value='memory_gray[1]'), 'Gray bit identity')

    def test_wrong_gray_destination_clock_is_rejected(self):
        self.reject('Gray first clock', self.change('u_runtime_memory_guard/gray_meta_0_s0',
                    port='CLK', value="1'b0"), 'Gray destination clock')

    def test_registered_gray_msb_alias_disconnect_is_rejected(self):
        self.reject('Gray registered binary MSB alias disconnected', self.change(
                    'u_managed/runtime/service/workstation/runtime_effects.effects/delay_stage/u_write_fifo/write_binary_9_s0',
                    port='Q', value='wrong_msb'), 'Gray bit identity or unique producer')

    def test_wrong_second_stage_is_rejected(self):
        self.reject('Gray second-stage bypass', self.change('u_runtime_memory_guard/gray_sync_0_s0',
                    port='D', value='memory_gray[0]'), 'Gray second-stage connection')

    def test_tf_clear_lut_truth_table_is_rejected(self):
        self.reject('TF Gray clear LUT function', self.change('u_tf_audio/path/u_capture_fifo/n519_s3',
                    parameter='INIT', value="8'hff"), 'Gray local-clear LUT truth table')

    def test_tf_second_stage_clear_lut_truth_table_is_rejected(self):
        self.reject('TF Gray second-stage clear LUT function', self.change('u_tf_audio/path/u_capture_fifo/n532_s3',
                    parameter='INIT', value="8'hff"), 'Gray local-clear LUT truth table')

    def test_tf_second_stage_clear_conditions_are_identical(self):
        self.reject('TF Gray second-stage clear differs', self.change('u_tf_audio/path/u_capture_fifo/n532_s3',
                    port='I1', value='clear_rd_meta'), 'Gray clear conditions differ between stages')

    def test_tf_clear_nonlocal_source_is_rejected(self):
        self.reject('TF Gray clear local clock', self.change('u_tf_audio/path/u_capture_fifo/clear_rd_meta_s0',
                    port='CLK', value="1'b0"), 'Gray clear input is not a local register')

    def test_extra_gray_bit_is_rejected(self):
        extra = "\nDFFCE gray_meta_32_s0 (.Q(extra_gray), .D(memory_gray[0]), .CLK(clk_50m_i), .CLEAR(1'b0), .CE(1'b1)\n);\n"
        self.reject('Gray selector extra bit', self.change('u_runtime_memory_guard/gray_meta_0_s0', append=extra),
                    'exact register bit inventory')

    def test_ble_alias_shift_corruption_is_rejected(self):
        self.reject('BLE shared release wrong shift', self.change('u_managed/midi_bytes/source_release_1_s0',
                    port='D', value="1'b1"), 'BLE release alias shift')

    def test_installation_requires_exact_lines_and_preserves_gray_setup(self):
        result = audit_runtime_cdc(ROOT, self.text, self.clocks)
        proposed = runtime_cdc_bundle(ROOT)['sdc']
        self.assertTrue(validate_installed_constraints(ROOT, proposed, result)['reviewed_group_lines_installed'])
        # Exercise the full sealed SDC's unchanged command forms as well as the
        # isolated bundle. This is a constructed text fixture, not a new stage.
        original = (self.stage / 'constraints/custom_138k.sdc').read_text().splitlines()
        installed_fixture = '\n'.join(line for line in original if 'tf_run_meta' not in line and not (
            'u_runtime_memory_guard/memory_gray' in line)) + '\n' + proposed
        self.assertTrue(validate_installed_constraints(ROOT, installed_fixture, result)['reviewed_group_lines_installed'])
        for label, sdc, message in (
                ('missing bound', proposed.replace('set_max_delay 10.000', 'set_max_delay 100.000', 1), 'missing or duplicated'),
                ('duplicate group', proposed + proposed.splitlines()[0] + '\n', 'missing or duplicated'),
                ('setup cut', proposed + 'set_false_path -to [get_pins {u_runtime_memory_guard/gray_meta*/D}]\n', 'masks reviewed Gray'),
                ('register setup cut', proposed + 'set_false_path -to [get_regs {u_runtime_memory_guard/gray_meta*}]\n', 'masks reviewed Gray'),
                ('source setup cut', proposed + 'set_false_path -from [get_pins {u_runtime_memory_guard/memory_gray*/Q}]\n', 'masks reviewed Gray'),
                ('global setup cut', proposed + 'set_false_path\n', 'masks reviewed Gray'),
                ('global hold cut', proposed + 'set_false_path -hold\n', 'unreviewed hold exception'),
                ('combined hold setup cut', proposed + 'set_false_path -hold -setup -to [get_pins {u_runtime_memory_guard/gray_meta*/D}]\n', 'combined hold/setup'),
                ('whole clock cut', proposed + 'set_false_path -from [get_clocks {clk_50m}] -to [get_clocks {audio_76m8}]\n', 'whole-clock setup'),
                ('extra relaxed bound', proposed + 'set_max_delay 999.000 -to [get_pins {u_runtime_memory_guard/gray_meta*/D}]\n', 'unreviewed max delay'),
                ('global relaxed bound', proposed + 'set_max_delay 999.000\n', 'unreviewed max delay'),
                ('unsupported endpoint query', proposed + 'set_false_path -to [get_cells {u_runtime_memory_guard/gray_meta*}]\n', 'unsupported timing query'),
                ('asynchronous clock groups', proposed + 'set_clock_groups -asynchronous -group {clk_50m} -group {audio_76m8}\n', 'unreviewed SDC command'),
                ('exclusive clock groups', proposed + 'set_clock_groups -logically_exclusive -group {clk_50m} -group {audio_76m8}\n', 'unreviewed SDC command'),
                ('disabled timing', proposed + 'set_disable_timing [get_pins {u_runtime_memory_guard/gray_meta*/D}]\n', 'unreviewed SDC command'),
                ('multicycle relaxation', proposed + 'set_multicycle_path 10 -to [get_pins {u_runtime_memory_guard/gray_meta*/D}]\n', 'unreviewed SDC command'),
                ('external SDC source', proposed + 'source unreviewed.sdc\n', 'unreviewed SDC command'),
                ('unreviewed peripheral command', proposed + 'set_min_delay 999.000 -to [get_pins {u_runtime_memory_guard/gray_meta*/D}]\n', 'unreviewed peripheral SDC command'),
                ('Tcl evaluation in hold path', proposed + 'set_false_path -hold -to [eval cut]\n', 'unsupported timing query'),
                ('multiple Tcl commands', proposed + 'set_false_path -hold; set_false_path\n', 'unsupported Tcl evaluation'),
                ('legacy selector', proposed + 'set_false_path -to [get_pins {tf_run_meta*/D}]\n', 'legacy TF run')):
            with self.subTest(case=label), self.assertRaisesRegex(ValueError, message) as e:
                validate_installed_constraints(ROOT, sdc, result)
            self.mutations.append(dict(case=label, rejected=True, error=str(e.exception)))


if __name__ == '__main__':
    unittest.main()
