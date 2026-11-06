"""Audit the immutable M/W demo synthesis closure without reinterpreting A26.

This is a synthesis-to-physical preparation gate. Source CDC structure, routed
CDC/STA, encrypted DDR implementation and hardware acceptance remain distinct
gates. A successful result never promotes any of those later stages.
"""

from pathlib import Path
import fnmatch
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from bisect import bisect_left

from tools.stage_usb_firmware import sha
from tools.workstation_synthesis_netlist import SynthesisNetlist
from tools.workstation_memory import CAPACITY, clock_estimates


TOP = 'workstation_custom_138k_top'
BASE = 'custom_138k_integration'
WS = 'u_managed/runtime/service/workstation'
EFFECTS = WS + '/runtime_effects.effects'
ENGINES = WS + '/runtime_engines.engines'
PROFILES = {
    'custom138k-workstation-task3-m-independent-ddr-map-v1': ('M', 'custom138k-native-task3-m-independent-ddr-map-revision1',
                                      'rtl/workstation/workstation_profile_m_demo.sv'),
    'custom138k-workstation-task3-m-independent-v1': ('M', 'custom138k-native-task3-m-independent-revision1',
                                      'rtl/workstation/workstation_profile_m_demo.sv'),
    'custom138k-workstation-task3-m-direct-tf-v1': ('M', 'custom138k-native-task3-m-direct-tf-revision1',
                                      'rtl/workstation/workstation_profile_task3_m_direct_tf.sv'),
    'custom138k-workstation-m-demo-v1': ('M', 'custom138k-native-m-demo-base-revision1',
                                      'rtl/workstation/workstation_profile_m_demo.sv'),
    'custom138k-workstation-w-demo-v1': ('W', 'custom138k-native-w-demo-d-only-revision1',
                                      'rtl/workstation/workstation_profile_w_demo.sv'),
}
AUDIT_SOURCES = (
    'tools/workstation_demo_audit.py', 'tools/workstation_demo_policy.py',
    'tools/workstation_custom_board_audit.py', 'tools/workstation_synthesis_netlist.py',
    'tools/workstation_profile.py', 'tools/workstation_runtime_clock_audit.py',
    'tools/workstation_custom_clocks.py', 'tools/workstation_custom_usb2_cdc.py',
    'tools/workstation_custom_input_cdc.py', 'tools/workstation_usb2_bridge_audit.py',
    'tools/workstation_custom_timing.py', 'tools/workstation_ae350_clock_placement.py',
    'tools/workstation_ae350_rtc.py', 'tools/workstation_board_peripherals.py',
    'tools/workstation_memory.py', 'tools/stage_usb_firmware.py',
    'tools/workstation_usb_fifo_reset.py', 'tools/workstation_runtime_pcm_cdc.py',
    'tools/workstation_performance_reset.py',
    'tools/workstation_demo_boundary_cdc.py',
    'tools/workstation_native_protocol_audit.py', 'tools/workstation_recording_phase1_cdc.py',
    'tools/workstation_runtime_profile.py', 'tools/workstation_runtime_cdc.py',
)
COMMON_FEATURES = {
    'usb_host': 'u_native_usb/host', 'usb_cpu': 'u_native_usb/host/cpu',
    'usb_input_owner': 'u_native_usb/input_owner', 'authoritative_parameters': WS + '/parameters',
    'session': WS + '/session', 'serial_effects': EFFECTS,
    'delay': EFFECTS + '/delay_stage', 'chorus': EFFECTS + '/chorus_stage',
    'reverb': EFFECTS + '/reverb_stage', 'delay_ddr_dma': 'u_managed/runtime/delay_dma',
    'playback_service': 'u_managed/runtime/service',
    'final_pcm_router': 'u_managed/runtime/final_pcm',
    'physical_i2s': 'u_managed/runtime/serializer',
    'physical_frame_observation': 'u_managed/observation',
    'shared_ddr': 'u_memory', 'ae350_memory': 'u_boot_memory',
    'hdmi': 'u_video', 'hdmi_renderer': 'u_video/u_renderer',
    'hdmi_live_analysis': 'u_video/u_runtime_display/producer',
    'hdmi_waveform': 'u_video/u_runtime_display/producer/waveform',
    'hdmi_xy_alignment': 'u_video/u_runtime_display/producer/aligner',
    'hdmi_spectrum': 'u_video/u_runtime_display/producer/analysis',
    'hdmi_scanout': 'u_video/u_scanout', 'hdmi_serializer_clock': 'u_video/u_dvi/clock_lane',
    **{f'hdmi_serializer_data_{lane}': f'u_video/u_dvi/data_lanes[{lane}].serializer' for lane in range(3)},
}
M_FEATURES = dict(oscillator=ENGINES + '/oscillator', vector=ENGINES + '/vector_engine',
                  tf='u_tf_audio', tf_decoder='u_tf_audio/path/u_decoder/g_wav.u_wav')


