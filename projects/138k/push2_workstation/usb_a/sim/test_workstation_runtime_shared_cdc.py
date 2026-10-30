#!/usr/bin/env python3
"""Explicit profile policy plus sealed actual-netlist structural corruptions."""

from pathlib import Path
import copy
import json
import os
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_runtime_shared_cdc import (
    NO_CNN_SOURCE,
    SelectorIndex,
    audit_selected_shared,
    audit_shared_constraints,
    run_audit,
    select,
    validate_precision_profile,
)
from tools.workstation_runtime_pcm_cdc import PcmNetlist, Graph, TOP
from tools.workstation_runtime_clock_audit import (
    VG_RELATIVE,
    file_sha,
    verify_synthesis_identity,
)
from tools.workstation_recognition_policy import adapt_constraints


class PrecisionProfilePolicy(unittest.TestCase):
    def profile(self):
        return dict(
            schema=1,
            profile="custom138k-workstation-no-cnn-v1",
            profile_source=NO_CNN_SOURCE,
            profile_sha256=file_sha(ROOT / NO_CNN_SOURCE),
            configuration=json.loads((ROOT / NO_CNN_SOURCE).read_text())[
                "configuration"
            ],
            recognition=dict(
                policy="disabled_cnn_and_follow_v1",
                music_analysis_enabled=False,
                cnn_score_follow_enabled=False,
                constraints=dict(enabled=False),
            ),
        )

    def test_default_delegates_to_unchanged_generic_scope(self):
        with patch(
            "tools.workstation_runtime_shared_cdc.audit_shared_cdc",
            return_value={"constraints": 157},
        ) as original:
            result = audit_shared_constraints(
                ROOT, Path("/unused"), "original VG bytes"
            )
        original.assert_called_once_with(Path("/unused"), "original VG bytes")
        self.assertEqual(result["constraints"], 157)
        self.assertEqual(result["precision_profile"], "generic")

    def test_no_implicit_or_unknown_precision_selection(self):
        with self.assertRaisesRegex(ValueError, "unknown precision profile"):
            audit_shared_constraints(
                ROOT, Path("/unused"), "", precision_profile="runtime"
            )
        validate_precision_profile(ROOT, {}, "generic")
        with self.assertRaisesRegex(ValueError, "prepared no-CNN"):
            validate_precision_profile(ROOT, {}, "runtime-no-cnn-v1")
        validate_precision_profile(ROOT, self.profile(), "runtime-no-cnn-v1")

    def test_recording_profile_is_explicitly_outside_precision_scope(self):
        profile = self.profile()
        profile.update(profile="custom138k-workstation-r00-v1")
        with self.assertRaisesRegex(ValueError, "prepared no-CNN"):
            validate_precision_profile(ROOT, profile, "runtime-no-cnn-v1")

    def test_recognition_configuration_and_source_identity_fail_closed(self):
        changes = [
            lambda p: p.update(profile="custom138k-workstation-v1"),
            lambda p: p.update(profile_sha256="invalid-digest"),
            lambda p: p["configuration"].update(hdmi_mode="720p60"),
            lambda p: p["recognition"].update(music_analysis_enabled=True),
            lambda p: p["recognition"]["constraints"].update(enabled=True),
        ]
        for change in changes:
            with self.subTest(change=change):
                p = self.profile()
                change(p)
                with self.assertRaisesRegex(ValueError, "precision profile"):
                    validate_precision_profile(ROOT, p, "runtime-no-cnn-v1")


