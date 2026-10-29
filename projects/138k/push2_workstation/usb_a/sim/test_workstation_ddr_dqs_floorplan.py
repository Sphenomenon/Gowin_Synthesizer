#!/usr/bin/env python3
"""Locked physical descendants and observed four-lane DQS HOLD boundaries."""
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from tools import workstation_custom_board_implementation as physical
from tools.stage_usb_firmware import sha
import test_workstation_ddr_capture_floorplan as fixture


def routed_fixture():
    cells=[]
    for lane in range(4):
        cells.append(f'''DFFCE \\PHY/u_ddr_init/read_rclksel_conf_{lane}_s0 (
 .D(VCC), .CLK(memory_clk), .CE(enable{lane}), .CLEAR(reset), .Q(conf{lane})
);
defparam \\PHY/u_ddr_init/read_rclksel_conf_{lane}_s0 .INIT = 1'b0;
LUT2 \\PHY/u_ddr_init/hold_Z_{lane}_s (
 .I0(conf{lane}), .I1(hold{lane}), .F(held{lane})
);
defparam \\PHY/u_ddr_init/hold_Z_{lane}_s .INIT = 4'h4;
DQS \\PHY/u_ddr_phy_wds/data_lane_gen[{lane}].u_ddr_phy_data_lane/u_ddr_phy_data_io/u_dqs (
 .PCLK(memory_clk), .FCLK(mem400), .RESET(reset), .HOLD(held{lane})
);
defparam \\PHY/u_ddr_phy_wds/data_lane_gen[{lane}].u_ddr_phy_data_lane/u_ddr_phy_data_io/u_dqs .DQS_MODE = "X4";
''')
    extra=''.join(cells).replace('PHY/',physical.DDR_PHY+'/')
    return fixture.routed_fixture().replace('endmodule',extra+'endmodule')


