#!/usr/bin/env python3
"""Actual-source mutations and a declared synthetic netlist fixture, not STA."""

from pathlib import Path
import copy
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_usb2_owner_reset import (
    SDC, SELECTORS, SOURCE_FILES, STEM, PROFILES, audit_source_text,
    audit_reset_structure, source_bundle, validate_profile, validate_installation, OwnerResetNetlist, sha,
)
from tools.workstation_runtime_pcm_cdc import PcmNetlist, Graph, TOP
from tools.workstation_runtime_shared_cdc import audit_shared_constraints


def fixture():
    """Explicit expected logical 3-stage/23-consumer topology; no real VG claim."""
    rows = ['module ' + TOP + ' (clk_50m, usb_clk, audio_clk);',
            'input clk_50m;', 'input usb_clk;', 'input audio_clk;']

    def cell(kind, name, ports, init=None):
        label = '\\' + name + ' '
        rows.extend([kind + ' ' + label + '(',
                     ',\n'.join('.' + pin + '(' + net + ')' for pin, net in ports.items()), ');'])
        if init:
            rows.append('defparam ' + label + '.INIT = ' + init + ';')

    def ff(name, q, clock, clear="1'b0", data="1'b0"):
        cell('DFFCE', name + '_s0', dict(Q=q, D=data, CLK=clock, CLEAR=clear, CE="1'b1"), "1'b0")

    ff('u_reset/started', 'raw_reset', 'clk_50m')
    ff('u_runtime_memory_guard/started_o', 'guard_started', 'clk_50m')
    ff('usb_release_3', 'usb_reset', 'usb_clk')
    ff('u_native_usb/cpu_release_q_1', 'cpu_reset', 'usb_clk')
    cell('LUT3', 'qualified', dict(I0='raw_reset', I1='guard_started', I2='usb_reset', F='qualified_clear'), "8'h7f")
    for i in range(3):
        ff(STEM + '_' + str(i), 'q' + str(i), 'audio_clk', 'qualified_clear', "1'b1" if i == 0 else 'q' + str(i-1))
    cell('INV', 'final_invert', dict(I='q2', O='functional_clear'))
    cell('LUT2', 'cpu_qualified', dict(I0='q2', I1='cpu_reset', F='release_clear'), "4'h7")
    for i in range(12):
        ff('u_native_usb/input_owner/feedback_divider_' + str(i), 'counter' + str(i), 'audio_clk', 'functional_clear')
    for stem, count, clock in [('event_release', 3, 'usb_clk'), ('audio_release', 2, 'audio_clk'),
                               ('feedback/source_release', 3, 'audio_clk'), ('feedback/destination_release', 3, 'usb_clk')]:
        for i in range(count):
            name = 'u_native_usb/input_owner/' + stem + '_' + str(i)
            ff(name, 'sink' + str(len(rows)), clock, 'release_clear')
    rows.append('endmodule')
    return '\n'.join(rows) + '\n'


