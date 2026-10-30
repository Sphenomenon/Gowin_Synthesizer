#!/usr/bin/env python3
"""Read-only shared-CDC audit with explicit selected runtime scope.

Default `generic` delegates to the unchanged generic 157-line checker. The
`runtime-no-cnn-v1` and `runtime-r00-v1` precision profiles check their exact
retained installed scope; neither turns missing endpoints into optional
selectors. The latter excludes the additional native recording CDC. No EDA or
hardware operation is performed, and physical/deployment gates remain false.
"""

from collections import defaultdict
from pathlib import Path
import argparse
import fnmatch
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.workstation_custom_clocks import shared_cdc_bundle, audit_shared_cdc
from tools.workstation_runtime_profile import shared_constraints
from tools.workstation_recognition_policy import RETIRED_LINES, verify_adaptation
from tools.workstation_runtime_pcm_cdc import PcmNetlist, Graph, TOP, COMB
from tools.workstation_usb2_owner_reset import (
    OwnerResetNetlist, audit_reset_structure, installed_sources,
    NO_LOCAL_PANEL_PROFILE, NO_LOCAL_PANEL_SOURCE, NO_LOCAL_PANEL_CONFIGURATION_SHA256,
)
from tools.workstation_recording_policy import (
    POLICY as R00_RECORDING_POLICY, metadata as recording_metadata,
    verify_address_map as verify_recording_address_map,
)
from tools.workstation_runtime_clock_audit import (
    AUDIT_SOURCES as CLOCK_SOURCES,
    VG_RELATIVE,
    audit_runtime_clocks,
    verify_synthesis_identity,
    file_sha,
)

NO_LOCAL_PANEL_PRECISION = "runtime-r00-no-local-panel-v1"
PRECISION_PROFILES = ("generic", "runtime-no-cnn-v1", "runtime-r00-v1", NO_LOCAL_PANEL_PRECISION)
R00_PRECISIONS = ("runtime-r00-v1", NO_LOCAL_PANEL_PRECISION)
NO_CNN_SOURCE = "boards/custom_138k/workstation_profile_no_cnn_v1.json"
R00_SOURCE = "boards/custom_138k/workstation_profile_r00_v1.json"
PROFILE_SOURCES = {"runtime-no-cnn-v1": NO_CNN_SOURCE, "runtime-r00-v1": R00_SOURCE,
                   NO_LOCAL_PANEL_PRECISION: NO_LOCAL_PANEL_SOURCE}
PROFILE_NAMES = {"runtime-no-cnn-v1": "custom138k-workstation-no-cnn-v1",
                 "runtime-r00-v1": "custom138k-workstation-r00-v1",
                 NO_LOCAL_PANEL_PRECISION: NO_LOCAL_PANEL_PROFILE}
# Exact supported R00 configuration, canonical JSON (sorted keys, no spaces).
# Descriptive profile bytes may evolve, but a future LCD-off configuration
# needs an explicit retirement/topology review rather than inheriting 88 lines.
R00_CONFIGURATION_SHA256 = "b5c30ab0d1d4ec9b3470599f390596f1cf618c52a20b643522b19ed7e3746313"
AUDIT_SOURCES = (
    *CLOCK_SOURCES,
    "tools/workstation_runtime_shared_cdc.py",
    "tools/workstation_runtime_profile.py",
    "tools/workstation_recognition_policy.py",
    "tools/workstation_runtime_pcm_cdc.py",
    "tools/workstation_runtime_cdc.py",
    "tools/workstation_custom_usb2_cdc.py",
    NO_CNN_SOURCE,
    R00_SOURCE,
    "tools/workstation_recording_policy.py",
    "sim/test_workstation_runtime_shared_cdc.py",
    "sim/test_workstation_runtime_r00_shared_cdc.py",
    "sim/test_workstation_no_local_panel_precision.py",
    "tools/WORKSTATION_RUNTIME_SHARED_CDC.md",
    "tools/workstation_usb2_owner_reset.py",
    "sim/test_workstation_usb2_owner_reset.py",
)


def validate_precision_profile(root, profile, precision_profile):
    require(
        precision_profile in PRECISION_PROFILES,
        "unknown precision profile: " + precision_profile,
    )
    if precision_profile == "generic":
        return
    is_r00 = precision_profile in R00_PRECISIONS
    no_panel = precision_profile == NO_LOCAL_PANEL_PRECISION
    source_name = PROFILE_SOURCES[precision_profile]
    require(
        profile.get("schema") == 1
        and profile.get("profile") == PROFILE_NAMES[precision_profile]
        and profile.get("profile_source") == source_name,
        "precision profile requires the prepared " + ("R00 no-local-panel" if no_panel else "R00" if is_r00 else "no-CNN") + " v1 profile",
    )
    source = Path(root) / source_name
    config = json.loads(source.read_text())
    require(
        profile.get("configuration") == config.get("configuration")
        and re.fullmatch(r"[0-9a-f]{64}", profile.get("profile_sha256", ""))
        is not None,
        "precision profile configuration or historical source identity differs",
    )
    # Descriptive profile bytes may have changed since preparation. The complete
    # configuration must match; the prepared digest is recorded as historical
    # provenance, never reasserted as current-root byte equivalence.
    recognition = profile.get("recognition", {})
    require(
        recognition.get("policy") == "disabled_cnn_and_follow_v1"
        and recognition.get("music_analysis_enabled") is False
        and recognition.get("cnn_score_follow_enabled") is False
        and recognition.get("constraints", {}).get("enabled") is False,
        "precision profile requires exact disabled recognition policy",
    )
    if is_r00:
        recording = profile.get("recording", {})
        expected = recording_metadata()
        expected_configuration = NO_LOCAL_PANEL_CONFIGURATION_SHA256 if no_panel else R00_CONFIGURATION_SHA256
        require(sha(json.dumps(profile["configuration"], sort_keys=True, separators=(",", ":")).encode())
                == expected_configuration, "precision profile R00 supported configuration changed")
        require(
            profile["configuration"].get("recording_policy") == R00_RECORDING_POLICY
            and {key: value for key, value in recording.items() if key != "address_map"} == expected
            and isinstance(recording.get("address_map"), dict),
            "precision profile requires exact R00 owner8 recording policy metadata",
        )


