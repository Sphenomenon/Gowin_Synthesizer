#!/usr/bin/env python3
"""No-panel policy fixtures and old-candidate refusal; no no-panel VG claim."""

from pathlib import Path
from types import SimpleNamespace
import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_runtime_shared_cdc import (
    NO_LOCAL_PANEL_PRECISION, audit_selected_shared, audit_shared_constraints,
    validate_precision_profile,
)
from tools.workstation_usb2_owner_reset import (
    NO_LOCAL_PANEL_PROFILE, NO_LOCAL_PANEL_SOURCE, NO_LOCAL_PANEL_CONFIGURATION_SHA256,
    validate_profile as validate_reset_profile,
)
from tools.workstation_recording_policy import metadata as recording_metadata
from tools.workstation_runtime_clock_audit import verify_synthesis_identity
from tools.workstation_board_peripherals import LCD_SDC


class DeclaredNoPanelPolicy(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        config = json.loads((ROOT / "boards/custom_138k/workstation_profile_r00_v1.json").read_text())["configuration"]
        config["local_panel_policy"] = "disabled_local_lcd_touch_v1"
        self.source = self.root / NO_LOCAL_PANEL_SOURCE
        self.source.parent.mkdir(parents=True)
        self.source.write_text(json.dumps(dict(configuration=config)))
        self.profile = dict(schema=1, profile=NO_LOCAL_PANEL_PROFILE, profile_source=NO_LOCAL_PANEL_SOURCE,
            profile_sha256="a" * 64, configuration=config,
            recognition=dict(policy="disabled_cnn_and_follow_v1", music_analysis_enabled=False,
                             cnn_score_follow_enabled=False, constraints=dict(enabled=False)),
            recording=dict(recording_metadata(), address_map={}))

    def both(self, profile=None):
        value = self.profile if profile is None else profile
        validate_precision_profile(self.root, value, NO_LOCAL_PANEL_PRECISION)
        validate_reset_profile(self.root, value, NO_LOCAL_PANEL_PROFILE)

    def test_fixed_configuration_and_historical_descriptor_are_explicit(self):
        actual = hashlib.sha256(json.dumps(self.profile["configuration"], sort_keys=True,
                                          separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(actual, NO_LOCAL_PANEL_CONFIGURATION_SHA256)
        self.both()
        self.source.write_text(json.dumps(dict(configuration=self.profile["configuration"],
                                              purpose="source locks refreshed after preparation")))
        self.both()

    def test_candidate_and_current_descriptor_cannot_change_configuration_together(self):
        for field, value in [("local_panel_policy", "enabled"), ("high_speed_allowed", 1),
                             ("recording_policy", "legacy"), ("unreviewed_policy", True)]:
            profile = copy.deepcopy(self.profile)
            profile["configuration"][field] = value
            self.source.write_text(json.dumps(dict(configuration=profile["configuration"])))
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "supported configuration changed"):
                    validate_precision_profile(self.root, profile, NO_LOCAL_PANEL_PRECISION)
                with self.assertRaisesRegex(ValueError, "supported configuration changed"):
                    validate_reset_profile(self.root, profile, NO_LOCAL_PANEL_PROFILE)

    def test_malformed_digest_source_and_old_profile_identity_are_rejected(self):
        changes = [lambda p: p.update(profile_sha256="bad"),
                   lambda p: p.update(profile_sha256="a" * 63),
                   lambda p: p.update(profile_source="boards/custom_138k/workstation_profile_r00_v1.json"),
                   lambda p: p.update(profile="custom138k-workstation-r00-v1")]
        for change in changes:
            profile = copy.deepcopy(self.profile)
            change(profile)
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    validate_precision_profile(self.root, profile, NO_LOCAL_PANEL_PRECISION)
                with self.assertRaises(ValueError):
                    validate_reset_profile(self.root, profile, NO_LOCAL_PANEL_PROFILE)

    def test_disabled_recognition_and_exact_owner8_metadata_remain_required(self):
        for section, field, value in [("recognition", "music_analysis_enabled", True),
                                      ("recording", "owner", 7),
                                      ("recording", "physical_cdc_accepted", True)]:
            profile = copy.deepcopy(self.profile)
            profile[section][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_precision_profile(self.root, profile, NO_LOCAL_PANEL_PRECISION)

    def test_old_modes_and_unknown_modes_cannot_inherit_no_panel_identity(self):
        for precision in ("runtime-r00-v1", "runtime-no-cnn-v1", "runtime-r00-no-local-panel-v2"):
            with self.subTest(precision=precision), self.assertRaises(ValueError):
                validate_precision_profile(self.root, self.profile, precision)
        for profile in ("custom138k-workstation-r00-v1", "custom138k-workstation-no-cnn-v1"):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                validate_reset_profile(self.root, self.profile, profile)
        with self.assertRaisesRegex(ValueError, "explicit runtime-no-cnn"):
            audit_shared_constraints(self.root, Path("/unused"), "", precision_profile=NO_LOCAL_PANEL_PRECISION,
                                     usb2_owner_reset=True)

    def test_lcd_constraints_or_cells_cannot_remain_in_no_panel_scope(self):
        for sdc, cells, expected in [(LCD_SDC, {}, "SDC retains retired LCD"),
                                     ("", {"u_lcd/u_pll/PLL_inst": {}}, "netlist retains retired LCD")]:
            with self.subTest(expected=expected), self.assertRaisesRegex(ValueError, expected):
                audit_selected_shared(self.root, Path("/unused"), SimpleNamespace(cells=cells), None,
                    sdc, self.profile, precision_profile=NO_LOCAL_PANEL_PRECISION)


class SealedOldCandidateRefusal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stage = os.environ.get("GW138K_OLD_R00_STAGE")
        process = os.environ.get("GW138K_OLD_R00_PROCESS")
        if not stage or not process:
            raise unittest.SkipTest("select old sealed R00 stage/process for identity-refusal check; no EDA fallback")
        cls.stage, cls.process = Path(stage), Path(process)
        cls.before = verify_synthesis_identity(cls.stage, cls.process)
        cls.profile = json.loads((cls.stage.parents[1] / "workstation_profile.json").read_text())

    @classmethod
    def tearDownClass(cls):
        if cls.before != verify_synthesis_identity(cls.stage, cls.process):
            raise AssertionError("old candidate source seal changed")

    def test_old_r00_cannot_be_relabelled_as_no_panel_shared_scope(self):
        with self.assertRaisesRegex(ValueError, "prepared R00 no-local-panel"):
            audit_shared_constraints(ROOT, self.stage, "not parsed after wrong-profile refusal",
                                     precision_profile=NO_LOCAL_PANEL_PRECISION)

    def test_old_r00_cannot_be_relabelled_as_no_panel_reset_scope(self):
        with self.assertRaisesRegex(ValueError, "explicit prepared profile required"):
            validate_reset_profile(ROOT, self.profile, NO_LOCAL_PANEL_PROFILE)


if __name__ == "__main__":
    unittest.main()
