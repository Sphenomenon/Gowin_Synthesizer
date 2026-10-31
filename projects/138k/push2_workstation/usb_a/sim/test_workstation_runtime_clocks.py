#!/usr/bin/env python3
"""Actual runtime VG topology and fail-closed clock/provenance mutations.

GW138K_RUNTIME_CLOCK_STAGE and GW138K_RUNTIME_CLOCK_PROCESS select existing
synthesis evidence. This regression never prepares a project or invokes EDA.
"""

from pathlib import Path
from unittest.mock import patch
import copy
import json
import os
import re
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_runtime_clock_audit import (
    SELECTOR, SERIALIZER, VG_RELATIVE, audit_runtime_clocks, file_sha,
    prepared_local_panel_enabled, run_audit, verify_synthesis_identity,
)
from tools.workstation_synthesis_netlist import IDENTIFIER, SynthesisNetlist
from tools.workstation_profile import PROFILE_REGISTRY
from tools.workstation_board_peripherals import LCD_SDC


class RuntimeProvenance(unittest.TestCase):
    def test_registered_profile_clock_selection_and_invalid_identity(self):
        with tempfile.TemporaryDirectory(prefix='runtime-clock-profile-') as directory:
            stage = Path(directory) / 'candidate/workstation/Prj1'
            stage.mkdir(parents=True)
            manifest = stage.parents[1] / 'workstation_profile.json'
            self.assertTrue(prepared_local_panel_enabled(stage))
            for name, spec in PROFILE_REGISTRY.items():
                good = dict(profile=name, configuration=spec['configuration'],
                            profile_source=spec['config'], profile_sha256='a' * 64)
                manifest.write_text(json.dumps(good))
                with self.subTest(profile=name):
                    self.assertIs(prepared_local_panel_enabled(stage),
                                  spec.get('local_panel_enabled', True))
                mutations = [None, [], {}, dict(good, profile=None),
                             dict(good, profile='unregistered-workstation-profile'),
                             dict(good, configuration={}),
                             dict(good, profile_source='wrong-profile.json')]
                mutations.extend(dict(good, profile_sha256=value)
                                 for value in (None, 64, '', 'a' * 63, 'A' * 64))
                for bad in mutations:
                    manifest.write_text(json.dumps(bad))
                    with self.subTest(profile=name, bad=bad), self.assertRaises(ValueError):
                        prepared_local_panel_enabled(stage)
            manifest.write_text('{invalid JSON')
            with self.assertRaises(ValueError):
                prepared_local_panel_enabled(stage)

    def test_missing_changed_or_incomplete_synthesis_sources_fail(self):
        with tempfile.TemporaryDirectory(prefix='runtime-clock-seal-') as directory:
            stage = Path(directory) / 'candidate/workstation/Prj1'
            stage.mkdir(parents=True)
            (stage / 'input.sv').write_text('sealed source\n')
            (stage / 'second.sv').write_text('second sealed source\n')
            vg = stage / VG_RELATIVE
            vg.parent.mkdir(parents=True)
            vg.write_text('sealed netlist\n')
            evidence = stage / 'process.json'
            good = dict(cwd=str(stage), completed=True, exit_code=0, inputs_unchanged=True,
                        candidate_identity='runtime-fixture-candidate', stage='synthesis_only',
                        input_sha256={p: file_sha(stage / p) for p in ('input.sv', 'second.sv')},
                        output_sha256={VG_RELATIVE: file_sha(vg)})
            profile_path = stage.parents[1] / 'workstation_profile.json'
            profile = dict(candidate_identity=good['candidate_identity'],
                           staged_input_sha256=good['input_sha256'])
            profile_path.write_text(json.dumps(profile))
            evidence.write_text(json.dumps(good))
            self.assertEqual(verify_synthesis_identity(stage, evidence)['full_staged_input_count'], 2)
            for field, value, message in (
                    ('completed', False, 'completion/source seal'),
                    ('exit_code', 1, 'completion/source seal'),
                    ('inputs_unchanged', False, 'completion/source seal'),
                    ('cwd', str(stage / 'wrong'), 'project identity'),
                    ('input_sha256', {}, 'input identity is empty'),
                    ('input_sha256', {'../outside': '0' * 64}, 'closure differs'),
                    ('output_sha256', {VG_RELATIVE: '0' * 64}, 'VG output identity'),
                    ('candidate_identity', 'different-candidate', 'candidate identity differs'),
                    ('input_sha256', {'input.sv': good['input_sha256']['input.sv']}, 'closure differs'),
                    ('input_sha256', {**good['input_sha256'], 'second.sv': '0' * 64}, 'closure differs')):
                bad = copy.deepcopy(good)
                bad[field] = value
                evidence.write_text(json.dumps(bad))
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                    verify_synthesis_identity(stage, evidence)
            evidence.write_text(json.dumps(good))
            (stage / 'input.sv').write_text('changed source\n')
            with self.assertRaisesRegex(ValueError, 'staged input changed'):
                verify_synthesis_identity(stage, evidence)
            (stage / 'input.sv').unlink()
            with self.assertRaises(FileNotFoundError):
                verify_synthesis_identity(stage, evidence)
            (stage / 'input.sv').write_text('sealed source\n')
            profile_path.write_text(json.dumps({**profile, 'candidate_identity': 'wrong-prepared-candidate'}))
            with self.assertRaisesRegex(ValueError, 'candidate identity differs'):
                verify_synthesis_identity(stage, evidence)
            outside = {**good, 'input_sha256': {'../outside': '0' * 64}}
            profile_path.write_text(json.dumps({**profile, 'staged_input_sha256': outside['input_sha256']}))
            evidence.write_text(json.dumps(outside))
            with self.assertRaisesRegex(ValueError, 'invalid staged input path'):
                verify_synthesis_identity(stage, evidence)
            evidence.write_text(json.dumps(good))
            profile_path.unlink()
            with self.assertRaises(FileNotFoundError):
                verify_synthesis_identity(stage, evidence)