def require(c, m):
    if not c:
        raise ValueError("installed runtime shared CDC review: " + m)


def sha(b):
    return hashlib.sha256(b).hexdigest()


class SelectorIndex:
    """Name-only expansion cache for one parsed netlist inventory.

    Fresh public audits construct a fresh index. The regression reuses this
    index only while changing existing binding values/graph edges, never names
    or port inventories; the complete structural checks still run each time.
    """

    def __init__(self, n, g):
        self.universes = {
            "get_regs": frozenset(g.regs),
            "get_pins": frozenset(
                p + "/" + pin
                for p, c in n.cells.items()
                if c["kind"] not in n.modules
                for pin in c["ports"]
            ),
        }
        self.matches = {}

    def expand(self, kind, member):
        key = kind, member
        if key not in self.matches:
            self.matches[key] = tuple(
                sorted(
                    p for p in self.universes[kind] if fnmatch.fnmatchcase(p, member)
                )
            )
        return self.matches[key]


def select(n, g, kind, body, *, index=None):
    require(kind in ("get_regs", "get_pins"), "unknown selector kind: " + kind)
    index = index or SelectorIndex(n, g)
    result = {}
    for member in body.split():
        if member.startswith("u_memory/u_ddr3/gw3_top/"):
            result[member] = dict(opaque_ddr_deferred=True, matches=[])
            continue
        matches = list(index.expand(kind, member))
        require(matches, "empty retained selector member: " + member)
        result[member] = dict(opaque_ddr_deferred=False, matches=matches)
    return result


def group(g, scope, stem, bits=None):
    return (
        g.group(scope, stem, bits)
        if isinstance(bits, int)
        else (
            [g.register(scope, stem, i) for i in bits]
            if bits is not None
            else g.group(scope, stem)
        )
    )


def bitmap(paths, stem):
    result = {}
    for p in paths:
        m = re.fullmatch(re.escape(stem) + r"_(\d+)_s\d+", p)
        require(m is not None, "unexpected payload register: " + p)
        k = int(m[1])
        require(k not in result, "duplicate payload bit: " + p)
        result[k] = p
    return result


def ff(n, g, p, clock, reset=None):
    c = n.cells[p]
    require(c["kind"] == "DFFCE", "synchronizer FF kind: " + p)
    require(
        g.drivers[n.pin(p, "Q")] == [(p, "Q")],
        "synchronizer Q driver absent/ambiguous: " + p,
    )
    require(n.pin(p, "CLK") == clock, "synchronizer clock: " + p)
    require(n.pin(p, "CE") in g.high, "conditional synchronizer CE: " + p)
    require("CLEAR" in c["ports"], "synchronizer CLEAR missing: " + p)
    if reset is not None:
        require(n.pin(p, "CLEAR") == reset, "synchronizer reset mismatch: " + p)
    return dict(
        path=p,
        kind=c["kind"],
        clock=clock,
        clear=n.pin(p, "CLEAR"),
        d=n.pin(p, "D"),
        q=n.pin(p, "Q"),
    )


def pair(n, g, first, second, clock, source_net=None, recovery_gate=False):
    a = ff(n, g, first, clock)
    b = ff(n, g, second, clock, a["clear"])
    if source_net is not None:
        require(a["d"] == source_net, "first D producer changed: " + first)
    proof = None
    if recovery_gate:
        guard = g.register("u_memory/u_recovery", "controller_reset_n")
        gate = n.pin(guard, "Q")
        require(n.pin(guard, "CLK") == clock, "recovery gate source domain changed")
        proof = g.equivalent(
            "reviewed recovery synchronous-zero gate",
            [a["q"], b["d"], gate],
            lambda v: v[1] == (v[0] & v[2]),
        )
        proof["source_D"] = g.equivalent(
            "reviewed recovery first D synchronous-zero gate",
            [a["d"], "memory_calibrated", gate],
            lambda v: v[0] == (v[1] & v[2]),
            cuts=("memory_calibrated",),
        )
    else:
        require(a["q"] == b["d"], "first Q to second D changed: " + first)
    ends = g.closure([first])
    require(
        ends["endpoints"] == {second + "/D": clock}
        and ends["combinational_cells"] == int(recovery_gate),
        "first Q complete fanout changed: " + first,
    )
    complete = full_closure(n, g, [first])
    require(
        not complete["top_output_endpoints"]
        and not complete["ram_input_endpoints"]
        and complete["ff_endpoints"] == {second + "/D": clock},
        "first Q has physical/primitive export: " + first,
    )
    return dict(
        first=a,
        second=b,
        first_q_complete_fanout=ends,
        complete_first_Q_endpoints=complete,
        reviewed_recovery_synchronous_zero_gate=proof,
    )


