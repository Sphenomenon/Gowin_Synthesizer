#!/usr/bin/env python3
"""Read-only physical BSRAM inventory for the complete timing_p27 snapshot.

Includes RAM and ROM primitives, checks counts against the PNR report, and
records logical-memory arithmetic separately from unimplemented savings.
No synthesis, RTL edits, firmware execution, or board access.
"""
from pathlib import Path
from collections import Counter
import argparse
import hashlib
import json
import math
import re

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / 'results/timing_p27_uart_cdc_route1_20261018_142516_456857/Prj1'
PATTERN = re.compile(r'^\s*(SDPB|SDPX9B|SPB|SPX9B|DPB|DPX9B|pROM|pROMX9)\s+\\?(\S+)\s+\(', re.M)


def count_prefix(blocks, prefix):
    return sum(b['instance'].startswith(prefix + '/') for b in blocks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=DEFAULT)
    parser.add_argument('--out', type=Path, default=Path(__file__).with_name('inventory.json'))
    args = parser.parse_args()
    vo = args.project / 'impl/pnr/Prj1.vo'
    rpt = args.project / 'impl/pnr/Prj1.rpt.txt'
    text = vo.read_text(errors='strict')
    blocks = [{'primitive': m[1], 'instance': m[2]} for m in PATTERN.finditer(text)]
    row = re.search(r'^\s*BSRAM\s*\|\s*(\d+)/(\d+)\s*\|', rpt.read_text(), re.M)
    if not row or len(blocks) != int(row[1]):
        raise ValueError('physical primitive count does not agree with PNR utilization')
    groups = Counter(b['instance'].split('/')[0] for b in blocks)
    subtrees = {
        'dds': 'u_managed/u_audio/u_workstation/engine',
        'vector': 'u_managed/u_audio/u_workstation/vector_engine',
        'chorus': 'u_managed/u_audio/u_workstation/effects/chorus_stage',
        'reverb': 'u_managed/u_audio/u_workstation/effects/reverb_stage',
        'recorder': 'u_managed/u_audio/u_extensions/recorder',
        'score': 'u_managed/u_audio/u_extensions/score',
        'feature_cache': 'u_music/u_basic_pitch/g_ddr_features.u_feature_ddr',
        'weight_cache': 'u_music/u_basic_pitch/g_ddr_weights.u_weight_cache',
        'plane_cache': 'u_music/u_basic_pitch/g_ddr_plane.g_plane_cache.u_plane_cache',
        'viterbi': 'u_music/u_basic_pitch/g_full_dp.u_cnn_stream/u_viterbi',
        'scanout': 'u_video/u_scanout',
        'analysis': 'u_video/u_renderer/g_analysis.u_analysis',
        'usb_register_file': 'u_usb_host/rv',
    }
    features = 7 * 88 * 32
    firmware = json.loads((args.project.parent / 'build_metadata.json').read_text())['usb_firmware']
    result = {
        'date': '2026-10-20',
        'basis': 'complete routed timing_p27 snapshot, not a reading of the running board',
        'netlist': str(vo.resolve()),
        'netlist_sha256': hashlib.sha256(vo.read_bytes()).hexdigest(),
        'physical_used': len(blocks),
        'physical_capacity': int(row[2]),
        'primitive_types': dict(Counter(b['primitive'] for b in blocks)),
        'top_level': dict(groups),
        'subtrees': {name: count_prefix(blocks, prefix) for name, prefix in subtrees.items()},
        'logical_memory_arithmetic': {
            'feature_cache_words16': features,
            'feature_cache_bytes': features * 2,
            'feature_cache_kib': features * 2 / 1024,
            'feature_cache_1024x16_banks_capacity_target': math.ceil(features / 1024),
            'feature_cache_capacity_target_savings': 32 - math.ceil(features / 1024),
            'scanout_bytes': 256 * 256 // 8,
            'recorder_bytes': 256 * 96 // 8,
            'score_bytes': 256 * 64 // 8,
            'usb_static_end': firmware['static_ram_end'],
            'usb_margin_if_32k_bytes': 32768 - firmware['static_ram_end'],
        },
        'unimplemented_first_round': {
            'usb_ram_savings': 16,
            'usb_register_file_savings': 4,
            'feature_banking_savings': 12,
            'scanout_32bit_sdp_savings': 8,
            'recorder_32bit_sdp_savings': 3,
            'score_32bit_sdp_savings': 2,
            'total_target': 45,
            'target_total': len(blocks) - 45,
            'status': 'design targets only; each requires implementation and mapping/timing validation',
        },
        'blocks': blocks,
    }
    assert sum(result['top_level'].values()) == len(blocks)
    assert sum(v for k, v in result['unimplemented_first_round'].items() if k.endswith('_savings')) == 45
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ['physical_used','physical_capacity','primitive_types','top_level','subtrees','logical_memory_arithmetic','unimplemented_first_round']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
