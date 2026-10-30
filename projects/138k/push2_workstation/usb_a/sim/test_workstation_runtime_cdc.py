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
from tools.workstation_runtime_profile import shared_constraints, bluetooth_constraints, LEGACY_BLE_RELEASE_RESET
from tools.workstation_bluetooth import SDC as BLUETOOTH_SDC


class RuntimeCdcPolicy(unittest.TestCase):
    def test_runtime_ble_keeps_payload_and_uart_and_uses_shared_release(self):
        selected = bluetooth_constraints(BLUETOOTH_SDC)
        self.assertEqual(selected['sdc'], BLUETOOTH_SDC.replace(LEGACY_BLE_RELEASE_RESET + '\n', '', 1))
        self.assertEqual(len(selected['sdc'].splitlines()), 6)
        self.assertIn('u_ble_pcm_cdc/held_data*', selected['sdc'])
        self.assertIn('u_ble_pcm_cdc/req_meta*/D u_ble_pcm_cdc/ack_meta*/D', selected['sdc'])
        self.assertIn('ble_uart_rx_i', selected['sdc'])
        self.assertEqual(selected['evidence']['replacement']['owner'], 'runtime_cdc_bundle')
        self.assertEqual(runtime_cdc_bundle(ROOT)['sdc'].splitlines().count(
            selected['evidence']['replacement']['constraint']), 1)
        self.assertFalse(selected['evidence']['physical_cdc_accepted'])

    def test_runtime_ble_adapter_rejects_anchor_and_input_drift(self):
        for changed in (BLUETOOTH_SDC.replace(LEGACY_BLE_RELEASE_RESET + '\n', ''),
                        BLUETOOTH_SDC + LEGACY_BLE_RELEASE_RESET + '\n',
                        BLUETOOTH_SDC.replace('destination_release*/CLEAR', 'destination_release*/D'),
                        BLUETOOTH_SDC.replace('held_data*', 'other_held_data*'),
                        BLUETOOTH_SDC + '# unreviewed source drift\n'):
            with self.subTest(sdc=changed), self.assertRaisesRegex(ValueError, 'runtime BLE'):
                bluetooth_constraints(changed)

    def test_source_period_limits_and_explicit_partial_scope(self):
        b = runtime_cdc_bundle(ROOT)
        self.assertEqual(len(GRAY), 21)
        self.assertEqual(sum(g['width'] for g in b['gray_groups']), 400)
        self.assertEqual(len(b['sdc'].splitlines()), 53)
        self.assertEqual(b['policy'], 'native-runtime-cdc-gray-media-fence-v2')
        self.assertEqual(len(b['media_control_groups']), 3)
        self.assertFalse(b['media_hold_assertion']['recovery_removal_cut'])
        self.assertFalse(b['usb_queue_fence']['recovery_removal_cut'])
        self.assertFalse(any('tf_audio/path/u_' in line for line in b['sdc'].splitlines()))
        self.assertFalse(any(line.startswith('set_false_path') and ('PRESET' in line or 'drain_release' in line and 'CLEAR' in line) for line in b['sdc'].splitlines()))
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
        self.assertEqual(len(result['media_control_groups']), 3)
        self.assertEqual(len(result['media_hold']['release']), 2)
        self.assertEqual(len(result['usb_queue_fence']['drain_release']), 6)
        self.assertEqual(len(result['protected_async_pins']), 8)
        for group in result['gray_groups']:
            for bit in group['paths']:
                self.assertEqual(bit['through'], [])
                self.assertEqual(bit['second_through'], [])
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

    def reg(self, scope, stem):
        paths = [p for p, c in self.netlist.cells.items() if c['kind'].startswith('DFF') and
                 re.fullmatch(re.escape(scope + '/' + stem) + r'_s\d+', p)]
        self.assertEqual(len(paths), 1)
        return paths[0]

    def test_old_vg_cannot_substitute_legacy_tf_scopes(self):
        old = os.environ.get('GW138K_RUNTIME_CDC_LEGACY_VG')
        if not old:
            self.skipTest('optional explicit sealed legacy VG path; no historical-cache fallback')
        self.reject('old VG legacy TF scope cannot satisfy v2', Path(old).read_text(),
                    'Gray or reset scope missing: u_tf_audio/path/g_runtime_capture')

    def test_failed_mixed_async_hold_vg_is_rejected(self):
        old = os.environ.get('GW138K_RUNTIME_CDC_BLOCKED_VG')
        if not old:
            self.skipTest('optional explicit structurally blocked revision5 VG path')
        self.reject('mixed asynchronous controls split hold register', Path(old).read_text(),
                    'duplicate register bit: u_managed/media_stop/hold_compute')

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

    def test_tf_direct_first_identity_is_required(self):
        path = self.reg('u_tf_audio/path/g_runtime_capture.u_capture_fifo', 'wr_gray_r1_0')
        self.reject('TF direct first stage source', self.change(path, port='D', value='wr_gray[1]'),
                    'Gray bit identity')

    def test_tf_second_stage_cannot_use_old_clear_or_source(self):
        path = self.reg('u_tf_audio/path/g_runtime_capture.u_capture_fifo', 'wr_gray_r2_0')
        self.reject('TF direct second stage rejects old clear/source topology',
                    self.change(path, port='D', value='wr_gray[0]'), 'Gray second-stage connection')

    def test_tf_conditional_first_enable_is_rejected(self):
        path = self.reg('u_tf_audio/path/g_runtime_playback.u_playback_fifo', 'rd_gray_w1_0')
        self.reject('TF continuously sampled first stage', self.change(path, port='CE', value='clear_wr_meta'),
                    'Gray synchronizer enable is conditional')

    def test_tf_first_stage_functional_fanout_is_rejected(self):
        path = self.reg('u_tf_audio/path/g_runtime_capture.u_capture_fifo', 'wr_gray_r1_0')
        extra = "\nDFFCE extra_tf_functional_s0 (.Q(extra_function), .D(wr_gray_r1[0]), .CLK(rd_clk), .CLEAR(1'b0), .CE(1'b1)\n);\n"
        self.reject('TF first stage functional fanout', self.change(path, append=extra), 'Gray first-stage fanout')

    def test_media_request_source_is_required(self):
        p = self.reg('u_managed/media_stop', 'request_compute_0')
        self.reject('media request source swapped', self.change(p, port='D', value='compute_failure'),
                    'media receiver source identity')

    def test_media_ack_extra_settle_stage_is_required(self):
        p = self.reg('u_managed/media_stop', 'acknowledge_50_2')
        self.reject('media ACK bypasses extra settling edge', self.change(p, port='D', value='acknowledge_50[0]'),
                    'media receiver source identity or stage connection')

    def test_media_failure_is_held_until_ack_event(self):
        p = self.reg('u_managed/media_stop', 'compute_failure')
        self.reject('media failure updates independently of ACK', self.change(p, port='CE', value="1'b1"),
                    'media/fence Boolean function changed: held failure')

    def test_media_ack_enabled_transition_must_match_failure_capture(self):
        p = self.reg('u_managed/media_stop', 'acknowledge_toggle')
        self.reject('ACK CE suppresses real result transition', self.change(p, port='CE', value="1'b0"),
                    'media/fence Boolean function changed: held failure')
        self.reject('ACK D no longer toggles on real result', self.change(p, port='D', value='acknowledge_toggle'),
                    'media/fence Boolean function changed: held failure')

    def test_media_failure_synchronizer_enable_is_unconditional(self):
        p = self.reg('u_managed/media_stop', 'failed_50_0')
        self.reject('media failure first-stage gated', self.change(p, port='CE', value='hold_50'),
                    'media receiver conditional enable')

    def test_media_hold_assertion_and_shift_are_required(self):
        p = self.reg('u_managed/media_stop', 'hold_compute_0')
        self.reject('media hold preset disconnected', self.change(p, port='PRESET', value="1'b0"),
                    'media/fence Boolean function changed: common reset OR hold')
        p = self.reg('u_managed/media_stop', 'hold_compute_1')
        self.reject('media hold bypasses two real compute edges', self.change(p, port='D', value="1'b0"),
                    'media/fence release intermediate fanout')

    def test_usb_drain_six_edges_clock_and_reset_are_required(self):
        p = self.reg('u_native_usb/input_owner', 'stopped_clock_queue_fence.drain_release_5')
        self.reject('USB drain shortened', self.change(p, port='D', value="1'b1"),
                    'media/fence release shift')
        self.reject('USB drain wrong clock', self.change(p, port='CLK', value='clk'),
                    'media/fence release clock')
        self.reject('USB drain reset differs', self.change(p, port='CLEAR', value='input_reset'),
                    'media/fence release assertion differs')

    def test_usb_write_ready_requires_drained_queue(self):
        p = self.reg('u_native_usb/input_owner', 'queue_write_release_0')
        self.reject('USB writes reopen before actual drain', self.change(p, port='D', value="1'b1"),
                    'media/fence Boolean function changed: USB queue ready')

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
        preview = []
        for line in original:
            if line in proposed.splitlines():
                continue
            if 'tf_run_meta' in line or 'u_native_usb/input_owner/queue_write_release_0' in line:
                # Apply only the strict legacy source-policy adapters in this
                # constructed preview. The sealed stage SDC is never changed.
                preview.extend(shared_constraints(line)['sdc'].splitlines())
            else:
                preview.append(line)
        installed_fixture = '\n'.join(preview) + '\n' + proposed
        self.assertTrue(validate_installed_constraints(ROOT, installed_fixture, result)['reviewed_group_lines_installed'])
        for label, sdc, message in (
                ('missing bound', proposed.replace('set_max_delay 10.000', 'set_max_delay 100.000', 1), 'missing or duplicated'),
                ('duplicate group', proposed + proposed.splitlines()[0] + '\n', 'missing or duplicated'),
                ('setup cut', proposed + 'set_false_path -to [get_pins {u_runtime_memory_guard/gray_meta*/D}]\n', 'masks reviewed Gray'),
                ('register setup cut', proposed + 'set_false_path -to [get_regs {u_runtime_memory_guard/gray_meta*}]\n', 'masks reviewed Gray'),
                ('source setup cut', proposed + 'set_false_path -from [get_pins {u_runtime_memory_guard/memory_gray*/Q}]\n', 'protected asynchronous control'),
                ('global setup cut', proposed + 'set_false_path\n', 'protected asynchronous control'),
                ('global hold cut', proposed + 'set_false_path -hold\n', 'protected asynchronous control'),
                ('combined hold setup cut', proposed + 'set_false_path -hold -setup -to [get_pins {u_runtime_memory_guard/gray_meta*/D}]\n', 'combined hold/setup'),
                ('whole clock cut', proposed + 'set_false_path -from [get_clocks {clk_50m}] -to [get_clocks {audio_76m8}]\n', 'whole-clock setup'),
                ('extra relaxed bound', proposed + 'set_max_delay 999.000 -to [get_pins {u_runtime_memory_guard/gray_meta*/D}]\n', 'unreviewed max delay'),
                ('global relaxed bound', proposed + 'set_max_delay 999.000\n', 'protected asynchronous control'),
                ('unsupported endpoint query', proposed + 'set_false_path -to [get_cells {u_runtime_memory_guard/gray_meta*}]\n', 'unsupported timing query'),
                ('asynchronous clock groups', proposed + 'set_clock_groups -asynchronous -group {clk_50m} -group {audio_76m8}\n', 'unreviewed SDC command'),
                ('exclusive clock groups', proposed + 'set_clock_groups -logically_exclusive -group {clk_50m} -group {audio_76m8}\n', 'unreviewed SDC command'),
                ('disabled timing', proposed + 'set_disable_timing [get_pins {u_runtime_memory_guard/gray_meta*/D}]\n', 'unreviewed SDC command'),
                ('multicycle relaxation', proposed + 'set_multicycle_path 10 -to [get_pins {u_runtime_memory_guard/gray_meta*/D}]\n', 'unreviewed SDC command'),
                ('external SDC source', proposed + 'source unreviewed.sdc\n', 'unreviewed SDC command'),
                ('unreviewed peripheral command', proposed + 'set_min_delay 999.000 -to [get_pins {u_runtime_memory_guard/gray_meta*/D}]\n', 'unreviewed peripheral SDC command'),
                ('Tcl evaluation in hold path', proposed + 'set_false_path -hold -to [eval cut]\n', 'unsupported timing query'),
                ('multiple Tcl commands', proposed + 'set_false_path -hold; set_false_path\n', 'unsupported Tcl evaluation'),
                ('async hold setup cut', proposed + 'set_false_path -to [get_pins {u_managed/media_stop/hold_compute*_s*/PRESET}]\n', 'protected asynchronous control'),
                ('USB drain removal cut', proposed + 'set_false_path -hold -to [get_pins {u_native_usb/input_owner/stopped_clock_queue_fence.drain_release*_s*/CLEAR}]\n', 'protected asynchronous control'),
                ('legacy selector', proposed + 'set_false_path -to [get_pins {tf_run_meta*/D}]\n', 'legacy TF run')):
            with self.subTest(case=label), self.assertRaisesRegex(ValueError, message) as e:
                validate_installed_constraints(ROOT, sdc, result)
            self.mutations.append(dict(case=label, rejected=True, error=str(e.exception)))


    def test_async_control_protection_is_independent_of_source_filters(self):
        result = audit_runtime_cdc(ROOT, self.text, self.clocks)
        proposed = runtime_cdc_bundle(ROOT)['sdc']
        hold = '[get_pins {u_managed/media_stop/hold_compute*/PRESET}]'
        drain = '[get_pins {u_native_usb/input_owner/stopped_clock_queue_fence.drain_release*/CLEAR}]'
        hold_regs = '[get_regs {u_managed/media_stop/hold_compute*}]'
        sources = (
            '[get_ports {reset_n}]', '[get_pins {unreviewed_source/Q}]',
            '[get_regs {unreviewed_source}]',
        )
        hazards = []
        for origin in sources:
            for flag in ('', ' -hold'):
                for target in (hold, drain, hold_regs):
                    hazards.append('set_false_path' + flag + ' -from ' + origin + ' -to ' + target)
            for target in (hold, drain, hold_regs):
                hazards.append('set_max_delay 999.000 -from ' + origin + ' -to ' + target)
        hazards += [
            'set_false_path -from ' + sources[0],
            'set_false_path -hold -from ' + sources[1],
            'set_max_delay 999.000 -from ' + sources[0],
        ]
        for line in hazards:
            with self.subTest(line=line), self.assertRaisesRegex(ValueError, 'protected asynchronous control') as e:
                validate_installed_constraints(ROOT, proposed + line + '\n', result)
            self.mutations.append(dict(case='async target protected independently of source: ' + line,
                                       rejected=True, error=str(e.exception)))
        # Compatibility controls for endpoints outside the reviewed inventory;
        # acceptance here makes no claim about those endpoints' CDC safety.
        for line in (
                'set_false_path -from [get_ports {reset_n}] -to [get_pins {unreviewed_receiver/D}]',
                'set_false_path -hold -from [get_regs {unreviewed_source}] -to [get_regs {unreviewed_receiver}]',
                'set_max_delay 999.000 -from [get_pins {unreviewed_source/Q}] -to [get_pins {unreviewed_receiver/D}]'):
            self.assertTrue(validate_installed_constraints(ROOT, proposed + line + '\n', result)['reviewed_group_lines_installed'])


if __name__ == '__main__':
    unittest.main()