# Every false-path first-D member in the installed shared bundle is independently
# declared here. Bit vectors are indexed, never discovered from source D values.
MAILBOXES = (
    ("u_runtime/u_cpu_cdc", "ram_clk", "clk_50m"),
    ("u_cpu_ddr", "ram_clk", "memory_clk"),
    ("u_ui_control", "ram_clk", "memory_clk"),
    ("u_runtime/u_performance_cdc", "audio_clk", "clk_50m"),
    ("u_runtime/u_usb_cdc", "usb_clk", "clk_50m"),
    ("u_native_usb/input_owner/feedback", "audio_clk", "usb_clk"),
    ("u_display_push_cdc", "memory_clk", "usb_clk"),
    ("u_service_push_cdc", "audio_clk", "usb_clk"),
    ("u_tf_control_cdc", "audio_clk", "clk_50m"),
)
# Status sources intentionally remain status sources. Their digital cone is
# inventoried below; this does not prove glitch freedom or physical pulse width.
STATUS = (
    (
        "u_video",
        "flags_meta",
        "flags_sync",
        8,
        "clk_50m",
        (
            "memory_calibrated",
            "u_video/bist_done",
            "u_video/bist_failed",
            "u_video/front_valid_Z",
            "u_video/memory_status[4]",
            "u_video/memory_status[5]",
            "memory_pll_locked",
            "u_video/startup_pipe[4]",
        ),
    ),
    (
        "u_video/u_diagnostics",
        "flags_meta",
        "flags_sync",
        5,
        "clk_50m",
        (
            "hdmi_hpd",
            "u_video/startup_pipe[4]",
            "u_video/pixel_reset_n",
            "u_video/pixel_reset_pipe[2]",
            "u_video/serializer_reset",
        ),
    ),
    (
        "u_runtime",
        "flags_meta",
        "flags_sync",
        2,
        "clk_50m",
        ("audio_locked", "audio_reset_n"),
    ),
)
# R00 BIST status is exported through the wrapper, and the newer renderer uses
# front_valid without the old _Z suffix. The RTL producers stay explicit:
# u_bist.done/failed and u_scanout.front_valid, all in the memory clock domain.
R00_VIDEO_STATUS = (
    "memory_calibrated", "bist_done", "bist_failed", "u_video/front_valid",
    "u_video/memory_status[4]", "u_video/memory_status[5]", "memory_pll_locked",
    "u_video/startup_pipe[4]",
)
# The LCD-off composition retains the original front_valid_Z alias. Keep this
# spelling confined to its explicit profile; the same source FF Q is required.
R00_NO_LOCAL_PANEL_VIDEO_STATUS = (
    "memory_calibrated", "bist_done", "bist_failed", "u_video/front_valid_Z",
    "u_video/memory_status[4]", "u_video/memory_status[5]", "memory_pll_locked",
    "u_video/startup_pipe[4]",
)
R00_VIDEO_REGISTERED_STATUS = {
    1: ("u_video/u_bist", "done"),
    2: ("u_video/u_bist", "failed"),
    3: ("u_video/u_scanout", "front_valid"),
}


def audit_r00_status_rtl(stage, *, precision_profile="runtime-r00-v1"):
    relative = "rtl/workstation/workstation_hdmi_display.sv"
    path = Path(stage) / relative
    text = re.sub(r"\s+", "", re.sub(r"/\*.*?\*/|//[^\n]*", "", path.read_text(), flags=re.S))
    fragments = (
        "ddr3_bistu_bist(.clk(memory_clk),.rst_n(ui_rst_n)",
        ".done(bist_done),.failed(bist_failed),.error_count(bist_errors)",
        ".front_bank(front_bank),.front_valid(front_valid)",
        "wire[31:0]memory_status={24'd0,video_locked,memory_pll_locked,(underruns!=0),"
        "(fetch_fault||arbiter_fault||shared_load_fault),front_valid,bist_failed,bist_done,memory_calibrated};",
        "flags_meta<=memory_status[7:0];flags_sync<=flags_meta;",
    )
    require(all(text.count(fragment) == 1 for fragment in fragments), "R00 video status RTL contract changed")
    nets = R00_NO_LOCAL_PANEL_VIDEO_STATUS if precision_profile == NO_LOCAL_PANEL_PRECISION else R00_VIDEO_STATUS
    return dict(source=relative, sha256=file_sha(path), status_bits_1_2_3="BIST done, BIST failed, scanout front_valid",
                source_fragment_contract_verified=True, renamed_nets=list(nets[1:4]))


def producer_cone(n, g, net, active=()):
    """Complete LUT/INV cone to FF Q or exact named external boundary.

    Only the named DDR calibrated output, PLL LOCK and actual top-level HPD
    input are permitted external producers. Unknown/ambiguous drivers fail.
    """
    if net in g.high | g.low:
        return {
            "constants": [net],
            "registers": {},
            "boundaries": {},
            "combinational": {},
        }
    if net == "hdmi_hpd":
        require(
            n.directions[TOP].get(net) == "input"
            and n.cells["hdmi_hpd_ibuf"]["kind"] == "IBUF"
            and n.pin("hdmi_hpd_ibuf", "I") == net,
            "HPD boundary changed",
        )
        return {
            "constants": [],
            "registers": {},
            "boundaries": {net: "top input hdmi_hpd through IBUF"},
            "combinational": {},
        }
    if net == "memory_calibrated":
        p = "u_memory/u_ddr3/gw3_top"
        require(
            n.cells[p]["kind"] == "~GW_DDR3_PHY_MC.DDR3_Memory_Interface_Top"
            and n.pin(p, "memory_calibrated") == net,
            "DDR calibrated boundary changed",
        )
        return {
            "constants": [],
            "registers": {},
            "boundaries": {net: p + "/memory_calibrated (opaque producer)"},
            "combinational": {},
        }
    if net == "u_memory/u_pll/pll_lock":
        p = "u_memory/u_pll/u_pll_0/PLL_inst"
        require(
            n.cells[p]["kind"] == "PLL" and n.pin(p, "LOCK") == net,
            "PLL lock boundary changed",
        )
        return {
            "constants": [],
            "registers": {},
            "boundaries": {net: p + "/LOCK"},
            "combinational": {},
        }
    require(net not in active, "producer combinational cycle: " + net)
    ds = g.drivers[net]
    require(len(ds) == 1, "producer absent/ambiguous: " + net)
    p, port = ds[0]
    if p in g.regs:
        require(port == "Q", "non-Q FF producer: " + p)
        return {
            "constants": [],
            "registers": {
                p: dict(clock=n.pin(p, "CLK"), q=net, kind=n.cells[p]["kind"])
            },
            "boundaries": {},
            "combinational": {},
        }
    c = n.cells[p]
    require(
        c["kind"] == "INV" or re.fullmatch("LUT[1-6]", c["kind"]),
        "unsupported producer primitive: " + p,
    )
    inputs = (
        ["I"]
        if c["kind"] == "INV"
        else ["I" + str(i) for i in range(int(c["kind"][3:]))]
    )
    result = {
        "constants": [],
        "registers": {},
        "boundaries": {},
        "combinational": {
            p: dict(
                kind=c["kind"],
                parameters=c["parameters"],
                ports={x: n.pin(p, x) for x in c["ports"]},
            )
        },
    }
    for x in inputs:
        part = producer_cone(n, g, n.pin(p, x), (*active, net))
        for k in ("registers", "boundaries", "combinational"):
            result[k].update(part[k])
        result["constants"].extend(part["constants"])
    result["constants"] = sorted(set(result["constants"]))
    return result