class ActualSource(unittest.TestCase):
    def setUp(self):
        self.texts = [(ROOT / p).read_text() for p in SOURCE_FILES]

    def test_actual_source_contract_and_exact_runtime_installation(self):
        result = source_bundle(ROOT)
        self.assertEqual(result['source_contract']['declaration_initial_value'], None)
        self.assertEqual(result['source_contract']['release_sequence'], ['001', '011', '111'])
        self.assertFalse(result['full_reset_accepted'])
        # Accepted source-selection regressions separately guard the default.
        from tools.workstation_runtime_profile import constraints
        installed = constraints(ROOT, dict(sdc=''))
        self.assertEqual(installed['sdc'].splitlines().count(SDC.strip()), 1)
        self.assertEqual(installed['usb2_owner_reset']['selectors'], list(SELECTORS))
        self.assertNotIn(STEM, installed['shared_sdc'])
        validate_installation(ROOT, installed['usb2_owner_reset'], installed['sdc'])
        for metadata, sdc in [(None, installed['sdc']),
                              (installed['usb2_owner_reset'], ''),
                              (installed['usb2_owner_reset'], SDC + SDC)]:
            with self.subTest(metadata=metadata is None, sdc=sdc), self.assertRaises(ValueError):
                validate_installation(ROOT, metadata, sdc)

    def test_actual_source_mutations_fail(self):
        changes = [(0, 'release_q[2];', 'release_q[0];'),
                   (0, 'posedge clk_audio or negedge qualified_n', 'posedge clk_ref or negedge qualified_n'),
                   (0, 'posedge clk_audio or negedge qualified_n', 'posedge clk_audio'),
                   (0, 'release_q[1:0]', 'release_q[0:1]'),
                   (0, '.audio_reset_n(owner_audio_reset_n)', '.audio_reset_n(audio_reset_n)'),
                   (0, '? owner_audio_reset_n :', '? audio_reset_n :'),
                   (0, 'AUDIO_OWNER_RESET_SYNC = 0', 'AUDIO_OWNER_RESET_SYNC = 1'),
                   (1, '.AUDIO_OWNER_RESET_SYNC(1)', '.AUDIO_OWNER_RESET_SYNC(0)'),
                   (1, 'wire runtime_reset_n=reset_n && memory_guard_started;', 'wire runtime_reset_n=audio_reset_n;'),
                   (2, 'reset_n && audio_reset_n', 'reset_n || audio_reset_n')]
        for index, before, after in changes:
            with self.subTest(before=before):
                texts = self.texts.copy()
                self.assertEqual(texts[index].count(before), 1)
                texts[index] = texts[index].replace(before, after)
                with self.assertRaises(ValueError):
                    audit_source_text(*texts)

    def test_standalone_profile_scope_is_explicit(self):
        for profile, suffix in zip(PROFILES, ('no_cnn', 'r00')):
            source = 'boards/custom_138k/workstation_profile_' + suffix + '_v1.json'
            prepared = dict(schema=1, profile=profile, profile_source=source, profile_sha256=sha(ROOT / source),
                            configuration=json.loads((ROOT / source).read_text())['configuration'])
            validate_profile(ROOT, prepared, profile)
            with self.assertRaisesRegex(ValueError, 'configuration/source changed'):
                validate_profile(ROOT, dict(prepared, profile_sha256='a'*64), profile)
            with self.assertRaisesRegex(ValueError, 'explicit prepared profile'):
                validate_profile(ROOT, prepared, 'auto')
            with self.assertRaisesRegex(ValueError, 'explicit prepared profile'):
                validate_profile(ROOT, prepared, PROFILES[1] if profile == PROFILES[0] else PROFILES[0])
        with self.assertRaisesRegex(ValueError, 'explicit runtime-no-cnn'):
            audit_shared_constraints(ROOT, Path('/unused'), '', usb2_owner_reset=True)
        with patch('tools.workstation_runtime_shared_cdc.audit_shared_cdc', return_value={'constraints':157}) as original:
            self.assertEqual(audit_shared_constraints(ROOT, Path('/unused'), 'old VG')['constraints'], 157)
            original.assert_called_once()


