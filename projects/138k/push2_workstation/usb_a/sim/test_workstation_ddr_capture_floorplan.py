#!/usr/bin/env python3
"""A physical-only child must preserve the locked source and reject drift."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_custom_board_implementation as physical
from tools.stage_usb_firmware import sha


def routed_fixture():
    return '''module workstation_custom_138k_top ();
VCC power (
 .V(VCC)
);
IBUF clk_50m_ibuf (
 .I(clk_50m), .O(clk_50m_d)
);
CLKDIV \\PHY/fclkdiv (
 .HCLKIN(mem400), .RESETN(resetn), .CALIB(GND), .CLKOUT(memory_clk)
);
defparam \\PHY/fclkdiv .DIV_MODE = "4";
DFFCE \\PHY/ddr_init_internal_r_s0 (
 .D(init), .CLK(memory_clk), .CE(VCC), .CLEAR(reset), .Q(init_r)
);
defparam \\PHY/ddr_init_internal_r_s0 .INIT = 1'b0;
DFFCE \\PHY/wloadn_3_s0 (
 .D(init_r), .CLK(clk_50m_d), .CE(VCC), .CLEAR(reset), .Q(wloadn3)
);
defparam \\PHY/wloadn_3_s0 .INIT = 1'b0;
endmodule
'''.replace('PHY/', physical.DDR_PHY + '/')


class CaptureFloorplan(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.source = self.base / 'parent'
        self.source.mkdir()
        self.output = self.base / 'child'
        self.evidence_path = self.base / 'parent_evidence.json'
        self.cst = (b'IO_LOC "port" A1;\r\nIO_PORT "port" IO_TYPE=LVCMOS33;\r\n' +
                    b'INS_LOC "u_memory/u_pll/u_pll_0/PLL_inst" PLL_L[0];\r\n' +
                    f'INS_LOC "{physical.DDR_PHY}/u_dll" DDRDLLM_BL;\r\n'.encode() +
                    f'INS_LOC "{physical.DDR_PHY}/fclkdiv" LEFTSIDE[4];\r\n'.encode())
        inputs = {
            physical.BASE + '.vg': b'locked encrypted synthesis VG\n',
            'physical.cst': self.cst, 'physical.sdc': (physical.DDR_MINIMUM + '\n').encode(),
            'run.tcl': physical.implementation_script('C11030F2').encode(),
            'parent_integration_inputs.json': b'{"fixed_source":"rev2"}\n',
            'parent_pinout.json': b'{"fixed_pinout":true}\n'}
        for name, payload in inputs.items():
            (self.source / name).write_bytes(payload)
        audit = dict(identity='locked-synthesis', top_module=physical.TOP,
                     netlist_sha256=sha(self.source / (physical.BASE + '.vg')),
                     integration_inputs_sha256=sha(self.source / 'parent_integration_inputs.json'))
        (self.source / 'parent_synthesis_audit.json').write_text(json.dumps(audit))
        self.previous = dict(
            identity='custom138k-native-physical-C11030F2', user_code='0xC11030F2',
            parent_candidate='/locked/synthesis-candidate', parent_identity='locked-synthesis',
            top_module=physical.TOP, device=physical.DEVICE,
            place_option=2, route_option=0, replicate_resources=False,
            electrical_risk_explicitly_acknowledged=True, electrical_blocked=False,
            remaining_gaps=['original setup/hold failures'],
            input_sha256={path.name: sha(path) for path in self.source.iterdir()})
        (self.source / 'physical_inputs.json').write_text(json.dumps(self.previous))
        self.route = self.source / f'impl/pnr/{physical.BASE}.vo'
        self.route.parent.mkdir(parents=True)
        self.route.write_text(routed_fixture())
        self.refresh_evidence()
        self.mock_audit = patch.object(physical, 'audit_synthesis',
                                       side_effect=AssertionError('mutable current RTL must not be audited')).start()
        self.addCleanup(patch.stopall)

    def refresh_evidence(self):
        evidence = dict(physical_identity=self.previous['identity'], preparation=self.previous,
                        source_commit='locked-rev2', profile_revision=2, profile_identity='locked-profile',
                        status={'timing_closed': False, 'hardware_tested': False},
                        evidence={str(path.relative_to(self.source)): dict(sha256=sha(path), bytes=path.stat().st_size)
                                  for path in self.source.rglob('*') if path.is_file()})
        self.evidence_path.write_text(json.dumps(evidence))
        self.evidence_sha = sha(self.evidence_path)

    def prepare(self, **kwargs):
        return physical.derive_ddr_capture_region(
            self.source, self.output, kwargs.get('user_code', 'C11030F3'), self.evidence_path,
            kwargs.get('evidence_sha', self.evidence_sha), kwargs.get('acknowledge', True))

    def test_exact_append_and_fixed_source_identity_without_current_RTL_audit(self):
        result = self.prepare()
        self.assertEqual((self.output / 'physical.cst').read_bytes(), self.cst +
                         ('\n' + physical.DDR_CAPTURE_CONSTRAINT + '\n').encode())
        for name in (physical.BASE + '.vg', 'physical.sdc', 'parent_pinout.json'):
            self.assertEqual((self.output / name).read_bytes(), (self.source / name).read_bytes())
        self.assertEqual((self.source / 'physical.cst').read_bytes(), self.cst)
        self.assertEqual(result['user_code'], '0xC11030F3')
        self.assertEqual(result['parent_physical_identity'], self.previous['identity'])
        self.assertEqual(result['parent_candidate'], self.previous['parent_candidate'])
        self.assertEqual(result['parent_identity'], self.previous['parent_identity'])
        self.assertEqual(result['parent_physical_evidence_sha256'], self.evidence_sha)
        self.assertFalse(result['current_working_tree_RTL_used'])
        self.assertFalse(result['EDA_started'])
        self.assertTrue(result['automatic_hold_repair'])
        for key in ('release_ready', 'timing_closed', 'physical_gates_passed', 'hardware_tested',
                    'board_programming_authorized', 'sram_programmed', 'flash_programmed'):
            self.assertFalse(result[key])
        for name, expected in result['input_sha256'].items():
            self.assertEqual(sha(self.output / name), expected)
        self.assertEqual((self.output / 'run.tcl').read_text(), physical.implementation_script('C11030F3'))
        self.assertFalse((self.output / 'impl').exists())
        self.mock_audit.assert_not_called()

    def test_explicit_evidence_identity_and_acknowledgement_required(self):
        for kwargs, message in (({'evidence_sha': '0' * 64}, 'evidence identity'),
                                ({'evidence_sha': None}, 'evidence identity'),
                                ({'acknowledge': False}, 'acknowledgement')):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, message):
                self.prepare(**kwargs)
            self.assertFalse(self.output.exists())

    def test_parent_file_drift_rejected_before_output(self):
        for path in (self.source / 'physical.cst', self.source / 'physical.sdc', self.route,
                     self.source / (physical.BASE + '.vg'), self.source / 'physical_inputs.json',
                     self.source / 'parent_pinout.json'):
            original = path.read_bytes()
            path.write_bytes(original + b'\n')
            with self.subTest(path=path.name), self.assertRaisesRegex(ValueError, 'drifted|preparation evidence'):
                self.prepare()
            self.assertFalse(self.output.exists())
            path.write_bytes(original)

    def test_reused_identity_and_output_rejected(self):
        with self.assertRaisesRegex(ValueError, 'new UserCode'):
            self.prepare(user_code='C11030F2')
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, 'independent physical output'):
            self.prepare()

    def test_existing_target_missing_hard_location_or_minimum_drift_rejected(self):
        sdc = (physical.DDR_MINIMUM + '\n').encode()
        variants = ((self.cst + physical.DDR_CAPTURE_CONSTRAINT.encode(), sdc, 'already appears'),
                    (self.cst.replace(b'DDRDLLM_BL', b'DDRDLLM_BR'), sdc, 'hard-resource'),
                    (self.cst, sdc.replace(b'0.800', b'0.000'), 'unique exact'),
                    (self.cst, sdc + sdc, 'unique exact'))
        for cst, changed_sdc, message in variants:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                physical.ddr_capture_region_constraints(cst, changed_sdc, routed_fixture())

    def test_observed_FF_clock_data_enable_and_reset_bypass_rejected(self):
        original = routed_fixture()
        variants = (
            (original.replace('.D(init_r)', '.D(init)'), 'data/reset/enable'),
            (original.replace('.CLK(clk_50m_d)', '.CLK(memory_clk)'), 'clock boundary'),
            (original.replace('.CLK(memory_clk)', '.CLK(clk_50m_d)'), 'clock boundary'),
            (original.replace('.CE(VCC)', '.CE(GND)'), 'data/reset/enable'),
            (original.replace('.CLEAR(reset), .Q(wloadn3)', '.CLEAR(other), .Q(wloadn3)'), 'data/reset/enable'),
            (original.replace('.INIT = 1\'b0', '.INIT = 1\'b1'), 'type/INIT/pins'),
            (original.replace('DFFCE', 'DFFPE'), 'type/INIT/pins'),
            (original.replace('.DIV_MODE = "4"', '.DIV_MODE = "2"'), 'clock boundary'))
        for changed, message in variants:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                physical.ddr_capture_region_constraints(self.cst, (physical.DDR_MINIMUM + '\n').encode(), changed)

    def test_previous_route_evidence_must_be_hash_bound(self):
        evidence = json.loads(self.evidence_path.read_bytes())
        del evidence['evidence'][str(self.route.relative_to(self.source))]
        self.evidence_path.write_text(json.dumps(evidence))
        with self.assertRaisesRegex(ValueError, 'route VO'):
            self.prepare(evidence_sha=sha(self.evidence_path))
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
