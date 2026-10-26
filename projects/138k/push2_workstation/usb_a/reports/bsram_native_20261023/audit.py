#!/usr/bin/env python3
"""Inventory existing native-workstation RAM evidence without rebuilding it."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
PRIMITIVE = re.compile(
    r"^\s*(SP|SDPB|SDPX9B|SPB|SPX9B|DPB|DPX9B|pROM|pROMX9)\s+\\?(\S+)\s+\(",
    re.M,
)
MODULE = re.compile(r"^module\s+(\S+)\s*\(", re.M)
PARAMETER = re.compile(r"^\s*defparam\s+(.+?)\s*=\s*([^;\n]+);", re.M)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def memory_definitions(path):
    content = path.read_text()
    modules = list(MODULE.finditer(content))
    definitions = {}
    for index, module in enumerate(modules):
        end = modules[index + 1].start() if index + 1 < len(modules) else len(content)
        body = content[module.end():end]
        parameters = {}
        for parameter in PARAMETER.finditer(body):
            instance, key = parameter[1].strip().lstrip("\\").rsplit(".", 1)
            parameters.setdefault(instance.strip(), {})[key] = parameter[2].strip()
        for primitive in PRIMITIVE.finditer(body):
            key = module[1] + "/" + primitive[2]
            definitions[key] = [primitive[1], parameters.get(primitive[2], {})]
    return definitions


def physical_inventory(netlist, report):
    blocks = [
        {"primitive": match[1], "instance": match[2]}
        for match in PRIMITIVE.finditer(netlist.read_text())
    ]
    usage = re.search(r"^\s*BSRAM\s*\|\s*(\d+)/(\d+)\s*\|", report.read_text(), re.M)
    if not usage or len(blocks) != int(usage[1]):
        raise ValueError("Physical primitive inventory does not match P&R report")
    return {
        "netlist": str(netlist.resolve()),
        "netlist_sha256": sha256(netlist),
        "report": str(report.resolve()),
        "report_sha256": sha256(report),
        "used": len(blocks),
        "capacity": int(usage[2]),
        "primitive_types": dict(Counter(block["primitive"] for block in blocks)),
        "top_level": dict(Counter(block["instance"].split("/")[0] for block in blocks)),
        "blocks": blocks,
    }


def synthesis_inventory(directory):
    project = directory / "workstation/Prj1/impl/gwsynthesis"
    netlist = project / "custom_138k_integration.vg"
    resources = project / "custom_138k_integration_syn_rsc.xml"
    manifest = directory / "integration_inputs.json"
    tree = ET.parse(resources).getroot()
    return {
        "identity": json.loads(manifest.read_text())["identity"],
        "manifest_sha256": sha256(manifest),
        "netlist_sha256": sha256(netlist),
        "resource_report_sha256": sha256(resources),
        "equivalent": int(tree.attrib["T_Bsram"].split("(")[0]),
        "top_level": {
            node.attrib["name"]: int(node.attrib["T_Bsram"].split("(")[0])
            for node in tree if "T_Bsram" in node.attrib
        },
    }, memory_definitions(netlist)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path,
                        default=Path.home() / ".cache/fpga-validation-20261023")
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("inventory.json"))
    args = parser.parse_args()
    physical_dir = args.cache_root / "native-ble-a13-place2-route0/impl/pnr"
    physical = physical_inventory(physical_dir / "custom_138k_integration.vo",
                                  physical_dir / "custom_138k_integration.rpt.txt")
    previous, previous_definitions = synthesis_inventory(args.cache_root / "native-ble-v5")
    current, current_definitions = synthesis_inventory(args.cache_root / "native-ble-v9")
    reference_dir = ROOT / "results/resource_timing_20261020_124632_064482/Prj1/impl/pnr"
    reference = physical_inventory(reference_dir / "Prj1.vo", reference_dir / "Prj1.rpt.txt")
    reference.pop("blocks")
    prefixes = {
        "dds": "u_managed/u_audio/u_workstation/engine/",
        "vector": "u_managed/u_audio/u_workstation/vector_engine/",
        "chorus": "u_managed/u_audio/u_workstation/effects/chorus_stage/",
        "reverb": "u_managed/u_audio/u_workstation/effects/reverb_stage/",
        "recorder_packets": "u_managed/u_audio/u_extensions/recorder/",
        "score_cues": "u_managed/u_audio/u_extensions/score/",
        "cue_player": "u_managed/u_audio/u_workstation/cue_player/",
        "parameters": "u_managed/u_audio/u_workstation/parameters/",
        "ble_pcm": "u_bluetooth/u_core/application/command_endpoint/recording/live_capture.pcm_memory",
        "ble_download_buffer": "u_bluetooth/u_core/application/command_endpoint/recording/transfer_bank",
        "ble_command_cache": "u_bluetooth/u_core/application/command_endpoint/",
        "ble_patch": "u_bluetooth/u_core/initializer/patch_mem",
        "ble_parameters": "u_bluetooth/u_core/initializer/parameter_mem",
        "ble_h5": "u_bluetooth/u_core/transport/",
        "ble_acl": "u_bluetooth/u_core/acl_bridge/",
        "ble_gatt": "u_bluetooth/u_core/application/bulk_tx",
        "analysis_display": "u_video/u_renderer/g_analysis.u_analysis/",
        "scanout": "u_video/u_scanout/",
        "display_data_reader": "u_video/u_data_reader/",
        "renderer": "u_video/u_renderer/",
        "cnn_feature": "u_music/u_basic_pitch/g_ddr_features.u_feature_ddr/",
        "cnn_weights": "u_music/u_basic_pitch/g_ddr_weights.u_weight_cache/",
        "cnn_plane": "u_music/u_basic_pitch/g_ddr_plane.g_plane_cache.u_plane_cache/",
        "viterbi": "u_music/u_basic_pitch/g_full_dp.u_cnn_stream/u_viterbi/",
        "cnn_intermediate": "u_music/u_basic_pitch/",
        "usb_cpu_ram": "u_native_usb/host/bus/",
        "usb_register_file": "u_native_usb/host/cpu/",
        "usb_packet_buffers": "u_native_usb/host/usb/",
        "usb_events": "u_native_usb/input_owner/",
        "ddr_write": "u_memory/u_ddr3/gw3_top/u_gwmc_top/",
        "ddr_read": "u_memory/u_ddr3/gw3_top/u_ddr_phy_top/",
        "ae350_boot": "u_boot_memory/",
        "tf_audio": "u_tf_audio/",
    }
    groups = Counter()
    for block in physical["blocks"]:
        matches = [(len(prefix), name) for name, prefix in prefixes.items()
                   if block["instance"].startswith(prefix)]
        if not matches:
            raise ValueError("Unclassified physical memory: " + block["instance"])
        group = max(matches)[1]
        block["group"] = group
        groups[group] += 1
    if sum(groups.values()) != physical["used"]:
        raise ValueError("Subsystem counts do not sum to physical usage")
    physical["exclusive_subgroups"] = dict(groups)
    result = {
        "date": "2026-10-23",
        "scope": "Existing full-workstation evidence; no rebuild or board operation",
        "physical_identity": "custom138k-native-physical-20261023-b6",
        "physical_acceptance": "Timing failed; not deployed",
        "physical": physical,
        "current_synthesis": current,
        "physical_input_synthesis": previous,
        "memory_comparison": {
            "definition_count": len(current_definitions),
            "all_primitive_types_and_defparams_equal": previous_definitions == current_definitions,
            "top_level_equivalents_equal": previous["top_level"] == current["top_level"],
            "scope": "Module-definition comparison including initialization; not netlist formal equivalence or a16 P&R",
        },
        "t24_reference": reference,
    }
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"physical": physical["used"], "capacity": physical["capacity"],
                      "groups": dict(groups), "current_synthesis": current["equivalent"],
                      "memory_comparison": result["memory_comparison"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