def audit_syncs(n, g, installed_first, *, precision_profile="runtime-no-cnn-v1"):
    records = []

    def add(scope, a, b, clock, source_net, source=None):
        if scope:
            first = g.register(scope, a)
            second = g.register(scope, b)
        else:
            firsts = [p for p in g.regs if re.fullmatch(re.escape(a) + r"_s\d+", p)]
            seconds = [p for p in g.regs if re.fullmatch(re.escape(b) + r"_s\d+", p)]
            require(
                len(firsts) == len(seconds) == 1,
                "root synchronizer inventory changed: " + a,
            )
            first, second = firsts[0], seconds[0]
        source_function = None
        if source_net is None:
            require(
                scope == "u_memory/u_recovery"
                or (scope == "u_native_usb/input_owner" and a == "defaults_sync_0"),
                "source discovery outside exact reviewed functional boundary",
            )
            source_net = n.pin(first, "D")
            if scope == "u_native_usb/input_owner":
                source_function = g.equivalent(
                    "USB defaults source follows existing mode policy",
                    [source_net, "u_native_usb/generic_midi", "u_native_usb/gw25k"],
                    lambda v: v[0] == int(not v[1] or v[2]),
                )
        record = pair(
            n,
            g,
            first,
            second,
            clock,
            source_net,
            recovery_gate=scope == "u_memory/u_recovery",
        )
        record["source_function_proof"] = source_function
        record["producer"] = producer_cone(n, g, source_net)
        if source is not None:
            require(
                g.drivers[source_net] == [(source, "Q")],
                "registered source Q identity: " + first,
            )
            record["registered_source"] = source
        record["source_waveform_and_physical_safety_verified"] = False
        records.append(record)

    s = "u_video/u_scanout"
    for a, b, c, d in (
        ("request_meta", "request_sync", "memory_clk", "request_toggle"),
        ("ack_meta", "ack_sync", "u_video/pixel_clk", "ack_toggle"),
        ("done0_meta", "done0_sync", "u_video/pixel_clk", "done0_toggle"),
        ("done1_meta", "done1_sync", "u_video/pixel_clk", "done1_toggle"),
    ):
        src = g.register(s, d)
        add(s, a, b, c, n.pin(src, "Q"), src)
    for s, source_clock, dest_clock in MAILBOXES:
        for a, b, d, c, sc in (
            ("req_meta", "req_sync", "request_toggle", dest_clock, source_clock),
            ("ack_meta", "ack_sync", "acknowledge_toggle", source_clock, dest_clock),
        ):
            src = g.register(s, d)
            require(n.pin(src, "CLK") == sc, "toggle source clock: " + src)
            add(s, a, b, c, n.pin(src, "Q"), src)
    for s, a, b, width, c, nets in STATUS:
        r00_video = precision_profile in R00_PRECISIONS and s == "u_video"
        if r00_video:
            nets = R00_NO_LOCAL_PANEL_VIDEO_STATUS if precision_profile == NO_LOCAL_PANEL_PRECISION else R00_VIDEO_STATUS
        for bit in range(width):
            source = None
            if r00_video and bit in R00_VIDEO_REGISTERED_STATUS:
                source = g.register(*R00_VIDEO_REGISTERED_STATUS[bit])
                require(n.pin(source, "CLK") == "memory_clk", "R00 video status source clock changed")
            add(s, a + "_" + str(bit), b + "_" + str(bit), c, nets[bit], source)
    add("u_memory/u_recovery", "calibrated_meta", "calibrated_sync", "clk_50m", None)
    add("", "tf_format_meta50", "tf_format_sync50", "clk_50m", "tf_format_ready")
    add("", "tf_source_meta50", "tf_source_sync50", "clk_50m", "tf_busy50")
    usb = "u_native_usb/input_owner"
    for a, b, c, d in (
        (
            "settled_sync_0",
            "settled_sync_1",
            "usb_clk",
            "u_native_usb/input_owner/input_settled",
        ),
        (
            "panic_sync_0",
            "panic_sync_1",
            "audio_clk",
            "u_native_usb/input_owner/panic_toggle",
        ),
        ("defaults_sync_0", "defaults_sync_1", "audio_clk", None),
    ):
        add(usb, a, b, c, d)
    actual = {x["first"]["path"] + "/D" for x in records}
    require(
        actual == installed_first,
        "installed false-path first-D coverage differs: missing="
        + str(sorted(installed_first - actual))
        + " extra="
        + str(sorted(actual - installed_first)),
    )
    require(len(records) == 43, "first-D bit count changed")
    return records


