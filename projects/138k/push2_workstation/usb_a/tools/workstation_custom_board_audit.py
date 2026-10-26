"""Read-only provenance, feature, storage and CPU ROM audit for native synthesis."""

from pathlib import Path
import argparse
import json
import re
import xml.etree.ElementTree as ElementTree

from tools.stage_usb_firmware import sha
from tools.workstation_custom_board import NATIVE_SOURCES, REPLACED_INPUTS, EXCLUDED_INPUTS, FPC_AUDIO_CST, FPC_AUDIO_SDC, DISPLAY_CST, BLUETOOTH_SDC, DDR_CST
from tools.workstation_memory import CAPACITY, REQUIRED, check_feature_storage, clock_estimates
from tools.workstation_usb2_input import LOCKED_INPUT_SOURCES
from tools.workstation_custom_clocks import PLAN_SOURCE, audit_clocks, shared_cdc_bundle, audit_shared_cdc
from tools.workstation_board_peripherals import reviewed_profile, LCD_SDC
from tools.workstation_usb2_bridge_audit import audit_bridge_resets
from tools.workstation_custom_usb2_cdc import PLAN_SOURCE as CDC_PLAN_SOURCE, cdc_bundle, audit_usb2_cdc
from tools.workstation_custom_input_cdc import PLAN_SOURCE as INPUT_CDC_PLAN_SOURCE, input_cdc_bundle, audit_input_fifo
from tools.workstation_synthesis_netlist import SynthesisNetlist
from tools.workstation_custom_timing import INPUTS as TIMING_INPUTS, constraints as timing_constraints, audit_resets as audit_usb_resets
from tools.workstation_custom_flash import CST as MODEL_FLASH_CST, SDC as MODEL_FLASH_SDC, reviewed_cst as reviewed_flash_cst
from tools.workstation_video_mode import IDENTITY_720, LOCKED_INPUTS as VIDEO_INPUTS, RENDERER, PROFILES_720, MODES


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


