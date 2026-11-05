"""Read-only audit of explicit paired M/W closures; never physical acceptance.

Identity/source failures are fatal. Independent synthesis gates are all attempted
and their actual failures retained. In particular, a paired SDC comment cannot
satisfy source CDC, routed CDC, PLL, STA, resource or hardware gates.
"""
from pathlib import Path
import fnmatch
import json
import re
import subprocess
import xml.etree.ElementTree as ET

from tools.stage_usb_firmware import sha
from tools.workstation_synthesis_netlist import SynthesisNetlist
from tools.workstation_demo_audit import (TOP, BASE, WS, ENGINES, checked, digest,
    hierarchy_counts, audit_features, audit_m_voice_storage, audit_sdc_selectors)
from tools.workstation_memory import CAPACITY, clock_estimates

PROFILES = {
    'custom138k-workstation-task3-m-paired-checkpoint-v1': ('M', 'custom138k-native-task3-m-paired-checkpoint-revision1',
        'rtl/workstation/workstation_profile_task3_m_paired_sync_storage.sv'),
    'custom138k-workstation-task3-w-paired-checkpoint-v1': ('W', 'custom138k-native-task3-w-paired-checkpoint-revision1',
        'rtl/workstation/workstation_profile_task3_w_paired_phone_batch.sv'),
    'custom138k-workstation-task3-m-paired-sync-storage-v1': ('M', 'custom138k-native-task3-m-paired-sync-storage-revision1',
        'rtl/workstation/workstation_profile_task3_m_paired_sync_storage.sv'),
    'custom138k-workstation-task3-m-paired-phone-batch-tf-v1': ('M', 'custom138k-native-task3-m-paired-phone-batch-tf-revision1',
        'rtl/workstation/workstation_profile_task3_m_paired_phone_batch.sv'),
    'custom138k-workstation-task3-m-paired-phone-batch-reset-v1': ('M', 'custom138k-native-task3-m-paired-phone-batch-reset-revision1',
        'rtl/workstation/workstation_profile_task3_m_paired_phone_batch.sv'),
    'custom138k-workstation-task3-m-paired-phone-batch-v1': ('M', 'custom138k-native-task3-m-paired-phone-batch-revision1',
        'rtl/workstation/workstation_profile_task3_m_paired_phone_batch.sv'),
    'custom138k-workstation-task3-w-paired-phone-batch-v1': ('W', 'custom138k-native-task3-w-paired-phone-batch-revision1',
        'rtl/workstation/workstation_profile_task3_w_paired_phone_batch.sv'),
    'custom138k-workstation-task3-m-paired-phone-blocks-v1': ('M', 'custom138k-native-task3-m-paired-phone-blocks-revision1',
        'rtl/workstation/workstation_profile_task3_m_paired_phone_blocks.sv'),
    'custom138k-workstation-task3-w-paired-phone-blocks-v1': ('W', 'custom138k-native-task3-w-paired-phone-blocks-revision1',
        'rtl/workstation/workstation_profile_task3_w_paired_phone_blocks.sv'),
    'custom138k-workstation-task3-m-paired-cpu48-v1': ('M', 'custom138k-native-task3-m-paired-cpu48-revision1',
        'rtl/workstation/workstation_profile_task3_m_paired.sv'),
    'custom138k-workstation-task3-m-paired-v1': ('M', 'custom138k-native-task3-m-paired-revision1',
        'rtl/workstation/workstation_profile_task3_m_paired.sv'),
    'custom138k-workstation-task3-w-paired-v1': ('W', 'custom138k-native-task3-w-paired-revision1',
        'rtl/workstation/workstation_profile_task3_w_paired.sv'),
}
AUDIT_SOURCES = (
    'tools/workstation_task3_paired_audit.py', 'tools/workstation_custom_board_audit.py',
    'tools/workstation_usb_cpu_rom.py', 'tools/stage_usb_firmware.py',
    'tools/workstation_demo_audit.py', 'tools/workstation_profile.py',
    'tools/workstation_task3_paired_board.py', 'tools/workstation_task3_m_paired_profile.py',
    'tools/workstation_task3_w_paired_profile.py', 'tools/workstation_task3_w_media_profile.py',
    'tools/workstation_synthesis_netlist.py', 'tools/workstation_memory.py',
    'tools/workstation_runtime_clock_audit.py', 'tools/workstation_custom_clocks.py',
    'tools/workstation_custom_usb2_cdc.py', 'tools/workstation_custom_input_cdc.py',
    'tools/workstation_usb2_bridge_audit.py', 'tools/workstation_custom_timing.py',
    'tools/workstation_ae350_clock_placement.py', 'tools/workstation_ae350_rtc.py',
    'tools/workstation_usb_fifo_reset.py', 'tools/workstation_runtime_pcm_cdc.py',
    'tools/workstation_performance_reset.py', 'tools/workstation_demo_boundary_cdc.py',
    'tools/workstation_demo_policy.py', 'tools/workstation_native_protocol_audit.py',
    'tools/workstation_worker_audio_only.py', 'tools/workstation_task3_tf_direct.py',
    'tools/workstation_task3_tf_storage_selection.py',
    'tools/workstation_task3_root_reset_audit.py', 'tools/workstation_task3_native_held.py',
    'tools/workstation_task3_phone_batch_mapped_m.py',
    'tools/workstation_task3_phone_batch_mapped_w.py',
    'tools/workstation_task3_peripheral_releases_audit.py',
    'tools/workstation_task3_tf_startup_audit.py', 'tools/workstation_task3_receipt_audit.py',
    'tools/workstation_task3_tf_sdc_audit.py', 'tools/workstation_task3_clock_release_audit.py',
    'tools/workstation_task3_lcd_cdc_audit.py',
    'tools/workstation_task3_paired_clock_audit.py',
    'tools/workstation_task3_m_paired_releases_audit.py',
    'tools/workstation_task3_m_midi_release_sdc.py',
    'tools/workstation_task3_tf_contacts.py',
    'tools/workstation_task3_w_paired_cdc_audit.py',
    'tools/workstation_recording_phase1_cdc.py', 'tools/workstation_runtime_profile.py',
)