GRAY = (
    (
        "u_video/u_scanout",
        "under_gray",
        "under_meta",
        "under_sync",
        32,
        "u_video/pixel_clk",
        "memory_clk",
    ),
    (
        "u_video/u_diagnostics",
        "pixel_block_gray",
        "pixel_block_meta",
        "pixel_block_sync",
        16,
        "u_video/pixel_clk",
        "clk_50m",
    ),
    (
        "u_video/u_diagnostics",
        "pixel_frame_gray",
        "pixel_frame_meta",
        "pixel_frame_sync",
        32,
        "u_video/pixel_clk",
        "clk_50m",
    ),
    (
        "u_video/u_diagnostics",
        "memory_rendered_gray",
        "memory_rendered_meta",
        "memory_rendered_sync",
        32,
        "memory_clk",
        "clk_50m",
    ),
    (
        "u_video/u_diagnostics",
        "memory_underrun_gray",
        "memory_underrun_meta",
        "memory_underrun_sync",
        32,
        "memory_clk",
        "clk_50m",
    ),
    (
        "u_runtime",
        "sample_gray",
        "sample_meta",
        "sample_sync",
        32,
        "audio_clk",
        "clk_50m",
    ),
    (
        "u_playlist_bridge/fifo",
        "read_gray",
        "read_gray_meta",
        "read_gray_sync",
        3,
        "usb_clk",
        "clk_50m",
    ),
    (
        "u_playlist_bridge/fifo",
        "write_gray",
        "write_gray_meta",
        "write_gray_sync",
        3,
        "clk_50m",
        "usb_clk",
    ),
)


def full_closure(n, g, sources):
    """Complete graph endpoint list; RAM inputs are explicit local endpoints.

    Graph's unknown primitive bindings include both directions. Accept only
    documented RAM input pins, and fail if a source reaches anything else.
    """
    todo = [n.pin(p, "Q") for p in sources]
    seen = set()
    ends = {}
    ram = {}
    comb = set()
    exports = {}
    if not hasattr(g, "_shared_top_outputs"):
        g._shared_top_outputs = {
            n.canonical("", bit): name
            for name, direction in n.directions[TOP].items()
            if direction in ("output", "inout")
            for bit in g.binding_bits("", name)
        }
    top_outputs = g._shared_top_outputs
    while todo:
        net = todo.pop()
        if net in seen:
            continue
        seen.add(net)
        if net in top_outputs:
            exports[top_outputs[net]] = net
        for p, pin, role in g.fan[net]:
            if role == "ff":
                ends[p + "/" + pin] = n.pin(p, "CLK")
            elif role == "comb":
                comb.add(p)
                todo.extend(n.pin(p, out) for out in COMB[n.cells[p]["kind"]])
            else:
                c = n.cells[p]
                require(
                    c["kind"] == "RAM16SDP4"
                    and pin in ("DI", "WAD", "RAD", "WRE", "CLK"),
                    "unexpected primitive consumer: " + p + "/" + pin,
                )
                ram[p + "/" + pin] = {"kind": c["kind"], "clock": n.pin(p, "CLK")}
    return {
        "ff_endpoints": dict(sorted(ends.items())),
        "ram_input_endpoints": dict(sorted(ram.items())),
        "combinational_cells": len(comb),
        "top_output_endpoints": dict(sorted(exports.items())),
    }


def audit_gray(n, g):
    groups = []
    covered = set()
    for s, src, a, b, width, sc, dc in GRAY:
        source = group(
            g,
            s,
            src,
            width if not (src == "read_gray" and s.startswith("u_playlist")) else 2,
        )
        if src == "read_gray" and s.startswith("u_playlist"):
            source.append(g.register(s, "read_binary", 2))
        first = group(g, s, a, width)
        second = group(g, s, b, width)
        rows = []
        for bit, (p, f, z) in enumerate(zip(source, first, second)):
            require(n.pin(p, "CLK") == sc, "Gray producer clock: " + p)
            require(
                g.drivers[n.pin(p, "Q")] == [(p, "Q")], "Gray producer ambiguous: " + p
            )
            row = pair(n, g, f, z, dc, n.pin(p, "Q"))
            row["registered_source"] = p
            rows.append(row)
        closure = full_closure(n, g, source)
        expected = {p + "/D": dc for p in first}
        foreign = {p: c for p, c in closure["ff_endpoints"].items() if c != sc}
        require(
            foreign == expected,
            "Gray full foreign-consumer inventory changed: " + s + "/" + src,
        )
        require(
            all(v["clock"] == sc for v in closure["ram_input_endpoints"].values()),
            "Gray pointer reaches foreign RAM input: " + src,
        )
        require(
            not closure["top_output_endpoints"],
            "Gray source exports outside synchronized boundary: " + src,
        )
        covered.update(first)
        groups.append(
            dict(
                scope=s,
                source_stem=src,
                registered_sources=source,
                source_clock=sc,
                destination_clock=dc,
                bits=rows,
                complete_source_fanout=closure,
                gray_sequence_behavior_verified=False,
                physical_bounds_verified=False,
            )
        )
    require(sum(len(x["bits"]) for x in groups) == 182, "Gray bit inventory changed")
    return groups, covered


