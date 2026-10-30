#!/usr/bin/env python3
"""Explicit R00 policy and optional sealed actual-VG retained-scope checks."""

from pathlib import Path
import json
import os
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_runtime_shared_cdc import (
    R00_SOURCE, SelectorIndex, audit_selected_shared, audit_shared_constraints,
    run_audit, validate_precision_profile,
)
from tools.workstation_recording_policy import metadata as recording_metadata
from tools.workstation_runtime_clock_audit import file_sha, verify_synthesis_identity, VG_RELATIVE
from tools.workstation_runtime_pcm_cdc import PcmNetlist, Graph, TOP
from tools.workstation_board_peripherals import LCD_SDC


class R00PrecisionPolicy(unittest.TestCase):
    def profile(self):
        return dict(schema=1, profile="custom138k-workstation-r00-v1",
                    profile_source=R00_SOURCE, profile_sha256=file_sha(ROOT / R00_SOURCE),
                    configuration=json.loads((ROOT / R00_SOURCE).read_text())["configuration"],
                    recognition=dict(policy="disabled_cnn_and_follow_v1", music_analysis_enabled=False,
                                     cnn_score_follow_enabled=False, constraints=dict(enabled=False)),
                    recording=dict(recording_metadata(), address_map={}))

    def test_explicit_r00_policy_and_historical_profile_digest(self):
        profile = self.profile()
        validate_precision_profile(ROOT, profile, "runtime-r00-v1")
        # The synthesis seal authenticates the prepared source. Descriptive
        # active-root profile changes do not make historical bytes equivalent.
        profile["profile_sha256"] = "a" * 64
        validate_precision_profile(ROOT, profile, "runtime-r00-v1")

    def test_r00_does_not_select_no_cnn_or_unknown_scope(self):
        with self.assertRaisesRegex(ValueError, "prepared no-CNN"):
            validate_precision_profile(ROOT, self.profile(), "runtime-no-cnn-v1")
        for precision in ("runtime-r00", "runtime-r00-v2", "auto"):
            with self.subTest(precision=precision), self.assertRaisesRegex(ValueError, "unknown precision"):
                audit_shared_constraints(ROOT, Path("/unused"), "", precision_profile=precision)
        with self.assertRaisesRegex(ValueError, "explicit runtime-no-cnn"):
            audit_shared_constraints(ROOT, Path("/unused"), "", precision_profile="runtime-r00-v1",
                                     usb2_owner_reset=True)

    def test_configuration_recognition_and_profile_identity_fail_closed(self):
        changes = [lambda p: p.update(profile="custom138k-workstation-no-cnn-v1"),
                   lambda p: p.update(profile_source=R00_SOURCE.replace("r00", "no_cnn")),
                   lambda p: p.update(profile_sha256="invalid"),
                   lambda p: p["configuration"].update(recording_policy="legacy"),
                   lambda p: p["configuration"].update(lcd_policy="retired"),
                   lambda p: p["recognition"].update(cnn_score_follow_enabled=True),
                   lambda p: p["recognition"]["constraints"].update(enabled=True)]
        for change in changes:
            profile = self.profile()
            change(profile)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "precision profile"):
                validate_precision_profile(ROOT, profile, "runtime-r00-v1")

    def test_future_lcd_off_config_cannot_inherit_current_scope(self):
        profile = self.profile()
        profile["configuration"]["lcd_policy"] = "retired"
        with patch("pathlib.Path.read_text", return_value=json.dumps(dict(configuration=profile["configuration"]))):
            with self.assertRaisesRegex(ValueError, "supported configuration changed"):
                validate_precision_profile(ROOT, profile, "runtime-r00-v1")

    def test_exact_owner8_recording_metadata_is_required_but_not_accepted(self):
        changes = [lambda r: r.update(policy="legacy"), lambda r: r.update(owner=7),
                   lambda r: r.update(owner_bits=3), lambda r: r.update(source_cdc_complete=True),
                   lambda r: r.update(physical_cdc_accepted=True), lambda r: r.pop("pcm_cdc"),
                   lambda r: r.pop("address_map"), lambda r: r.update(unreviewed_backend=True)]
        for change in changes:
            profile = self.profile()
            change(profile["recording"])
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "R00 owner8 recording"):
                validate_precision_profile(ROOT, profile, "runtime-r00-v1")