def require(ok, message):
    if not ok:
        raise ValueError('paired synthesis audit: ' + message)


def verify_m_batch_source_receipt(stage, actual, expected):
    """Read the pre-retirement receipt without making its document a new input.

    The immutable stage closure is checked before this call. Only the exact
    retired document is compatible; all executable source/proof fields remain
    exact, and neither the candidate nor its original receipt is rewritten.
    """
    if actual == expected:
        return
    document = 'rtl/workstation/TASK3_PHONE_BATCH_CONTRACT.md'
    historical = '605f3dc41c3fcbd7c1c8bf313a88433e4fa45d45a406f04a9ad6e73d724bae38'
    require(isinstance(actual, dict) and isinstance(actual.get('source_sha256'), dict),
            'M phone batch source receipt missing')
    sources = dict(actual['source_sha256'])
    require(set(sources) == set(expected['source_sha256']) | {document} and
            sources.pop(document) == historical and sha(checked(stage, document)) == historical,
            'M phone batch historical document receipt changed')
    require(dict(actual, source_sha256=sources) == expected,
            'M phone batch prepared source evidence changed')


def verify_prepared(output, metadata):
    """Verify the immutable candidate rather than today's mutable source locks."""
    output = Path(output)
    selected = metadata.get('workstation_profile', {})
    require(selected.get('name') in PROFILES, 'unregistered paired profile')
    role, identity, provider = PROFILES[selected['name']]
    artifact = checked(output, selected.get('artifact', ''))
    require(selected.get('artifact') == 'workstation_profile.json' and
            sha(artifact) == selected.get('artifact_sha256'), 'profile artifact changed')
    profile = json.loads(artifact.read_text())
    from tools.workstation_profile import prepared_specification
    spec = prepared_specification(profile)
    require(spec.get('paired_role') == role and spec.get('paired_board') is True and
            metadata.get('identity') == identity == spec['integration_identity'] and
            profile.get('profile') == selected['name'] and
            profile.get('profile_source') == spec['config'] and
            profile.get('revision') == spec['revision'], 'role/configuration identity changed')
    require(selected.get('configuration_sha256') == profile.get('profile_sha256'),
            'profile configuration binding changed')
    require(profile.get('integration_metadata_sha256') == digest(
        {k: v for k, v in metadata.items() if k != 'workstation_profile'}),
        'integration metadata binding changed')
    for key in ('staged_input_sha256', 'source_snapshot_sha256', 'firmware', 'ae350_firmware'):
        require(profile.get(key) == metadata.get(key), 'profile/integration mismatch: ' + key)
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
    require(actual - set(inputs) <= {'Prj1.gprj.user'} and set(inputs) <= actual,
            'staged file inventory changed')
    for relative, expected in inputs.items():
        require(re.fullmatch(r'[0-9a-f]{64}', expected) is not None and
                sha(checked(stage, relative)) == expected, 'staged input changed: ' + relative)
    enabled = [row.get('path') for row in ET.parse(stage / 'Prj1.gprj').find('FileList')
               if row.get('enable') == '1']
    require(enabled == metadata['enabled_inputs'] and len(enabled) == len(set(enabled)) and
            set(enabled) == set(profile['enabled_inputs']), 'GPRJ selection changed')
    from tools.workstation_profile import PROFILE_REGISTRY
    providers = {row['provider'] for row in PROFILE_REGISTRY.values()}
    require([p for p in enabled if p in providers] == [provider], 'paired provider changed')
    from tools.workstation_usb_fifo_reset import verify_demo_selection
    verify_demo_selection(stage, profile['configuration'], metadata.get('demo_usb_fifo_write_reset'),
                          enabled, expected_configuration=spec['configuration'])
    from tools import workstation_task3_paired_board as common
    # root=stage intentionally: a candidate remains inspectable after live sources
    # advance. All helper inputs used here were already checked in its closure.
    common.verify_selection(stage, stage, metadata.get('task3_paired', {}), role)
    constraints = common.verify_constraints(stage, stage, metadata)
    role_top = common.inverse_top(stage, (stage / common.TOP).read_text(), role)
    restored = common.role_helper(role).inverse_top(stage, role_top)
    require(common.digest(restored) == common.role_helper(role).PARENT_TOP_SHA256,
            'common then role exact top inverse changed')
    if spec.get('phone_batch', False):
        # Only the explicitly selected batch profiles consume these proofs.
        # root=stage keeps the immutable candidate independent of live sources.
        if role == 'M':
            from tools.workstation_task3_m_paired_profile import selected_batch_source_evidence
            verify_m_batch_source_receipt(stage, metadata.get('task3_phone_batch'),
                selected_batch_source_evidence(stage, stage, profile['configuration'], provider))
        else:
            from tools.workstation_task3_w_paired_profile import (
                BATCH_PROVIDER, BATCH_FIRMWARE_POLICY, selected_source_evidence)
            runtime = metadata.get('classic_runtime', {})
            require(provider == BATCH_PROVIDER and runtime.get('provider') == provider and
                    runtime.get('policy') == BATCH_FIRMWARE_POLICY and
                    runtime.get('worker_paired') is True and
                    runtime.get('worker_media') is True and runtime.get('phone_batch') is True,
                    'W phone batch runtime selection changed')
            preprocessed = checked(output, 'classic_runtime_preprocessed.v')
            require(sha(preprocessed) == runtime.get('preprocessed_sha256'),
                    'W phone batch preprocessed evidence changed')
            require(runtime.get('worker_media_source') == selected_source_evidence(
                stage, preprocessed.read_text()),
                'W phone batch prepared source evidence changed')
    sdc = common.restore_constraints(stage, (stage / 'constraints/custom_138k.sdc').read_text(), metadata.get('task3_paired_sdc', {}))
    if role == 'M':
        from tools.workstation_task3_tf_direct import restore_constraints
        from tools.workstation_task3_tf_storage_selection import prepared_selection
        require(metadata.get('task3_tf_direct_storage') ==
                prepared_selection(stage, stage, profile['configuration'],
                    captured_source_sha256=metadata['source_snapshot_sha256']), 'direct TF selection changed')
        sdc = restore_constraints(stage, sdc, metadata.get('task3_tf_direct_cdc', {}))
    else:
        from tools.workstation_task3_w_paired_profile import restore_constraints
        sdc = restore_constraints(sdc, metadata['worker_media']['constraints'])
    if spec.get('worker_audio_only', False):
        from tools.workstation_worker_audio_only import restore_constraints
        sdc = restore_constraints(sdc, metadata['worker_audio_only']['constraints'])
    from tools.workstation_performance_reset import verify_demo_timing
    from tools.workstation_demo_boundary_cdc import verify_demo_boundary
    verify_demo_timing(stage, sdc, role, metadata.get('demo_runtime_timing'))
    verify_demo_boundary(stage, sdc, role, metadata.get('demo_boundary_cdc'))
    from tools.workstation_demo_policy import verify_constraints
    verify_constraints(sdc, metadata.get('demo_constraint_retirement'), role,
                       tf_playback_enabled=spec.get('tf_menu_enabled', False))
    require(sha(checked(output, 'parent_prepare_metadata.json')) ==
            metadata['parent_prepare_metadata_sha256'] and
            sha(checked(output, 'pinout/pinout.json')) == metadata['pinout_sha256'],
            'parent or pinout changed')
    from tools.workstation_task3_tf_contacts import verify_plan as verify_tf_contacts
    verify_tf_contacts(stage, json.loads((output / 'pinout/pinout.json').read_text()),
                       profile['configuration'].get('tf_contact_policy'))
    require(sha(checked(output, 'workstation/resource_rework_overlays.json')) ==
            profile['resource_overlays_sha256'], 'resource overlay changed')
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
    require(metadata.get('top_module') == TOP and
            metadata.get('validation_stage') == 'integration_prepare_only' and
            metadata.get('source_policy') == 'explicit_native_board_on_resource_timing' and
            metadata.get('synthesis_allowed') is True and metadata.get('native_usb') is True and
            metadata.get('tmds_polarity_inverted') == [True] * 4 and
            metadata.get('bitstream_sha256') is None, 'prepare policy changed')
    for flag in ('place_route_allowed', 'io_electrical_complete', 'timing_constraints_complete',
                 'hardware_tested', 'deployment_allowed', 'release_ready', 'legacy_usb_host_elaborated'):
        require(metadata.get(flag) is False, 'synthesis cannot promote ' + flag)
    require(metadata.get('lcd_behavior') == common.LCD_BEHAVIOR and
            metadata.get('audio_pin_behavior') == 'ak4493s_i2s32_dual_rate_output_paced_final_pcm' and
            metadata.get('audio_clock_policy') == 'qualified_12m288_or_16m9344_native_DCS',
            'paired physical output policy changed')
    return role, profile, stage, constraints


