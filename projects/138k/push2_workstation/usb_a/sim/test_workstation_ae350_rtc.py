#!/usr/bin/env python3
"""Independent RTC source/reset, minimum-period and exact output-net negatives."""
from pathlib import Path
from unittest.mock import patch
import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
from tools.workstation_ae350_rtc import (
    POLICY, SOURCE, SHARED_TOP, TOP, INSTANCE, SDC, CLOCK_ENTRY, SOURCE_BINDING,
    CPU_BINDING, source_contract, prepared, verify_prepared, audit_netlist, audit_synthesis_netlist, validate_constraints,
)
from tools.workstation_custom_clocks import clock_bundle
from tools.workstation_physical_pll_audit import rtc_gate


def cell(kind, name, ports):
    return kind + ' \\' + name + ' (\n' + ',\n'.join(' .' + p + '(' + v + ')' for p, v in ports) + '\n);\n'


def fixture(extra='', clock='clk_50m', rtc='rtc_tick', kind='DFFCE'):
    return ('module ' + TOP + ' (clk_50m);\ninput clk_50m;\nwire rtc_tick, q, GND, VCC;\n' +
            cell('VCC', 'vcc', [('V', 'VCC')]) +
            cell(kind, INSTANCE, [('Q', 'rtc_tick'), ('CLK', clock), ('D', 'q'),
                                  ('CLEAR', 'GND'), ('CE', 'VCC')]) +
            "defparam \\" + INSTANCE + " .INIT=1'b0;\n" +
            cell('LUT2', 'u_rtc/feedback', [('F', 'q'), ('I0', 'rtc_tick'), ('I1', 'GND')]) +
            cell('AE350_SOC', 'u_cpu/hard_macro', [('RTC_CLK', rtc)]) + extra + 'endmodule\n')


def copy_sources(root, stage):
    for relative in (SOURCE, SHARED_TOP):
        for base in (root, stage):
            path = base / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / relative).read_bytes())
    path = stage / 'constraints/custom_138k.sdc'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SDC)


