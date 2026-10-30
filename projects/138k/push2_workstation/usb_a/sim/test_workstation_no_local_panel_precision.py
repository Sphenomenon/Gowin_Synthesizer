#!/usr/bin/env python3
"""No-panel policy, old-candidate refusal and optional sealed actual-VG checks."""

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
    NO_LOCAL_PANEL_PRECISION, SelectorIndex, audit_selected_shared, audit_shared_constraints,
    validate_precision_profile,
)
from tools.workstation_usb2_owner_reset import (
    NO_LOCAL_PANEL_PROFILE, NO_LOCAL_PANEL_SOURCE, NO_LOCAL_PANEL_CONFIGURATION_SHA256,
    validate_profile as validate_reset_profile,
)
from tools.workstation_recording_policy import metadata as recording_metadata
from tools.workstation_runtime_clock_audit import verify_synthesis_identity
from tools.workstation_board_peripherals import LCD_SDC
from tools.workstation_runtime_pcm_cdc import PcmNetlist, Graph, TOP
from tools.workstation_runtime_clock_audit import VG_RELATIVE


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


class ActualNoPanelRetainedShared(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stage = os.environ.get("GW138K_NO_PANEL_SHARED_CDC_STAGE")
        process = os.environ.get("GW138K_NO_PANEL_SHARED_CDC_PROCESS")
        if not stage or not process:
            raise unittest.SkipTest("select sealed no-panel stage/process; no EDA fallback")
        cls.stage, cls.process = Path(stage), Path(process)
        cls.before = verify_synthesis_identity(cls.stage, cls.process)
        cls.profile = json.loads((cls.stage.parents[1] / "workstation_profile.json").read_text())
        cls.sdc = (cls.stage / "constraints/custom_138k.sdc").read_text()
        cls.n = PcmNetlist((cls.stage / VG_RELATIVE).read_text(), TOP)
        cls.index = SelectorIndex(cls.n, Graph(cls.n))
        cls.negatives = []

    @classmethod
    def actual(cls):
        return audit_selected_shared(ROOT, cls.stage, cls.n, Graph(cls.n), cls.sdc, cls.profile,
            precision_profile=NO_LOCAL_PANEL_PRECISION, selector_index=cls.index)

    @classmethod
    def tearDownClass(cls):
        if cls.before != verify_synthesis_identity(cls.stage, cls.process):
            raise AssertionError("sealed actual no-panel synthesis inputs changed")
        output = os.environ.get("GW138K_NO_PANEL_SHARED_CDC_TEST_EVIDENCE")
        if output:
            Path(output).write_text(json.dumps(dict(schema=1, synthesis=cls.before,
                mutations=cls.negatives, mutation_count=len(cls.negatives),
                actual_no_panel_netlist_objects=True, original_vg_rewritten=False,
                source_seal_before_and_after=True, eda_invoked=False, hardware_operated=False,
                recording_cdc_accepted=False, physical_cdc_accepted=False, deployment_allowed=False), indent=2) + "\n")

    def test_actual_no_panel_keeps_all_shared_endpoints_and_exact_status_producer(self):
        result = self.actual()
        self.assertEqual((result["installed_shared_constraint_count"], result["false_path_first_stage_bits"],
            result["gray_group_count"], result["gray_first_stage_bits"], result["payload_group_count"],
            result["payload_bits"]), (88, 43, 8, 182, 14, 1308))
        self.assertEqual(len(result["query_inventory"]), 89)
        self.assertEqual(len(result["reset_and_primitive_pin_inventory"]), 110)
        self.assertEqual(len(result["deferred_opaque_ddr_queries"]), 13)
        for line in LCD_SDC.splitlines():
            self.assertNotIn(line, self.sdc.splitlines())
        self.assertFalse(any(p.startswith("u_lcd/") for p in self.n.cells))
        for bit, source, net in [(1, "u_video/u_bist/done_s0", "bist_done"),
                                 (2, "u_video/u_bist/failed_s0", "bist_failed"),
                                 (3, "u_video/u_scanout/front_valid_s0", "u_video/front_valid_Z")]:
            record = next(x for x in result["first_stage_pairs"]
                          if x["first"]["path"] == "u_video/flags_meta_" + str(bit) + "_s0")
            self.assertEqual(record["registered_source"], source)
            self.assertEqual(self.n.pin(source, "Q"), net)
            self.assertEqual(self.n.pin(source, "CLK"), "memory_clk")
        for key in ("full_reset_accepted", "whole_workstation_cdc_accepted", "recording_cdc_accepted",
                    "tool_query_resolution_verified", "physical_cdc_accepted", "routed_timing_verified",
                    "constraints_complete", "hardware_tested", "deployment_allowed", "release_ready"):
            self.assertFalse(result[key], key)

    def test_actual_no_panel_alias_producer_and_fanout_negatives(self):
        cases = [("done replaced by failed", "u_video/flags_meta_1_s0", "D", "bist_failed", "first D producer changed"),
                 ("failed replaced by done", "u_video/flags_meta_2_s0", "D", "bist_done", "first D producer changed"),
                 ("front-valid replaced by done", "u_video/flags_meta_3_s0", "D", "bist_done", "first D producer changed"),
                 ("old R00 alias not optional", "u_video/flags_meta_3_s0", "D", "front_valid", "first D producer changed"),
                 ("front-valid wrong clock", "u_video/u_scanout/front_valid_s0", "CLK", "usb_clk", "R00 video status source clock changed"),
                 ("front-valid disconnected", "u_video/u_scanout/front_valid_s0", "Q", "negative_disconnected", "producer absent/ambiguous"),
                 ("BIST wrong clock", "u_video/u_bist/done_s0", "CLK", "usb_clk", "R00 video status source clock changed"),
                 ("BIST disconnected", "u_video/u_bist/done_s0", "Q", "negative_disconnected", "producer absent/ambiguous"),
                 ("first Q extra CE consumer", "u_video/flags_meta_7_s0", "CE", self.n.cells["u_video/flags_meta_1_s0"]["ports"]["Q"], "first Q complete fanout changed")]
        for label, path, pin, value, expected in cases:
            old = self.n.cells[path]["ports"][pin]
            self.n.cells[path]["ports"][pin] = value
            try:
                with self.subTest(case=label), self.assertRaisesRegex(ValueError, expected) as error:
                    self.actual()
                self.negatives.append(dict(case=label, rejected=True, error=str(error.exception)))
            finally:
                self.n.cells[path]["ports"][pin] = old
        self.actual()


if __name__ == "__main__":
    unittest.main()