class DQSHoldFloorplan(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture.CaptureFloorplan('test_exact_append_and_fixed_source_identity_without_current_RTL_audit')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f=self.fixture
        f.cst+=(physical.DDR_CAPTURE_CONSTRAINT+'\n').encode()
        (f.source/'physical.cst').write_bytes(f.cst)
        (f.source/'run.tcl').write_text(physical.implementation_script('C11030F3'))
        (f.source/'parent_physical_inputs.json').write_bytes(b'{"ancestor":"originalF2"}\n')
        (f.source/'parent_physical_evidence.json').write_bytes(b'{"ancestor":"originalF2evidence"}\n')
        f.previous.update(identity='custom138k-native-physical-C11030F3',user_code='0xC11030F3')
        f.previous['input_sha256']={path.name:sha(path) for path in f.source.iterdir() if path.is_file() and path.name!='physical_inputs.json'}
        (f.source/'physical_inputs.json').write_text(json.dumps(f.previous))
        f.route.write_text(routed_fixture())
        f.refresh_evidence()

    def prepare(self):
        f=self.fixture
        return physical.derive_ddr_capture_region(f.source,f.output,'C11030F4',f.evidence_path,f.evidence_sha,True,dqs_hold_regions=True)

    def test_exact_append_preserves_ancestor_inputs_and_same_synthesis_SDC(self):
        f=self.fixture
        result=self.prepare()
        child=(f.output/'physical.cst').read_bytes()
        self.assertTrue(child.startswith(f.cst))
        self.assertEqual(child[len(f.cst):].decode(),'\n'+'\n'.join(result['ddr_dqs_hold_regions_adaptation']['constraints'])+'\n')
        self.assertEqual(len(result['ddr_dqs_hold_regions_adaptation']['constraints']),8)
        for name,expected in f.previous['input_sha256'].items():
            if name not in ('physical.cst','run.tcl'):
                self.assertEqual(sha(f.output/name),expected)
        self.assertEqual((f.output/'parent_physical_inputs.json').read_bytes(),b'{"ancestor":"originalF2"}\n')
        self.assertEqual(sha(f.output/'parent_C11030F3_inputs.json'),sha(f.source/'physical_inputs.json'))
        self.assertEqual(sha(f.output/'parent_C11030F3_evidence.json'),f.evidence_sha)
        for key in ('current_working_tree_RTL_used','new_synthesis_run','EDA_started','physical_gates_passed','deployment_allowed','sram_programmed','flash_programmed'):
            self.assertFalse(result[key])
        self.assertEqual(result['parent_physical_identity'],f.previous['identity'])
        for name,expected in result['input_sha256'].items():self.assertEqual(sha(f.output/name),expected)

    def test_lut_only_exact_four_targets_regions_and_free_registers(self):
        f=self.fixture
        result=physical.derive_ddr_capture_region(f.source,f.output,'C11030F6',f.evidence_path,
                                                f.evidence_sha,True,dqs_hold_lut_only=True)
        placement=result['ddr_dqs_hold_regions_adaptation']
        expected=[f'INS_LOC "{physical.DDR_PHY}/u_ddr_init/hold_Z_{lane}_s" {region};'
                  for lane,region in enumerate(physical.DDR_DQS_HOLD_REGIONS)]
        self.assertEqual(placement['mode'],'LUT_only')
        self.assertEqual(placement['constraints'],expected)
        self.assertEqual((f.output/'physical.cst').read_bytes(),f.cst+('\n'+'\n'.join(expected)+'\n').encode())
        self.assertEqual(len(placement['unconstrained_config_registers']),4)
        for lane in placement['lanes']:
            self.assertFalse(lane['register_constrained']);self.assertTrue(lane['gate_constrained'])
        for name in (physical.BASE+'.vg','physical.sdc','parent_physical_inputs.json','parent_physical_evidence.json'):
            self.assertEqual((f.output/name).read_bytes(),(f.source/name).read_bytes())
        self.assertIn('LUT_only',result['source_policy'])
        self.assertEqual(result['parent_physical_manifest_sha256'],sha(f.source/'physical_inputs.json'))
        self.assertEqual(result['parent_physical_evidence_sha256'],f.evidence_sha)
        self.assertFalse(result['EDA_started']);self.assertFalse(result['new_synthesis_run'])
        self.assertFalse(result['current_working_tree_RTL_used']);self.assertFalse(result['release_ready'])
        for name,expected_hash in result['input_sha256'].items():self.assertEqual(sha(f.output/name),expected_hash)

    def test_lut_only_does_not_accept_constrained_config_parent(self):
        f=self.fixture
        target=f'INS_LOC "{physical.DDR_PHY}/u_ddr_init/read_rclksel_conf_0_s0" R2C2;\n'.encode()
        with self.assertRaisesRegex(ValueError,'already appears'):
            physical.ddr_dqs_hold_region_constraints(f.cst+target,(physical.DDR_MINIMUM+'\n').encode(),
                                                    routed_fixture(),lut_only=True)

    def test_lut_only_still_checks_all_four_ff_lut_dqs_topologies(self):
        f=self.fixture
        for lane in range(4):
            changed=routed_fixture().replace(f'.I0(conf{lane})',f'.I0(wrong{lane})')
            with self.subTest(lane=lane),self.assertRaisesRegex(ValueError,'observed'):
                physical.ddr_dqs_hold_region_constraints(f.cst,(physical.DDR_MINIMUM+'\n').encode(),changed,lut_only=True)

    def test_lut_only_parent_evidence_identity_and_route_drift_rejected(self):
        f=self.fixture
        with self.assertRaisesRegex(ValueError,'evidence identity'):
            physical.derive_ddr_capture_region(f.source,f.output,'C11030F6',f.evidence_path,
                                               '0'*64,True,dqs_hold_lut_only=True)
        for path in (f.route,f.source/'physical.cst',f.source/'parent_physical_inputs.json'):
            original=path.read_bytes();path.write_bytes(original+b'changed')
            with self.subTest(path=path.name),self.assertRaisesRegex(ValueError,'drifted'):
                physical.derive_ddr_capture_region(f.source,f.output,'C11030F6',f.evidence_path,
                                                   f.evidence_sha,True,dqs_hold_lut_only=True)
            self.assertFalse(f.output.exists());path.write_bytes(original)

    def test_dqs_modes_are_mutually_exclusive_before_output(self):
        f=self.fixture
        with self.assertRaisesRegex(ValueError,'mutually exclusive'):
            physical.derive_ddr_capture_region(f.source,f.output,'C11030F6',f.evidence_path,
                                               f.evidence_sha,True,dqs_hold_regions=True,dqs_hold_lut_only=True)
        self.assertFalse(f.output.exists())

    def test_data_reset_clock_configuration_mutations_rejected(self):
        f=self.fixture
        original=routed_fixture()
        for changed in (original.replace('.I0(conf2)','.I0(conf1)'),
                        original.replace('.HOLD(held2)','.HOLD(held1)'),
                        original.replace('.PCLK(memory_clk)','.PCLK(mem400)'),
                        original.replace('.RESET(reset)','.RESET(other)'),
                        original.replace(".INIT = 4'h4",".INIT = 4'h8"),
                        original.replace('.D(VCC)','.D(enable0)'),
                        original.replace('.DQS_MODE = "X4"','.DQS_MODE = "X2"')):
            with self.subTest(changed=changed[-100:]),self.assertRaisesRegex(ValueError,'observed'):
                physical.ddr_dqs_hold_region_constraints(f.cst,(physical.DDR_MINIMUM+'\n').encode(),changed)

    def test_capture_and_hard_resources_and_minimum_must_remain(self):
        f=self.fixture
        for cst,sdc in ((f.cst.replace(physical.DDR_CAPTURE_CONSTRAINT.encode(),b''),physical.DDR_MINIMUM),
                        (f.cst.replace(b'DDRDLLM_BL',b'DDRDLLM_BR'),physical.DDR_MINIMUM),
                        (f.cst,physical.DDR_MINIMUM.replace('0.800','0.000'))):
            with self.subTest(sdc=sdc),self.assertRaises(ValueError):
                physical.ddr_dqs_hold_region_constraints(cst,(sdc+'\n').encode(),routed_fixture())

    def test_preexisting_target_and_missing_lane_rejected(self):
        f=self.fixture
        target=f'INS_LOC "{physical.DDR_PHY}/u_ddr_init/hold_Z_1_s" R1C1;\n'.encode()
        with self.assertRaisesRegex(ValueError,'already appears'):
            physical.ddr_dqs_hold_region_constraints(f.cst+target,(physical.DDR_MINIMUM+'\n').encode(),routed_fixture())
        changed=routed_fixture().replace('read_rclksel_conf_3_s0','missing_conf_3_s0')
        with self.assertRaisesRegex(ValueError,'boundary is missing'):
            physical.ddr_dqs_hold_region_constraints(f.cst,(physical.DDR_MINIMUM+'\n').encode(),changed)

    def test_hash_bound_parent_route_and_ancestor_drift_rejected(self):
        f=self.fixture
        for path in (f.route,f.source/'parent_physical_inputs.json'):
            original=path.read_bytes();path.write_bytes(original+b'changed')
            with self.subTest(path=path.name),self.assertRaisesRegex(ValueError,'drifted'):
                self.prepare()
            self.assertFalse(f.output.exists());path.write_bytes(original)


if __name__=='__main__':unittest.main()