class IndependentRTC(unittest.TestCase):
    def test_synthesis_wrapper_has_separate_scope_and_cannot_pass_physical_gate(self):
        def opaque(text):
            return text.replace('AE350_SOC', 'RiscV_AE350_SOC').replace(
                'u_cpu/hard_macro', 'u_cpu/u_RiscV_AE350_SOC').replace('.RTC_CLK(', '.rtc_tick(')
        text = opaque(fixture())
        result = audit_synthesis_netlist(text)
        self.assertEqual(result['visible_cpu_endpoint'], 'u_cpu/u_RiscV_AE350_SOC/rtc_tick')
        self.assertEqual(result['connectivity_scope'], 'opaque_synthesis_wrapper_input')
        self.assertIsNone(result['hard_macro'])
        self.assertFalse(result['hard_macro_input_connectivity_verified'])
        self.assertFalse(result['encrypted_internal_connectivity_verified'])
        self.assertTrue(result['direct_unique_driver_verified'])
        with self.assertRaisesRegex(ValueError, 'exactly one AE350 hard macro'):
            audit_netlist(text)
        with self.assertRaisesRegex(ValueError, 'opaque synthesis wrapper'):
            audit_synthesis_netlist(fixture())
        cases = [opaque(fixture(rtc='clk_50m')),
                 opaque(fixture(clock='core_clk')),
                 text.replace('.rtc_tick(rtc_tick)', '.OTHER(rtc_tick)'),
                 text.replace('.rtc_tick(rtc_tick)', '.rtc_tick({rtc_tick})'),
                 text.replace('u_cpu/u_RiscV_AE350_SOC', 'u_cpu/other'),
                 text.replace('RiscV_AE350_SOC', 'unknown'),
                 opaque(fixture(extra=cell('AE350_SOC', 'extra', [('RTC_CLK', 'rtc_tick')]))),
                 text.replace('endmodule', cell('AE350_SOC', 'extra', [('RTC_CLK', 'rtc_tick')])+'endmodule'),
                 opaque(fixture(extra=cell('LUT2','outside/driver',[('F','rtc_tick'),('I0','GND')]))),
                 opaque(fixture(extra=cell('LUT2','outside/consumer',[('I0','rtc_tick'),('F','q')]))),
                 text.replace('.rtc_tick(rtc_tick)', '.rtc_tick(rtc_tick),\n .rtc_tick(clk_50m)')]
        for changed in cases:
            with self.subTest(text=changed), self.assertRaises(ValueError):
                audit_synthesis_netlist(changed)

    def test_synthesis_vectors_cannot_hide_extra_rtc_consumers(self):
        base = fixture().replace('AE350_SOC', 'RiscV_AE350_SOC').replace(
            'u_cpu/hard_macro', 'u_cpu/u_RiscV_AE350_SOC').replace('.RTC_CLK(', '.rtc_tick(')
        for stem, selection in [('payload', 'payload[0]'), ('\\payload ', '\\payload [0]')]:
            child = ('module child ('+stem+');\ninput [1:0] '+stem+';\nwire out;\n'+
                     cell('LUT2','leaf',[('I0',selection),('F','out')])+'endmodule\n')
            for binding, hidden in [('{GND,GND}',False),('{GND,rtc_tick}',True)]:
                text=base.replace('endmodule',cell('child','outside',[(stem,binding)])+'endmodule',1)+child
                if hidden:
                    with self.assertRaisesRegex(ValueError,'unreviewed|non-scalar driver/consumer'):
                        audit_synthesis_netlist(text)
                else:
                    self.assertTrue(audit_synthesis_netlist(text)['direct_unique_driver_verified'])
        for vector in ('[1:0]', '[0:0]', '[0:1]'):
            text=base.replace('wire rtc_tick, q, GND, VCC;',
                              'wire q, GND, VCC;\nwire '+vector+' rtc_tick;')
            text=text.replace('endmodule', cell('LUT2','extra_driver',
                [('F','rtc_tick[0]'),('I0','GND')])+'endmodule')
            with self.subTest(vector=vector), self.assertRaisesRegex(ValueError,'same single scalar wire'):
                audit_synthesis_netlist(text)

    def test_source_reset_and_timing_bound_are_distinct_from_average_frequency(self):
        result = source_contract(ROOT)
        self.assertEqual(result['average_frequency_hz'], 32768)
        self.assertEqual(result['half_period_reference_cycles'], [762, 763])
        self.assertEqual(result['sta_minimum_period_ns'], 762 * 2 * 20)
        self.assertTrue(result['independent_of_cpu_apb_memory_ready'])
        self.assertTrue(result['average_is_not_sta_frequency'])
        self.assertFalse(result['sta_verified'])
        self.assertFalse(result['hardware_tested'])
        bundle = clock_bundle(ROOT)
        self.assertEqual(bundle['plan']['fabric_generated'], [CLOCK_ENTRY])
        self.assertTrue(bundle['sdc'].endswith(SDC))
        for key, value in (('average_frequency_hz', 32769), ('sta_divide_by', 1526),
                           ('pin', 'u_rtc/rtc_tick_s0/Q'), ('source', 'cpu_ram50')):
            plan = copy.deepcopy(bundle['plan']);plan['fabric_generated'][0][key] = value
            with self.subTest(key=key), patch('tools.workstation_custom_clocks.json.loads', return_value=plan):
                with self.assertRaisesRegex(ValueError, 'RTC timing-bound inventory'):
                    clock_bundle(ROOT)

    def test_prepared_source_composition_and_metadata_are_recomputed(self):
        with tempfile.TemporaryDirectory() as directory:
            root, stage = Path(directory) / 'root', Path(directory) / 'stage'
            copy_sources(root, stage)
            evidence = prepared(root, stage)
            self.assertEqual(verify_prepared(root, stage, evidence), evidence)
            for key, value in (('policy', 'other'), ('reset', 'cpu_reset_n'),
                               ('sta_verified', True), ('hardware_tested', True)):
                bad = dict(evidence, **{key: value})
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'metadata changed'):
                    verify_prepared(root, stage, bad)
            (stage / SOURCE).write_text((stage / SOURCE).read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'prepared RTC source differs'):
                verify_prepared(root, stage, evidence)
            copy_sources(root, stage)
            (stage / SHARED_TOP).write_text((stage / SHARED_TOP).read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'composition differs'):
                verify_prepared(root, stage, evidence)

    def test_source_reference_reset_or_native_cpu_binding_cannot_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root, stage = Path(directory) / 'root', Path(directory) / 'stage'
            for before, after in (('.reset_n(system_reset_n)', '.reset_n(cpu_reset_n)'),
                                  (SOURCE_BINDING, SOURCE_BINDING.replace('.clk_50m(clk_50m)', '.clk_50m(bus_clk)')),
                                  (CPU_BINDING, CPU_BINDING.replace('.RTC_CLK(rtc_clk)', '.RTC_CLK(clk_50m)')),
                                  ('wire system_reset_n=reset_n;', 'wire system_reset_n=cpu_reset_n;'),
                                  (SOURCE_BINDING, SOURCE_BINDING + '\n' + SOURCE_BINDING)):
                copy_sources(root, stage)
                p = root / SHARED_TOP;p.write_text(p.read_text().replace(before, after, 1))
                with self.subTest(after=after), self.assertRaisesRegex(ValueError, 'source/reference/reset'):
                    source_contract(root)
            copy_sources(root, stage)
            p = root / SOURCE;p.write_text(p.read_text().replace("26'd65536", "26'd65535"))
            with self.assertRaisesRegex(ValueError, 'source identity changed'):
                source_contract(root)

    def test_exact_minimum_period_target_is_required_without_overrides(self):
        self.assertEqual(validate_constraints('# comment\n' + SDC)['sta_divide_by'], 1524)
        for sdc in ('', SDC + SDC, SDC.replace('1524', '1525'),
                    SDC.replace('clk_50m', 'bus_clk'), SDC.replace('_s1/Q', '_s0/Q'),
                    SDC + SDC.replace('cpu_rtc_bound', 'hidden_rtc'),
                    SDC + SDC.replace('u_rtc/rtc_tick_s1/Q', 'other/Q'),
                    SDC + 'set x 0; ' + SDC.replace('cpu_rtc_bound', 'hidden'),
                    SDC + 'if {1} { ' + SDC.rstrip() + ' }\n',
                    SDC + 'remove_clock [get_clocks {cpu_rtc_bound}]\n',
                    SDC + 'remove_clock [all_clocks]\n', SDC + 'reset_timing\n'):
            with self.subTest(sdc=sdc), self.assertRaises(ValueError):
                validate_constraints(sdc)

    def test_only_unique_direct_cpu_clock_and_internal_feedback_are_allowed(self):
        result = audit_netlist(fixture())
        self.assertEqual(result['rtc_net_identity'], dict(scope='', name='rtc_tick'))
        self.assertEqual(len(result['direct_endpoints']), 3)
        self.assertTrue(result['direct_unique_driver_verified'])
        self.assertFalse(result['physical_timing_verified'])
        cases = [fixture(clock='other_clk'), fixture(rtc='clk_50m'), fixture(kind='DFF'),
                 fixture().replace('.CE(VCC)', ".CE(1'b0)"),
                 fixture().replace("INIT=1'b0", "INIT=1'b1"),
                 fixture().replace('.CLK(clk_50m),', ''),
                 fixture().replace('.CE(VCC)', '.OTHER(VCC)'),
                 fixture().replace('.Q(rtc_tick),', ''),
                 fixture(extra=cell('AE350_SOC', 'second', [('RTC_CLK', 'rtc_tick')])),
                 fixture(extra=cell('BUFG', 'buffer', [('I', 'rtc_tick'), ('O', 'buffered')]), rtc='buffered'),
                 fixture(extra=cell('DFFCE', 'external_clock', [('CLK', 'rtc_tick'), ('Q', 'unused')])),
                 fixture(extra=cell('LUT2', 'u_rtc/driver', [('F', 'rtc_tick'), ('I0', 'GND')])),
                 fixture(extra=cell('LUT2', 'outside/consumer', [('I0', 'rtc_tick'), ('F', 'unused')])),
                 fixture(extra=cell('LUT2', 'outside/driver', [('F', 'rtc_tick'), ('I0', 'GND')])),
                 fixture(extra=cell('LUT2', 'outside/expression', [('F', '{rtc_tick}'), ('I0', 'GND')])),
                 fixture(extra='assign rtc_tick = clk_50m;\n'),
                 fixture(extra='LUT2 single_line(.F(rtc_tick), .I0(GND));\n'),
                 fixture().replace('.RTC_CLK(rtc_tick)', '.RTC_CLK((rtc_tick))'),
                 fixture().replace('.RTC_CLK(rtc_tick)', '.RTC_CLK(clk_50m),\n .RTC_CLK(rtc_tick)'),
                 fixture().replace('AE350_SOC', 'NO_CPU'),
                 fixture().replace('(clk_50m);', '(clk_50m,rtc_tick);', 1)
                          .replace('wire rtc_tick,', 'output rtc_tick;\nwire unused,'),
                 fixture().replace('(clk_50m);', '(input clk_50m);', 1)]
        for text in cases:
            with self.subTest(text=text), self.assertRaises(ValueError):
                audit_netlist(text)

    def test_escaped_alias_and_scope_collision_cannot_hide_another_driver(self):
        escaped = fixture().replace('(rtc_tick)', '(\\rtc_tick )')
        self.assertEqual(audit_netlist(escaped)['rtc_net_identity']['name'], 'rtc_tick')
        extra = cell('LUT2', 'alias_driver', [('F', 'rtc_tick'), ('I0', 'GND')])
        with self.assertRaisesRegex(ValueError, 'unreviewed'):
            audit_netlist(escaped.replace('endmodule', extra + 'endmodule'))
        scoped = (fixture().replace('.RTC_CLK(rtc_tick)', '.RTC_CLK(\\child/x )')
                  .replace('endmodule', cell('child', 'child', []) + 'endmodule', 1) +
                  'module child ();\nwire x;\n' +
                  cell('LUT2', 'producer', [('F', 'x'), ('I0', 'GND')]) + 'endmodule\n')
        with self.assertRaisesRegex(ValueError, 'not directly driven'):
            audit_netlist(scoped)

    def test_physical_subgate_requires_new_prepared_source_and_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            root, stage = Path(directory) / 'root', Path(directory) / 'stage'
            copy_sources(root, stage)
            parent = dict(ae350_rtc=prepared(root, stage))
            result = rtc_gate(root, stage, parent, SDC, fixture(), sealed_source=True)
            self.assertTrue(result['gate_applied'])
            self.assertFalse(result['physical_timing_verified'])
            self.assertFalse(rtc_gate(root, stage, {}, '', '', sealed_source=False)['gate_applied'])
            cases = [({}, SDC, fixture()), (parent, SDC.replace('1524', '1526'), fixture()),
                     (parent, SDC, fixture(rtc='clk_50m'))]
            for metadata, sdc, text in cases:
                with self.subTest(metadata=metadata, sdc=sdc), self.assertRaises(ValueError):
                    rtc_gate(root, stage, metadata, sdc, text, sealed_source=True)