def audit_paired_features(role, rows, netlist, *, usb_cpu_ram_bytes=65536):
    pair = {
        'bounded_lcd_link': 'u_task3_pair_link',
        'lcd_transport': 'u_task3_pair_link/transport',
        'lcd_pad_owner': 'u_task3_pair_link/pins',
        'F808_config': 'u_task3_pair_link/config_owner',
        'F808_CDC': 'u_task3_pair_link/config_cdc',
        'paired_endpoint': 'u_task3_m_endpoint' if role == 'M' else 'u_task3_bus_endpoint',
    }
    if role == 'M':
        retained = audit_features('M', rows, netlist, tf_enabled=True, tf_direct_enabled=True,
                                  usb_cpu_ram_bytes=usb_cpu_ram_bytes)
    else:
        retained = dict(retained={}, retired_prefixes=[])
        pair.update(usb_host='u_native_usb/host', usb_cpu='u_native_usb/host/cpu',
            usb_input='u_native_usb/input_owner', ae350='u_boot_memory',
            authoritative_parameters=WS + '/parameters',
            media_memory='u_task3_media/memory', media_bist='u_task3_media/memory/u_bist',
            media_arbiter='u_task3_media/memory/u_arbiter',
            real_recording_store='u_task3_media/raw_store',
            recording_object='u_bluetooth/u_core/application/command_endpoint/recording',
            HCI='u_bluetooth/u_core/transport', GATT='u_bluetooth/u_core/application',
            remote_PCM1_CDC='u_task3_pcm_control',
            CNN_stream='u_task3_media/cnn_stream',
            CNN_task='u_task3_media/cnn_stream/task_service',
            CNN='u_task3_media/cnn_stream/task_service/cnn')
        kinds = {cell['kind'] for cell in netlist.cells.values()}
        for kind in ('workstation_ble_record_data_engine', 'workstation_ble_raw_ddr_store',
                     'basic_pitch_workstation_link', 'workstation_task3_cnn_stream_w',
                     'workstation_cnn_task_service'):
            require(sum(cell['kind'] == kind for cell in netlist.cells.values()) == 1,
                    'W real owner must be unique: ' + kind)
        retired = ['u_video', 'u_tf_audio', 'u_lcd', 'recording_owner8', 'recording_ble_store',
                   'u_task3_media_apb', 'u_clock_service', ENGINES]
        for prefix in retired:
            require(not any(p == prefix or p.startswith(prefix + '/') for p in (*rows, *netlist.cells)),
                    'W retired hierarchy remains: ' + prefix)
        for forbidden in ('workstation_recording_backend', 'workstation_recording_ddr_backend',
                          'workstation_recording_service', 'ble_recording',
                          'workstation_ae350_pcm_owner', 'workstation_task3_media_apb_service',
                          'workstation_runtime_oscillator_engine', 'workstation_runtime_scope_vec', 'dvi_tx'):
            require(forbidden not in kinds, 'W duplicate/local retired kind remains: ' + forbidden)
        retained['retired_prefixes'] = retired
        require(rows['u_native_usb/host']['Bsram'] >= 38 and
                rows['u_native_usb/input_owner']['Bsram'] >= 1, 'W USB storage swept')
    require(all(path in rows for path in pair.values()),
            'paired functionality swept: ' + ', '.join(k for k, p in pair.items() if p not in rows))
    retained['retained'].update({key: dict(instance=path, **rows[path]) for key, path in pair.items()})
    retained.update(paired_role=role, unique_real_owners_verified=True,
                    hardware_functionality_verified=False)
    return retained


