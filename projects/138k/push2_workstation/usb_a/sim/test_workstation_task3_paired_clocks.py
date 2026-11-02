#!/usr/bin/env python3
"""Explicit paired-clock policy against selected immutable synthesis evidence.

Set GW138K_TASK3_PAIRED_M/W to candidate directories. No preparation, EDA,
historical fallback, candidate writes or hardware operations are performed.
"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import os
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_runtime_clock_audit as runtime
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_synthesis_netlist import IDENTIFIER
from tools.workstation_task3_paired_clock_audit import (
    DRIVEN, RECEIVED, audit_paired_lcd_clock_boundary,
    audit_paired_worker_monitor_release, paired_clock_selection,
)
from tools.workstation_task3_root_reset_audit import audit_root_startup


class ExplicitRole(unittest.TestCase):
    def test_no_implicit_or_unknown_paired_role(self):
        for role in (None, '', 'm', 'worker', 0):
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, 'explicit role'):
                paired_clock_selection(Path('/nonexistent'), role)


@unittest.skipUnless(os.environ.get('GW138K_TASK3_PAIRED_M') and os.environ.get('GW138K_TASK3_PAIRED_W'),
    'set GW138K_TASK3_PAIRED_M/W to immutable prepared candidate directories with synthesis')
class ActualPairedClocks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.results, cls.mutations = {}, {}, []
        for role in ('M', 'W'):
            stage = Path(os.environ['GW138K_TASK3_PAIRED_' + role]) / 'workstation/Prj1'
            text = (stage / runtime.VG_RELATIVE).read_text()
            n = protocol_netlist(text, mapping='synthesis')
            cls.rows[role] = (stage, text, n)
            cls.results[role] = runtime.audit_runtime_clocks(ROOT, stage, text, paired_role=role)
        cls.worker_root = audit_root_startup(cls.rows['W'][2], stage=cls.rows['W'][0])

    @classmethod
    def tearDownClass(cls):
        if os.environ.get('GW138K_TASK3_PAIRED_CLOCK_TEST_EVIDENCE'):
            target = Path(os.environ['GW138K_TASK3_PAIRED_CLOCK_TEST_EVIDENCE'])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(dict(schema=1,
                vg_sha256={role: hashlib.sha256(row[1].encode()).hexdigest()
                           for role, row in cls.rows.items()},
                mutations=cls.mutations, rejected_mutations=len(cls.mutations),
                actual_root_state_machine_proven=True, root_state_bits=35,
                actual_monitor_state_and_input_assignments=256,
                eda_invoked=False, hardware_operated=False, sta_verified=False,
                whole_source_CDC_accepted=False), indent=2) + '\n')

    def reject(self, role, label, call, message=None):
        with self.subTest(role=role, mutation=label):
            context = self.assertRaisesRegex(ValueError, message) if message else self.assertRaises(ValueError)
            with context as error:
                call()
            self.mutations.append(dict(role=role, mutation=label, rejected=True,
                                       error=str(error.exception)))

    def mutated_cell(self, n, path, section, pin, value, call):
        original = deepcopy(n.cells[path])
        try:
            self.assertNotEqual(n.cells[path][section].get(pin), value)
            n.cells[path][section][pin] = value
            return call()
        finally:
            n.cells[path].clear()
            n.cells[path].update(original)

    def change_text_cell(self, role, path, *, port=None, parameter=None, value):
        _, text, n = self.rows[role]
        module = n.frames[n.scopes[path]]['kind']
        blocks = list(re.finditer(r'^module\s+(' + IDENTIFIER + r')\s*\(.*?^endmodule\b', text, re.M | re.S))
        matches = [m for m in blocks if m[1].removeprefix('\\') == module]
        self.assertEqual(len(matches), 1)
        match = matches[0]
        label = path.rsplit('/', 1)[-1]
        original = match[0]
        if port:
            cells = list(re.finditer(r'^[ \t]*(' + IDENTIFIER + r')[ \t]+(' + IDENTIFIER +
                r')[ \t]*\((.*?)^[ \t]*\);', original, re.M | re.S))
            selected = [c for c in cells if c[2].removeprefix('\\') == label]
            self.assertEqual(len(selected), 1)
            cell = selected[0]
            replacement, count = re.subn(r'(\.' + re.escape(port) + r'\()\s*[^()]*?(\))',
                lambda p: p[1] + value + p[2], cell[0])
            self.assertEqual(count, 1)
            changed = original[:cell.start()] + replacement + original[cell.end():]
        else:
            pattern = r'(defparam\s+(?:\\)?' + re.escape(label) + r'\s*\.' + re.escape(parameter) + r'\s*=\s*)[^;]+;'
            changed, count = re.subn(pattern, lambda p: p[1] + value + ';', original)
            self.assertEqual(count, 1)
        self.assertNotEqual(changed, original)
        return text[:match.start()] + changed + text[match.end():]

    def test_actual_role_clock_output_and_truthful_acceptance_scope(self):
        for role, result in self.results.items():
            with self.subTest(role=role):
                self.assertFalse(result['local_panel_enabled'])
                self.assertIs(result['hdmi_enabled'], role == 'M')
                self.assertEqual({k: len(v) for k, v in result['visible_clock_primitives'].items()},
                                 dict(PLL=6, CLKDIV=1, DCS=1) if role == 'M' else dict(PLL=4, CLKDIV=0, DCS=1))
                panel = result['local_panel']
                self.assertEqual(panel['programmable_pads'], 25)
                self.assertEqual(set(panel['driven_pads']), DRIVEN[role])
                self.assertEqual(set(panel['received_pads']), RECEIVED[role])
                self.assertEqual(len(panel['reserved_high_impedance_pads']), 11)
                self.assertTrue(panel['actual_role_source_verified'])
                self.assertFalse(panel['runtime_enable_boolean_function_verified'])
                self.assertFalse(panel['interboard_CDC_verified'])
                self.assertFalse(panel['physical_electrical_acceptance'])
                for key in ('whole_source_clock_topology_verified', 'physical_clock_tree_verified',
                            'sta_verified', 'routed_timing_verified', 'hardware_tested', 'release_ready', 'deployment_allowed'):
                    self.assertFalse(result[key], key)
        worker = self.results['W']
        self.assertEqual(worker['dcs']['select_registers'][1]['constant'], 0)
        self.assertTrue(worker['audio_outputs']['hp_din']['permanent_mute_source_binding_verified'])
        self.assertFalse(worker['audio_outputs']['hp_din']['serial_zero_invariant_verified'])
        for monitor in worker['monitor_groups'].values():
            proof = monitor['reset_release']['actual_paired_worker_startup_qualified_next_q']
            self.assertTrue(proof['full_root_state_machine_proven'])
            self.assertEqual(proof['root_proof']['actual_state_bits'], 35)
            self.assertTrue(proof['root_proof']['all_state_assignments_proven'])
            self.assertEqual(proof['arbitrary_state_and_input_assignments'], 256)

    def test_role_source_and_legacy_entry_are_fail_closed(self):
        for role, (stage, text, _) in self.rows.items():
            self.reject(role, 'opposite explicit role',
                lambda: paired_clock_selection(stage, 'W' if role == 'M' else 'M'))
            self.reject(role, 'paired inout cannot silently use default single-board policy',
                lambda: runtime.audit_runtime_clocks(ROOT, stage, text))
            top = stage / 'rtl/workstation/gw138k_push_workstation_top.v'
            actual = top.read_text()
            changed = actual.replace(".output_mute_i(1'b1)", ".output_mute_i(1'b0)", 1) if role == 'W' else actual + '\n// source drift\n'
            self.assertNotEqual(actual, changed)
            original_read = Path.read_text
            with patch.object(Path, 'read_text', lambda p, *a, **kw:
                              changed if p == top else original_read(p, *a, **kw)):
                self.reject(role, 'permanent mute/source inverse changed', lambda: paired_clock_selection(stage, role))

    def test_lcd_actual_pad_and_local_clock_mutations_fail(self):
        for role, (stage, _, n) in self.rows.items():
            base = self.results[role]['base_clock_audit']
            audit = lambda: audit_paired_lcd_clock_boundary(stage, n, role, base)
            for pad, direction in (('lcd_r', 'input'), ('lcd_ctp_int', 'output')):
                original = n.directions[runtime.TOP][pad]
                try:
                    n.directions[runtime.TOP][pad] = direction
                    self.reject(role, 'LCD direction ' + pad, audit, 'inout width/direction')
                finally:
                    n.directions[runtime.TOP][pad] = original
            original = n.ranges[runtime.TOP]['lcd_r']
            try:
                n.ranges[runtime.TOP]['lcd_r'] = (3, 0)
                self.reject(role, 'LCD width', audit, 'inout width/direction')
            finally:
                n.ranges[runtime.TOP]['lcd_r'] = original
            # Locate exact physical names from the positive actual inventory.
            evidence = self.results[role]['local_panel']['pad_primitives']
            received = evidence[next(iter(sorted(RECEIVED[role])))]['primitive']
            driven = evidence[next(iter(sorted(DRIVEN[role])))]['primitive']
            reserved = evidence['lcd_pclk']['primitive']
            pair_ff = next(p for p, c in n.cells.items() if p.startswith('u_task3_pair_link/') and
                           not p.startswith('u_task3_pair_link/config_cdc/') and c['kind'].startswith('DFF'))
            for label, path, pin, value in (
                ('RX pad drives', received, 'OEN', "1'b0"),
                ('reserved pad drives', reserved, 'OEN', "1'b0"),
                ('constant TX enable', driven, 'OEN', "1'b0"),
                ('constant TX data', driven, 'I', "1'b0"),
                ('independent TX enable', driven, 'OEN', 'different_enable'),
                ('pair clock becomes audio', pair_ff, 'CLK', 'audio_clk'),
                ('LCD pad becomes clock', pair_ff, 'CLK', 'lcd_g[0]' if role == 'M' else 'lcd_r[0]')):
                self.reject(role, label, lambda p=path, k=pin, v=value:
                    self.mutated_cell(n, p, 'ports', k, v, audit))

    def test_worker_qualified_release_state_mutations_fail(self):
        stage, _, n = self.rows['W']
        g = Graph(n)
        scope = 'u_managed/runtime/clocks/reference_48_monitor'
        startup = g.group(scope, 'startup_source', 2)
        pre = g.group(scope, 'source_reset_pre', 3)
        release = g.register(scope, 'source_reset_n')
        audit = lambda: audit_paired_worker_monitor_release(n, stage=stage,
            name='reference_48_monitor', source_clock='clk_12m288', root=self.worker_root)
        for label, path, section, pin, value in (
            ('startup bypass', startup[1], 'ports', 'D', 'control_reset_n'),
            ('startup unqualified pre0', pre[0], 'ports', 'D', "1'b1"),
            ('missing pre1 qualification', pre[1], 'ports', 'D', n.cells[pre[0]]['ports']['Q']),
            ('missing pre2 qualification', pre[2], 'ports', 'D', n.cells[pre[1]]['ports']['Q']),
            ('release bypass', release, 'ports', 'D', n.cells[pre[1]]['ports']['Q']),
            ('removed async root', pre[0], 'ports', 'CLEAR', "1'b0"),
            ('wrong positive clock', pre[0], 'ports', 'CLK', 'clk_50m'),
            ('release becomes posedge', release, 'ports', 'CLK', 'clk_12m288'),
            ('disabled startup', startup[0], 'ports', 'CE', "1'b0"),
            ('nonzero startup INIT', startup[0], 'parameters', 'INIT', "1'b1")):
            self.reject('W', label, lambda p=path, s=section, k=pin, v=value:
                self.mutated_cell(n, p, s, k, v, audit))
        root_ff = g.register('u_reset', 'started')
        self.reject('W', 'actual root startup changed', lambda:
            self.mutated_cell(n, root_ff, 'ports', 'D', "1'b0", lambda:
                audit_paired_worker_monitor_release(n, stage=stage,
                    name='reference_48_monitor', source_clock='clk_12m288')))

    def test_actual_clock_and_audio_source_mutations_fail(self):
        cases = (
            ('W', 'remote 44k authority bypass', runtime.SELECTOR, 'CLKSEL', None,
             '{GND,GND,rate_select[0],rate_select[0]}', 'local 44.1kHz clock-selection authority'),
            ('W', 'wrong audio reference', runtime.SELECTOR, 'CLKIN1', None,
             'clk_12m288_d', 'DCS reference wiring'),
            ('M', 'wrong PLL divider', 'u_audio_clock/g_hardware.u_pll/PLL_inst', None,
             'FBDIV_SEL', '2', 'feedback/input mode'),
            ('M', 'wrong PLL phase', 'u_audio_clock/g_hardware.u_pll/PLL_inst', None,
             'CLKOUT0_PE_FINE', '1', 'phase, feedback or output enable'),
            ('W', 'DAC data arbitrary bypass', 'hp_din_obuf', 'I', None,
             'pc_uart_rx_i_d', 'direct selected-clock serializer register'),
        )
        for role, label, path, port, parameter, value, message in cases:
            stage = self.rows[role][0]
            changed = self.change_text_cell(role, path, port=port, parameter=parameter, value=value)
            self.reject(role, label, lambda: runtime.audit_runtime_clocks(ROOT, stage, changed, paired_role=role), message)


if __name__ == '__main__':
    unittest.main()