@unittest.skipUnless(os.environ.get('GW138K_AE350_RTC_C10'), 'select fixed C10 evidence; no EDA fallback')
class FixedPhysicalRTC(unittest.TestCase):
    def test_kept_rtc_pin_matches_fixed_actual_netlist_without_changing_inputs(self):
        base = Path(os.environ['GW138K_AE350_RTC_C10'])
        files = [base / 'probe.sdc', base / 'impl/pnr/ae350_local_memory_probe.vo',
                 base / 'probe.cst', base / 'impl/pnr/ae350_local_memory_probe.tr']
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        validate_constraints(files[0].read_text())
        result = audit_netlist(files[1].read_text(), top='workstation_ae350_local_memory_probe_top')
        self.assertTrue(result['direct_unique_driver_verified'])
        self.assertEqual(len(result['direct_endpoints']), 3)
        from tools.workstation_ae350_clock_placement import audit_routed
        pll = audit_routed(files[2].read_text(), files[3].read_text(), files[1].read_text(),
                           top='workstation_ae350_local_memory_probe_top')
        self.assertEqual(pll['observed_site'], 'PLL_R[0]')
        self.assertEqual(before, {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files})


@unittest.skipUnless(os.environ.get('GW138K_AE350_RTC_OLD_VG'), 'select fixed old workstation VG; syntax proof only')
class FixedSynthesisSurface(unittest.TestCase):
    def test_whole_actual_vg_syntax_parses_but_old_rtc_connection_cannot_pass(self):
        from tools.workstation_ae350_clock_placement import check_named_ports
        from tools.workstation_synthesis_netlist import SynthesisNetlist
        path = Path(os.environ['GW138K_AE350_RTC_OLD_VG'])
        raw = path.read_bytes();before = hashlib.sha256(raw).hexdigest()
        netlist = SynthesisNetlist(check_named_ports(raw.decode()), TOP)
        self.assertGreater(len(netlist.cells), 100000)
        with self.assertRaisesRegex(ValueError, 'kept RTC register'):
            audit_netlist(raw.decode())
        self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())


