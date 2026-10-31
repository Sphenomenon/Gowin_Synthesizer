#!/usr/bin/env python3
"""Independent CST, actual routed site and direct hard-macro clock negatives."""
from pathlib import Path
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_ae350_clock_placement import (
    CONSTRAINT, SOURCE, DESTINATION, INSTANCE, SITE, TOP,
    compose, validate_constraints, verify_prepared, audit_routed,
)


def cell(kind, name, ports):
    return kind + ' \\' + name + ' (\n' + ',\n'.join(' .' + p + '(' + n + ')' for p,n in ports) + '\n);\n'


def fixture(extra='', core='core_clk', pll_kind='PLL'):
    return ('module ' + TOP + ' ();\nwire core_clk, bus_clk, GND, q;\n' +
            cell(pll_kind, INSTANCE, [('CLKOUT0','bus_clk'),('CLKOUT1','core_clk')]) +
            cell('AE350_SOC','u_cpu/hard_macro',[('CORE_CLK',core)]) +
            cell('DFFCE','core_release_s0',[('Q','q'),('D','GND'),('CLK','core_clk'),('CE','GND'),('CLEAR','GND')]) +
            extra + 'endmodule\n')


REPORT = (' 0.000 0.000 tCL RR 5 PLL_R[0] u_cpu_pll/PLL_inst/CLKOUT0\n'
          ' 0.000 0.000 tCL RR 5 PLL_R[0] u_cpu_pll/PLL_inst/CLKOUT1\n')
LOCATIONLESS = ' 5.000 0.000 tCL FF u_cpu_pll/PLL_inst/CLKOUT1\n'