class ActualR00RetainedShared(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stage = os.environ.get("GW138K_R00_SHARED_CDC_STAGE")
        process = os.environ.get("GW138K_R00_SHARED_CDC_PROCESS")
        if not stage or not process:
            raise unittest.SkipTest("select sealed R00 stage/process with GW138K_R00_SHARED_CDC_STAGE/PROCESS; no EDA fallback")
        cls.stage, cls.process = Path(stage), Path(process)
        cls.before = verify_synthesis_identity(cls.stage, cls.process)
        cls.profile = json.loads((cls.stage.parents[1] / "workstation_profile.json").read_text())
        cls.sdc = (cls.stage / "constraints/custom_138k.sdc").read_text()
        cls.n = PcmNetlist((cls.stage / VG_RELATIVE).read_text(), TOP)
        cls.index = SelectorIndex(cls.n, Graph(cls.n))
        cls.negatives = []
        cls.baseline = cls.actual()

    @classmethod
    def actual(cls):
        return audit_selected_shared(ROOT, cls.stage, cls.n, Graph(cls.n), cls.sdc, cls.profile,
                                     precision_profile="runtime-r00-v1", selector_index=cls.index)

    @classmethod
    def tearDownClass(cls):
        if cls.before != verify_synthesis_identity(cls.stage, cls.process):
            raise AssertionError("sealed actual R00 synthesis inputs changed")
        output = os.environ.get("GW138K_R00_SHARED_CDC_TEST_EVIDENCE")
        if output:
            Path(output).write_text(json.dumps(dict(schema=1, synthesis=cls.before,
                mutations=cls.negatives, mutation_count=len(cls.negatives),
                actual_b9a2_netlist_objects=True, original_vg_rewritten=False,
                source_seal_before_and_after=True, eda_invoked=False, hardware_operated=False,
                recording_cdc_accepted=False, physical_cdc_accepted=False, deployment_allowed=False), indent=2) + "\n")

    def test_actual_sealed_r00_scope_keeps_lcd_and_excludes_new_recording(self):
        result = run_audit(ROOT, self.stage, self.process, precision_profile="runtime-r00-v1")
        self.assertEqual((result["installed_shared_constraint_count"], result["false_path_first_stage_bits"],
                          result["gray_group_count"], result["gray_first_stage_bits"],
                          result["payload_group_count"], result["payload_bits"]), (88, 43, 8, 182, 14, 1308))
        self.assertEqual(len(result["query_inventory"]), 89)
        self.assertEqual(len(result["reset_and_primitive_pin_inventory"]), 110)
        self.assertEqual(len(result["deferred_opaque_ddr_queries"]), 13)
        # The four peripheral LCD commands are outside the shared 88-line
        # bundle. Preserve them in the sealed full SDC without claiming their
        # endpoint structures were accepted by this partial shared audit.
        self.assertEqual(len(LCD_SDC.splitlines()), 4)
        for line in LCD_SDC.splitlines():
            self.assertEqual(self.sdc.splitlines().count(line), 1)
        self.assertFalse(any("u_lcd/" in key for key in result["query_inventory"]))
        r00 = result["recording_cdc_scope"]
        self.assertTrue(r00["additional_native_recording_present"])
        self.assertFalse(r00["included_in_selected_shared_scope"])
        self.assertEqual(r00["excluded_native_scopes"], ["u_recording/pcm_cdc", "u_recording/commands",
            "u_recording/seal_cdc", "u_recording/service", "u_recording/native_commit",
            "u_video/u_arbiter/g_recording/u_core"])
        for key in ("full_reset_accepted", "whole_workstation_cdc_accepted", "recording_cdc_accepted",
                    "tool_query_resolution_verified", "physical_cdc_accepted", "routed_timing_verified",
                    "constraints_complete", "hardware_tested", "deployment_allowed", "release_ready"):
            self.assertFalse(result[key], key)
        self.assertTrue(result["source_seal_before_and_after"])
        for bit, producer in [(1, "u_video/u_bist/done_s0"), (2, "u_video/u_bist/failed_s0"),
                              (3, "u_video/u_scanout/front_valid_s0")]:
            record = next(x for x in result["first_stage_pairs"] if x["first"]["path"] == "u_video/flags_meta_" + str(bit) + "_s0")
            self.assertEqual(record["registered_source"], producer)
        output = os.environ.get("GW138K_R00_SHARED_CDC_POSITIVE_EVIDENCE")
        if output:
            Path(output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    def test_actual_r00_status_alias_producers_and_fanout_fail_closed(self):
        cases = [("BIST done replaced by failed", "u_video/flags_meta_1_s0", "D", "bist_failed", "first D producer changed"),
                 ("BIST failed replaced by done", "u_video/flags_meta_2_s0", "D", "bist_done", "first D producer changed"),
                 ("front_valid replaced by BIST", "u_video/flags_meta_3_s0", "D", "bist_done", "first D producer changed"),
                 ("BIST producer wrong clock", "u_video/u_bist/done_s0", "CLK", "usb_clk", "R00 video status source clock changed"),
                 ("BIST producer disconnected", "u_video/u_bist/done_s0", "Q", "negative_disconnected", "producer absent/ambiguous"),
                 ("status first Q gains CE consumer", "u_video/flags_meta_7_s0", "CE",
                  self.n.cells["u_video/flags_meta_1_s0"]["ports"]["Q"], "first Q complete fanout changed")]
        for label, path, pin, value, expected in cases:
            old = self.n.cells[path]["ports"][pin]
            self.n.cells[path]["ports"][pin] = value
            try:
                with self.subTest(case=label), self.assertRaisesRegex(ValueError, expected) as error:
                    self.actual()
                self.negatives.append(dict(case=label, rejected=True, expected_error_regex=expected,
                                           error=str(error.exception)))
            finally:
                self.n.cells[path]["ports"][pin] = old
        # All mutated values have been restored; the exact positive structure
        # must still pass before rechecking the original 584-file source seal.
        self.actual()


if __name__ == "__main__":
    unittest.main()