def audit_paired_ports(stage, plan, role):
    """Extend the exact old location authority by the four reserved CTP pads."""
    from tools import workstation_task3_paired_board as common
    from tools.workstation_profile import PROFILE_REGISTRY
    stage = Path(stage)
    require(role in ('M', 'W'), 'unknown paired port role')
    files = ET.parse(stage / 'Prj1.gprj').find('FileList')
    require(files is not None, 'paired GPRJ file list missing')
    registered = {row['provider'] for row in PROFILE_REGISTRY.values()}
    selected = [row.get('path') for row in files
                if row.get('enable') == '1' and row.get('path') in registered]
    require(len(selected) == 1, 'paired GPRJ provider missing or mixed')
    provider = selected[0]
    require(provider in {row[2] for row in PROFILES.values() if row[0] == role},
            'paired GPRJ provider does not match role ' + role)
    result = subprocess.run(['iverilog', '-g2012', '-DSYNTHESIS', '-E', '-I', str(stage),
        '-o', '-', provider], cwd=stage, capture_output=True, text=True, timeout=30)
    require(result.returncode == 0, 'paired selected provider preprocessing failed: ' + result.stderr)
    text = re.sub(r'//[^\n]*|/\*.*?\*/', '', result.stdout, flags=re.S)
    headers = re.findall(r'module\s+' + TOP + r'\s*#\(.*?\)\s*\((.*?)\);', text, re.S)
    require(len(headers) == 1, 'paired source header missing or duplicated')
    pieces = re.split(r'\b(input|output|inout)\b', headers[0])
    ports = {}
    for direction, declaration in zip(pieces[1::2], pieces[2::2]):
        declaration = declaration.strip().removeprefix('wire').strip()
        width = re.match(r'\[(\d+):(\d+)\]', declaration)
        indices = range(int(width[2]), int(width[1]) + 1) if width else None
        names = declaration[width.end():] if width else declaration
        for name in re.findall(r'[A-Za-z_][A-Za-z_0-9]*', names):
            bits = {name + f'[{index}]' for index in indices} if indices is not None else {name}
            require(not set(ports).intersection(bits), 'paired duplicate port: ' + name)
            ports.update({bit: direction for bit in bits})
    pinplan = json.loads((stage / common.PINPLAN).read_text())
    lcd = {row['port']: [row['fpga_ball']] for row in pinplan['pins'] if row['kind'] == 'programmable'}
    reserved = {port: balls for port, balls in lcd.items() if port.startswith('lcd_ctp_')}
    require(len(lcd) == 25 and len(reserved) == 4 and
            all(ports.get(port) == 'inout' for port in lcd), 'paired LCD pad direction/inventory changed')
    expected = {name: row['balls'] for name, row in plan['ports'].items()}
    require(not set(reserved).intersection(expected), 'reserved CTP duplicates original authority')
    for port in set(lcd) - set(reserved):
        require(expected.get(port) == lcd[port], 'existing LCD ball changed: ' + port)
    probe = json.loads((stage / 'probes/audio_clock_i2s/probe.json').read_text())
    require(probe['pins'].get('clk_16m9344') == 'J19' and probe['pins'].get('clk_12m288') == 'K18',
            'runtime clock supplemental pin changed')
    extra = dict(clk_16m9344=['J19'], **reserved)
    implicit = {'tmds_clk_n', 'ddr_ck_n', *(f'tmds_data_n[{i}]' for i in range(3)),
                *(f'ddr_dqs_n[{i}]' for i in range(4))}
    require(implicit.issubset(ports) and set(ports) - implicit == set(expected) | set(extra),
            'paired source and selected location coverage mismatch')
    def locations(path):
        rows = re.findall(r'^\s*IO_LOC\s+"([^"]+)"\s+([^;]+);', path.read_text(), re.M)
        actual = {name: [ball.strip() for ball in balls.split(',')] for name, balls in rows}
        require(len(actual) == len(rows), 'duplicate selected location')
        return actual
    require(locations(stage / 'constraints/custom_138k.locations.cst') == expected,
            'original location authority changed')
    require(locations(stage / 'constraints/custom_138k.cst') == dict(expected, **extra),
            'combined paired location authority changed')
    return dict(physical_port_bits=len(ports), original_location_entries=len(expected),
        compilation_provider=provider, provider_sha256=sha(stage / provider),
        preprocessed_sha256=common.digest(result.stdout), paired_LCD_inout_ports=25,
        reserved_CTP_ports=reserved, supplemental_clock=dict(clk_16m9344=['J19']),
        original_pinout_unchanged=True, scope='selected_source_ports_only',
        hardware_electrical_acceptance=False)


