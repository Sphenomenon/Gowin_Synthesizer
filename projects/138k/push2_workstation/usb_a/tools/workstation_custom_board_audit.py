"""Read-only provenance, feature, storage and CPU ROM audit for native synthesis."""

from pathlib import Path
import argparse
import json
import re
import xml.etree.ElementTree as ElementTree

from tools.stage_usb_firmware import sha
from tools.workstation_custom_board import NATIVE_SOURCES, REPLACED_INPUTS, EXCLUDED_INPUTS
from tools.workstation_memory import CAPACITY, REQUIRED, check_feature_storage, clock_estimates
from tools.workstation_usb2_input import LOCKED_INPUT_SOURCES
from tools.workstation_custom_clocks import PLAN_SOURCE, audit_clocks


ROOT = Path(__file__).resolve().parents[1]
TOP = 'workstation_custom_138k_top'
SHARED_TOP = 'rtl/workstation/gw138k_push_workstation_top.v'
FEATURES = dict(REQUIRED, usb_host='u_native_usb/host', push_surface='u_native_usb/input_owner',
                playback_service='u_playback_service', output_router='u_output_router',
                delay_ddr_dma='u_delay_ddr_dma', native_cpu='u_native_usb/host/cpu',
                clock_serializer='u_video/u_dvi/clock_lane', **{
                    f'data_serializer_{lane}': f'u_video/u_dvi/data_lanes[{lane}].serializer' for lane in range(3)})
DISALLOWED = ('place_route_allowed', 'io_electrical_complete', 'timing_constraints_complete',
              'hardware_tested', 'deployment_allowed', 'release_ready', 'legacy_usb_host_elaborated')


def checked_file(base, relative):
    source = (base / relative).resolve()
    if Path(relative).is_absolute() or not source.is_relative_to(base.resolve()):
        raise ValueError('native audit path escapes its root: ' + relative)
    if not source.is_file():
        raise ValueError('native audit input missing: ' + relative)
    return source


def check_files(base, identities, label):
    if not identities:
        raise ValueError('native audit empty identity map: ' + label)
    for relative, expected in identities.items():
        if sha(checked_file(base, relative)) != expected:
            raise ValueError('native audit ' + label + ' changed: ' + relative)


def hierarchy(root):
    if root.tag != 'Module' or root.get('name') != TOP:
        raise ValueError('native synthesis report top mismatch')
    resources = ('Register', 'Lut', 'Alu', 'Bsram', 'Ssram', 'MULTALU27X18', 'MULT12X12', 'MULT27X36')
    rows = {}

    def walk(node, path):
        if path in rows:
            raise ValueError('native duplicate hierarchy path: ' + path)
        rows[path] = {}
        children = []
        for child in node:
            if child.tag != 'SubModule' or not child.get('name'):
                raise ValueError('native malformed hierarchy node: ' + path)
            children.append(walk(child, (path + '/' if path else '') + child.get('name')))
        for resource in resources:
            own = int(node.get(resource, '0'))
            match = re.fullmatch(r'(\d+)\((\d+)\)', node.get('T_' + resource, f'{own}({own})'))
            if not match or own < 0 or int(match[2]) != own:
                raise ValueError('native malformed hierarchy count: ' + path + '/' + resource)
            total = int(match[1])
            if total != own + sum(child[resource] for child in children):
                raise ValueError('native inconsistent hierarchy total: ' + path + '/' + resource)
            rows[path][resource] = total
        rows[path]['self_bsram'] = int(node.get('Bsram', '0'))
        rows[path]['subtree_bsram'] = rows[path]['Bsram']
        return rows[path]

    totals = walk(root, '')
    if totals['Bsram'] > CAPACITY:
        raise ValueError('native synthesis BSRAM budget exceeded')
    missing = [name for name, path in FEATURES.items() if path not in rows]
    if missing:
        raise ValueError('native missing elaborated features: ' + ', '.join(missing))
    if any(path in rows for path in ('u_usb_host', 'u_push')):
        raise ValueError('native synthesis retained legacy USB host')
    check_feature_storage(rows)
    if rows[FEATURES['usb_host']]['Bsram'] < 38 or rows[FEATURES['push_surface']]['Bsram'] < 1:
        raise ValueError('native CPU ROM or event FIFO storage swept')
    if 'u_tf_audio/u_path/u_decoder/g_wav.u_wav' not in rows:
        raise ValueError('native requested WAV decoder missing')
    return totals, rows