class ActualSelectedSharedCdc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stage = os.environ.get("GW138K_SHARED_CDC_STAGE")
        process = os.environ.get("GW138K_SHARED_CDC_PROCESS")
        if not stage or not process:
            raise unittest.SkipTest(
                "select sealed no-CNN v1 stage/process with GW138K_SHARED_CDC_STAGE/PROCESS; no EDA fallback"
            )
        cls.stage, cls.process = Path(stage), Path(process)
        cls.before = verify_synthesis_identity(cls.stage, cls.process)
        cls.profile = json.loads(
            (cls.stage.parents[1] / "workstation_profile.json").read_text()
        )
        cls.sdc = (cls.stage / "constraints/custom_138k.sdc").read_text()
        cls.n = PcmNetlist((cls.stage / VG_RELATIVE).read_text(), TOP)
        cls.g = Graph(cls.n)
        cls.negatives = []
        cls.selector_index = SelectorIndex(cls.n, cls.g)
        # An unrelated profile/metadata refusal must never make structural
        # negatives appear to pass. Establish the unchanged object first.
        cls.baseline = audit_selected_shared(
            ROOT,
            cls.stage,
            cls.n,
            cls.g,
            cls.sdc,
            cls.profile,
            precision_profile="runtime-no-cnn-v1",
            selector_index=cls.selector_index,
        )

    @classmethod
    def tearDownClass(cls):
        if verify_synthesis_identity(cls.stage, cls.process) != cls.before:
            raise AssertionError("sealed original changed during in-memory negatives")
        output = os.environ.get("GW138K_SHARED_CDC_TEST_EVIDENCE")
        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    dict(
                        schema=1,
                        vg_sha256=cls.before["vg_sha256"],
                        mutations=cls.negatives,
                        mutation_count=len(cls.negatives),
                        source_seal_before_and_after=True,
                        actual_netlist_object_mutations=True,
                        original_vg_rewritten=False,
                        eda_invoked=False,
                        hardware_operated=False,
                        physical_cdc_accepted=False,
                        deployment_allowed=False,
                    ),
                    indent=2,
                )
                + "\n"
            )

    def actual(self, *, sdc=None, profile=None):
        return audit_selected_shared(
            ROOT,
            self.stage,
            self.n,
            self.g,
            self.sdc if sdc is None else sdc,
            self.profile if profile is None else profile,
            precision_profile="runtime-no-cnn-v1",
            selector_index=self.selector_index,
        )

    def rejected(self, label, action, undo, check=None):
        action()
        try:
            expected = {
                "toggle first D disconnected": "first D producer changed",
                "second-stage shift broken": "first Q to second D changed",
                "first-stage clock changed": "synchronizer clock",
                "second-stage clock changed": "synchronizer clock",
                "first-stage conditional CE": "conditional synchronizer CE",
                "second-stage conditional CE": "conditional synchronizer CE",
                "second-stage reset mismatch": "synchronizer reset mismatch",
                "extra asynchronous first Q consumer": "first Q complete fanout changed",
                "extra enable first Q consumer": "first Q complete fanout changed",
                "empty selector member hidden inside valid union": "empty retained selector member",
                "playlist Gray source bit swapped": "first D producer changed",
                "held payload destination disconnected": "held payload direct bit mapping changed",
                "recovery AND changed to OR at calibrated_meta": "reviewed recovery first D synchronous-zero gate",
                "recovery AND changed to OR at calibrated_sync": "reviewed recovery synchronous-zero gate",
            }[label]
            with self.assertRaisesRegex(ValueError, expected) as error:
                (check or self.actual)()
            self.negatives.append(
                dict(
                    case=label,
                    rejected=True,
                    expected_error_regex=expected,
                    error=str(error.exception),
                )
            )
        finally:
            undo()

    def test_sealed_installed_scope_and_all_deployment_gates_false(self):
        result = run_audit(
            ROOT, self.stage, self.process, precision_profile="runtime-no-cnn-v1"
        )
        self.assertEqual(
            (
                result["installed_shared_constraint_count"],
                result["false_path_first_stage_bits"],
                result["gray_group_count"],
                result["gray_first_stage_bits"],
                result["payload_group_count"],
                result["payload_bits"],
            ),
            (88, 43, 8, 182, 14, 1308),
        )
        output = os.environ.get("GW138K_SHARED_CDC_POSITIVE_EVIDENCE")
        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        self.assertEqual(len(result["deferred_opaque_ddr_queries"]), 13)
        self.assertEqual(len(result["reset_and_primitive_pin_inventory"]), 110)
        self.assertEqual(len(result["query_inventory"]), 89)
        self.assertTrue(result["source_seal_before_and_after"])
        self.assertEqual(
            sum(
                bool(x["reviewed_recovery_synchronous_zero_gate"])
                for x in result["first_stage_pairs"]
            ),
            1,
        )
        for key in (
            "source_waveform_and_held_handshake_behavior_verified",
            "all_reset_semantics_verified",
            "tool_query_resolution_verified",
            "physical_cdc_verified",
            "physical_cdc_accepted",
            "routed_timing_verified",
            "constraints_complete",
            "hardware_tested",
            "deployment_allowed",
            "release_ready",
        ):
            self.assertFalse(result[key], key)

    def test_fourteen_actual_netlist_corruptions_are_rejected(self):
        n, g = self.n, self.g
        a = g.register("u_runtime/u_cpu_cdc", "req_meta")
        b = g.register("u_runtime/u_cpu_cdc", "req_sync")
        cases = [
            (a, "D", "1'b0", "toggle first D disconnected"),
            (b, "D", "1'b0", "second-stage shift broken"),
            (a, "CLK", "1'b0", "first-stage clock changed"),
            (b, "CLK", "1'b0", "second-stage clock changed"),
            (a, "CE", "1'b0", "first-stage conditional CE"),
            (b, "CE", "1'b0", "second-stage conditional CE"),
            (b, "CLEAR", "1'b0", "second-stage reset mismatch"),
        ]
        for p, pin, value, label in cases:
            original = n.cells[p]["ports"][pin]
            self.rejected(
                label,
                lambda p=p, pin=pin, value=value: n.cells[p]["ports"].__setitem__(
                    pin, value
                ),
                lambda p=p, pin=pin, original=original: n.cells[p]["ports"].__setitem__(
                    pin, original
                ),
            )
        q = n.pin(a, "Q")
        for pin, label in [
            ("CLEAR", "extra asynchronous first Q consumer"),
            ("CE", "extra enable first Q consumer"),
        ]:
            entry = (a, pin, "ff")
            self.rejected(
                label, lambda: g.fan[q].append(entry), lambda: g.fan[q].remove(entry)
            )
        self.rejected(
            "empty selector member hidden inside valid union",
            lambda: None,
            lambda: None,
            lambda: select(n, g, "get_pins", a + "/D missing_actual_runtime*/D"),
        )
        p = g.register("u_playlist_bridge/fifo", "read_gray_meta", 0)
        other = g.register("u_playlist_bridge/fifo", "read_gray", 1)
        original = n.cells[p]["ports"]["D"]
        self.rejected(
            "playlist Gray source bit swapped",
            lambda: n.cells[p]["ports"].__setitem__("D", n.cells[other]["ports"]["Q"]),
            lambda: n.cells[p]["ports"].__setitem__("D", original),
        )
        p = g.register("u_cpu_ddr", "request_local", 0)
        original = n.cells[p]["ports"]["D"]
        self.rejected(
            "held payload destination disconnected",
            lambda: n.cells[p]["ports"].__setitem__("D", "1'b0"),
            lambda: n.cells[p]["ports"].__setitem__("D", original),
        )
        for stem in ("calibrated_meta", "calibrated_sync"):
            p = g.register("u_memory/u_recovery", stem)
            lut = g.drivers[n.pin(p, "D")][0][0]
            original = n.cells[lut]["parameters"]["INIT"]
            self.assertEqual(original, "4'h8")
            self.rejected(
                "recovery AND changed to OR at " + stem,
                lambda: n.cells[lut]["parameters"].__setitem__("INIT", "4'hE"),
                lambda: n.cells[lut]["parameters"].__setitem__("INIT", original),
            )
        self.assertEqual(len(self.negatives), 14)

    def test_retained_delay_drift_rejected_even_with_recomputed_retirement_metadata(
        self,
    ):
        original_lines = self.sdc.splitlines(keepends=True)
        for row in self.profile["recognition"]["constraints"]["retired"]:
            original_lines.insert(row["line_number"] - 1, row["line"])
        original = "".join(original_lines)
        anchor = "set_max_delay 20.000 -from [get_regs {u_cpu_ddr/request_held*}]"
        self.assertEqual(original.count(anchor), 1)
        changed = original.replace(anchor, anchor.replace("20.000", "200.000"))
        selected, metadata = adapt_constraints(changed, False)
        p = copy.deepcopy(self.profile)
        p["recognition"]["constraints"] = metadata
        with self.assertRaisesRegex(
            ValueError, "retained shared constraint not installed exactly once"
        ):
            self.actual(sdc=selected, profile=p)

    def test_defaults_combination_drift_rejected_by_independent_function(self):
        n, g = self.n, self.g
        first = g.register("u_native_usb/input_owner", "defaults_sync_0")
        lut = g.drivers[n.pin(first, "D")][0][0]
        original = n.cells[lut]["parameters"]["INIT"]
        n.cells[lut]["parameters"]["INIT"] = "4'h0"
        try:
            with self.assertRaisesRegex(
                ValueError, "USB defaults source follows existing mode policy"
            ):
                self.actual()
        finally:
            n.cells[lut]["parameters"]["INIT"] = original


if __name__ == "__main__":
    unittest.main()