def audit_constraint_inventory(sdc, metadata, netlist):
    """Resolve every retirement/rebinding against the actual final netlist.

    The immutable inverse establishes policy identity. This separate check
    proves that removed names are absent and surviving replacements are live.
    A later explicit adaptation may retire an earlier replacement.
    """
    universes = dict(get_regs={p for p, c in netlist.cells.items() if c['kind'].startswith('DFF')},
        get_pins={p + '/' + pin for p, c in netlist.cells.items() for pin in c['ports']},
        get_ports=set(netlist.directions[TOP]),
        get_clocks=set(re.findall(r'^create_(?:generated_)?clock -name (\S+)', sdc, re.M)))
    query = re.compile(r'\[(get_pins|get_regs|get_ports|get_clocks)\s+\{([^{}]+)\}\]')
    bundles = [metadata['demo_constraint_retirement']]
    if 'worker_audio_only' in metadata:
        bundles.append(metadata['worker_audio_only']['constraints'])
    if 'worker_media' in metadata:
        paired = metadata['worker_media']['constraints']
        bundles.extend((paired['delegated_media'], paired))
    rules = []
    for bundle in bundles:
        for change in bundle['changes']:
            for kind, body in query.findall(change['original']):
                rules.extend((kind, member, None) for member in body.split()
                             if member in change['removed_selectors'])
            rules.extend((row['query'], row['original'], row['selected'])
                         for row in change.get('rebound_selectors', []))
    release_rebinding = metadata.get('task3_paired_sdc', {}).get('M_release_rebinding')
    if release_rebinding is not None:
        require(metadata.get('task3_paired', {}).get('role') == 'M', 'release rebinding requires explicit M')
        rules.extend(('get_pins', row['before'], row['after']) for row in release_rebinding['mappings'])
    def matches(kind, member):
        pattern = re.compile(fnmatch.translate(member))
        return sorted(p for p in universes[kind] if p == member or pattern.fullmatch(p))
    from tools.workstation_demo_policy import W_SCOPE_BINDINGS
    absent, live = {}, {}
    for index, (kind, old, selected) in enumerate(rules):
        require(not matches(kind, old), 'retired/rebound source is still live: ' + old)
        if selected is None:
            # A removed slash-form generate name must also be absent in
            # Gowin's known dot-form canonical hierarchy.
            for before, after in W_SCOPE_BINDINGS:
                if old.startswith(before):
                    alias = after + old[len(before):]
                    require(not matches(kind, alias), 'retired canonical source is still live: ' + alias)
        absent[kind + ' ' + old] = dict(matches=0)
        if selected is None:
            continue
        final = selected
        for next_kind, before, after in rules[index + 1:]:
            if next_kind == kind and final == before:
                final = after
                if final is None:
                    break
        if final is None:
            require(not matches(kind, selected), 'later retired replacement remains live: ' + selected)
            continue
        found = matches(kind, final)
        require(bool(found), 'retained replacement has no final endpoint: ' + final)
        live[kind + ' ' + old] = dict(selected=final, matches=len(found),
                                      endpoints_sha256=digest(found))
    return dict(retired=absent, retained_rebindings=live,
        every_retired_selector_absent=True, every_retained_rebinding_live=True,
        timing_budgets_or_clocks_relaxed=False, physical_CDC_accepted=False)


