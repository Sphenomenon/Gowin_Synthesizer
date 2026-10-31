#!/usr/bin/env python3
"""Fixed source-monitor placement preserves the complete locked physical parent."""
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_custom_board_implementation as physical
from tools.stage_usb_firmware import sha
from test_workstation_ddr_capture_floorplan import CaptureFloorplan, routed_fixture


def monitor_fixture():
    body=[]
    for monitor,port,_ in physical.REFERENCE_SOURCE_MONITORS:
        stem=physical.REFERENCE_MONITOR_ROOT+monitor
        body.append(f'IBUF {port}_ibuf (\n .I({port}), .O({port}_d)\n);\n')
        for bank in ('binary','gray'):
            for bit in range(32):
                name=f'{stem}/source_{bank}_{bit}_s0'
                body.append(f'DFFCE \\{name} (\n .D(data_{bit}), .CLK({port}_d), .CE(VCC), '
                            f'.CLEAR(\\{stem}/n60_6 ), .Q(\\{stem}/source_{bank} [{bit}])\n);\n'
                            f'defparam \\{name} .INIT = 1\'b0;\n')
    return routed_fixture().replace('endmodule',''.join(body)+'endmodule')


class ReferenceMonitorFloorplan(unittest.TestCase):
    setUp=CaptureFloorplan.setUp
    refresh_evidence=CaptureFloorplan.refresh_evidence

    def parent(self,measured=True):
        self.cst+=('\n'+f'INS_LOC "{physical.DDR_CAPTURE}" {physical.DDR_FAR_CAPTURE_REGION};\n'+
                   f'INS_LOC "{physical.DDR_LAUNCH}" {physical.DDR_FAR_LAUNCH_REGION};\n').encode()
        (self.source/'physical.cst').write_bytes(self.cst)
        (self.source/'physical.sdc').write_text(physical.DDR_STRICT_MINIMUM+'\n')
        self.route.write_text(monitor_fixture())
        self.previous['parent_candidate_identity']='frozen-demo-candidate'
        for name in ('physical.cst','physical.sdc'):
            self.previous['input_sha256'][name]=sha(self.source/name)
        (self.source/'physical_inputs.json').write_text(json.dumps(self.previous))
        self.refresh_evidence()
        if measured:
            evidence=dict(schema=1,stage='full_physical_implementation_measurement',
                directory=str(self.source),candidate_identity='frozen-demo-candidate',
                user_code='C11030F2',pnr_completed=True,process_exit_code=0,
                physical_input_inventory_reverified_after_pnr=True,
                timing_closed=False,hardware_tested=False,release_ready=False,
                source_and_output_sha256={str(p.relative_to(self.source)):sha(p)
                    for p in self.source.rglob('*') if p.is_file()})
            self.evidence_path.write_text(json.dumps(evidence));self.evidence_sha=sha(self.evidence_path)

    def prepare(self,**kwargs):
        return physical.derive_ddr_capture_region(self.source,self.output,'D2110105',
            self.evidence_path,self.evidence_sha,True,reference_monitor_source_regions=True,**kwargs)

    def test_measured_parent_keeps_all_bytes_and_appends_complete_fixed_inventory(self):
        self.parent();result=self.prepare();proof=result['reference_monitor_source_regions_adaptation']
        self.assertEqual((self.output/'physical.cst').read_bytes(),self.cst+
                         ('\n'+'\n'.join(proof['constraints'])+'\n').encode())
        self.assertEqual(len(proof['constraints']),128);self.assertEqual(proof['register_count'],128)
        self.assertEqual([m['register_count'] for m in proof['monitors']],[64,64])
        self.assertEqual([m['region'] for m in proof['monitors']],['R[54:54]C[64:84]','R[56:56]C[64:84]'])
        self.assertFalse(proof['selected_monitor_constrained']);self.assertTrue(proof['sdc_unchanged'])
        for name in (physical.BASE+'.vg','physical.sdc','parent_pinout.json'):
            self.assertEqual((self.source/name).read_bytes(),(self.output/name).read_bytes())
        self.assertEqual((self.source/'physical.cst').read_bytes(),self.cst)
        self.assertEqual((self.output/'run.tcl').read_text(),physical.implementation_script('D2110105'))
        self.assertTrue(result['automatic_hold_repair']);self.assertTrue(result['full_timing_gates_required'])
        for name,identity in result['input_sha256'].items():self.assertEqual(sha(self.output/name),identity)
        self.assertFalse(result['deployment_allowed']);self.assertFalse(result['current_working_tree_RTL_used'])
        self.mock_audit.assert_not_called()

    def test_actual_fixed_names_high_bits_FF_configuration_and_clocks_are_required(self):
        self.parent();route=self.route.read_text();stem=physical.REFERENCE_MONITOR_ROOT+'reference_48_monitor'
        variants=[(route.replace(stem+'/source_gray_31_s0',stem+'/source_gray_32_s0'),'inventory'),
                  (route.replace('DFFCE \\'+stem+'/source_gray_31_s0','DFFPE \\'+stem+'/source_gray_31_s0'),'FF type'),
                  (route.replace('.INIT = 1\'b0','.INIT = 1\'b1'),'FF type'),
                  (route.replace('.CLK(clk_12m288_d)','.CLK(clk_16m9344_d)'),'topology'),
                  (route.replace('.CE(VCC), .CLEAR(\\'+stem,'.CE(GND), .CLEAR(\\'+stem),'topology'),
                  (route.replace(stem+'/n60_6',stem+'/changed_reset'),'topology'),
                  (route.replace('.I(clk_12m288)','.I(clk_16m9344)'),'IBUF')]
        for changed,message in variants:
            with self.subTest(message=message),self.assertRaisesRegex(ValueError,message):
                physical.reference_monitor_source_region_constraints(self.cst,
                    (physical.DDR_STRICT_MINIMUM+'\n').encode(),changed)
        with self.assertRaisesRegex(ValueError,'already appears'):
            physical.reference_monitor_source_region_constraints(self.cst+
                f'INS_LOC "{stem}/source_gray_31_s0" R1C1;\n'.encode(),
                physical.DDR_STRICT_MINIMUM.encode(),route)
        with self.assertRaisesRegex(ValueError,'unique exact 3.500'):
            physical.reference_monitor_source_region_constraints(self.cst,physical.DDR_MINIMUM.encode(),route)

    def test_parent_drift_and_mixed_modes_fail_before_output(self):
        self.parent()
        for name in ('physical.cst','physical.sdc',physical.BASE+'.vg',f'impl/pnr/{physical.BASE}.vo'):
            path=self.source/name;original=path.read_bytes();path.write_bytes(original+b'\n')
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'drifted'):self.prepare()
            self.assertFalse(self.output.exists());path.write_bytes(original)
        for mode in ('dqs_hold_regions','dqs_hold_lut_only','launch_capture_regions','launch_capture_far_regions'):
            with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,'mutually exclusive'):
                self.prepare(**{mode:True})
            self.assertFalse(self.output.exists())


if __name__=='__main__':unittest.main()