def require(ok, message):
    if not ok:
        raise ValueError('demo synthesis audit: ' + message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def checked(base, relative):
    path = Path(relative)
    require(not path.is_absolute() and '..' not in path.parts, 'input path escapes candidate: ' + relative)
    target = (base / path).resolve()
    require(target.is_relative_to(base.resolve()) and target.is_file(), 'input missing: ' + relative)
    return target


def verify_prepared(output, metadata):
    """Verify captured inputs, including old candidates after live sources move.

    The closure is checked against its original mutually bound manifests. It is
    deliberately not regenerated from today's source tree or today's source
    locks. Current-tree reproducibility belongs to profile.verify at prepare.
    """
    selected = metadata.get('workstation_profile', {})
    require(selected.get('name') in PROFILES, 'unregistered demo profile')
    role, identity, provider = PROFILES[selected['name']]
    artifact_path = checked(output, selected.get('artifact', ''))
    require(selected.get('artifact') == 'workstation_profile.json' and
            sha(artifact_path) == selected.get('artifact_sha256'), 'profile artifact identity changed')
    profile = json.loads(artifact_path.read_text())
    from tools.workstation_profile import prepared_specification
    spec = prepared_specification(profile)
    identity = spec['integration_identity']
    require(metadata.get('identity') == identity and profile.get('profile') == selected['name'] and
            profile.get('configuration', {}).get('demo_role') == role and
            profile.get('profile_source') == spec['config'] and
            profile.get('revision') == spec['revision'], 'role/configuration identity changed')
    require(selected.get('configuration_sha256') == profile.get('profile_sha256'),
            'profile configuration hash binding changed')
    require(profile.get('integration_metadata_sha256') == digest(
        {k: v for k, v in metadata.items() if k != 'workstation_profile'}),
        'integration metadata hash binding changed')
    for field in ('staged_input_sha256', 'source_snapshot_sha256', 'firmware', 'ae350_firmware'):
        require(profile.get(field) == metadata.get(field), 'profile/integration mismatch: ' + field)
    candidate_hash = digest(dict(profile_sha256=profile['profile_sha256'],
        staged_input_sha256=metadata['staged_input_sha256'],
        source_snapshot_sha256=metadata['source_snapshot_sha256'],
        firmware=metadata['firmware'], ae350_firmware=metadata['ae350_firmware']))
    require(profile.get('candidate_input_sha256') == candidate_hash and
            profile.get('candidate_identity') == selected['name'] + '-' + candidate_hash[:16] and
            selected.get('candidate_identity') == profile['candidate_identity'],
            'candidate input identity changed')
    stage = output / 'workstation/Prj1'
    inputs = metadata['staged_input_sha256']
    require(bool(inputs), 'empty staged closure')
    actual = {p.relative_to(stage).as_posix() for p in stage.rglob('*')
              if p.is_file() and 'impl' not in p.relative_to(stage).parts}
    # Gowin writes this project-session file during synthesis. It is neither a
    # FileList input nor an include dependency; all other additions fail closed.
    require(actual - set(inputs) <= {'Prj1.gprj.user'} and set(inputs) <= actual,
            'staged file inventory changed')
    for relative, expected in inputs.items():
        require(re.fullmatch(r'[0-9a-f]{64}', expected) is not None and
                sha(checked(stage, relative)) == expected, 'staged input changed: ' + relative)
    if profile['configuration'].get('ddr_map_alias_policy') is not None:
        from tools import workstation_ddr_map_aliases as ddr_aliases
        require(ddr_aliases.configured(profile['configuration']), 'DDR include alias policy missing')
        source = 'projects/138k/push2_workstation/usb_a/' + ddr_aliases.SOURCE
        ddr_aliases.verify_staged(stage, metadata.get('runtime_ddr_aliases'),
                                 authority_sha256=profile['source_sha256'][source])
    selected_inputs = [e.get('path') for e in ET.parse(stage / 'Prj1.gprj').find('FileList')
                       if e.get('enable') == '1']
    require(selected_inputs == metadata['enabled_inputs'] and
            len(selected_inputs) == len(set(selected_inputs)) and
            set(selected_inputs) == set(profile['enabled_inputs']), 'GPRJ compilation selection changed')
    from tools.workstation_usb_fifo_reset import verify_demo_selection
    verify_demo_selection(stage, profile['configuration'], metadata.get('demo_usb_fifo_write_reset'),
        selected_inputs, expected_configuration=spec['configuration'])
    installed_sdc = (stage / 'constraints/custom_138k.sdc').read_text()
    if spec.get('tf_direct_enabled', False):
        from tools.workstation_task3_tf_direct import restore_constraints
        # The manifest is a versioned policy input, while the synthesized
        # closure remains independently immutable after live sources advance.
        installed_sdc = restore_constraints(stage, installed_sdc, metadata['task3_tf_direct_cdc'])
    if spec.get('worker_audio_only', False):
        from tools.workstation_worker_audio_only import restore_constraints
        installed_sdc = restore_constraints(installed_sdc, metadata['worker_audio_only']['constraints'])
    from tools.workstation_performance_reset import verify_demo_timing
    verify_demo_timing(stage, installed_sdc, role,
        metadata.get('demo_runtime_timing'))
    from tools.workstation_demo_boundary_cdc import verify_demo_boundary
    verify_demo_boundary(stage, installed_sdc, role,
        metadata.get('demo_boundary_cdc'))
    providers = {entry['provider'] for entry in __import__(
        'tools.workstation_profile', fromlist=['PROFILE_REGISTRY']).PROFILE_REGISTRY.values()}
    require([p for p in selected_inputs if p in providers] == [provider], 'selected top provider changed')
    require(sha(checked(output, 'parent_prepare_metadata.json')) == metadata['parent_prepare_metadata_sha256'] and
            sha(checked(output, 'pinout/pinout.json')) == metadata['pinout_sha256'],
            'parent or pinout identity changed')
    require(sha(checked(output, 'workstation/resource_rework_overlays.json')) ==
            profile['resource_overlays_sha256'], 'parent overlay identity changed')
    ae350 = metadata['ae350_firmware']
    evidence = checked(output, ae350['evidence_directory'] + '/build_metadata.json').parent
    for relative, expected in ae350['artifacts_sha256'].items():
        require(sha(checked(evidence, relative)) == expected, 'AE350 artifact changed: ' + relative)
    require(json.loads((evidence / 'build_metadata.json').read_text()) == ae350['build'],
            'AE350 build metadata changed')
    rom = ae350['installed_rom']
    require(rom['path'] == 'firmware/boot.mem' and rom['sha256'] == ae350['build']['rom_sha256'] and
            sha(checked(stage, rom['path'])) == rom['sha256'] and
            sha(checked(evidence, 'boot.mem')) == rom['sha256'], 'AE350 installed ROM changed')
    return role, profile, stage


def hierarchy_counts(root):
    require(root.tag == 'Module' and root.get('name') == TOP, 'resource hierarchy top changed')
    resources = ('Register', 'Lut', 'Alu', 'Bsram', 'Ssram', 'MULTALU27X18', 'MULT12X12', 'MULT27X36')
    rows = {}
    def walk(node, path):
        require(path not in rows, 'duplicate hierarchy: ' + path)
        rows[path] = {}
        children = []
        for child in node:
            require(child.tag == 'SubModule' and bool(child.get('name')), 'malformed resource hierarchy')
            children.append(walk(child, (path + '/' if path else '') + child.get('name')))
        for resource in resources:
            own = int(node.get(resource, '0'))
            match = re.fullmatch(r'(\d+)\((\d+)\)', node.get('T_' + resource, f'{own}({own})'))
            require(match is not None and own >= 0 and int(match[2]) == own,
                    'malformed resource count: ' + path + '/' + resource)
            total = int(match[1])
            require(total == own + sum(c[resource] for c in children),
                    'inconsistent resource total: ' + path + '/' + resource)
            rows[path][resource] = total
        return rows[path]
    totals = walk(root, '')
    require(totals['Bsram'] <= CAPACITY, 'synthesis BSRAM budget exceeded')
    return totals, rows


def audit_features(role, rows, netlist, *, tf_enabled=True, worker_audio_only=False, tf_direct_enabled=False, usb_cpu_ram_bytes=65536):
    selected_m = {k: p for k, p in M_FEATURES.items() if tf_enabled or k not in ('tf', 'tf_decoder')}
    if tf_direct_enabled:
        require(role == 'M' and tf_enabled, 'direct TF requires retained M playback')
        selected_m.update(tf_decoder='u_tf_audio/native/ingress/decoder',
            tf_file_owner='u_tf_audio/native/file_owner',
            tf_sd_sector='u_tf_audio/native/file_owner/u_sector_reader',
            tf_spi='u_tf_audio/native/file_owner/u_sector_reader/u_spi_session',
            tf_pcm_ingress='u_tf_audio/native/ingress',tf_transport='u_tf_audio/frames',
            tf_physical_tail='u_managed/runtime/g_direct_tf.tail')
    features = dict(COMMON_FEATURES, **(selected_m if role == 'M' else {}))
    if worker_audio_only:
        require(role == 'W', 'audio-only selection on non-W role')
        features = {k: p for k, p in features.items() if not k.startswith('hdmi')}
        features.update(audio_memory='u_audio_memory', audio_memory_bist='u_audio_memory/u_bist',
                        audio_memory_queues='u_audio_memory/u_arbiter')
    require(not any(p not in rows for p in features.values()),
            'retained features missing: ' + ', '.join(k for k, p in features.items() if p not in rows))
    require(type(usb_cpu_ram_bytes) is int and usb_cpu_ram_bytes in (49152,65536),
            'unregistered USB CPU RAM capacity')
    # An explicit RAM48 profile replaces exactly eight CPU RAM SDPB lanes.
    # Packet/register/event storage remains required, and the paired caller
    # separately proves all24 RAM primitive widths and every initialized word.
    if usb_cpu_ram_bytes==49152:
        require(rows.get('u_native_usb/host/bus',{}).get('Bsram')==24,
                'explicit RAM48 must retain all24 CPU RAM blocks')
    require(rows['u_native_usb/host']['Bsram'] >= (30 if usb_cpu_ram_bytes==49152 else 38) and
            rows['u_native_usb/input_owner']['Bsram'] >= 1, 'USB CPU ROM/event storage swept')
    for name, minimum in (('delay', 8), ('chorus', 4), ('reverb', 20), ('hdmi_live_analysis', 32),
                          ('hdmi_waveform', 1), ('hdmi_xy_alignment', 1), ('hdmi_spectrum', 30)):
        if name not in features:
            continue
        require(rows[features[name]]['Bsram'] >= minimum, 'retained storage swept: ' + name)
    retired = ['u_music', 'u_recording', 'u_lcd', 'u_usb_host', 'u_push']
    if role == 'M':
        retired += ['u_bluetooth', 'u_ble_pcm_cdc']
        if not tf_enabled:
            retired += ['u_tf_audio', 'u_tf_control_cdc', 'u_tf_scope_transport',
                        'u_playback_service', 'u_audio_command_buffer', 'u_playlist_bridge',
                        WS + '/parameters/tf_controls']
            kinds = {c['kind'] for c in netlist.cells.values()}
            for forbidden in ('workstation_tf_runtime_service', 'tf_audio_ddr_path',
                              'workstation_tf_direct_native_v1', 'workstation_tf_direct_ingress_v1'):
                require(forbidden not in kinds, 'M deferred TF implementation remains: ' + forbidden)
        require(rows[M_FEATURES['vector']]['Bsram'] >= 8 and rows[M_FEATURES['oscillator']]['Bsram'] >= 8,
                'M vector geometry or oscillator storage swept')
        if tf_direct_enabled:
            kinds = {c['kind'] for c in netlist.cells.values()}
            for forbidden in ('workstation_tf_runtime_service', 'workstation_tf_runtime_dma', 'tf_audio_ddr_path'):
                require(forbidden not in kinds, 'direct TF retains legacy intermediate: ' + forbidden)
            require(rows['u_tf_audio/native/ingress']['Bsram'] >= 11, 'native prefill/byte storage swept')
    else:
        retired += ['u_tf_audio', 'u_tf_control_cdc', ENGINES, WS + '/instrument_cue.cue_player']
        kinds = {c['kind'] for c in netlist.cells.values()}
        required_kinds = ['workstation_ae350_pcm_owner', 'workstation_hci_native_transport']
        if not worker_audio_only:
            required_kinds += ['workstation_ble_record_data_engine', 'workstation_ble_raw_ddr_store']
        for required in required_kinds:
            require(required in kinds, 'W real PCM/recording/transport primitive missing: ' + required)
        for forbidden in ('workstation_recording_backend', 'workstation_recording_ddr_backend',
                          'workstation_recording_service', 'ble_recording', 'workstation_runtime_oscillator_engine',
                          'workstation_runtime_scope_vec'):
            require(forbidden not in kinds, 'W retired implementation remains: ' + forbidden)
        for unique in ('workstation_ble_record_data_engine', 'workstation_ble_raw_ddr_store'):
            require(sum(c['kind'] == unique for c in netlist.cells.values()) == (0 if worker_audio_only else 1),
                    'W recording owner inventory changed: ' + unique)
        if worker_audio_only:
            retired += ['u_video', 'u_ui_control', 'u_ui_services', 'u_cpu_ddr', 'u_ble_pcm_cdc',
                        'u_managed/display', 'u_managed/display_observation_health',
                        'u_bluetooth/u_core/application', 'u_bluetooth/u_core/acl_bridge']
            for forbidden in ('workstation_ble_record_data_engine', 'workstation_ble_raw_ddr_store',
                              'workstation_recording_top', 'bt_gatt', 'bt_acl_bridge',
                              'gw138k_ui_services', 'gw138k_ui_workstation_top', 'gw138k_ahb_ddr',
                              'workstation_display_data_runtime', 'workstation_audio_spectrum',
                              'workstation_observation_display_health', 'dvi_tx'):
                require(forbidden not in kinds, 'W audio-only retired kind remains: ' + forbidden)
    for prefix in retired:
        require(not any(p == prefix or p.startswith(prefix + '/') for p in (*rows, *netlist.cells)),
                'retired hierarchy remains: ' + prefix)
    return dict(retained={k: dict(instance=p, **rows[p]) for k, p in features.items()},
                retired_prefixes=retired, role_retirement_verified=True,
                worker_audio_only=worker_audio_only,
                synthesis_storage_only=True, hardware_functionality_verified=False)


def audit_m_voice_storage(netlist):
    """Observe all 32 real voice envelopes, states and pressure registers."""
    prefix = ENGINES + '/oscillator/'
    groups = {}
    for stem, width in (('sample_envelope_q18', 18), ('envelope_state', 3), ('expression_gain_q8', 8)):
        pattern = re.compile(re.escape(prefix + stem) + r'\[(\d+)\]_(\d+)_s\d+')
        found = {}
        for path, cell in netlist.cells.items():
            match = pattern.fullmatch(path)
            if match and cell['kind'].startswith('DFF'):
                key = int(match[1]), int(match[2])
                require(key not in found, 'duplicate M voice storage bit: ' + path)
                found[key] = path
        require(set(found) == {(voice, bit) for voice in range(32) for bit in range(width)},
                'M 32-voice storage swept: ' + stem)
        groups[stem] = dict(voices=32, bits_per_voice=width, registers=len(found),
                            register_inventory_sha256=digest(sorted(found.values())))
    return dict(voices=32, groups=groups, synthesized_storage_verified=True,
                concurrent_voice_functionality_hardware_verified=False)


def audit_worker_feedback(netlist, clocks):
    """Prove the W snapshot that the 25K firmware actually reads.

    W removes Push display delivery, whose unused destination_valid pulse is
    swept. Its 112 live parameter bits and complete request/ack mailbox remain;
    accepting an arbitrary smaller payload or an unknown register is forbidden.
    """
    prefix = 'u_native_usb/input_owner/feedback/'
    source_clock = clocks['clocks']['audio_76m8']['net']
    destination_clock = clocks['clocks']['usb_48m']['net']
    bits = {*range(32, 35), *range(37, 42), *range(56, 64), *range(132, 196),
            *range(224, 245), 276, *range(278, 288)}
    regs = {p: c for p, c in netlist.cells.items()
            if p.startswith(prefix) and c['kind'].startswith('DFF')}
    groups = {}
    for stem in ('held_data', 'destination_data'):
        found = {}
        for path in regs:
            match = re.fullmatch(re.escape(prefix + stem) + r'_(\d+)_s\d+', path)
            if match:
                require(int(match[1]) not in found, 'duplicate W feedback payload bit')
                found[int(match[1])] = path
        require(set(found) == bits, 'W feedback live parameter bitmap changed: ' + stem)
        groups[stem] = found
    source_stems = ('source_release_', 'ack_meta_', 'ack_sync_', 'request_toggle_')
    dest_stems = ('destination_release_', 'req_meta_', 'req_sync_', 'req_settled_', 'acknowledge_toggle_')
    source = [p for p in regs if p.removeprefix(prefix).startswith(source_stems)]
    dest = [p for p in regs if p.removeprefix(prefix).startswith(dest_stems)]
    require(set(regs) == {*source, *dest, *groups['held_data'].values(), *groups['destination_data'].values()},
            'unknown W feedback register or unexpected destination_valid consumer')
    for stem in ('source_release', 'destination_release'):
        actual = [p for p in regs if p.startswith(prefix + stem + '_')]
        require(len(actual) == 3 and all(sum(bool(re.fullmatch(
            re.escape(prefix + stem + '_' + str(bit)) + r'_s\d+', p)) for p in actual) == 1
            for bit in range(3)), 'W feedback reset release inventory changed: ' + stem)
    for paths, clock in (([*source, *groups['held_data'].values()], source_clock),
                         ([*dest, *groups['destination_data'].values()], destination_clock)):
        require(all(regs[p]['kind'] == 'DFFCE' and netlist.pin(p, 'CLK') == clock for p in paths),
                'W feedback primitive/source/destination clock changed')
    def one(stem):
        found = [p for p in regs if re.fullmatch(re.escape(prefix + stem) + r'_s\d+', p)]
        require(len(found) == 1, 'W feedback handshake register missing: ' + stem)
        return found[0]
    request, ack = one('request_toggle'), one('acknowledge_toggle')
    req_meta, req_sync, req_settled = (one(s) for s in ('req_meta', 'req_sync', 'req_settled'))
    ack_meta, ack_sync = one('ack_meta'), one('ack_sync')
    for first, second in ((request, req_meta), (req_meta, req_sync), (req_sync, req_settled),
                          (req_settled, ack), (ack, ack_meta), (ack_meta, ack_sync)):
        require(netlist.pin(first, 'Q') == netlist.pin(second, 'D'),
                'W feedback request/ack direct stage changed')
    for bit in bits:
        held, captured = groups['held_data'][bit], groups['destination_data'][bit]
        require(netlist.pin(held, 'Q') == netlist.pin(captured, 'D') and
                netlist.pin(held, 'CE') == netlist.pin(request, 'CE') and
                netlist.pin(captured, 'CE') == netlist.pin(ack, 'CE'),
                'W feedback immutable payload/capture enable changed: ' + str(bit))
    return dict(policy='worker_25k_112_parameter_bit_mailbox_v1',
                source_clock=source_clock, destination_clock=destination_clock,
                source_registers=len(source) + len(bits), destination_registers=len(dest) + len(bits),
                live_payload_bits=sorted(bits), request=request, acknowledge=ack,
                source_domain_verified=True, payload_bit_identity_verified=True,
                unused_Push_destination_valid_swept=True, physical_timing_verified=False)


def audit_constraint_retirement(sdc, evidence, role, netlist, worker_evidence=None, *, tf_playback_enabled=False):
    from tools.workstation_demo_policy import verify_constraints, W_SCOPE_BINDINGS
    selected = sdc
    if worker_evidence is not None:
        from tools.workstation_worker_audio_only import restore_constraints, REBIND, RETIRED_SELECTORS, RETIRED_CLOCKS
        selected = restore_constraints(sdc, worker_evidence)
    original = verify_constraints(selected, evidence, role, tf_playback_enabled=tf_playback_enabled)
    universes = dict(get_regs=sorted(p for p, c in netlist.cells.items() if c['kind'].startswith('DFF')),
        get_pins=sorted(p + '/' + pin for p, c in netlist.cells.items() for pin in c['ports']),
        get_ports=sorted(netlist.directions[TOP]),
        get_clocks=sorted(set(re.findall(r'^create_(?:generated_)?clock -name (\S+)', sdc, re.M))))
    query = re.compile(r'\[(get_pins|get_regs|get_ports|get_clocks)\s+\{([^{}]+)\}\]')
    absent, rebound = {}, {}
    def matches(kind, member):
        prefix = re.split(r'[*?\[]', member, maxsplit=1)[0]
        values = universes[kind]
        candidates = values[bisect_left(values, prefix):bisect_left(values, prefix + '\U0010ffff')]
        pattern = re.compile(fnmatch.translate(member))
        return [p for p in candidates if p == member or pattern.fullmatch(p)]
    for change in evidence['changes']:
        for kind, body in query.findall(change['original']):
            for member in body.split():
                if member not in change['removed_selectors']:
                    continue
                require(not matches(kind, member), 'retired SDC selector still has live endpoints: ' + member)
                actual_member = member
                if role == 'W':
                    for old, new in W_SCOPE_BINDINGS:
                        if member.startswith(old):
                            actual_member = new + member[len(old):]
                            break
                require(not matches(kind, actual_member),
                        'retired SDC selector still has live rebound endpoints: ' + actual_member)
                absent[kind + ' ' + member] = dict(matches=0,
                    canonical_selector=actual_member, original_line_index=change['line_index'])
        for binding in change.get('rebound_selectors', []):
            kind, old, new = binding['query'], binding['original'], binding['selected']
            require(not matches(kind, old), 'rebound SDC source selector still has live endpoints: ' + old)
            if worker_evidence is not None:
                for before, after in REBIND:
                    if new.startswith(before):
                        new = after + new[len(before):]
                        break
                if new.startswith(RETIRED_SELECTORS):
                    require(not matches(kind, new), 'W retired rebound selector remains: ' + new)
                    absent[kind + ' ' + old] = dict(matches=0, canonical_selector=new,
                        reason='explicit_worker_audio_only_retirement')
                    continue
            actual = matches(kind, new)
            require(bool(actual), 'rebound SDC replacement has no live endpoints: ' + new)
            rebound[kind + ' ' + old] = dict(selected=new, matched=len(actual),
                endpoints_sha256=digest(actual), original_line_index=change['line_index'])
    worker_retirement = None
    if worker_evidence is not None:
        worker_absent, worker_rebound = {}, {}
        for change in worker_evidence['changes']:
            for kind, body in query.findall(change['original']):
                for member in body.split():
                    if member in change['removed_selectors']:
                        require(not matches(kind, member), 'W retired selector still live: ' + member)
                        worker_absent[kind + ' ' + member] = dict(matches=0)
            for binding in change['rebound_selectors']:
                kind, old, new = binding['query'], binding['original'], binding['selected']
                require(not matches(kind, old), 'W rebound source still live: ' + old)
                actual = matches(kind, new)
                require(bool(actual), 'W rebound target missing: ' + new)
                worker_rebound[kind + ' ' + old] = dict(selected=new, matched=len(actual), endpoints_sha256=digest(actual))
        worker_retirement = dict(policy=worker_evidence['policy'], retired_selectors=worker_absent,
            rebound_selectors=worker_rebound, exact_inverse_verified=True,
            every_retired_selector_proven_absent=True, every_rebound_selector_verified=True)
    return dict(policy=evidence['policy'], role=role, input_sha256=evidence['input_sha256'],
                output_sha256=evidence['output_sha256'], retired_selectors=absent,
                rebound_selectors=rebound, every_rebound_selector_verified=True,
                every_retired_selector_proven_absent=True, worker_audio_only=worker_retirement,
                clocks_or_live_exceptions_relaxed=False)


def audit_w_recording_diagnostic_retirement(stage, netlist):
    """Prove two unused diagnostics absent while the real completion path lives."""
    source = Path(stage) / 'rtl/bluetooth/cpu_owner/workstation_ble_record_data_engine.sv'
    text = re.sub(r'//[^\n]*|/\*.*?\*/', '', source.read_text(), flags=re.S)
    unused = ('raw_start_done_i', 'raw_failure_code_i')
    for name in unused:
        require(len(re.findall(r'\b' + name + r'\b', text)) == 1 and
                re.search(r'\binput\s+wire\s+[^;]*\b' + name + r'\b', text),
                'recording diagnostic gained a source consumer: ' + name)
    for name in ('raw_start_ready_i', 'raw_capture_ready_i', 'raw_committed_frames_i',
                 'raw_channel_fault_i', 'raw_clear_done_i', 'raw_fetch_done_i',
                 'raw_fetch_fault_i', 'raw_cache_valid_i', 'raw_drained_i'):
        require(len(re.findall(r'\b' + name + r'\b', text)) > 1,
                'recording true completion/fault source consumer missing: ' + name)
    engine = 'u_bluetooth/u_core/application/command_endpoint/recording/'
    sources = {}
    for stem, net in (('channel_fault_o', 'raw_channel_fault'), ('clear_done_o', 'raw_clear_done'),
                      ('fetch_done_o', 'raw_fetch_done'), ('fetch_fault_o', 'raw_fetch_fault'),
                      ('cache_valid_o', 'raw_cache_valid'), ('object_fault_o', 'raw_object_fault')):
        names = [p for p, c in netlist.cells.items() if c['kind'].startswith('DFF') and
                 re.fullmatch('recording_ble_store/' + stem + r'_s\d+', p)]
        require(len(names) == 1 and netlist.pin(names[0], 'Q') == net and
                netlist.pin(names[0], 'CLK') == 'clk_50m',
                'recording true completion/fault driver missing: ' + stem)
        sources[net] = names[0]
    for bit in range(32):
        names = [p for p, c in netlist.cells.items() if c['kind'].startswith('DFF') and
                 re.fullmatch(f'recording_ble_store/committed_frames_o_{bit}_s' + r'\d+', p)]
        net = f'raw_committed[{bit}]'
        require(len(names) == 1 and netlist.pin(names[0], 'Q') == net and
                netlist.pin(names[0], 'CLK') == 'clk_50m',
                'recording committed frame driver missing: ' + str(bit))
        sources[net] = names[0]
    consumers = {net: [] for net in sources}
    for path, cell in netlist.cells.items():
        if not path.startswith(engine) or not re.fullmatch(r'LUT[1-6]|ALU', cell['kind']):
            continue
        for pin in cell['ports']:
            if not re.fullmatch(r'I[0-5]|CIN', pin):
                continue
            net = netlist.pin(path, pin)
            if net in consumers:
                consumers[net].append(path + '/' + pin)
    for net, pins in consumers.items():
        require(bool(pins), 'recording true completion/fault netlist consumer missing: ' + net)
    aliases = ('raw_start_done', 'raw_failure')
    for cell in netlist.cells.values():
        require(not any(re.search(r'\b(?:' + '|'.join(aliases) + r')\b', value)
                        for value in cell['ports'].values()), 'retired diagnostic has an actual alias')
    return dict(source_sha256=sha(source), unused_source_formals=list(unused),
        diagnostic_aliases_absent=list(aliases), true_status_source_count=len(sources),
        true_status={net: dict(driver=sources[net], actual_consumers=len(pins),
                              consumer_sha256=digest(sorted(pins))) for net, pins in consumers.items()},
        source_and_actual_consumer_closure_verified=True, hardware_acceptance=False)


def audit_sdc_selectors(sdc, netlist):
    """Fail on every unresolved retained member, including mixed collections.

    Only the encrypted DDR interior is deferred, by its exact opaque boundary.
    It must be rechecked against the routed VO and real STA after P&R.
    """
    clocks = set(re.findall(r'^create_(?:generated_)?clock -name (\S+)', sdc, re.M))
    universes = dict(get_regs={p for p, c in netlist.cells.items() if c['kind'].startswith('DFF')},
        get_pins={p + '/' + pin for p, c in netlist.cells.items() for pin in c['ports']},
        get_ports=set(netlist.directions[TOP]), get_clocks=clocks)
    ordered = {kind: sorted(values) for kind, values in universes.items()}
    query = re.compile(r'\[(get_pins|get_regs|get_ports|get_clocks)\s+\{([^{}]+)\}\]')
    supported = {'create_clock', 'create_generated_clock', 'set_false_path', 'set_max_delay',
                 'set_min_delay', 'set_input_delay', 'set_output_delay', 'report_timing'}
    resolutions, deferred, missing = {}, {}, []
    for number, raw in enumerate(sdc.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        require(not any(c in line for c in (';', '$', '\\')), 'unreviewed Tcl evaluation in SDC')
        shape = query.sub('QUERY', line)
        require('[' not in shape and ']' not in shape and line.split()[0] in supported,
                'unsupported SDC command/query: ' + line)
        if 'get_clocks' in line and line.startswith('set_false_path'):
            from tools.workstation_runtime_clock_audit import MODE_EXCLUSIONS
            require(line in MODE_EXCLUSIONS, 'unreviewed whole-clock cut: ' + line)
        for kind, body in query.findall(line):
            for member in body.split():
                key = kind + ' ' + member
                if key in resolutions or key in deferred:
                    continue
                if member.startswith('u_memory/u_ddr3/gw3_top/'):
                    opaque = netlist.cells.get('u_memory/u_ddr3/gw3_top', {})
                    require(opaque.get('kind') == '~GW_DDR3_PHY_MC.DDR3_Memory_Interface_Top',
                            'encrypted DDR boundary changed')
                    deferred[key] = dict(line=number, reason='encrypted_DDR_interior_requires_routed_VO')
                    continue
                pattern = re.compile(fnmatch.translate(member))
                prefix = re.split(r'[*?\[]', member, maxsplit=1)[0]
                values = ordered[kind]
                candidates = values[bisect_left(values, prefix):bisect_left(values, prefix + '\U0010ffff')]
                matches = [p for p in candidates if p == member or pattern.fullmatch(p)]
                if not matches:
                    missing.append(dict(line=number, kind=kind, member=member))
                resolutions[key] = dict(matches=len(matches), expansion_sha256=digest(matches))
    require(not missing, 'unresolved retained SDC members: ' + json.dumps(missing, separators=(',', ':')))
    return dict(sdc_sha256=hashlib.sha256(sdc.encode()).hexdigest(),
                resolved=resolutions, deferred_encrypted_ddr=deferred,
                all_visible_selector_members_resolved=True, missing_members=[],
                tool_Tcl_resolution_verified=False, encrypted_DDR_deferred=bool(deferred),
                routed_CDC_or_STA_accepted=False)


def audit_usb_rom(stage, vg_text, netlist, firmware, configuration):
    """Prove the selected capacity against actual mapped initialization words."""
    capacity = configuration.get('usb2_cpu_ram_bytes', 65536)
    require(type(capacity) is int and capacity in (49152, 65536),
            'unregistered USB CPU RAM capacity')
    # Historical RAM64 receipts predate the explicit capacity field. The word
    # checker still proves their complete64KiB image; RAM48 must name48KiB.
    require(firmware.get('ram_bytes', 65536) == capacity, 'USB firmware capacity mismatch')
    if capacity == 49152:
        from tools.workstation_usb_cpu_rom import check_banked_rom
        return check_banked_rom(stage, netlist, firmware)
    from tools.workstation_custom_board_audit import check_rom
    return dict(words=check_rom(stage, vg_text, firmware['rom_sha256']), bytes=65536,
                every_word_verified=True)


def audit(root, output, metadata):
    # Import lazily so the unchanged native auditor can dispatch here.
    from tools.workstation_custom_board_audit import (check_ports, audit_native_feedback)
    from tools.workstation_runtime_clock_audit import audit_runtime_clocks
    from tools.workstation_custom_usb2_cdc import audit_usb2_cdc
    from tools.workstation_custom_input_cdc import audit_input_fifo
    from tools.workstation_usb2_bridge_audit import audit_bridge_resets
    from tools.workstation_custom_timing import audit_resets
    from tools.workstation_ae350_clock_placement import verify_prepared as verify_clock_placement
    from tools.workstation_ae350_rtc import verify_prepared as verify_rtc
    root, output = Path(root), Path(output)
    audit_source_names = AUDIT_SOURCES
    if metadata.get('workstation_profile',{}).get('name') in (
            'custom138k-workstation-task3-m-independent-v1',
            'custom138k-workstation-task3-m-independent-ddr-map-v1'):
        audit_source_names += ('tools/workstation_usb_cpu_rom.py',)
    if metadata.get('runtime_ddr_aliases') is not None:
        audit_source_names += ('tools/workstation_ddr_map_aliases.py',)
    if metadata.get('workstation_profile',{}).get('name')=='custom138k-workstation-task3-m-direct-tf-v1':
        audit_source_names+=('tools/workstation_task3_tf_direct.py',
            'boards/custom_138k/task3_tf_direct_legacy_cdc_v1.json',
            'tools/workstation_task3_root_reset_audit.py',
            'tools/workstation_task3_native_held.py',
            'tools/workstation_task3_peripheral_releases_audit.py',
            'tools/workstation_task3_tf_startup_audit.py',
            'tools/workstation_task3_receipt_audit.py',
            'tools/workstation_task3_tf_sdc_audit.py')
    from tools.workstation_performance_reset import W_RETURN_TIMING_POLICY
    if (metadata.get('demo_runtime_timing') or {}).get('policy') == W_RETURN_TIMING_POLICY:
        audit_source_names += ('tools/workstation_w_return_mailbox_cdc.py',
                               'tools/workstation_bluetooth_ddr.py')
    audit_sources = {relative: sha(root / relative) for relative in audit_source_names}
    role, profile, stage = verify_prepared(output, metadata)
    worker_audio_only = profile['configuration'].get('display_policy') == 'disabled_worker_audio_only_v1'
    tf_direct = profile['configuration'].get('tf_policy') == 'task3_m_native_direct_tf_v1'
    require(metadata.get('top_module') == TOP and metadata.get('validation_stage') == 'integration_prepare_only' and
            metadata.get('source_policy') == 'explicit_native_board_on_resource_timing' and
            metadata.get('synthesis_allowed') is True and metadata.get('native_usb') is True and
            metadata.get('tmds_polarity_inverted') == [True] * 4 and
            metadata.get('bitstream_sha256') is None, 'prepare policy changed')
    for flag in ('place_route_allowed', 'io_electrical_complete', 'timing_constraints_complete',
                 'hardware_tested', 'deployment_allowed', 'release_ready', 'legacy_usb_host_elaborated'):
        require(metadata.get(flag) is False, 'synthesis cannot promote ' + flag)
    require(metadata.get('audio_pin_behavior') == 'ak4493s_i2s32_dual_rate_output_paced_final_pcm' and
            metadata.get('audio_clock_policy') == 'qualified_12m288_or_16m9344_native_DCS' and
            metadata.get('volume_application') == ('once_in_runtime_final_pcm_before_I2S' if worker_audio_only else
                                                  'once_in_runtime_final_pcm_before_I2S_display_and_BLE'),
            'real runtime DAC/volume selection changed')
    log = checked(output, 'synthesis.log')
    log_text = log.read_text()
    require(not re.search(r'(?m)^ERROR\b', log_text) and log_text.count('GowinSynthesis finish') == 1,
            'synthesis did not finish without errors')
    base = stage / 'impl/gwsynthesis' / BASE
    vg = base.with_suffix('.vg')
    report = base.with_name(BASE + '_syn_rsc.xml')
    output_identity = {str(p): sha(p) for p in (vg, report, log)}
    vg_text = vg.read_text()
    netlist = SynthesisNetlist(vg_text, TOP)
    totals, rows = hierarchy_counts(ET.parse(report).getroot())
    features = audit_features(role, rows, netlist,
        tf_enabled=profile['configuration'].get('tf_policy') != 'disabled_first_m_core_demo_v1',
        worker_audio_only=worker_audio_only,tf_direct_enabled=tf_direct,
        usb_cpu_ram_bytes=profile['configuration'].get('usb2_cpu_ram_bytes',65536))
    voices = audit_m_voice_storage(netlist) if role == 'M' else None
    plan = json.loads((output / 'pinout/pinout.json').read_text())
    electrical = plan['electrical_check']
    require(metadata.get('device') == plan['device'] and
            electrical.get('status') in ('blocked', 'no_voltage_domain_conflict_detected') and
            metadata.get('electrical_blocked') is (electrical['status'] == 'blocked') and
            electrical.get('actual_board_measured') is False and
            electrical.get('full_electrical_acceptance') is False, 'electrical evidence changed')
    ports = check_ports(stage, plan)
    clock_placement = verify_clock_placement(root, stage, metadata.get('ae350_core_clock_placement'))
    # Both RTC sources are in the fully hashed stage; a later live-top edit
    # cannot rewrite what this completed candidate actually synthesized.
    rtc = verify_rtc(stage, stage, metadata.get('ae350_rtc'))
    clocks = audit_runtime_clocks(root, stage, vg_text)
    base_clocks = clocks['base_clock_audit']
    usb_cdc = audit_usb2_cdc(root, vg_text, base_clocks)
    input_cdc = audit_input_fifo(root, vg_text, base_clocks)
    fifo_write_reset = None
    if profile['configuration'].get('usb_fifo_reset_policy') is not None:
        from tools.workstation_usb_fifo_reset import verify_prepared as verify_fifo_reset, audit_synthesis as audit_fifo_reset
        from tools.workstation_runtime_pcm_cdc import PcmNetlist
        fifo_write_reset = dict(prepared=verify_fifo_reset(stage, metadata['demo_usb_fifo_write_reset']),
            actual_synthesis=audit_fifo_reset(PcmNetlist(vg_text, TOP)))
    bridge = audit_bridge_resets(vg_text, TOP)
    resets = audit_resets(vg_text, base_clocks, feedback_source_clock='audio_76m8')
    feedback = (audit_worker_feedback(netlist, base_clocks) if role == 'W' else
                audit_native_feedback(vg_text, base_clocks))
    sdc = (stage / 'constraints/custom_138k.sdc').read_text()
    retirement_sdc=sdc
    if tf_direct:
        from tools.workstation_task3_tf_direct import restore_constraints
        retirement_sdc=restore_constraints(stage,sdc,metadata['task3_tf_direct_cdc'])
    retirement = audit_constraint_retirement(retirement_sdc, metadata.get('demo_constraint_retirement'), role, netlist,
        metadata['worker_audio_only']['constraints'] if worker_audio_only else None,tf_playback_enabled=tf_direct)
    performance_release = None
    demo_held_handshakes = None
    demo_boundary_cdc = None
    if metadata.get('demo_runtime_timing') is not None:
        from tools.workstation_performance_reset import audit_demo_held_handshakes, DEMO_HELD_TIMING_POLICIES
        from tools.workstation_native_protocol_audit import protocol_netlist
        timing_evidence = metadata['demo_runtime_timing']
        demo_held_handshakes = audit_demo_held_handshakes(stage, sdc, role,
            timing_evidence, protocol_netlist(vg_text, mapping='synthesis')
            if timing_evidence.get('policy') in DEMO_HELD_TIMING_POLICIES else None,
            mapping='synthesis', netlist_text=vg_text,
            task3_direct_constraints=metadata['task3_tf_direct_cdc'] if tf_direct else None,
            **({'native_protocol_profile':'m-task3-independent'}
               if profile['profile'] == 'custom138k-workstation-task3-m-independent-ddr-map-v1' else {}))
    if metadata.get('demo_boundary_cdc') is not None:
        from tools.workstation_demo_boundary_cdc import audit as audit_boundary, netlist as boundary_netlist
        from tools.workstation_demo_boundary_cdc import validate_sdc as validate_boundary
        boundary_n = boundary_netlist(vg_text, mapping='synthesis')
        demo_boundary_cdc = audit_boundary(boundary_n, mapping='synthesis', expected_role=role)
        require(demo_boundary_cdc.get('inventory_role') == role,
                'DEMO boundary consumer inventory does not match selected role')
        demo_boundary_cdc['installed_sdc'] = validate_boundary(sdc, boundary_n, demo_boundary_cdc)
    if (metadata.get('demo_runtime_timing') or {}).get('performance_release_selected') is True:
        if tf_direct:
            require(demo_held_handshakes is not None and
                    'actual_peripheral_releases' in demo_held_handshakes,
                    'DIRECT requires the actual shared performance release proof')
            performance_release = demo_held_handshakes['actual_peripheral_releases']
        else:
            from tools.workstation_performance_reset import audit as audit_performance, validate_sdc as validate_performance
            from tools.workstation_performance_reset import netlist as performance_netlist
            performance_n = performance_netlist(vg_text, mapping='synthesis')
            performance_release = audit_performance(performance_n, mapping='synthesis')
            performance_release['installed_sdc'] = validate_performance(sdc, performance_n, performance_release)
    from tools.workstation_demo_policy import POLICY, V3_POLICY
    recording_diagnostics = (audit_w_recording_diagnostic_retirement(stage, netlist)
        if role == 'W' and not worker_audio_only and retirement['policy'] in (V3_POLICY, POLICY) else None)
    selectors = audit_sdc_selectors(sdc, netlist)
    rom = audit_usb_rom(stage, vg_text, netlist, metadata['firmware'], profile['configuration'])
    # Rehash the frozen closure after all source/netlist checks.
    require(verify_prepared(output, metadata)[1] == profile, 'candidate drifted during audit')
    require(output_identity == {str(p): sha(p) for p in (vg, report, log)},
            'synthesis outputs drifted during audit')
    require(audit_sources == {relative: sha(root / relative) for relative in audit_source_names},
            'audit implementation drifted during review')
    return dict(schema=1, identity=metadata['identity'], candidate_identity=profile['candidate_identity'],
        validation_stage='task3_m_direct_tf_synthesis_only' if tf_direct else 'demo_full_profile_synthesis_only', demo_role=role, top_module=TOP,
        auditor_sha256=sha(Path(__file__)), integration_inputs_sha256=sha(output / 'integration_inputs.json'),
        audit_sources_sha256=audit_sources, audit_source_seal_before_and_after=True,
        synthesis_log_sha256=sha(log), netlist_sha256=sha(vg), resource_report_sha256=sha(report),
        staged_inputs=len(metadata['staged_input_sha256']), enabled_inputs=len(metadata['enabled_inputs']),
        source_snapshot_entries=len(metadata['source_snapshot_sha256']), source_policy='immutable_prepared_closure',
        current_live_tree_reproducibility_rechecked=False,
        resources=totals, synthesis_bsram_equivalent=totals['Bsram'], bsram_capacity=CAPACITY,
        features=features, m_voice_storage=voices, port_coverage=ports, verified_rom_words=rom['words'],
        usb_cpu_rom_audit=rom,
        rom_sha256=metadata['firmware']['rom_sha256'], high_speed_allowed=metadata['high_speed_allowed'],
        explicit_clock_audit=clocks, ae350_core_clock_placement=clock_placement, ae350_rtc=rtc,
        usb2_bridge_cdc_audit=usb_cdc, input_fifo_cdc_audit=input_cdc,
        demo_usb_fifo_write_reset_audit=fifo_write_reset,
        demo_performance_release_audit=performance_release,
        demo_held_handshake_audit=demo_held_handshakes,
        demo_boundary_cdc_audit=demo_boundary_cdc,
        bridge_reset_audit=bridge, native_usb_reset_audit=resets, native_feedback_clock_audit=feedback,
        visible_sdc_selector_audit=selectors, constraint_retirement_audit=retirement,
        recording_diagnostic_retirement_audit=recording_diagnostics,
        synthesis_clock_estimates=clock_estimates(base.with_name(BASE + '_syn.rpt.html')),
        synthesis_warnings=len(re.findall(r'(?m)^WARN\s+\(', log_text)),
        electrical_check=electrical, electrical_blocked=metadata['electrical_blocked'],
        io_electrical_complete=False, timing_closed=False, constraints_complete=False,
        whole_source_CDC_accepted=False, place_route_verified=False, hardware_tested=False,
        deployment_allowed=False, release_ready=False, bitstream_sha256=None)