def check_ports(stage, plan):
    text = (stage / SHARED_TOP).read_text()
    header = re.search(r'module\s+' + TOP + r'\s*#\(.*?\)\s*\((.*?)\);', text, re.S)
    if not header:
        raise ValueError('native top source header missing')
    ports = set()
    for declaration in re.split(r'\b(input|output|inout)\b', header[1])[2::2]:
        declaration = declaration.strip().removeprefix('wire').strip()
        width = re.match(r'\[(\d+):(\d+)\]', declaration)
        indices = range(int(width[2]), int(width[1]) + 1) if width else None
        names = declaration[width.end():] if width else declaration
        for name in re.findall(r'[A-Za-z_][A-Za-z_0-9]*', names):
            ports.update(name + f'[{index}]' for index in indices) if indices is not None else ports.add(name)
    implicit_negative = {'tmds_clk_n', 'ddr_ck_n', *(f'tmds_data_n[{index}]' for index in range(3)),
                         *(f'ddr_dqs_n[{index}]' for index in range(4))}
    if not implicit_negative.issubset(ports) or ports - implicit_negative != set(plan['ports']):
        raise ValueError('native top and pinout port coverage mismatch')
    locations = re.findall(r'IO_LOC\s+"([^"]+)"\s+([^;]+);',
                           (stage / 'constraints/custom_138k.locations.cst').read_text())
    actual = {name: [ball.strip() for ball in balls.split(',')] for name, balls in locations}
    if len(actual) != len(locations) or actual != {name: value['balls'] for name, value in plan['ports'].items()}:
        raise ValueError('native CST locations differ from authoritative pinout')
    return dict(logical_location_entries=len(actual), physical_port_bits=len(ports),
                implicit_negative_partners=sorted(implicit_negative))


def check_rom(stage, netlist_text, expected_sha256):
    modules = re.findall(r'^module\s+workstation_usb2_cpu_bus\s*\((.*?)^endmodule\b', netlist_text, re.M | re.S)
    if len(modules) != 1:
        raise ValueError('native CPU bus module missing or duplicated')
    planes = []
    for byte_lane in range(4):
        for bit_lane in range(8):
            instance = f'memory_{byte_lane}_memory_{byte_lane}_0_{bit_lane}_s'
            for port in (0, 1):
                if modules[0].count(f'defparam {instance}.BIT_WIDTH_{port}=1;') != 1:
                    raise ValueError('native CPU bit-plane mapping changed')
            chunks = re.findall(r'defparam ' + instance + r"\.INIT_RAM_([0-9A-Fa-f]{2})=256'h([0-9A-Fa-f]+);", modules[0])
            if (len({index for index, _ in chunks}) != len(chunks) or
                    any(int(index, 16) >= 64 or len(value) > 64 for index, value in chunks)):
                raise ValueError('native CPU ROM initialization chunks changed')
            value = sum(int(value, 16) << (int(index, 16) * 256) for index, value in chunks)
            planes.append(value.to_bytes(2048, 'little'))
    rom = stage / 'usb2_cpu.hex'
    words = [int(word, 16) for word in rom.read_text().splitlines()]
    if len(words) != 16384 or sha(rom) != expected_sha256:
        raise ValueError('native CPU ROM input identity changed')
    for index, expected in enumerate(words):
        actual = sum(((plane[index >> 3] >> (index & 7)) & 1) << bit for bit, plane in enumerate(planes))
        if actual != expected:
            raise ValueError(f'native synthesized ROM mismatch at word {index}')
    return len(words)