def audit_native_receivers(netlist_text, clocks, direct_dac_reference=False):
    netlist = SynthesisNetlist(netlist_text, TOP)
    constants = {"1'b1"} | {netlist.pin(name, 'V') for name, cell in netlist.cells.items()
                              if cell['kind'] == 'VCC'}
    evidence = {}
    receivers = [
            ('bluetooth_uart', 'u_bluetooth/u_core/transport/uart', 'rx_sync', 'DFFPE', 'PRESET'),
            ('fpc_pll_reset', 'u_fpc_audio', 'pll_release', 'DFFCE', 'CLEAR')]
    if direct_dac_reference:
        receivers.append(('fpc_reference_monitor', 'u_fpc_audio', 'reference_sync', 'DFFCE', 'CLEAR'))
        reference = clocks['clocks']['dac_ref12m288']['net']
        phases = [name for name, cell in netlist.cells.items()
                  if re.fullmatch(r'u_fpc_audio/phase_\d+_s\d+', name)]
        if (netlist.pin('dac_mclk_obuf', 'I') != reference or len(phases) != 8 or
                any(netlist.pin(name, 'CLK') != reference for name in phases)):
            raise ValueError('native DAC does not use the direct 12.288 MHz reference')
        if any(name.startswith('u_fpc_audio/') and cell['kind'] == 'PLL'
               for name, cell in netlist.cells.items()):
            raise ValueError('native DAC unexpectedly reintroduced an unsupported PLL')
    for label, scope, stem, kind, control in receivers:
        registers = {}
        for name, cell in netlist.cells.items():
            match = re.fullmatch(re.escape(scope + '/' + stem) + r'_(\d+)_s\d+', name)
            if match:
                if int(match[1]) in registers:
                    raise ValueError('native receiver duplicate stage: ' + label)
                registers[int(match[1])] = name
        if set(registers) != {0, 1}:
            raise ValueError('native receiver stage inventory changed: ' + label)
        first, second = registers[0], registers[1]
        for name in (first, second):
            if (netlist.cells[name]['kind'] != kind or netlist.pin(name, 'CE') not in constants or
                    netlist.pin(name, 'CLK') != clocks['clocks']['clk_50m']['net']):
                raise ValueError('native receiver must be unconditionally clocked at 50 MHz: ' + label)
        if (netlist.pin(second, 'D') != netlist.pin(first, 'Q') or
                netlist.pin(first, control) != netlist.pin(second, control)):
            raise ValueError('native receiver direct two-stage connection changed: ' + label)
        if label == 'bluetooth_uart' and netlist.pin(first, 'D') != 'ble_uart_rx_i':
            raise ValueError('native UART input bypasses first synchronizer')
        if label == 'fpc_pll_reset' and netlist.pin(first, 'D') not in constants:
            raise ValueError('native FPC PLL reset no longer releases from a constant')
        if label == 'fpc_reference_monitor':
            toggles = [name for name, cell in netlist.cells.items()
                       if re.fullmatch(r'u_fpc_audio/reference_toggle_s\d+', name)]
            if (len(toggles) != 1 or netlist.pin(toggles[0], 'CLK') != reference or
                    netlist.pin(first, 'D') != netlist.pin(toggles[0], 'Q')):
                raise ValueError('native reference monitor bypasses the DAC-domain heartbeat')
        local_output = netlist.cells[first]['ports']['Q'].split('[')[0]
        if local_output in netlist.directions[netlist.frames[scope]['kind']]:
            raise ValueError('native receiver first stage has functional fanout: ' + label)
        for name, cell in netlist.cells.items():
            if netlist.scopes[name] == scope and cell['kind'] in netlist.modules:
                if any(re.search(r'(?<![\w$])' + re.escape(local_output) + r'(?![\w$])', value)
                       for value in cell['ports'].values()):
                    raise ValueError('native receiver first stage has functional fanout: ' + label)
        consumers = {(name, pin) for name, cell in netlist.cells.items()
                     if netlist.scopes[name] == scope and cell['kind'] not in netlist.modules for pin in cell['ports']
                     if pin != 'Q' and netlist.pin(name, pin) == netlist.pin(first, 'Q')}
        if consumers != {(second, 'D')}:
            raise ValueError('native receiver first stage has functional fanout: ' + label)
        evidence[label] = dict(first=first, second=second, first_stage_consumers=sorted(consumers),
                               clock=netlist.pin(first, 'CLK'), routed_timing_verified=False)
    return evidence


def checked_file(base, relative):
    source = (base / relative).resolve()
    if Path(relative).is_absolute() or not source.is_relative_to(base.resolve()):
        raise ValueError('native audit path escapes its root: ' + relative)
    if not source.is_file():
        raise ValueError('native audit input missing: ' + relative)
    return source