class DeclaredFixture(unittest.TestCase):
    def setUp(self):
        self.n = PcmNetlist(fixture(), TOP)
        self.g = Graph(self.n)

    def check(self, sdc=SDC):
        return audit_reset_structure(self.n, Graph(self.n), sdc)

    def test_positive_declared_fixture_has_no_physical_acceptance(self):
        result = self.check()
        self.assertEqual(len(result['stages']), 3)
        self.assertEqual(len(result['complete_Q_fanout'][2]['endpoints']), 23)
        self.assertEqual(sum(len(x) for x in result['sdc']['resolved_pin_selectors'].values()), 3)
        boundary = result['timing_boundaries']
        raw = boundary['raw_to_chain_clear']
        functional = boundary['final_q_to_functional_clear']
        self.assertFalse(raw['fixed_release_phase'])
        self.assertEqual(len(raw['resolved_pins']), 3)
        self.assertEqual(raw['exception_checks'], ['setup', 'hold', 'recovery', 'removal'])
        self.assertEqual(len(boundary['chain_q_to_next_d']['resolved_paths']), 2)
        self.assertEqual(functional['sta_policy'], 'retain_timed_recovery_and_removal')
        self.assertEqual(len(functional['resolved_pins']), 12)
        self.assertTrue(set(functional['resolved_pins']) <= set(result['sdc']['protected_timed_pins']))
        self.assertEqual(len(boundary['final_q_to_existing_release_chains']['resolved_pins']), 11)
        self.assertFalse(raw['physical_reset_accepted'])
        self.assertFalse(functional['new_false_path_allowed'])
        self.assertFalse(functional['physical_reset_accepted'])
        for gate in ('full_reset_accepted', 'recording_cdc_accepted', 'shared_cdc_accepted',
                     'routed_recovery_removal_verified', 'deployment_allowed'):
            self.assertFalse(result[gate])

    def test_omitted_INIT_is_reported_as_primitive_default(self):
        for i in range(3):
            self.n.cells[STEM + '_' + str(i) + '_s0']['parameters'].pop('INIT')
        result = self.check()
        self.assertEqual({s['init_source'] for s in result['stages']}, {'Gowin_DFFCE_primitive_default'})

    def test_exact_escaped_vector_formal_adapter(self):
        text = r'''module workstation_custom_138k_top (audio_clk);
input audio_clk;
wrapper u_native_usb (.audio_clk(audio_clk)
);
endmodule
module wrapper (audio_clk);
input audio_clk;
wire [2:0] \audio_owner_reset.release_q ;
DFFCE \audio_owner_reset.release_q_2_s0  (
.Q(\audio_owner_reset.release_q [2]), .D(1'b1), .CE(1'b1), .CLK(audio_clk), .CLEAR(1'b0)
);
owner input_owner (.audio_clk(audio_clk),
.\audio_owner_reset.release_q (\audio_owner_reset.release_q [2])
);
endmodule
module owner (audio_clk, \audio_owner_reset.release_q );
input audio_clk;
input [2:2] \audio_owner_reset.release_q ;
INV invert (.I(\audio_owner_reset.release_q [2]), .O(clear)
);
DFFCE counter_s0 (.Q(q), .D(1'b0), .CE(1'b1), .CLK(audio_clk), .CLEAR(clear)
);
endmodule
'''
        n = OwnerResetNetlist(text, TOP)
        self.assertEqual(n.pin('u_native_usb/input_owner/invert', 'I'),
                         n.pin('u_native_usb/audio_owner_reset.release_q_2_s0', 'Q'))
        with self.assertRaisesRegex(ValueError, 'formal range/binding changed'):
            Graph(OwnerResetNetlist(text.replace('[2:2]', '[1:1]'), TOP))

    def test_structure_mutations_fail_after_rebuilding_graph(self):
        p = STEM + '_1_s0'
        c = 'u_native_usb/input_owner/feedback_divider_0_s0'
        changes = [(p, 'ports', 'D', "1'b0"), (p, 'ports', 'CLK', 'usb_clk'),
                   (p, 'ports', 'CE', 'q2'), (p, 'ports', 'CLEAR', 'functional_clear'),
                   (p, 'parameters', 'INIT', "1'b1"),
                   ('qualified', 'parameters', 'INIT', "8'h80"),
                   ('qualified', 'ports', 'I0', 'cpu_reset'),
                   (c, 'ports', 'CE', 'q0'), (c, 'ports', 'CLEAR', 'q1'),
                   (c, 'ports', 'D', 'q2'),
                   ('cpu_qualified', 'parameters', 'INIT', "4'h1")]
        for name, section, key, value in changes:
            with self.subTest(name=name, key=key):
                old = self.n.cells[name][section][key]
                self.n.cells[name][section][key] = value
                try:
                    with self.assertRaises(ValueError):
                        self.check()
                finally:
                    self.n.cells[name][section][key] = old

    def test_new_chain_cannot_export_or_gain_extra_stage(self):
        self.n.directions[TOP]['q0'] = 'output'
        with self.assertRaisesRegex(ValueError, 'exports to top output'):
            self.check()
        del self.n.directions[TOP]['q0']
        name = STEM + '_3_s0'
        self.n.cells[name] = copy.deepcopy(self.n.cells[STEM + '_2_s0'])
        self.n.cells[name]['ports']['Q'] = 'extra_q'
        self.n.scopes[name] = ''
        with self.assertRaisesRegex(ValueError, 'inventory changed'):
            self.check()

    def test_sdc_mutations_fail(self):
        extra = [
            'set_false_path -to [get_pins {u_native_usb/*/CLEAR}]',
            'set_false_path -to [get_pins {u_native_usb/input_owner/feedback_divider*/CLEAR}]',
            'set_false_path -hold -to [get_pins {' + STEM + '_1_s0/D}]',
            'set_max_delay 200 -to [get_regs {u_native_usb/input_owner/feedback_divider*}]',
            'set_false_path -from [get_regs {' + STEM + '_0*}]',
            'set_false_path -to [get_clocks {audio_76m8}]',
        ]
        bad = ['', SDC + SDC, SDC.replace(SELECTORS[1], 'missing/CLEAR'),
               SDC.replace(SELECTORS[0], 'u_native_usb/*/CLEAR')]
        for value in bad + [SDC + line + '\n' for line in extra]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.check(value)


if __name__ == '__main__':
    unittest.main()
