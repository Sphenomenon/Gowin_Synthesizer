#!/usr/bin/env python3
"""Structural resolution must never substitute naming compatibility for topology."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from workstation_serializer_startup_audit import logic_driver, inspect_grant_reset_inputs


class LogicResolverTests(unittest.TestCase):
    def fixture(self, suffix='pll_stop_d_s0'):
        name = 'phy/' + suffix
        cells = {name: ('LUT1', {'I0': 'stop2', 'F': 'gate'}),
                 'phy/stop2': ('DFFCE', {'D': 'stop1', 'Q': 'stop2'})}
        return cells, {(name, 'INIT'): "2'h1"}, name

    def test_legacy_and_new_names_require_same_structure(self):
        for suffix in ('pll_stop_s0', 'pll_stop_d_s0', 'unrelated_generated_name'):
            cells, parameters, name = self.fixture(suffix)
            self.assertEqual(logic_driver(cells, parameters, 'gate', 'LUT1', {'I0': 'stop2'}, 'phy', "2'h1"), name)

    def test_reject_polarity_even_with_historical_name(self):
        cells, parameters, name = self.fixture('pll_stop_s0')
        parameters[(name, 'INIT')] = "2'h2"
        with self.assertRaisesRegex(AssertionError, 'polarity'):
            logic_driver(cells, parameters, 'gate', 'LUT1', {'I0': 'stop2'}, 'phy', "2'h1")

    def test_reject_other_source_and_multiple_drivers(self):
        cells, parameters, name = self.fixture()
        for mode in ('wrong_input', 'second_driver'):
            changed = copy.deepcopy(cells)
            if mode == 'wrong_input':
                changed[name][1]['I0'] = 'bypass'
            else:
                changed['phy/second'] = ('INV', {'I': 'bypass', 'O': 'gate'})
            with self.assertRaises(AssertionError):
                logic_driver(changed, parameters, 'gate', 'LUT1', {'I0': 'stop2'}, 'phy', "2'h1")

    def test_reject_type_or_extra_input(self):
        cells, parameters, name = self.fixture()
        for kind, pins in [('INV', {'I': 'stop2', 'O': 'gate'}),
                           ('LUT1', {'I0': 'stop2', 'I1': 'unexpected', 'F': 'gate'})]:
            changed = copy.deepcopy(cells); changed[name] = (kind, pins)
            with self.assertRaises(AssertionError):
                logic_driver(changed, parameters, 'gate', 'LUT1', {'I0': 'stop2'}, 'phy', "2'h1")


class GrantResetTests(unittest.TestCase):
    def fixture(self, role='M'):
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root))
        from tools.workstation_custom_timing import RUNTIME_GRANT_RESET_INPUTS, RUNTIME_GRANT_CHAINS
        domains = {'audio_76m8': 'audio_clk', 'ddr_ui100': 'memory_clk',
                   'selected48/selected44': 'dac_mclk_d', 'usb_48m': 'usb_clk'}
        destinations = {prefix: domain for prefix, source, domain in RUNTIME_GRANT_CHAINS}
        prefixes = [prefix for prefix in RUNTIME_GRANT_RESET_INPUTS
                    if role == 'M' or not prefix.startswith('u_tf_audio/')]
        cells, lines = ['VCC power (.V(VCC));', 'GND ground (.G(GND));'], []
        for index, prefix in enumerate(prefixes):
            clock = domains[destinations[prefix]]
            cells.extend((f'DFFRE \\{prefix}_0_s0  (.D(grant{index}),.CLK({clock}),.CE(VCC),.RESET(level{index}),.Q(q{index}));',
                          f'DFFCE \\{prefix}_1_s0  (.D(q{index}),.CLK({clock}),.CE(VCC),.CLEAR(GND),.Q(done{index}));',
                          f'defparam \\{prefix}_0_s0 .INIT=1\'b0;', f'defparam \\{prefix}_1_s0 .INIT=1\'b0;'))
            lines.extend((f'set_false_path -to [get_pins {{{prefix}_0_s*/D}}]',
                          f'set_false_path -to [get_pins {{{prefix}_0_s*/RESET}}]',
                          f'set_max_delay 2.000 -from [get_pins {{{prefix}_0_s*/Q}}] -to [get_pins {{{prefix}_1_s*/D}}]'))
        return 'module workstation_custom_138k_top ();\n' + '\n'.join(cells) + '\nendmodule\n', '\n'.join(lines), prefixes

    def test_explicit_roles_keep_only_clocked_first_stage_reset_inputs(self):
        for role, count in (('M', 9), ('W', 6)):
            text, sdc, prefixes = self.fixture(role)
            proof = inspect_grant_reset_inputs(text, sdc, role)
            self.assertEqual(len(proof), count)
            self.assertTrue(all(row['synchronous_data_input'] and not row['stopped_clock_reset'] and
                                row['first_stage_fanout_only_second_D'] for row in proof))
            if role == 'W': self.assertFalse(any(row['first'].startswith('u_tf_audio/') for row in proof))

    def test_explicit_independent_m_requires_absent_tf_and_preserves_six_grants(self):
        text, sdc, prefixes = self.fixture('W')
        proof = inspect_grant_reset_inputs(text, sdc, 'M', tf_disabled_m_core=True)
        self.assertEqual(len(proof), 6)
        self.assertTrue(all(row['first_stage_fanout_only_second_D'] for row in proof))
        with self.assertRaisesRegex(AssertionError, 'grant receiver inventory'):
            inspect_grant_reset_inputs(text, sdc, 'M')
        with self.assertRaisesRegex(AssertionError, 'requires M role'):
            inspect_grant_reset_inputs(text, sdc, 'W', tf_disabled_m_core=True)
        with self.assertRaisesRegex(AssertionError, 'must be boolean'):
            inspect_grant_reset_inputs(text, sdc, 'M', tf_disabled_m_core=1)

    def test_independent_m_rejects_retained_tf_and_stale_tf_queries(self):
        full_text, full_sdc, _ = self.fixture('M')
        text, sdc, _ = self.fixture('W')
        with self.assertRaisesRegex(AssertionError, 'retains TF cells'):
            inspect_grant_reset_inputs(full_text, sdc, 'M', tf_disabled_m_core=True)
        with self.assertRaisesRegex(AssertionError, 'retains TF constraint queries'):
            inspect_grant_reset_inputs(text, full_sdc, 'M', tf_disabled_m_core=True)
        with self.assertRaisesRegex(AssertionError, 'later stage'):
            inspect_grant_reset_inputs(text, sdc + '\nset_false_path -to [get_pins '
                '{u_managed/startup_compute_1_s*/D}]', 'M', tf_disabled_m_core=True)

    def test_first_stage_cannot_feed_functional_logic(self):
        text, sdc, prefixes = self.fixture()
        text = text.replace('endmodule', 'LUT1 extra (.I0(q0),.F(escaped));\nendmodule')
        with self.assertRaisesRegex(AssertionError, 'functional fanout'):
            inspect_grant_reset_inputs(text, sdc, 'M')

    def test_first_stage_cannot_have_competing_driver_or_ambiguous_port(self):
        text, sdc, prefixes = self.fixture()
        changed = text.replace('endmodule', 'LUT1 competitor (.I0(other),.F(q0));\nendmodule')
        with self.assertRaisesRegex(AssertionError, 'competing driver'):
            inspect_grant_reset_inputs(changed, sdc, 'M')
        changed = text.replace('.D(grant0)', '.D(hidden),.D(grant0)', 1)
        with self.assertRaisesRegex(AssertionError, 'duplicate or unparsed port'):
            inspect_grant_reset_inputs(changed, sdc, 'M')
        changed = text.replace('module workstation_custom_138k_top ();',
                               'module workstation_custom_138k_top (q0);\noutput q0;')
        with self.assertRaisesRegex(AssertionError, 'output is exported'):
            inspect_grant_reset_inputs(changed, sdc, 'M')

    def test_primitive_clock_enable_init_and_second_stage_are_strict(self):
        text, sdc, prefixes = self.fixture()
        for original, changed in (('DFFRE \\u_managed/startup_compute_0_s0', 'DFFCE \\u_managed/startup_compute_0_s0'),
                                  ('.CLK(audio_clk)', '.CLK(memory_clk)'), ('.CE(VCC)', '.CE(GND)'),
                                  (".INIT=1'b0", ".INIT=1'b1"), ('.D(q0)', '.D(grant0)'),
                                  ('.CLEAR(GND)', '.CLEAR(level0)')):
            with self.subTest(mutation=changed), self.assertRaises((AssertionError, ValueError)):
                inspect_grant_reset_inputs(text.replace(original, changed, 1), sdc, 'M')

    def test_missing_duplicate_relaxed_and_later_stage_exceptions_fail(self):
        text, sdc, prefixes = self.fixture()
        for line in sdc.splitlines():
            for changed in (sdc.replace(line, ''), sdc + '\n' + line):
                with self.subTest(line=line), self.assertRaisesRegex(AssertionError, 'constraint'):
                    inspect_grant_reset_inputs(text, changed, 'M')
        for prefix in prefixes:
            for kind in ('get_pins', 'get_regs'):
                target = prefix + '_1_s*' + ('/D' if kind == 'get_pins' else '')
                for qualifier in ('', '-hold ', '-setup '):
                    changed = sdc + f'\nset_false_path {qualifier}-to [{kind} {{{target}}}]'
                    with self.subTest(target=target, qualifier=qualifier), self.assertRaisesRegex(AssertionError, 'later stage'):
                        inspect_grant_reset_inputs(text, changed, 'M')
        with self.assertRaisesRegex(AssertionError, 'constraint'):
            inspect_grant_reset_inputs(text, sdc.replace('2.000', '3.000'), 'M')


if __name__ == '__main__':
    unittest.main()
