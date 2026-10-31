#!/usr/bin/env python3
"""The current initialization hold experiment preserves the real 3.500ns SDC."""
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_custom_board_implementation as physical
from tools.stage_usb_firmware import sha
from test_workstation_ddr_capture_floorplan import CaptureFloorplan, routed_fixture


class StrictHoldFloorplan(unittest.TestCase):
    setUp = CaptureFloorplan.setUp
    refresh_evidence = CaptureFloorplan.refresh_evidence

    def strict_parent(self, measured=False):
        (self.source / 'physical.sdc').write_text(physical.DDR_STRICT_MINIMUM + '\n')
        self.previous['parent_candidate_identity'] = 'frozen-demo-candidate'
        self.previous['input_sha256']['physical.sdc'] = sha(self.source / 'physical.sdc')
        (self.source / 'physical_inputs.json').write_text(json.dumps(self.previous))
        self.refresh_evidence()
        if measured:
            evidence = dict(schema=1, stage='full_physical_implementation_measurement',
                directory=str(self.source), candidate_identity='frozen-demo-candidate',
                user_code='C11030F2', pnr_completed=True, process_exit_code=0,
                physical_input_inventory_reverified_after_pnr=True,
                timing_closed=False, hardware_tested=False, release_ready=False,
                source_and_output_sha256={str(p.relative_to(self.source)): sha(p)
                    for p in self.source.rglob('*') if p.is_file()})
            self.evidence_path.write_text(json.dumps(evidence))
            self.evidence_sha = sha(self.evidence_path)

    def prepare(self, **kwargs):
        return physical.derive_ddr_capture_region(self.source, self.output, 'D2103104',
            self.evidence_path, self.evidence_sha, True, launch_capture_regions=True, **kwargs)

    def test_legacy_and_measured_evidence_keep_exact_sdc_and_only_append_two_locations(self):
        for measured in (False, True):
            with self.subTest(measured=measured):
                self.strict_parent(measured)
                self.output = self.base / ('strict-measured' if measured else 'strict-legacy')
                before = (self.source / 'physical.sdc').read_bytes()
                result = self.prepare()
                self.assertEqual((self.output / 'physical.sdc').read_bytes(), before)
                self.assertEqual((self.output / 'physical.cst').read_bytes(), self.cst +
                    ('\n' + physical.DDR_CAPTURE_CONSTRAINT + '\n' + physical.DDR_LAUNCH_CONSTRAINT + '\n').encode())
                self.assertEqual((self.source / 'physical.cst').read_bytes(), self.cst)
                proof = result['ddr_launch_capture_regions_adaptation']
                self.assertEqual(proof['minimum_delay_ns'], 3.5)
                self.assertTrue(proof['sdc_unchanged'])
                self.assertFalse(proof['new_route_verified'])
                self.assertEqual(sha(self.output / (physical.BASE + '.vg')),
                                 sha(self.source / (physical.BASE + '.vg')))
                for name, value in result['input_sha256'].items():
                    self.assertEqual(sha(self.output / name), value)
                self.assertFalse(result['new_synthesis_run'])
                self.assertFalse(result['deployment_allowed'])
                self.assertFalse(result['timing_closed'])
                self.mock_audit.assert_not_called()

    def test_old_or_changed_minimum_and_existing_launch_are_rejected(self):
        for sdc in (physical.DDR_MINIMUM, physical.DDR_STRICT_MINIMUM.replace('3.500', '0.000'),
                    physical.DDR_STRICT_MINIMUM + '\n' + physical.DDR_STRICT_MINIMUM):
            with self.subTest(sdc=sdc), self.assertRaisesRegex(ValueError, 'unique exact 3.500'):
                physical.ddr_launch_capture_region_constraints(self.cst, sdc.encode(), routed_fixture())
        with self.assertRaisesRegex(ValueError, 'launch target already'):
            physical.ddr_launch_capture_region_constraints(
                self.cst + physical.DDR_LAUNCH_CONSTRAINT.encode(),
                physical.DDR_STRICT_MINIMUM.encode(), routed_fixture())

    def test_measured_identity_hash_output_and_mixed_modes_are_rejected(self):
        self.strict_parent(True)
        original = self.evidence_path.read_text()
        for key, value in (('directory', str(self.base / 'other')),
                           ('candidate_identity', 'different'), ('user_code', 'C11030F3'),
                           ('physical_input_inventory_reverified_after_pnr', False)):
            evidence = json.loads(original); evidence[key] = value
            self.evidence_path.write_text(json.dumps(evidence)); self.evidence_sha = sha(self.evidence_path)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'measured parent identity'):
                self.prepare()
            self.assertFalse(self.output.exists())
        self.evidence_path.write_text(original); self.evidence_sha = sha(self.evidence_path)
        self.route.write_text(self.route.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'drifted'):
            self.prepare()
        with self.assertRaisesRegex(ValueError, 'mutually exclusive'):
            self.prepare(dqs_hold_regions=True)
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