def audit_master_volume(netlist_text):
    netlist = SynthesisNetlist(netlist_text, TOP)
    parameters = 'u_managed/u_audio/u_workstation/parameters'
    effects = 'u_managed/u_audio/u_workstation/effects'
    authority_ports = [f'performance_words_{bit}' for bit in range(56, 64)]
    expected_ports = [(parameters, port, 'output', None) for port in authority_ports]
    expected_ports += [('u_fpc_audio', 'performance_words', 'input', (63, 56)),
                       (parameters, 'expression_gain', 'output', (15, 8)),
                       (effects, 'expression_gain', 'input', (15, 8))]
    for scope, port, direction, width in expected_ports:
        frame = netlist.frames[scope]
        if (port not in frame['ports'] or netlist.directions[frame['kind']].get(port) != direction or
                netlist.ranges[frame['kind']].get(port) != width):
            raise ValueError('native master volume synthesized port changed: ' + scope + '/' + port)
    master = [netlist.canonical(parameters, port) for port in authority_ports]
    output = [netlist.canonical('u_fpc_audio', f'performance_words[{bit}]') for bit in range(56, 64)]
    expression = [netlist.canonical(parameters, f'expression_gain[{bit}]') for bit in range(8, 16)]
    effect_gain = [netlist.canonical(effects, f'expression_gain[{bit}]') for bit in range(8, 16)]
    if master != output or expression != effect_gain or master == expression:
        raise ValueError('native master volume must reach final output once, independently of expression')
    return dict(authority=parameters, final_output='u_fpc_audio', master_bits=master,
                authority_ports=authority_ports, effect_input_bits=effect_gain, double_master_attenuation=False,
                physical_audio_verified=False)


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
    if (metadata.get('identity') not in ('custom138k-native-integration-20261022-a2',
                                       'custom138k-native-integration-20261022-a3',
                                       'custom138k-native-integration-20261022-a4',
                                       'custom138k-native-integration-20261022-a5',
                                       'custom138k-native-integration-20261022-a6',
                                       'custom138k-native-integration-20261022-a7',
                                       'custom138k-native-integration-20261022-a8',
                                        'custom138k-native-integration-20261023-a9',
                                        'custom138k-native-integration-20261023-a10',
                                        'custom138k-native-integration-20261023-a11',
                                        'custom138k-native-integration-20261023-a12',
                                        'custom138k-native-integration-20261023-a13',
                                        'custom138k-native-integration-20261023-a14',
                                        'custom138k-native-integration-20261023-a15',
                                        'custom138k-native-integration-20261023-a16',
                                        'custom138k-native-integration-20261024-a17',
                                        'custom138k-native-integration-20261025-a18',
                                        'custom138k-native-integration-20261025-a19',
                                        'custom138k-native-integration-20261025-a20',
                                        'custom138k-native-integration-20261025-a21',
                                        'custom138k-native-integration-20261025-a22',
                                        'custom138k-native-integration-20261025-a23',
                                        'custom138k-native-integration-20261026-a24',
                                        'custom138k-native-integration-20261027-a25',
                                        'custom138k-native-integration-20261027-a26', IDENTITY_720,
                                        PROFILES_720['720p60']['identity']) or
            metadata.get('top_module') != TOP or metadata.get('validation_stage') != 'integration_prepare_only' or
            metadata.get('source_policy') != 'explicit_native_board_on_resource_timing' or
            metadata.get('tmds_polarity_inverted') != [True] * 4 or
            metadata.get('native_usb') is not True or metadata.get('synthesis_allowed') is not True or
            metadata.get('audio_pin_behavior') != ('ak4493_i2s32_48k_mclk256fs_final_master_volume'
                if metadata['identity'].endswith(('-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')) else 'fpc_i2s32_48k_mclk512fs_muted_startup'
                if metadata['identity'].endswith(('-a8', '-a9', '-a10', '-a11', '-a12', '-a13', '-a14', '-a15', '-a16')) else 'high_impedance_pending_actual_dac_identity') or
            metadata.get('cec_behavior') != 'released_high_impedance' or metadata.get('bitstream_sha256') is not None):
        raise ValueError('native board preparation policy changed')
    for flag in DISALLOWED:
        if metadata.get(flag) is not False:
            raise ValueError('native synthesis is not board acceptance: ' + flag)
    stage = output / 'workstation/Prj1'
    hdmi_mode = metadata.get('hdmi', {}).get('mode', '1080p60')
    if hdmi_mode not in MODES:
        raise ValueError('unsupported native HDMI mode')
    selected_video_identity = PROFILES_720.get(hdmi_mode, {}).get('identity')
    if (selected_video_identity is not None and metadata['identity'] != selected_video_identity or
            selected_video_identity is None and metadata['identity'] in
            {profile['identity'] for profile in PROFILES_720.values()}):
        raise ValueError('native HDMI mode does not match candidate identity')
    if hdmi_mode in PROFILES_720:
        profile = PROFILES_720[hdmi_mode]
        timing, adapted_pll = profile['timing'], profile['pll']
        video = metadata['hdmi']
        expected = dict(width=1280, height=720, refresh_hz=profile['refresh_hz'], pixel_hz=74250000,
                        serial_hz=371250000, h_total=profile['h_total'], v_total=750,
                        canvas_width=1920, canvas_height=1080,
                        canvas_mapping='floor(output_coordinate*3/2)')
        if any(video.get(key) != value for key, value in expected.items()) or video.get('source_inputs') != VIDEO_INPUTS:
            raise ValueError('native ' + hdmi_mode + ' video contract changed')
        if video.get('source_overlays') != {relative: sha(ROOT / relative) for relative in (RENDERER, timing)}:
            raise ValueError('native ' + hdmi_mode + ' video source overlays changed')
        check_files(stage, video['adapted'], hdmi_mode + ' video')
        if ('vendor/sipeed_dvi/video_pll_1080p_gw5a.v' in metadata['enabled_inputs'] or
                any(metadata['enabled_inputs'].count(relative) != 1 for relative in (adapted_pll, timing))):
            raise ValueError('native ' + hdmi_mode + ' PLL/timing selection changed')
    required_snapshot = {*NATIVE_SOURCES, SHARED_TOP, 'build.py', 'firmware.c', 'gw25k_panel.h',
                         'tools/workstation_custom_board.py', 'tools/build_resource_rework.py',
                         'tools/workstation_baselines.py', 'tools/stage_usb_firmware.py',
                         'tools/workstation_usb2_soc.py', 'tools/workstation_usb2_input.py',
                         'tools/workstation_pinout.py', 'baselines/index.json', 'boards/custom_138k/pinout.json'}
    if metadata['identity'].endswith(('-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        required_snapshot.update(('boards/custom_138k/peripherals.json', 'tools/workstation_board_peripherals.py'))
        if (metadata.get('volume_application') != 'post_effects_post_source_selection_once_before_I2S_and_BLE' or
                metadata.get('volume_control') != 'Push_CC71_or_CC79_and_25K_encoder1_to_authoritative_CC7' or
                metadata.get('bluetooth', {}).get('transport_source') != 'example/RTL8723DS/vendor/rtl8723ds_ble'):
            raise ValueError('native volume or remote Bluetooth integration policy changed')
    if metadata['identity'].endswith(('-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')) and metadata.get('audio_clock_policy') != 'direct_12m288_reference_with_50m_watchdog_no_DAC_PLL':
        raise ValueError('native DAC reference clock policy changed')
    if metadata['identity'].endswith(('-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')) and metadata.get('delay_fifo_storage') != 'two_65x512_banked_BSRAM_FIFOs_same_capacity_latency_and_gray_protocol':
        raise ValueError('native delay FIFO storage policy changed')
    if metadata['identity'].endswith(('-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        required_snapshot.add('tools/workstation_custom_timing.py')
        adaptations = metadata.get('native_timing_adaptations', {})
        if set(adaptations) != set(TIMING_INPUTS):
            raise ValueError('native checked timing adaptation inventory changed')
        for relative, record in adaptations.items():
            if record['before'] != TIMING_INPUTS[relative] or record['after'] != sha(stage / relative):
                raise ValueError('native checked timing adaptation identity changed: ' + relative)
    if metadata['identity'].endswith(('-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        required_snapshot.update(('tools/workstation_custom_flash.py', MODEL_FLASH_CST))
        reviewed_flash_cst(ROOT)
        if not metadata.get('model_flash', {}).get('use_flash_weights'):
            raise ValueError('native model Flash boot is not explicitly enabled')
    if not metadata['identity'].endswith('-a2'):
        required_snapshot.update((PLAN_SOURCE, 'tools/workstation_custom_clocks.py'))
        if metadata.get('clock_plan_source') != PLAN_SOURCE or metadata.get('clock_plan_sha256') != sha(ROOT / PLAN_SOURCE):
            raise ValueError('native clock plan identity changed')
    if metadata['identity'].endswith(('-a7', '-a8', '-a9', '-a10', '-a11', '-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        required_snapshot.add('tools/audit_clk50_timing.py')
    if metadata['identity'].endswith(('-a8', '-a9', '-a10', '-a11', '-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        required_snapshot.add(FPC_AUDIO_CST)
        if (not metadata['identity'].endswith(('-a10', '-a11', '-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')) and
                metadata['enabled_inputs'].count('constraints/custom_138k.audio.cst') != 1):
            raise ValueError('native FPC audio electrical constraints not enabled')
        if (stage / 'constraints/custom_138k.audio.cst').read_bytes() != (ROOT / FPC_AUDIO_CST).read_bytes():
            raise ValueError('native FPC audio electrical constraints changed')
    if metadata['identity'].endswith(('-a10', '-a11', '-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        required_snapshot.add(DISPLAY_CST)
    if metadata['identity'].endswith(('-a4', '-a5', '-a6', '-a7', '-a8', '-a9', '-a10', '-a11', '-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        required_snapshot.update(('tools/workstation_usb2_bridge_audit.py', 'tools/workstation_synthesis_netlist.py'))
    if metadata['identity'].endswith(('-a5', '-a6', '-a7', '-a8', '-a9', '-a10', '-a11', '-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        required_snapshot.update((CDC_PLAN_SOURCE, 'tools/workstation_custom_usb2_cdc.py'))
        if (metadata.get('usb2_cdc_plan_source') != CDC_PLAN_SOURCE or
                metadata.get('usb2_cdc_plan_sha256') != sha(ROOT / CDC_PLAN_SOURCE)):
            raise ValueError('native USB2 CDC plan identity changed')
    if metadata['identity'].endswith(('-a6', '-a7', '-a8', '-a9', '-a10', '-a11', '-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        required_snapshot.update((INPUT_CDC_PLAN_SOURCE, 'tools/workstation_custom_input_cdc.py'))
        if (metadata.get('input_cdc_plan_source') != INPUT_CDC_PLAN_SOURCE or
                metadata.get('input_cdc_plan_sha256') != sha(ROOT / INPUT_CDC_PLAN_SOURCE)):
            raise ValueError('native input FIFO CDC plan identity changed')
    if not required_snapshot.issubset(metadata['source_snapshot_sha256']):
        raise ValueError('native source snapshot lost required provenance')
    check_files(ROOT, metadata['source_snapshot_sha256'], 'source snapshot')
    if metadata['identity'].endswith(('-a9', '-a10', '-a11', '-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        check_files(ROOT.parents[3], metadata['bluetooth']['source_snapshot_sha256'], 'BLE business source')
        if metadata['bluetooth']['capacity_frames'] != 16384 or not metadata['bluetooth']['sources']:
            raise ValueError('native BLE source or short recording capacity changed')
        if (stage / 'constraints/custom_138k.bluetooth.cst').read_bytes() != (ROOT / 'boards/custom_138k/bluetooth.cst').read_bytes():
            raise ValueError('native BLE electrical constraints changed')
    if metadata['identity'].endswith(('-a10', '-a11', '-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        if [name for name in metadata['enabled_inputs'] if name.endswith('.cst')] != ['constraints/custom_138k.cst']:
            raise ValueError('native project must select one complete physical constraint file')
        if (stage / 'constraints/custom_138k.display.cst').read_bytes() != (ROOT / DISPLAY_CST).read_bytes():
            raise ValueError('native display electrical constraints changed')
        parts = ('locations', 'audio', 'bluetooth', 'display')
        if metadata['identity'].endswith(('-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
            parts += ('peripherals',)
        if metadata['identity'].endswith(('-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
            parts += ('model_flash',)
        if metadata['identity'].endswith('-a24', '-a25', '-a26'):
            if (stage / 'constraints/custom_138k.ddr.cst').read_bytes() != (ROOT / DDR_CST).read_bytes():
                raise ValueError('native DDR hard-resource constraints changed')
            parts += ('ddr',)
        combined = ''.join((stage / ('constraints/custom_138k.' + part + '.cst')).read_text() + '\n'
                           for part in parts)
        if (stage / 'constraints/custom_138k.cst').read_text() != combined:
            raise ValueError('native combined physical constraints changed')
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
    if metadata['identity'].endswith(('-a11', '-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')) and plan['constraints_sha256'] != sha(output / 'pinout/custom_138k.locations.cst'):
        raise ValueError('native location constraint identity changed')
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
    if metadata['identity'].endswith(('-a8', '-a9', '-a10', '-a11', '-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')) and 'u_fpc_audio' not in rows:
        raise ValueError('native FPC audio output missing from synthesis')
    netlist_text = netlist.read_text()
    if (len(re.findall(r'^module\s+' + TOP + r'\s*\(', netlist_text, re.M)) != 1 or
            re.search(r'^module\s+(iosys2|gw138k_push_workstation_top)\s*\(', netlist_text, re.M)):
        raise ValueError('native synthesized module identity changed')
    rom_words = check_rom(stage, netlist_text, metadata['firmware']['rom_sha256'])
    if metadata['identity'].endswith(('-a9', '-a10', '-a11', '-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        recorder = 'u_bluetooth/u_core/application/command_endpoint/recording'
        if rows.get(recorder, {}).get('Bsram', 0) < 32:
            raise ValueError('native BLE real PCM recording storage missing')
    crossing_bundle = cdc_bundle(ROOT) if metadata['identity'].endswith(('-a5', '-a6', '-a7', '-a8', '-a9', '-a10', '-a11', '-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')) else None
    input_bundle = input_cdc_bundle(ROOT) if metadata['identity'].endswith(('-a6', '-a7', '-a8', '-a9', '-a10', '-a11', '-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')) else None
    extra_sdc = (crossing_bundle['sdc'] if crossing_bundle else '') + (input_bundle['sdc'] if input_bundle else '')
    if metadata['identity'].endswith(('-a8', '-a9', '-a10', '-a11', '-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        extra_sdc += FPC_AUDIO_SDC
    if metadata['identity'].endswith(('-a9', '-a10', '-a11', '-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        extra_sdc += BLUETOOTH_SDC
    shared_crossings = None
    if metadata['identity'].endswith(('-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        profile = reviewed_profile(ROOT)
        if metadata.get('peripherals') != dict(profile_source='boards/custom_138k/peripherals.json',
                profile_sha256=sha(ROOT / 'boards/custom_138k/peripherals.json'), **profile):
            raise ValueError('native reviewed peripheral provenance changed')
        if 'u_lcd' not in rows:
            raise ValueError('native LCD consumer missing from synthesis')
        extra_sdc += LCD_SDC
    if metadata['identity'].endswith(('-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        bundle = shared_cdc_bundle(stage)
        if metadata.get('shared_cdc_adaptation') != {key: value for key, value in bundle.items() if key != 'sdc'}:
            raise ValueError('native shared CDC adaptation provenance changed')
        extra_sdc += bundle['sdc']
        shared_crossings = audit_shared_cdc(stage, netlist_text)
    if metadata['identity'].endswith(('-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        extra_sdc += timing_constraints()
    if metadata['identity'].endswith(('-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        extra_sdc += MODEL_FLASH_SDC
    clocks = (audit_clocks(ROOT, stage, netlist_text, extra_sdc=extra_sdc, hdmi_mode=hdmi_mode)
              if not metadata['identity'].endswith('-a2') else None)
    usb_resets = audit_usb_resets(netlist_text, clocks) if metadata['identity'].endswith(('-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')) else None
    if metadata['identity'].endswith(('-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        native = SynthesisNetlist(netlist_text, TOP)
        readers = [name for name, cell in native.cells.items()
                   if name.startswith('u_music/') and cell['kind'] == 'basic_pitch_flash_model_loader']
        recoveries = [name for name, cell in native.cells.items()
                      if name.startswith('u_music/') and cell['kind'] == 'basic_pitch_uart_model_loader']
        if len(readers) != 1 or len(recoveries) != 1 or native.pin(readers[0], 'flash_miso_d') != 'flash_miso':
            raise ValueError('native Flash model reader, MISO or UART recovery missing')
        zero = {native.pin(name, 'G') for name, cell in native.cells.items() if cell['kind'] == 'GND'}
        one = {native.pin(name, 'V') for name, cell in native.cells.items() if cell['kind'] == 'VCC'}
        control = native.pin(readers[0], 'model_flash_cs_n')
        for port, data in [('flash_cs_n', zero), ('flash_clk', {native.pin(readers[0], 'model_flash_clk')}),
                            ('flash_mosi', {native.pin(readers[0], 'model_flash_mosi')}),
                            ('flash_wp_n', one), ('flash_hold_n', one)]:
            drivers = [name for name, cell in native.cells.items()
                       if cell['kind'] == 'TBUF' and native.pin(name, 'O') == port]
            if (len(drivers) != 1 or native.pin(drivers[0], 'OEN') != control or
                    native.pin(drivers[0], 'I') not in data):
                raise ValueError('native Flash shared-pad guard truth table changed: ' + port)
    receivers = audit_native_receivers(netlist_text, clocks, metadata['identity'].endswith(('-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26'))) if metadata['identity'].endswith(('-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')) else None
    resets = None
    if metadata['identity'].endswith(('-a4', '-a5', '-a6', '-a7', '-a8', '-a9', '-a10', '-a11', '-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
        if rows.get('u_native_usb/host/usb/bridge', {}).get('Bsram') != 2:
            raise ValueError('native bridge instance or dual-clock packet memories missing')
        resets = audit_bridge_resets(netlist_text, TOP)
    crossings = audit_usb2_cdc(ROOT, netlist_text, clocks) if crossing_bundle else None
    input_crossings = audit_input_fifo(ROOT, netlist_text, clocks) if input_bundle else None
    master_volume = audit_master_volume(netlist_text) if metadata['identity'].endswith(('-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')) else None
    delay_storage = audit_delay_fifo_storage(netlist_text, rows) if metadata['identity'].endswith(('-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')) else None
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
                native_receiver_audit=receivers,
                shared_cdc_audit=shared_crossings,
                bridge_reset_audit=resets,
                native_usb_reset_audit=usb_resets,
                usb2_bridge_cdc_audit=crossings,
                input_fifo_cdc_audit=input_crossings,
                master_volume_audit=master_volume,
                delay_fifo_storage_audit=delay_storage,
                synthesis_clock_estimates=clock_estimates(base.with_name(base.name + '_syn.rpt.html')),
                synthesis_warnings=len(re.findall(r'(?m)^WARN\s+\(', text)),
                electrical_blocked=True, io_electrical_complete=False, timing_closed=False,
                place_route_verified=False, hardware_tested=False, deployment_allowed=False,
                release_ready=False, bitstream_sha256=None)


def audit_delay_fifo_storage(text, rows):
    netlist = SynthesisNetlist(text, TOP)
    result = {}
    for label in ('u_write_fifo', 'u_read_fifo'):
        prefix = 'u_managed/u_audio/u_workstation/effects/delay_stage/' + label
        if rows.get(prefix, {}).get('Bsram') != 4 or rows[prefix].get('Ssram', 0) != 0:
            raise ValueError('native delay FIFO must use four BSRAM and no distributed RAM: ' + label)
        clocks = {}
        for side in ('write', 'read'):
            pointers = [name for name, cell in netlist.cells.items()
                        if name.startswith(prefix + '/') and cell['kind'].startswith('DFF')
                        and re.fullmatch(re.escape(prefix + '/' + side + '_binary_') + r'\d+_s\d+', name)]
            if len(pointers) != 10:
                raise ValueError('native delay FIFO full 512-entry capacity changed: ' + label)
            selected = {netlist.pin(name, 'CLK') for name in pointers}
            if len(selected) != 1:
                raise ValueError('native delay FIFO pointer clocks changed: ' + label)
            clocks[side] = selected.pop()
        memory = {name: cell for name, cell in netlist.cells.items()
                  if name.startswith(prefix + '/') and cell['kind'] == 'SDPX9B'}
        banks = {bank: sum('/g_large_head.' + bank + '_memory' in name for name in memory)
                 for bank in ('even', 'odd')}
        if len(memory) != 4 or banks != {'even': 2, 'odd': 2}:
            raise ValueError('native delay FIFO parity banking changed: ' + label)
        for name, cell in memory.items():
            if (netlist.pin(name, 'CLKA') != clocks['write'] or netlist.pin(name, 'CLKB') != clocks['read'] or
                    cell['parameters'].get('BIT_WIDTH_0') != '36' or cell['parameters'].get('BIT_WIDTH_1') != '36' or
                    cell['parameters'].get('READ_MODE') != "1'b0" or cell['parameters'].get('RESET_MODE') != '"ASYNC"'):
                raise ValueError('native delay FIFO dual-clock memory contract changed: ' + name)
        result[label] = dict(bsram_blocks=4, distributed_ram_blocks=0, entries=512, width=65,
                             parity_banks=banks, clocks=clocks, primitive_paths=sorted(memory))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