@unittest.skipUnless(os.environ.get('GW138K_AE350_RTC_NEW_VG'), 'select explicit new synthesis VG; no EDA fallback')
class FixedNewSynthesisRTC(unittest.TestCase):
    def test_actual_visible_wrapper_passes_only_synthesis_scope(self):
        path=Path(os.environ['GW138K_AE350_RTC_NEW_VG'])
        raw=path.read_bytes();before=hashlib.sha256(raw).hexdigest()
        result=audit_synthesis_netlist(raw.decode())
        self.assertEqual(result['visible_cpu_endpoint'], 'u_cpu/u_RiscV_AE350_SOC/rtc_tick')
        self.assertEqual(result['connectivity_scope'], 'opaque_synthesis_wrapper_input')
        self.assertFalse(result['hard_macro_input_connectivity_verified'])
        with self.assertRaisesRegex(ValueError, 'exactly one AE350 hard macro'):
            audit_netlist(raw.decode())
        self.assertEqual(before,hashlib.sha256(path.read_bytes()).hexdigest())


@unittest.skipUnless(os.environ.get('GW138K_AE350_RTC_PREPARED'), 'select fresh native RTC prepare explicitly')
class PreparedRTC(unittest.TestCase):
    def test_fresh_profile_rejects_rtc_metadata_and_source_tampering(self):
        from tools import workstation_profile as profile
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'candidate'
            shutil.copytree(os.environ['GW138K_AE350_RTC_PREPARED'], output)
            artifact = profile.verify(ROOT, output)
            self.assertEqual(artifact['ae350_rtc']['policy'], POLICY)
            self.assertFalse(artifact['ae350_rtc']['hardware_tested'])
            p = output / 'integration_inputs.json';good = json.loads(p.read_text())
            for key, value in (('sta_divide_by', 1526), ('source_binding_verified', False), ('hardware_tested', True)):
                bad = copy.deepcopy(good);bad['ae350_rtc'][key] = value;p.write_text(json.dumps(bad))
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'RTC metadata changed'):
                    profile.verify(ROOT, output)
            p.write_text(json.dumps(good))
            source = output / 'workstation/Prj1' / SOURCE;source.write_text(source.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'prepared RTC source differs'):
                profile.verify(ROOT, output)


if __name__ == '__main__':
    unittest.main()