class DedicatedClock(unittest.TestCase):
    def test_versioned_component_composes_and_is_reverified(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);source=base/'root';stage=base/'stage'
            (source/SOURCE).parent.mkdir(parents=True);(source/SOURCE).write_bytes((ROOT/SOURCE).read_bytes())
            before='INS_LOC "ddr/PLL_inst" PLL_L[0];\nIO_PORT "clock" IO_TYPE=LVCMOS33;\n'
            combined,evidence=compose(source,stage,before)
            (stage/'constraints/custom_138k.cst').write_text(combined)
            self.assertEqual(combined,before+CONSTRAINT+'\n')
            self.assertEqual(verify_prepared(source,stage,evidence),evidence)
            self.assertFalse(evidence['placement_verified'])
            changed=copy.deepcopy(evidence);changed['requested_site']='PLL_B[2]'
            with self.assertRaisesRegex(ValueError,'metadata changed'):verify_prepared(source,stage,changed)
            (stage/DESTINATION).write_text(CONSTRAINT+'\n')
            with self.assertRaisesRegex(ValueError,'component differs'):verify_prepared(source,stage,evidence)

    def test_missing_duplicate_conflicting_and_indirect_requests_are_rejected(self):
        cases=['',CONSTRAINT.replace(SITE,'PLL_B[2]'),CONSTRAINT+CONSTRAINT,
               CONSTRAINT+'INS_LOC "other/PLL_inst" PLL_R[0];\n',
               CONSTRAINT+'INS_LOC u_cpu_pll/PLL_inst PLL_B[2];\n',
               'INS_LOC $instance PLL_R[0];\n',CONSTRAINT.replace(';',''),
               CONSTRAINT.replace('INS_LOC','ins_loc'),
               CONSTRAINT+'INS_LOC "other/PLL_inst" [get_site];\nINS_LOC "u_cpu_pll/PLL_inst" PLL_R[0];\n']
        for text in cases:
            with self.subTest(text=text),self.assertRaises(ValueError):validate_constraints(text)
        self.assertTrue(validate_constraints('// not selected: INS_LOC other PLL_R[0];\n'+CONSTRAINT)['unique_assignment_verified'])

    def test_component_or_preexisting_assignment_cannot_be_overridden(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);(base/SOURCE).parent.mkdir(parents=True);(base/SOURCE).write_text(CONSTRAINT)
            for before in (CONSTRAINT,'INS_LOC "other" PLL_R[0];\n'):
                with self.assertRaisesRegex(ValueError,'parent CST already'):compose(base,base/'stage',before)
            (base/SOURCE).write_text(CONSTRAINT.replace(SITE,'PLL_B[2]'))
            with self.assertRaisesRegex(ValueError,'versioned board constraint changed'):compose(base,base/'stage','')

    def test_actual_site_output_and_unique_direct_driver_are_required(self):
        r=audit_routed(CONSTRAINT,REPORT+LOCATIONLESS,fixture())
        self.assertEqual((r['requested_site'],r['observed_site'],r['actual_output']),(SITE,SITE,'CLKOUT1'))
        self.assertTrue(r['direct_unique_driver_verified']);self.assertFalse(r['full_physical_acceptance'])
        self.assertEqual(r['locationless_clock_row_lines'],[3])
        cases=[(CONSTRAINT,'',fixture()),
               (CONSTRAINT,LOCATIONLESS,fixture()),
               (CONSTRAINT,REPORT+LOCATIONLESS.replace('5.000','unknown'),fixture()),
               (CONSTRAINT,REPORT+LOCATIONLESS.replace(' FF ',' FF 5 '),fixture()),
               (CONSTRAINT,REPORT.replace('CLKOUT1','CLKOUT0'),fixture()),
               (CONSTRAINT,REPORT.replace(SITE,'PLL_B[2]'),fixture()),
               (CONSTRAINT,REPORT+REPORT.replace(SITE,'PLL_B[2]'),fixture()),
               (CONSTRAINT,REPORT.replace('PLL_R[0]','unknown'),fixture()),
               (CONSTRAINT.replace(SITE,'PLL_B[2]'),REPORT,fixture()),
               (CONSTRAINT,REPORT,fixture(core='bus_clk')),
               (CONSTRAINT,REPORT,fixture(pll_kind='LUT4')),
               (CONSTRAINT,REPORT,fixture(extra=cell('LUT2','extra_driver',[('F','core_clk'),('I0','GND'),('I1','GND')]))),
               (CONSTRAINT,REPORT,fixture(extra=cell('LUT2','expression_driver',[('F','{core_clk}'),('I0','GND'),('I1','GND')]))),
               (CONSTRAINT,REPORT,fixture(extra=cell('LUT2','nested_driver',[('F','(core_clk)'),('I0','GND'),('I1','GND')]))),
               (CONSTRAINT,REPORT,fixture(extra=cell('LUT2','nested_consumer',[('F','unused'),('I0','(core_clk)'),('I1','GND')]))),
               (CONSTRAINT,REPORT,fixture(extra=cell('LUT2','spaced_consumer',[('F','unused'),('I0','core_clk'),('I1','GND')]).replace('.I0(','.I0 ('))),
               (CONSTRAINT,REPORT,fixture(extra='LUT2 single_line(.F(core_clk), .I0(GND), .I1(GND));\n')),
               (CONSTRAINT,REPORT,fixture(extra='wire second = core_clk;\n')),
               (CONSTRAINT,REPORT,fixture(extra='assign core_clk = bus_clk;\n')),
               (CONSTRAINT,REPORT,fixture(extra=cell('PLL','other/PLL_inst',[('CLKOUT1','core_clk')]))),
               (CONSTRAINT,REPORT,fixture(extra=cell('BUFG','buffer',[('I','core_clk'),('O','buffered')]),core='buffered')),
               (CONSTRAINT,REPORT,fixture(extra=cell('AE350_SOC','second_cpu',[('CORE_CLK','core_clk')]))),
               (CONSTRAINT,REPORT,fixture().replace('.CLKOUT1(core_clk)','.CLKOUT1(bus_clk),\n .CLKOUT1(core_clk)')),
               (CONSTRAINT,REPORT,fixture().replace('wire core_clk,','input core_clk;\nwire unused,')),
               (CONSTRAINT,REPORT,fixture().replace('module '+TOP+' ();','module '+TOP+' (input core_clk);')),
               (CONSTRAINT,REPORT,fixture().replace('module '+TOP+' ();','module '+TOP+' (core_clk);')
                    .replace('wire core_clk,','input core_clk, other;\nwire unused,')),
               (CONSTRAINT,REPORT,fixture().replace('AE350_SOC','MISSING_CPU'))]
        for cst,tr,vo in cases:
            with self.subTest(cst=cst,tr=tr,vo=vo),self.assertRaises(ValueError):audit_routed(cst,tr,vo)

    def test_escaped_scalar_alias_cannot_hide_top_port_or_another_driver(self):
        escaped = fixture().replace('(core_clk)', '(\\core_clk )')
        self.assertEqual(audit_routed(CONSTRAINT, REPORT, escaped)['core_clock_net'], 'core_clk')
        cases = [escaped.replace('module '+TOP+' ();', 'module '+TOP+' (\\core_clk );')
                        .replace('wire core_clk,', 'input \\core_clk ;\nwire unused,'),
                 escaped.replace('endmodule', cell('LUT2', 'alias_driver', [('F','core_clk'),('I0','GND'),('I1','GND')])+'endmodule')]
        for vo in cases:
            with self.subTest(vo=vo), self.assertRaises(ValueError):
                audit_routed(CONSTRAINT, REPORT, vo)

    def test_compact_routed_ram_closing_keeps_full_driver_inventory(self):
        ram = 'RAM16SDP4 memory (\n .CLK(bus_clk), .DO({q}));\n'
        self.assertTrue(audit_routed(CONSTRAINT, REPORT, fixture(extra=ram))['direct_unique_driver_verified'])
        hidden = cell('LUT2', 'after_ram', [('F', 'core_clk'), ('I0', 'GND')])
        with self.assertRaisesRegex(ValueError, 'unreviewed driver/consumer'):
            audit_routed(CONSTRAINT, REPORT, fixture(extra=ram+hidden))

    def test_synthesis_split_module_header_and_escaped_formal_are_fully_parsed(self):
        vo = ('module '+TOP+' ()\n;\nwire core_clk;\n'+
              cell('PLL', INSTANCE, [('CLKOUT1','core_clk')])+
              cell('child_clock', 'child', [('\\core.clock ','core_clk')])+'endmodule\n'+
              'module child_clock (\\core.clock )\n;\ninput \\core.clock ;\n'+
              cell('AE350_SOC', 'hard_macro', [('CORE_CLK','\\core.clock ')])+'endmodule\n')
        result = audit_routed(CONSTRAINT, REPORT, vo)
        self.assertEqual(result['direct_core_clock_endpoints'],
                         ['child/hard_macro/CORE_CLK', INSTANCE+'/CLKOUT1'])
        extra = cell('LUT2', 'hidden_driver', [('F','\\core.clock '),('I0','GND')])
        broken = vo.rsplit('endmodule',1)[0]+extra+'endmodule\n'
        with self.assertRaisesRegex(ValueError,'unreviewed driver/consumer'):
            audit_routed(CONSTRAINT, REPORT, broken)
        for bad in (vo.replace('.\\core.clock (core_clk)', '.\\core.clock ((core_clk))'),
                    vo.replace('.\\core.clock (core_clk)', '.\\core.clock (core_clk),\n .\\core.clock (core_clk)')):
            with self.subTest(vo=bad), self.assertRaises(ValueError):
                audit_routed(CONSTRAINT, REPORT, bad)

    def test_scalar_scope_and_escaped_slash_are_distinct(self):
        vo = ('module '+TOP+' ();\nwire \\child/x ;\nwire bus_clk;\n'+
              cell('PLL', INSTANCE, [('CLKOUT0','bus_clk'),('CLKOUT1','\\child/x ')])+
              cell('child_clock', 'child', [])+'endmodule\n'+
              'module child_clock ();\nwire x;\n'+
              cell('AE350_SOC','hard_macro',[('CORE_CLK','x')])+'endmodule\n')
        with self.assertRaisesRegex(ValueError,'not directly driven'):
            audit_routed(CONSTRAINT, REPORT, vo)