# Actual surviving payload pairs. Exact live bit indexes must agree at both
# ends; direct data is checked by index. Source counts include synthesis pruning.
PAYLOAD = (
    (
        "u_video/u_scanout",
        "held_request",
        "request_word",
        20,
        "u_video/pixel_clk",
        "memory_clk",
    ),
    ("u_video/u_scanout", "done0_tag", "tag0", 19, "memory_clk", "u_video/pixel_clk"),
    ("u_video/u_scanout", "done1_tag", "tag1", 19, "memory_clk", "u_video/pixel_clk"),
    ("u_runtime/u_cpu_cdc", "held_data", "destination_data", 224, "ram_clk", "clk_50m"),
    ("u_cpu_ddr", "request_held", "request_local", 93, "ram_clk", "memory_clk"),
    ("u_cpu_ddr", "response_held", "response_local", 64, "memory_clk", "ram_clk"),
    ("u_ui_control", "request_held", "request_local", 49, "ram_clk", "memory_clk"),
    ("u_ui_control", "response_held", "response_local", 33, "memory_clk", "ram_clk"),
    (
        "u_runtime/u_performance_cdc",
        "held_data",
        "destination_data",
        380,
        "audio_clk",
        "clk_50m",
    ),
    ("u_runtime/u_usb_cdc", "held_data", "destination_data", 194, "usb_clk", "clk_50m"),
    (
        "u_native_usb/input_owner/feedback",
        "held_data",
        "destination_data",
        152,
        "audio_clk",
        "usb_clk",
    ),
    ("u_display_push_cdc", "held_data", "destination_data", 3, "memory_clk", "usb_clk"),
    ("u_service_push_cdc", "held_data", "destination_data", 34, "audio_clk", "usb_clk"),
    ("u_tf_control_cdc", "held_data", "destination_data", 24, "audio_clk", "clk_50m"),
)


def audit_payloads(n, g):
    result = []
    covered = set()
    for s, a, b, width, sc, dc in PAYLOAD:
        src = bitmap(
            [
                p
                for p in g.regs
                if re.fullmatch(re.escape(s + "/" + a) + r"_\d+_s\d+", p)
            ],
            s + "/" + a,
        )
        dst = bitmap(
            [
                p
                for p in g.regs
                if re.fullmatch(re.escape(s + "/" + b) + r"_\d+_s\d+", p)
            ],
            s + "/" + b,
        )
        require(
            len(src) == width and set(src) == set(dst),
            "held payload bit inventory: " + s + "/" + a,
        )
        proofs = []
        for bit, p in src.items():
            q = dst[bit]
            require(
                n.pin(p, "CLK") == sc and n.pin(q, "CLK") == dc,
                "held payload clock: " + p,
            )
            require(
                g.drivers[n.pin(p, "Q")] == [(p, "Q")], "held source ambiguous: " + p
            )
            if a == "held_request":
                own = n.pin(q, "Q")
                origin = n.pin(p, "Q")
                d = n.pin(q, "D")
                controls = [
                    "u_video/active",
                    "u_video/request_pending",
                    "u_video/u_scanout/ack_toggle",
                    "u_video/u_scanout/request_settled",
                ]
                support = set(g.support(d))
                require(
                    support == {own, origin, *controls},
                    "scanout capture cone inputs changed",
                )
                proof = g.equivalent(
                    "scanout request bit " + str(bit),
                    [d, origin, own, *controls],
                    lambda v: v[0]
                    == (v[1] if (not v[3] and not v[4] and v[5] != v[6]) else v[2]),
                )
                proofs.append(proof)
            else:
                require(
                    n.pin(q, "D") == n.pin(p, "Q"),
                    "held payload direct bit mapping changed: " + q,
                )
        closure = full_closure(n, g, src.values())
        expected = {p + "/D": dc for p in dst.values()}
        require(
            closure["ff_endpoints"] == expected
            and not closure["ram_input_endpoints"]
            and not closure["top_output_endpoints"],
            "held payload complete consumer inventory changed: " + s + "/" + a,
        )
        covered.update(dst.values())
        result.append(
            dict(
                scope=s,
                source_stem=a,
                target_stem=b,
                source_clock=sc,
                destination_clock=dc,
                live_bit_indexes=sorted(src),
                source_registers=src,
                destination_registers=dst,
                complete_source_fanout=closure,
                capture_function_proofs=proofs,
                held_stability_and_handshake_behavior_verified=False,
                physical_bounds_verified=False,
            )
        )
    return result, covered