class ActualRuntimeClocks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get('GW138K_RUNTIME_CLOCK_STAGE') or not os.environ.get('GW138K_RUNTIME_CLOCK_PROCESS'):
            raise unittest.SkipTest('select existing runtime VG/process with GW138K_RUNTIME_CLOCK_STAGE/PROCESS; no EDA fallback')
        cls.stage = Path(os.environ['GW138K_RUNTIME_CLOCK_STAGE'])
        cls.process = Path(os.environ['GW138K_RUNTIME_CLOCK_PROCESS'])
        cls.text = (cls.stage / VG_RELATIVE).read_text()
        cls.sdc_path = cls.stage / 'constraints/custom_138k.sdc'
        cls.sdc = cls.sdc_path.read_text()
        cls.netlist = SynthesisNetlist(cls.text, 'workstation_custom_138k_top')
        cls.panel_off = not prepared_local_panel_enabled(cls.stage)
        cls.mutation_results = []

    @classmethod
    def tearDownClass(cls):
        if os.environ.get('GW138K_RUNTIME_CLOCK_TEST_EVIDENCE'):
            p = Path(os.environ['GW138K_RUNTIME_CLOCK_TEST_EVIDENCE'])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(dict(schema=1, vg_sha256=file_sha(cls.stage / VG_RELATIVE),
                mutations=cls.mutation_results, mutation_count=len(cls.mutation_results),
                hardware_operated=False, eda_invoked=False, sta_verified=False,
                dynamic_dcs_behavior_verified=False), indent=2) + '\n')

    def change_cell(self, path, *, port=None, parameter=None, value=None, append=''):
        scope = self.netlist.scopes[path]
        module = self.netlist.frames[scope]['kind']
        blocks = list(re.finditer(r'^module\s+(' + IDENTIFIER + r')\s*\(.*?^endmodule\b', self.text, re.M | re.S))
        selected = [m for m in blocks if m[1].removeprefix('\\') == module]
        self.assertEqual(len(selected), 1)
        m = selected[0]
        original = m[0]
        label = path.rsplit('/', 1)[-1]
        changed = original
        if port:
            instances = list(re.finditer(r'^[ \t]*(' + IDENTIFIER + r')[ \t]+(' + IDENTIFIER +
                r')[ \t]*\((.*?)^[ \t]*\);', original, re.M | re.S))
            cells = [c for c in instances if c[2].removeprefix('\\') == label]
            self.assertEqual(len(cells), 1)
            c = cells[0]
            replacement, count = re.subn(r'(\.' + re.escape(port) + r'\()\s*[^()]*?(\))',
                                          lambda p: p[1] + value + p[2], c[0])
            self.assertEqual(count, 1)
            changed = original[:c.start()] + replacement + original[c.end():]
        elif parameter:
            pattern = r'(defparam\s+(?:\\)?' + re.escape(label) + r'\s*\.' + re.escape(parameter) + r'\s*=\s*)[^;]+;'
            changed, count = re.subn(pattern, lambda p: p[1] + value + ';', original)
            self.assertEqual(count, 1)
        if append:
            changed = changed.removesuffix('endmodule') + append + '\nendmodule'
        self.assertNotEqual(changed, original)
        return self.text[:m.start()] + changed + self.text[m.end():]

    def reject(self, label, text, message):
        with self.subTest(mutation=label), self.assertRaisesRegex(ValueError, message) as error:
            audit_runtime_clocks(ROOT, self.stage, text)
        self.mutation_results.append(dict(case=label, rejected=True, error=str(error.exception)))

    def test_actual_source_topology_and_flags(self):
        result = run_audit(ROOT, self.stage, self.process)
        if result['local_panel_enabled']:
            self.assertEqual(len(result['base_clock_audit']['clocks']), 14)
            self.assertNotIn('base_13_clock_audit', result)
            self.assertEqual({k: len(v) for k, v in result['visible_clock_primitives'].items()},
                             dict(PLL=7, CLKDIV=1, DCS=1))
            self.assertEqual(result['declaration_scope']['clock_declarations_checked'], 17)
            self.assertIn('lcd_pixel31m5', result['base_clock_audit']['clocks'])
            self.assertTrue(result['local_panel']['hierarchy_present'])
        else:
            self.assertNotIn('base_13_clock_audit', result)
            self.assertEqual(len(result['base_clock_audit']['clocks']), 13)
            self.assertEqual({k: len(v) for k, v in result['visible_clock_primitives'].items()},
                             dict(PLL=6, CLKDIV=1, DCS=1))
            self.assertEqual(result['declaration_scope']['clock_declarations_checked'], 16)
            self.assertNotIn('lcd_pixel31m5', result['base_clock_audit']['clocks'])
            self.assertNotIn('u_lcd/u_pll/PLL_inst', result['visible_clock_primitives']['PLL'])
            self.assertFalse(result['local_panel']['hierarchy_present'])
            self.assertEqual(len(result['local_panel']['static_output_bits']), 21)
        self.assertTrue(result['runtime_audio_topology_verified'])
        self.assertTrue(result['source_seal_before_and_after'])
        self.assertFalse(result['base_clock_audit']['source_netlist_verified'])
        self.assertEqual(result['base_clock_audit']['deferred_opaque_ip_targets'],
                         ['u_memory/u_ddr3/gw3_top/u_ddr_phy_top/fclkdiv/CLKOUT'])
        self.assertGreater(len(result['serializer_registers']), 300)
        self.assertTrue(all(p['clock'] == 'clk_50m' for p in result['dcs']['select_registers']))
        for field in ('whole_source_clock_topology_verified', 'opaque_ddr_clock_verified',
                      'physical_clock_tree_verified', 'sta_verified', 'routed_timing_verified',
                      'constraints_complete', 'dynamic_dcs_behavior_verified', 'hardware_tested',
                      'release_ready', 'deployment_allowed'):
            self.assertFalse(result[field], field)

    def test_declaration_mutations_are_rejected(self):
        variants = [
            ('old_clock_period', self.sdc.replace('-period 20.000000 ', '-period 21.000000 ', 1), 'selected base-clock SDC prefix'),
            ('new_reference_period', self.sdc.replace('59.051398337', '60.000000000'), 'runtime clock declarations'),
            ('selected44_lost_add', self.sdc.replace('-divide_by 1 -add ', '-divide_by 1 '), 'runtime clock declarations'),
            ('selected44_wrong_master', self.sdc.replace('-master_clock dac_ref16m9344 ', '-master_clock dac_ref12m288 '), 'runtime clock declarations'),
            ('unexpected_clock', self.sdc + 'create_clock -name hidden -period 100 [get_ports {clk_50m}]\n', 'runtime clock declarations'),
            ('missing_mode_exclusion', self.sdc.replace('set_false_path -from [get_clocks {selected44}] -to [get_clocks {selected48}]\n', ''), 'mode exclusion'),
        ]
        if self.panel_off:
            variants.append(('retired_LCD_CDC_reintroduced', self.sdc + LCD_SDC, 'local-panel constraint remains'))
        original_read = Path.read_text
        for label, changed, message in variants:
            self.assertNotEqual(changed, self.sdc)
            with patch.object(Path, 'read_text', lambda path, *a, **kw:
                              changed if path == self.sdc_path else original_read(path, *a, **kw)):
                self.reject(label, self.text, message)

    def test_netlist_mutations_are_rejected(self):
        variants = [
            ('DCS_rising_mode', SELECTOR, dict(parameter='DCS_MODE', value='"RISING"'), 'DCS mode'),
            ('DCS_force', SELECTOR, dict(port='SELFORCE', value='VCC'), 'constant zero'),
            ('DCS_reference_swap', SELECTOR, dict(port='CLKIN0', value='clk_16m9344_d'), 'reference wiring'),
            ('DCS_unused_clock', SELECTOR, dict(port='CLKIN2', value='clk_12m288_d'), 'constant zero'),
            ('DCS_select_tie', SELECTOR, dict(port='CLKSEL', value='{GND,GND,rate_select[1],GND}'), 'direct unique register'),
            ('DCS_select_upper_clock', SELECTOR, dict(port='CLKSEL', value='{clk_12m288_d,GND,rate_select[1:0]}'), 'upper bits'),
            ('select_register_clock', 'u_managed/runtime/clocks/transaction/clock_select_o_0_s1', dict(port='CLK', value='wrong_clock'), '50MHz clock'),
            ('serializer_clock', SERIALIZER + 'bck_o_s0', dict(port='CLK', value='wrong_clock'), 'serializer consumer clock'),
            ('selected_monitor_clock', 'u_managed/runtime/clocks/selected_monitor/source_binary_0_s0', dict(port='CLK', value='wrong_clock'), 'monitor source/control clock'),
            ('MCLK_bypass', 'dac_mclk_obuf', dict(port='I', value='clk_12m288_d'), 'directly driven by DCS'),
            ('I2S_output_swap', 'hp_bck_obuf', dict(port='I', value='hp_ws_d'), 'direct selected-clock serializer'),
            ('audio_PLL_ratio', 'u_audio_clock/g_hardware.u_pll/PLL_inst', dict(parameter='MDIV_SEL', value='25'), 'PLL/divider frequency'),
            ('audio_PLL_dynamic', 'u_audio_clock/g_hardware.u_pll/PLL_inst', dict(parameter='DYN_MDIV_SEL', value='"TRUE"'), 'dynamic PLL divider'),
            ('pixel_divider', 'u_video/u_clock/g_hardware.u_pll/u_pixel_div', dict(parameter='DIV_MODE', value='"4"'), 'pixel divider waveform'),
            ('extra_DCS', SELECTOR, dict(append='\nDCS extra_dcs (\n.CLKOUT(unused),.CLKIN0(GND),.CLKIN1(GND),.CLKIN2(GND),.CLKIN3(GND),.CLKSEL({GND,GND,GND,GND}),.SELFORCE(GND)\n);'), 'single DCS inventory'),
        ]
        for label, path, change, message in variants:
            self.reject(label, self.change_cell(path, **change), message)
        self.reject('DDR_PLL_wrong_instance', self.text.replace('u_pll_0', 'u_pll_changed'),
                    'clock target not resolved')
        self.reject('reference_lost_input', self.text.replace('input clk_16m9344;',
                    'wire clk_16m9344;', 1), 'primary clock top input inventory')
        if self.panel_off:
            for port in ('lcd_bl', 'lcd_pclk', 'lcd_r[0]'):
                buffers = [path for path, cell in self.netlist.cells.items()
                           if cell['kind'] == 'OBUF' and self.netlist.pin(path, 'O') == port]
                self.assertEqual(len(buffers), 1)
                self.reject('disabled_panel_pin_' + port, self.change_cell(buffers[0], port='I', value='VCC'),
                            'local-panel output is not static low')
            self.reject('retired_LCD_owner_reintroduced', self.change_cell(buffers[0],
                append='\nPLL u_lcd (\n.CLKOUT0(unused_lcd_clock)\n);'), 'local-panel hierarchy remains')


if __name__ == '__main__':
    unittest.main()
