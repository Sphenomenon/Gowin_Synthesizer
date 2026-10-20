#!/usr/bin/env python3
"""Audit the elaborated full workstation; hierarchical RAM totals are not additive.

Reads Gowin reports only. No media, programming, board I/O, or source mutation.
"""
from pathlib import Path
import argparse
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET

CAPACITY = 340
TOP = 'gw138k_push_workstation_top'
WS = 'u_managed/u_audio/u_workstation'
REQUIRED = {
    'usb_host': 'u_usb_host',
    'push_surface': 'u_push',
    'synthesizer': WS + '/engine',
    'vector_voices': WS + '/vector_engine',
    'vector_control_events': WS + '/cue_player',
    'scope_dac_selection': 'u_tf_dac',
    'basic_pitch_pipeline': 'u_music/u_basic_pitch',
    'basic_pitch_ddr_port': 'u_music/u_ddr16',
    'serial_effects': WS + '/effects',
    'tf_spi_fat_reader': 'u_tf_audio/u_path/u_file_reader',
    'tf_capture_fifo': 'u_tf_audio/u_path/u_capture_fifo',
    'tf_playback_fifo': 'u_tf_audio/u_path/u_playback_fifo',
    'tf_ddr_dma': 'u_tf_audio/u_path/u_dma',
    'shared_ddr_controller': 'u_memory',
    'hdmi_display_analysis': 'u_video',
    'ae350_boot_memory': 'u_boot_memory',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hierarchy(root):
    if root.tag != 'Module' or root.get('name') != TOP:
        raise ValueError('expected full workstation top ' + TOP)
    rows = {}

    def walk(node, path):
        own = int(node.get('Bsram', '0'))
        raw = node.get('T_Bsram')
        match = re.fullmatch(r'(\d+)\((\d+)\)', raw) if raw else None
        if raw and not match:
            raise ValueError('invalid T_Bsram at ' + path)
        total = int(match[1]) if match else own
        if match and int(match[2]) != own:
            raise ValueError('inconsistent self count at ' + path)
        child_total = 0
        for child in node:
            name = child.get('name')
            if not name or child.tag != 'SubModule':
                raise ValueError('unexpected hierarchy node at ' + path)
            child_path = path + '/' + name if path else name
            child_total += walk(child, child_path)
        if total != own + child_total:
            raise ValueError('inconsistent hierarchical total at ' + (path or TOP))
        if path in rows:
            raise ValueError('duplicate hierarchy path ' + path)
        rows[path] = {'self_bsram': own, 'subtree_bsram': total}
        return total

    total = walk(root, '')
    if total > CAPACITY:
        raise ValueError(f'BSRAM budget exceeded: {total}/{CAPACITY}')
    missing = [name for name, path in REQUIRED.items() if path not in rows]
    if missing:
        raise ValueError('missing elaborated workstation features: ' + ', '.join(missing))
    return total, rows


def pnr_resources(stage):
    # P&R counts physical BSRAM primitives (SDPB/SDPX9B/pROM/pROMX9); the
    # synthesis hierarchy counts 18Kb-block equivalents. The two stages use
    # different unit mappings, so they are reported side by side, never merged.
    report = stage / 'impl/pnr/Prj1.rpt.txt'
    if not report.exists():
        return None
    rows = report.read_text().splitlines()
    used = None
    for index, line in enumerate(rows):
        match = re.fullmatch(r'\s*BSRAM\s*\|\s*(\d+)/(\d+)\s*\|\s*\d+%\s*', line)
        if not match:
            continue
        used, capacity = int(match[1]), int(match[2])
        breakdown = {}
        for extra in rows[index + 1:]:
            cell = re.fullmatch(r'\s*--(\S+)\s*\|\s*(\d+)\s*', extra)
            if not cell:
                break
            breakdown[cell[1]] = int(cell[2])
        break
    if used is None:
        raise ValueError('P&R report has no BSRAM utilization row')
    if used > CAPACITY:
        raise ValueError(f'P&R BSRAM budget exceeded: {used}/{capacity}')
    return {'bsram': used, 'bsram_capacity': capacity, 'primitive_breakdown': breakdown}


def clock_estimates(path):
    # SYN HTML contains a Clock Name / Constraint / Actual Fmax table.
    if not path.exists():
        return []
    result = []
    for raw in re.findall(r'<tr\b[^>]*>(.*?)</tr>', path.read_text(), re.S | re.I):
        cells = [html.unescape(re.sub(r'<[^>]*>', '', value)).strip()
                 for value in re.findall(r'<td\b[^>]*>(.*?)</td>', raw, re.S | re.I)]
        if len(cells) != 6 or not re.fullmatch(r'\d+', cells[0]):
            continue
        constraint = re.fullmatch(r'([\d.]+)\(MHz\)', cells[2])
        actual = re.fullmatch(r'([\d.]+)\(MHz\)', cells[3])
        if constraint and actual:
            target, estimated = float(constraint[1]), float(actual[1])
            result.append({'clock': cells[1], 'required_mhz': target,
                           'synthesis_estimated_mhz': estimated,
                           'estimate_meets_requirement': estimated >= target})
    return result


def check_feature_storage(rows):
    # A hierarchy row can survive even when a constant control sweeps the entire
    # vector datapath. Its fixed 16KiB geometry ROM must still be implemented.
    if rows.get(REQUIRED['vector_voices'], {}).get('subtree_bsram', 0) < 8:
        raise ValueError('vector geometry ROM swept or missing; reject reduced-resource candidate')


def audit(build, mode):
    build = Path(build).resolve()
    if mode not in ('synthesis_only', 'full', 'place_route_reuse'):
        raise ValueError('unsupported build mode ' + mode)
    tool = json.loads((build / 'tool_result.json').read_text())
    if tool.get('exit_code') != 0 or tool.get('inputs_unchanged') is not True:
        raise ValueError('successful immutable build inputs are required')
    stage = build / 'Prj1'
    resource = stage / 'impl/gwsynthesis/Prj1_syn_rsc.xml'
    root = ET.parse(resource).getroot()
    total, rows = hierarchy(root)
    check_feature_storage(rows)
    top_file = stage / 'src/push2/gw138k_push_workstation_top.v'
    profile = re.search(r'parameter integer TF_AUDIO_KIND\s*=\s*([123])', top_file.read_text())
    if not profile:
        raise ValueError('missing explicit TF decoder profile')
    decoder = {1: 'mp3', 2: 'wav', 3: 'flac'}[int(profile[1])]
    decoder_paths = [p for p in rows if p.startswith('u_tf_audio/u_path/u_decoder/')]
    if not any(p.endswith('g_' + decoder + '.u_' + decoder) for p in decoder_paths):
        raise ValueError('requested TF decoder was not elaborated: ' + decoder)
    nn_present = 'u_music/u_basic_pitch' in rows
    pnr = pnr_resources(stage)
    report = {
        'schema_version': 1,
        'top': TOP,
        'build_directory': build.name,
        'build_mode': mode,
        'bsram_measurement_stage': 'synthesis',
        'bsram': total,
        'bsram_capacity': CAPACITY,
        'bsram_remaining': CAPACITY - total,
        'pnr_available': pnr is not None,
        'pnr_bsram': pnr['bsram'] if pnr else None,
        'pnr_primitive_breakdown': pnr['primitive_breakdown'] if pnr else None,
        'timing_closed': None,
        'hardware_tested': False,
        'tf_decoder': decoder,
        'basic_pitch_elaborated': nn_present,
        'features': {name: {'instance': path, **rows[path]} for name, path in REQUIRED.items()},
        'top_level_bsram': {p: v['subtree_bsram'] for p, v in rows.items()
                            if p and '/' not in p and v['subtree_bsram']},
        'hierarchy': rows,
        'synthesis_clock_estimates': clock_estimates(stage / 'impl/gwsynthesis/Prj1_syn.rpt.html'),
        'evidence_sha256': {
            resource.relative_to(build).as_posix(): sha(resource),
            top_file.relative_to(build).as_posix(): sha(top_file),
            'workstation_inputs.json': sha(build / 'workstation_inputs.json'),
            'tool_result.json': sha(build / 'tool_result.json'),
        },
        'notes': [
            'Subtree counts already include descendants; sum only immediate top-level children plus top self.',
            'Synthesis BSRAM is not P&R physical utilization; no savings claim against historical routed 253.',
            'P&R counts SDPB/SDPX9B/pROM primitives; synthesis counts 18Kb-block equivalents. '
            'Compare only within one stage: bsram vs bsram, pnr_bsram vs pnr_bsram.',
            'Reserved NN DDR address space alone does not instantiate a neural network.',
            'Timing closure and board acceptance require separate routed/physical evidence.',
        ],
    }
    (build / 'workstation_memory.json').write_text(json.dumps(report, indent=2) + '\n')
    lines = ['# Full workstation memory audit', '',
             f'Build: `{build.name}`. Mode: `{mode}`. Top: `{TOP}`.', '',
             f'Synthesis BSRAM: **{total}/{CAPACITY}**, remaining **{CAPACITY-total}**.', '']
    if pnr:
        detail = ', '.join(f'{name} {count}' for name, count in pnr['primitive_breakdown'].items())
        lines += [f'P&R BSRAM: **{pnr["bsram"]}/{pnr["bsram_capacity"]}** ({detail}).', '']
    else:
        lines += ['P&R BSRAM: not available (no routed report in this build).', '']
    lines += [f'TF decoder: `{decoder}`. Basic Pitch elaborated: `{nn_present}`.', '',
             '| Immediate top-level instance | Subtree BSRAM |', '|---|---:|']
    lines.extend(f'| `{p}` | {n} |' for p, n in report['top_level_bsram'].items())
    lines += ['', 'Full hierarchical detail and report hashes: `workstation_memory.json`.', '',
              'Timing closure and board acceptance are unverified. Synthesis clock estimates:', '',
              '| Clock | Required MHz | SYN estimate MHz |', '|---|---:|---:|']
    lines.extend(f"| `{r['clock']}` | {r['required_mhz']} | {r['synthesis_estimated_mhz']} |"
                 for r in report['synthesis_clock_estimates'])
    lines += ['', *('- ' + text for text in report['notes']), '']
    (build / 'workstation_memory.md').write_text('\n'.join(lines))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path)
    parser.add_argument('--mode', choices=('synthesis_only', 'full', 'place_route_reuse'), required=True)
    args = parser.parse_args()
    try:
        report = audit(args.build, args.mode)
    except (OSError, ValueError, ET.ParseError) as exc:
        parser.exit(1, 'workstation memory audit failed: ' + str(exc) + '\n')
    pnr_text = f'; P&R BSRAM {report["pnr_bsram"]}/{CAPACITY}' if report['pnr_available'] else ''
    print(f"{report['top']}: SYN BSRAM {report['bsram']}/{CAPACITY}{pnr_text}; TF {report['tf_decoder']}")


if __name__ == '__main__':
    main()