def audit_selected_shared(
    root, stage, n, g, sdc, profile, *, precision_profile, selector_index=None
):
    validate_precision_profile(root, profile, precision_profile)
    no_panel = precision_profile == NO_LOCAL_PANEL_PRECISION
    if no_panel:
        require(not any("u_lcd/" in line or "lcd_pixel31m5" in line for line in sdc.splitlines()),
                "no-local-panel SDC retains retired LCD constraints/clock")
        require(not any(p == "u_lcd" or p.startswith("u_lcd/") for p in n.cells),
                "no-local-panel netlist retains retired LCD cells")
    r00_status_rtl = audit_r00_status_rtl(stage, precision_profile=precision_profile) if precision_profile in R00_PRECISIONS else None
    generic = shared_cdc_bundle(stage)
    runtime = shared_constraints(generic["sdc"])
    verify_adaptation(sdc, profile["recognition"]["constraints"], False)
    require(
        len(generic["sdc"].splitlines()) == 157
        and len(runtime["sdc"].splitlines()) == 105
        and len(runtime["omitted"]) == 52
        and len(runtime["adapted"]) == 4,
        "runtime scope selection changed",
    )
    retired = [line for line in runtime["sdc"].splitlines() if line in RETIRED_LINES]
    selected = [
        line for line in runtime["sdc"].splitlines() if line not in RETIRED_LINES
    ]
    require(
        len(retired) == 17 and len(selected) == 88,
        "disabled-recognition shared retirement scope changed",
    )
    for line in selected:
        require(
            sdc.splitlines().count(line) == 1,
            "retained shared constraint not installed exactly once: " + line,
        )
    for line in retired:
        require(
            line not in sdc.splitlines(),
            "retired recognition shared line remains installed",
        )
    selector_index = selector_index or SelectorIndex(n, g)
    queries = {}
    installed_first = set()
    pins_by_role = defaultdict(set)
    max_targets = set()
    for line in selected:
        require(
            line.startswith(("set_false_path ", "set_max_delay ")),
            "unknown shared command",
        )
        qs = re.findall(r"\[(get_regs|get_pins) \{([^}]+)\}\]", line)
        require(qs, "shared command lost exact query")
        for kind, body in qs:
            key = kind + " {" + body + "}"
            if key not in queries:
                queries[key] = select(n, g, kind, body, index=selector_index)
            for member, entry in queries[key].items():
                if not entry["opaque_ddr_deferred"]:
                    for p in entry["matches"]:
                        if kind == "get_pins":
                            pins_by_role[p.rsplit("/", 1)[1]].add(p)
        if line.startswith("set_false_path -to "):
            for kind, body in qs:
                if kind == "get_pins":
                    installed_first.update(
                        p
                        for entry in queries[kind + " {" + body + "}"].values()
                        for p in entry["matches"]
                        if p.endswith("/D")
                    )
        if line.startswith("set_max_delay ") and qs[-1][0] == "get_regs":
            max_targets.update(
                p
                for entry in queries["get_regs {" + qs[-1][1] + "}"].values()
                for p in entry["matches"]
            )
    syncs = audit_syncs(n, g, installed_first, precision_profile=precision_profile)
    gray, gray_targets = audit_gray(n, g)
    payloads, payload_targets = audit_payloads(n, g)
    require(
        max_targets == gray_targets | payload_targets,
        "retained shared max-delay destination coverage changed",
    )
    # List the broad wildcard overmatch explicitly. The true source is separately
    # declared in GRAY and checked by D; none of these 12 extra FFs is ignored.
    broad = {}
    for stem in ("read_gray", "write_gray"):
        scope = "u_playlist_bridge/fifo"
        matches = {
            p for p in g.regs if fnmatch.fnmatchcase(p, scope + "/" + stem + "*")
        }
        expected = (
            set(group(g, scope, stem, 2 if stem == "read_gray" else 3))
            | set(group(g, scope, stem + "_meta", 3))
            | set(group(g, scope, stem + "_sync", 3))
        )
        require(matches == expected, "playlist broad source wildcard inventory changed")
        broad[stem] = dict(
            matches=sorted(matches),
            actual_source=[p for p in gray if p["source_stem"] == stem][0][
                "registered_sources"
            ],
        )
    deferred = {
        key: value
        for key, value in queries.items()
        if all(x["opaque_ddr_deferred"] for x in value.values())
    }
    require(len(deferred) == 13, "opaque DDR query count changed")
    reset_inventory = {
        p: dict(kind=n.cells[p.rsplit("/", 1)[0]]["kind"], net=n.pin(*p.rsplit("/", 1)))
        for role, ps in pins_by_role.items()
        if role != "D"
        for p in sorted(ps)
    }
    require(
        len(reset_inventory) == 110, "reset/primitive retained pin inventory changed"
    )
    return dict(
        schema=1,
        scope=("selected_r00_no_local_panel_runtime_retained_shared_constraints_source_structure_only"
               if no_panel else "selected_r00_runtime_retained_shared_constraints_source_structure_only"
               if precision_profile == "runtime-r00-v1" else
               "selected_no_cnn_runtime_retained_shared_constraints_source_structure_only"),
        precision_profile=precision_profile,
        profile_policy_evidence=dict(
            prepared_profile_source_sha256=profile["profile_sha256"],
            current_configuration_source_sha256=file_sha(Path(root) / PROFILE_SOURCES[precision_profile]),
            complete_configuration_equal=True,
            current_root_profile_bytes_equivalence_claimed=False,
            supported_r00_configuration_sha256=(R00_CONFIGURATION_SHA256 if precision_profile == "runtime-r00-v1" else None),
            supported_no_local_panel_configuration_sha256=(NO_LOCAL_PANEL_CONFIGURATION_SHA256 if no_panel else None),
        ),
        reviewed_r00_status_rtl=r00_status_rtl,
        no_local_panel_policy_evidence=(dict(lcd_constraints_absent=True, lcd_cells_absent=True,
            lcd_constraints_inside_retained_shared_count=0, touch_retirement_delegated_to_public_clock_audit=True)
            if no_panel else None),
        generic_constraints=157,
        runtime_selected_constraints=105,
        runtime_omitted=runtime["omitted"],
        runtime_adapted=runtime["adapted"],
        recognition_shared_retired=retired,
        installed_shared_constraints=selected,
        installed_shared_constraint_count=88,
        installed_shared_sdc_sha256=sha(("\n".join(selected) + "\n").encode()),
        query_inventory=queries,
        deferred_opaque_ddr_queries=deferred,
        false_path_first_stage_bits=43,
        first_stage_pairs=syncs,
        gray_group_count=8,
        gray_first_stage_bits=182,
        gray_groups=gray,
        payload_group_count=len(payloads),
        payload_bits=sum(len(x["live_bit_indexes"]) for x in payloads),
        payload_groups=payloads,
        playlist_broad_selector_inventory=broad,
        reset_and_primitive_pin_inventory=reset_inventory,
        installed_query_resolution_verified=True,
        first_D_and_second_shift_and_complete_first_Q_consumers_verified=True,
        payload_source_to_capture_endpoint_structure_verified=True,
        default_generic_checker_modified=False,
        source_waveform_and_held_handshake_behavior_verified=False,
        all_reset_semantics_verified=False,
        full_reset_accepted=False,
        whole_workstation_cdc_accepted=False,
        recording_cdc_accepted=False,
        recording_cdc_scope=dict(
            policy=profile.get("configuration", {}).get("recording_policy"),
            additional_native_recording_present=precision_profile in R00_PRECISIONS,
            included_in_selected_shared_scope=False,
            excluded_native_scopes=(
                ["u_recording/pcm_cdc", "u_recording/commands", "u_recording/seal_cdc",
                 "u_recording/service", "u_recording/native_commit", "u_video/u_arbiter/g_recording/u_core"]
                if precision_profile in R00_PRECISIONS else []),
            source_structure_verified=False, physical_cdc_accepted=False,
        ),
        tool_query_resolution_verified=False,
        physical_cdc_verified=False,
        physical_cdc_accepted=False,
        routed_timing_verified=False,
        constraints_complete=False,
        deployment_allowed=False,
        hardware_tested=False,
        release_ready=False,
        remaining=[
            "Exact opaque DDR internal endpoints and implementation-time queries",
            "Status-cone glitch/pulse behavior and held-payload protocol behavior",
            "Full shared reset assertion/release source semantics and physical recovery/removal",
            "Post-route propagation/skew/MTBF and both switched clock modes",
            "Full workstation endpoint inventory and hardware acceptance",
            "R00 native recording CDC, service/native commit and owner8 arbiter are outside this retained shared scope",
        ],
    )