def audit_m_sync_storage(rows):
    """Require actual Gowin mapping, not just a block_ram source attribute."""
    selected={}
    for owner in ('collector_m','recording'):
        path='u_task3_m_endpoint/'+owner
        require(path in rows,'synchronous storage owner absent: '+path)
        counts=rows[path]
        require(counts['Bsram']>=1 and counts['Ssram']==0,
                'synchronous storage not mapped to BSRAM without RAM16: '+path)
        selected[path]=counts
    return dict(hierarchy_counts=selected,units='Gowin synthesis BSRAM-equivalent and SSRAM',
                physical_block_count_verified=False,physical_timing_verified=False)


def audit(root, output, metadata):
    root, output = Path(root), Path(output)
    seals = {name: sha(root / name) for name in AUDIT_SOURCES}
    role, profile, stage, constraint_policy = verify_prepared(output, metadata)
    log = checked(output, 'synthesis.log')
    log_text = log.read_text()
    require(not re.search(r'(?m)^ERROR\b', log_text) and log_text.count('GowinSynthesis finish') == 1,
            'synthesis did not finish without errors')
    base = stage / 'impl/gwsynthesis' / BASE
    vg, report = base.with_suffix('.vg'), base.with_name(BASE + '_syn_rsc.xml')
    output_identity = {str(p): sha(p) for p in (vg, report, log)}
    vg_text = vg.read_text()
    netlist = SynthesisNetlist(vg_text, TOP)
    totals, rows = hierarchy_counts(ET.parse(report).getroot())
    gates = {}
    def gate(name, function):
        try:
            evidence = function()
        except (ValueError, FileNotFoundError) as error:
            gates[name] = dict(passed=False, error=str(error))
            return None
        gates[name] = dict(passed=True, evidence=evidence)
        return evidence
    gate('feature_structure', lambda: audit_paired_features(role, rows, netlist,
        usb_cpu_ram_bytes=profile['configuration'].get('usb2_cpu_ram_bytes',65536)))
    if role == 'M':
        gate('M_32_voice_storage', lambda: audit_m_voice_storage(netlist))
        if profile['configuration'].get('m_endpoint_storage_policy')=='sync_score_and_final_tap_prefetch_v1':
            gate('M_sync_storage_mapping',lambda: audit_m_sync_storage(rows))
    from tools.workstation_custom_board_audit import check_ports, check_rom, audit_native_feedback
    from tools.workstation_ae350_clock_placement import verify_prepared as verify_clock
    from tools.workstation_ae350_rtc import verify_prepared as verify_rtc
    from tools.workstation_runtime_clock_audit import audit_runtime_clocks
    from tools.workstation_custom_usb2_cdc import audit_usb2_cdc
    from tools.workstation_custom_input_cdc import audit_input_fifo
    from tools.workstation_usb2_bridge_audit import audit_bridge_resets
    from tools.workstation_custom_timing import audit_resets
    plan = json.loads((output / 'pinout/pinout.json').read_text())
    electrical = plan['electrical_check']
    require(metadata.get('device') == plan['device'] and
            electrical.get('status') in ('blocked', 'no_voltage_domain_conflict_detected') and
            metadata.get('electrical_blocked') is (electrical['status'] == 'blocked') and
            electrical.get('actual_board_measured') is False and
            electrical.get('full_electrical_acceptance') is False, 'electrical evidence changed')
    gate('port_coverage', lambda: audit_paired_ports(stage, plan, role))
    gate('AE350_clock_placement', lambda: verify_clock(stage, stage, metadata.get('ae350_core_clock_placement')))
    gate('AE350_RTC', lambda: verify_rtc(stage, stage, metadata.get('ae350_rtc')))
    clocks = gate('runtime_clock_PLL_structure', lambda: audit_runtime_clocks(stage, stage, vg_text, paired_role=role))
    if clocks is not None:
        base_clocks = clocks['base_clock_audit']
        gate('USB2_CDC', lambda: audit_usb2_cdc(stage, vg_text, base_clocks))
        gate('input_FIFO_CDC', lambda: audit_input_fifo(stage, vg_text, base_clocks))
        gate('native_reset', lambda: audit_resets(vg_text, base_clocks, feedback_source_clock='audio_76m8'))
        if role == 'M':
            gate('native_feedback', lambda: audit_native_feedback(vg_text, base_clocks))
        else:
            from tools.workstation_demo_audit import audit_worker_feedback
            gate('worker_feedback', lambda: audit_worker_feedback(netlist, base_clocks))
    else:
        for name in ('USB2_CDC', 'input_FIFO_CDC', 'native_reset', 'native_feedback'):
            gates[name] = dict(passed=False, blocked_by='runtime_clock_PLL_structure')
    from tools.workstation_usb_fifo_reset import verify_prepared as verify_fifo, audit_synthesis as audit_fifo
    from tools.workstation_runtime_pcm_cdc import PcmNetlist
    gate('USB_FIFO_write_reset', lambda: dict(prepared=verify_fifo(stage, metadata['demo_usb_fifo_write_reset']),
                                             synthesis=audit_fifo(PcmNetlist(vg_text, TOP))))
    gate('USB_bridge_resets', lambda: audit_bridge_resets(vg_text, TOP))
    from tools.workstation_task3_lcd_cdc_audit import audit_lcd_input_chains
    from tools.workstation_native_protocol_audit import protocol_netlist
    if profile['profile'] in (
            'custom138k-workstation-task3-m-paired-checkpoint-v1',
            'custom138k-workstation-task3-w-paired-checkpoint-v1',
            'custom138k-workstation-task3-m-paired-sync-storage-v1',
            'custom138k-workstation-task3-m-paired-phone-batch-tf-v1',
            'custom138k-workstation-task3-m-paired-phone-batch-reset-v1',
            'custom138k-workstation-task3-m-paired-phone-batch-v1',
            'custom138k-workstation-task3-w-paired-phone-batch-v1'):
        from tools.workstation_task3_root_reset_audit import audit_selected_batch_structure
        def batch_structure():
            proof = audit_selected_batch_structure(
                protocol_netlist(vg_text, mapping='synthesis'), stage=stage)
            require(proof is not None, 'batch profile did not select a mapped batch proof')
            return proof
        gate('phone_batch_mapped_structure', batch_structure)
    gate('LCD_pad_synchronizer_structure', lambda: audit_lcd_input_chains(
        protocol_netlist(vg_text, mapping='synthesis'), stage=stage, role=role))
    sdc = (stage / 'constraints/custom_138k.sdc').read_text()
    gate('visible_SDC_members', lambda: audit_sdc_selectors(sdc, netlist))
    gate('constraint_retirement_and_rebinding', lambda: audit_constraint_inventory(sdc, metadata, netlist))
    if role == 'M':
        from tools.workstation_task3_root_reset_audit import audit_root_startup
        from tools.workstation_task3_m_paired_releases_audit import audit_paired_release_sdc
        def paired_releases():
            n = protocol_netlist(vg_text, mapping='synthesis')
            root_reset = audit_root_startup(n, stage=stage)
            return dict(actual_root_startup=root_reset,
                actual_release_SDC=audit_paired_release_sdc(n, sdc, root=root_reset))
        gate('M_paired_release_CDC', paired_releases)
        if profile['profile'] in ('custom138k-workstation-task3-m-paired-checkpoint-v1',
                                  'custom138k-workstation-task3-m-paired-sync-storage-v1',
                                  'custom138k-workstation-task3-m-paired-phone-batch-tf-v1',
                                  'custom138k-workstation-task3-m-paired-phone-batch-v1',
                                  'custom138k-workstation-task3-m-paired-phone-batch-reset-v1'):
            # Independent of the older final-consumer seals: those may reject
            # first, but must not conceal a selector reaching the wrong reset.
            from tools.workstation_task3_m_midi_release_sdc import audit_midi_release_sdc
            def midi_release_sdc():
                n = protocol_netlist(vg_text, mapping='synthesis')
                root_reset = audit_root_startup(n, stage=stage)
                return audit_midi_release_sdc(n, sdc, root=root_reset)
            gate('M_MIDI_release_SDC_semantics', midi_release_sdc)
    from tools.workstation_demo_boundary_cdc import audit as audit_boundary, netlist as boundary_netlist
    from tools.workstation_demo_boundary_cdc import validate_sdc as validate_boundary
    def boundary():
        n = boundary_netlist(vg_text, mapping='synthesis')
        if role == 'W':
            from tools.workstation_task3_w_paired_cdc_audit import audit_boundary as audit_worker_boundary
            return audit_worker_boundary(n, sdc, mapping='synthesis')
        evidence = audit_boundary(n, mapping='synthesis', expected_role=role)
        evidence['installed_sdc'] = validate_boundary(sdc, n, evidence)
        return evidence
    gate('native_boundary_CDC', boundary)
    from tools.workstation_performance_reset import audit_demo_held_handshakes
    from tools.workstation_native_protocol_audit import protocol_netlist
    from tools.workstation_task3_paired_board import restore_constraints as restore_common_sdc
    held_sdc = restore_common_sdc(stage, sdc, metadata.get('task3_paired_sdc', {}))
    if role == 'W':
        from tools.workstation_task3_w_paired_cdc_audit import audit_held as audit_worker_held
        gate('native_held_handshakes', lambda: audit_worker_held(stage, held_sdc, metadata,
            protocol_netlist(vg_text, mapping='synthesis'), mapping='synthesis'))
    else:
        gate('native_held_handshakes', lambda: audit_demo_held_handshakes(stage, held_sdc, role,
            metadata['demo_runtime_timing'], protocol_netlist(vg_text, mapping='synthesis'),
            mapping='synthesis', netlist_text=vg_text,
            task3_direct_constraints=metadata['task3_tf_direct_cdc']))
    if profile['configuration'].get('usb2_cpu_ram_bytes',65536)==49152:
        from tools.workstation_usb_cpu_rom import check_banked_rom
        gate('USB_ROM',lambda:check_banked_rom(stage,netlist,metadata['firmware']))
    else:
        gate('USB_ROM', lambda: check_rom(stage, vg_text, metadata['firmware']['rom_sha256']))
    require(verify_prepared(output, metadata)[1] == profile, 'prepared closure drifted during audit')
    require(output_identity == {str(p): sha(p) for p in (vg, report, log)}, 'synthesis outputs drifted')
    require(seals == {name: sha(root / name) for name in AUDIT_SOURCES}, 'auditor implementation drifted')
    return dict(schema=1, identity=metadata['identity'], candidate_identity=profile['candidate_identity'],
        validation_stage='task3_paired_synthesis_only', paired_role=role,
        synthesis_audit_passed=all(row['passed'] for row in gates.values()), gates=gates,
        source_policy='immutable_prepared_closure', staged_inputs=len(metadata['staged_input_sha256']),
        current_live_tree_reproducibility_rechecked=False, integration_inputs_sha256=sha(output / 'integration_inputs.json'),
        audit_sources_sha256=seals, audit_source_seal_before_and_after=True,
        synthesis_log_sha256=sha(log), netlist_sha256=sha(vg), resource_report_sha256=sha(report),
        resources=totals, synthesis_bsram_equivalent=totals['Bsram'], bsram_capacity=CAPACITY,
        constraints_exact_inverse=constraint_policy,
        synthesis_clock_estimates=clock_estimates(base.with_name(BASE + '_syn.rpt.html')),
        synthesis_warnings=len(re.findall(r'(?m)^WARN\s+\(', log_text)),
        electrical_check=plan['electrical_check'], electrical_blocked=metadata['electrical_blocked'],
        pending_physical_gates=['paired_LCD_endpoint_CDC', 'physical_BSRAM_and_resource_fit',
            'routed_PLL_budgets', 'full_STA', 'routed_CDC', 'LCD_electrical_and_link_budget',
            'two_board_functionality_and_control_to_sound_latency'],
        paired_SDC_marker_is_CDC_evidence=False, io_electrical_complete=False,
        timing_closed=False, constraints_complete=False, whole_source_CDC_accepted=False,
        place_route_verified=False, hardware_tested=False, deployment_allowed=False,
        release_ready=False, bitstream_sha256=None)