@unittest.skipUnless(os.environ.get('GW138K_AE350_PHYSICAL_C9'),'select fixed C9 evidence explicitly; no EDA fallback')
class FixedPhysicalReference(unittest.TestCase):
    def test_fixed_c9_site_and_c8_wrong_site_are_distinct(self):
        c9=Path(os.environ['GW138K_AE350_PHYSICAL_C9']);pnr=c9/'impl/pnr/ae350_local_memory_probe'
        result=audit_routed((c9/'probe.cst').read_text(),pnr.with_suffix('.tr').read_text(),
                            pnr.with_suffix('.vo').read_text(),top='workstation_ae350_local_memory_probe_top')
        self.assertEqual(result['observed_site'],SITE)
        if os.environ.get('GW138K_AE350_PHYSICAL_C8'):
            c8=Path(os.environ['GW138K_AE350_PHYSICAL_C8']);pnr=c8/'impl/pnr/ae350_local_memory_probe'
            # Request is supplied only in memory to isolate wrong observed site;
            # no file in either immutable candidate is changed.
            with self.assertRaisesRegex(ValueError,'actual routed CPU PLL'):
                audit_routed((c8/'probe.cst').read_text()+'\n'+CONSTRAINT,pnr.with_suffix('.tr').read_text(),
                             pnr.with_suffix('.vo').read_text(),top='workstation_ae350_local_memory_probe_top')


@unittest.skipUnless(os.environ.get('GW138K_AE350_CLOCK_PREPARED'),'select a new actual native prepare explicitly')
class PreparedClockReference(unittest.TestCase):
    def test_prepared_policy_and_metadata_cannot_claim_routed_acceptance(self):
        from tools import workstation_profile as profile
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'candidate'
            shutil.copytree(os.environ['GW138K_AE350_CLOCK_PREPARED'], output)
            artifact = profile.verify(ROOT, output)
            evidence = artifact['ae350_core_clock_placement']
            self.assertEqual((evidence['policy'], evidence['requested_site']), ('pll_r0_clkout1_v1', SITE))
            self.assertFalse(evidence['placement_verified'])
            self.assertFalse(evidence['hardware_tested'])
            metadata_path = output / 'integration_inputs.json'
            metadata = json.loads(metadata_path.read_text())
            for field, value in (('requested_site', 'PLL_B[2]'), ('placement_verified', True), ('hardware_tested', True)):
                changed = copy.deepcopy(metadata)
                changed['ae350_core_clock_placement'][field] = value
                metadata_path.write_text(json.dumps(changed))
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'dedicated clock metadata changed'):
                    profile.verify(ROOT, output)
            metadata_path.write_text(json.dumps(metadata))
            stage = output / 'workstation/Prj1'
            (stage / DESTINATION).write_text(CONSTRAINT.replace(SITE, 'PLL_B[2]'))
            with self.assertRaisesRegex(ValueError, 'component differs'):
                profile.verify(ROOT, output)


if __name__=='__main__':unittest.main()