def audit_shared_constraints(root, stage, netlist_text, *, precision_profile="generic", usb2_owner_reset=False):
    """Object-scope entry; default behavior is the unchanged generic checker."""
    require(
        precision_profile in PRECISION_PROFILES,
        "unknown precision profile: " + precision_profile,
    )
    require(not usb2_owner_reset or precision_profile == "runtime-no-cnn-v1",
            "USB2 owner reset needs explicit runtime-no-cnn-v1 scope")
    if precision_profile == "generic":
        return dict(audit_shared_cdc(stage, netlist_text), precision_profile="generic")
    stage = Path(stage)
    profile = json.loads((stage.parents[1] / "workstation_profile.json").read_text())
    validate_precision_profile(root, profile, precision_profile)
    n = (OwnerResetNetlist if usb2_owner_reset else PcmNetlist)(netlist_text, TOP)
    g = Graph(n)
    sdc = (stage / "constraints/custom_138k.sdc").read_text()
    result = audit_selected_shared(
        root,
        stage,
        n,
        g,
        sdc,
        profile,
        precision_profile=precision_profile,
    )
    if precision_profile in R00_PRECISIONS:
        verify_recording_address_map(root, stage, profile["recording"]["address_map"])
    if usb2_owner_reset:
        result["usb2_owner_reset"] = dict(audit_reset_structure(n, g, sdc),
                                           sources=installed_sources(root, stage))
    return result


def run_audit(root, stage, evidence, *, precision_profile="generic", usb2_owner_reset=False):
    root, stage = Path(root), Path(stage)
    require(
        precision_profile in PRECISION_PROFILES,
        "unknown precision profile: " + precision_profile,
    )
    before = verify_synthesis_identity(stage, evidence)
    audit_sources = (*AUDIT_SOURCES, NO_LOCAL_PANEL_SOURCE) if precision_profile == NO_LOCAL_PANEL_PRECISION else AUDIT_SOURCES
    sources = {p: file_sha(root / p) for p in audit_sources}
    text = (stage / VG_RELATIVE).read_text()
    result = audit_shared_constraints(
        root, stage, text, precision_profile=precision_profile, usb2_owner_reset=usb2_owner_reset
    )
    if precision_profile != "generic":
        result["clock_audit"] = audit_runtime_clocks(root, stage, text)
        if precision_profile == NO_LOCAL_PANEL_PRECISION:
            require(result["clock_audit"].get("local_panel_enabled") is False,
                    "no-local-panel precision requires its explicit disabled-panel clock audit")
    after = verify_synthesis_identity(stage, evidence)
    require(
        before == after and sources == {p: file_sha(root / p) for p in audit_sources},
        "synthesis or audit inputs drifted during review",
    )
    identity = sha(
        json.dumps(
            dict(
                policy="selected-runtime-shared-cdc-source-v1",
                precision_profile=precision_profile,
                usb2_owner_reset=usb2_owner_reset,
                synthesis=before,
                audit_sources=sources,
            ),
            sort_keys=True,
        ).encode()
    )
    result.update(
        identity="selected-shared-cdc-source-v1-" + identity[:16],
        source_set_sha256=identity,
        synthesis=before,
        audit_source_sha256=sources,
        source_seal_before_and_after=True,
        eda_invoked=False,
        hardware_operated=False,
        constraints_complete=False,
        physical_cdc_accepted=False,
        routed_timing_verified=False,
        hardware_tested=False,
        deployment_allowed=False,
        release_ready=False,
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--synthesis-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--precision-profile",
        choices=PRECISION_PROFILES,
        default="generic",
        help="generic preserves the existing checker; runtime-no-cnn-v1/runtime-r00-v1/runtime-r00-no-local-panel-v1 explicitly selects the exact retained scope",
    )
    parser.add_argument("--usb2-owner-reset", action="store_true",
                        help="Additionally audit the new exact reset chain; only with explicit runtime-no-cnn-v1")
    args = parser.parse_args()
    result = run_audit(
        ROOT,
        args.project,
        args.synthesis_evidence,
        precision_profile=args.precision_profile,
        usb2_owner_reset=args.usb2_owner_reset,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "identity",
                    "precision_profile",
                    "source_seal_before_and_after",
                    "constraints_complete",
                    "physical_cdc_accepted",
                    "deployment_allowed",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