def audit(output):
    output = Path(output).resolve()
    manifest = output / 'integration_inputs.json'
    metadata = json.loads(manifest.read_text())
    if (metadata.get('identity') not in ('custom138k-native-integration-20261022-a2', 'custom138k-native-integration-20261022-a3') or
            metadata.get('top_module') != TOP or metadata.get('validation_stage') != 'integration_prepare_only' or
            metadata.get('source_policy') != 'explicit_native_board_on_resource_timing' or
            metadata.get('tmds_polarity_inverted') != [True] * 4 or
            metadata.get('native_usb') is not True or metadata.get('synthesis_allowed') is not True or
            metadata.get('audio_pin_behavior') != 'high_impedance_pending_actual_dac_identity' or
            metadata.get('cec_behavior') != 'released_high_impedance' or metadata.get('bitstream_sha256') is not None):
        raise ValueError('native board preparation policy changed')
    for flag in DISALLOWED:
        if metadata.get(flag) is not False:
            raise ValueError('native synthesis is not board acceptance: ' + flag)
    stage = output / 'workstation/Prj1'
    required_snapshot = {*NATIVE_SOURCES, SHARED_TOP, 'build.py', 'firmware.c', 'gw25k_panel.h',
                         'tools/workstation_custom_board.py', 'tools/build_resource_rework.py',
                         'tools/workstation_baselines.py', 'tools/stage_usb_firmware.py',
                         'tools/workstation_usb2_soc.py', 'tools/workstation_usb2_input.py',
                         'tools/workstation_pinout.py', 'baselines/index.json', 'boards/custom_138k/pinout.json'}
    if metadata['identity'].endswith('-a3'):
        required_snapshot.update((PLAN_SOURCE, 'tools/workstation_custom_clocks.py'))
        if metadata.get('clock_plan_source') != PLAN_SOURCE or metadata.get('clock_plan_sha256') != sha(ROOT / PLAN_SOURCE):
            raise ValueError('native clock plan identity changed')
    if not required_snapshot.issubset(metadata['source_snapshot_sha256']):
        raise ValueError('native source snapshot lost required provenance')
    check_files(ROOT, metadata['source_snapshot_sha256'], 'source snapshot')
    check_files(stage, metadata['staged_input_sha256'], 'staged input')
    if set(metadata['copied_sources_sha256']) != {*NATIVE_SOURCES, SHARED_TOP}:
        raise ValueError('native source selection changed')
    check_files(ROOT, metadata['copied_sources_sha256'], 'native source')
    check_files(stage, metadata['copied_sources_sha256'], 'copied source')
    if set(metadata['shared_resource_support_sha256']) != set(LOCKED_INPUT_SOURCES):
        raise ValueError('native shared support selection changed')
    check_files(stage, metadata['shared_resource_support_sha256'], 'shared resource support')
    parent = output / 'parent_prepare_metadata.json'
    pinout = output / 'pinout/pinout.json'
    if sha(parent) != metadata['parent_prepare_metadata_sha256'] or sha(pinout) != metadata['pinout_sha256']:
        raise ValueError('native parent or pinout evidence changed')
    plan = json.loads(pinout.read_text())
    if (metadata['device'] != plan['device'] or metadata['electrical_blocked'] is not True or
            plan['electrical_check']['status'] != 'blocked'):
        raise ValueError('native electrical blocking evidence changed')
    files = ElementTree.parse(stage / 'Prj1.gprj').find('FileList')
    selected = [entry.get('path') for entry in files if entry.get('enable') == '1']
    if selected != metadata['enabled_inputs'] or len(selected) != len(set(selected)):
        raise ValueError('native GPRJ input selection changed')
    if not {*selected, SHARED_TOP, 'usb2_cpu.hex', 'Prj1.gprj', 'scripts/build.tcl',
            'scripts/custom_board_synthesis.tcl'}.issubset(metadata['staged_input_sha256']):
        raise ValueError('native compiler closure lost required identity')
    if any(selected.count(relative) != 1 for relative in (*NATIVE_SOURCES, *LOCKED_INPUT_SOURCES)):
        raise ValueError('native required compilation source missing')
    if set(metadata['replaced_compilation_inputs']) != {*REPLACED_INPUTS, *EXCLUDED_INPUTS}:
        raise ValueError('native replaced provider selection changed')
    for relative, record in metadata['replaced_compilation_inputs'].items():
        if relative in selected or sha(checked_file(stage, relative)) != record['sha256']:
            raise ValueError('native excluded historical input changed: ' + relative)
    synthesis_script = (stage / 'scripts/custom_board_synthesis.tcl').read_text()
    if (f'set_option -top_module {TOP}\n' not in synthesis_script or
            synthesis_script.count('run syn\n') != 1 or re.search(r'\brun\s+pnr\b', synthesis_script) or
            not (stage / 'scripts/build.tcl').read_text().startswith('error ')):
        raise ValueError('native stage no longer enforces synthesis-only preparation')
    firmware = metadata['firmware']
    if (firmware.get('firmware_profile') != 'workstation' or firmware.get('isa') != 'rv32i' or
            firmware.get('abi') != 'ilp32' or type(metadata.get('high_speed_allowed')) is not bool or
            firmware.get('high_speed_allowed') is not metadata['high_speed_allowed']):
        raise ValueError('native business firmware profile changed')
    ports = check_ports(stage, plan)
    log = output / 'synthesis.log'
    text = log.read_text()
    if re.search(r'(?m)^ERROR\b', text) or text.count('GowinSynthesis finish') != 1:
        raise ValueError('native synthesis did not finish without errors')
    base = stage / 'impl/gwsynthesis/custom_138k_integration'
    netlist = base.with_suffix('.vg')
    report = base.with_name(base.name + '_syn_rsc.xml')
    totals, rows = hierarchy(ElementTree.parse(report).getroot())
    netlist_text = netlist.read_text()
    if (len(re.findall(r'^module\s+' + TOP + r'\s*\(', netlist_text, re.M)) != 1 or
            re.search(r'^module\s+(iosys2|gw138k_push_workstation_top)\s*\(', netlist_text, re.M)):
        raise ValueError('native synthesized module identity changed')
    rom_words = check_rom(stage, netlist_text, metadata['firmware']['rom_sha256'])
    clocks = audit_clocks(ROOT, stage, netlist_text) if metadata['identity'].endswith('-a3') else None
    return dict(schema=1, identity=metadata['identity'], validation_stage='native_full_profile_synthesis_only',
                top_module=TOP, auditor_sha256=sha(Path(__file__)), integration_inputs_sha256=sha(manifest),
                synthesis_log_sha256=sha(log), netlist_sha256=sha(netlist), resource_report_sha256=sha(report),
                source_snapshot_entries=len(metadata['source_snapshot_sha256']), staged_inputs=len(metadata['staged_input_sha256']),
                enabled_inputs=len(selected), port_coverage=ports, resources=totals,
                synthesis_bsram_equivalent=totals['Bsram'], bsram_capacity=CAPACITY,
                features={name: dict(instance=path, **rows[path]) for name, path in FEATURES.items()},
                top_level_bsram={path: value['Bsram'] for path, value in rows.items() if path and '/' not in path and value['Bsram']},
                verified_rom_words=rom_words, rom_sha256=metadata['firmware']['rom_sha256'],
                high_speed_allowed=metadata['high_speed_allowed'],
                explicit_clock_audit=clocks,
                synthesis_clock_estimates=clock_estimates(base.with_name(base.name + '_syn.rpt.html')),
                synthesis_warnings=len(re.findall(r'(?m)^WARN\s+\(', text)),
                electrical_blocked=True, io_electrical_complete=False, timing_closed=False,
                place_route_verified=False, hardware_tested=False, deployment_allowed=False,
                release_ready=False, bitstream_sha256=None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
