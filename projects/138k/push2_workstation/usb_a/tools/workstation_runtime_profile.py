"""Explicit dual-rate inputs for the existing native workstation preparation.

Only the reviewed workstation profile opts in. This module selects versioned
owners and composes constraints; it never generates RTL or runs implementation.
"""
from pathlib import Path
import hashlib
import json
import re

from tools.stage_usb_firmware import sha
from tools.workstation_custom_clocks import clock_bundle
from tools.workstation_bluetooth import SDC as BLUETOOTH_SDC
from tools.workstation_custom_usb2_cdc import pattern, query
from tools.workstation_runtime_cdc import BLE_RELEASE_ALIASES, runtime_cdc_bundle
from tools.workstation_runtime_pcm_cdc import runtime_pcm_cdc_bundle
from tools.workstation_usb2_owner_reset import source_bundle as usb2_owner_reset_bundle
from tools.workstation_chorus_provenance import source_bundle as chorus_source_bundle
from tools.workstation_delay_storage_provenance import source_bundle as delay_storage_source_bundle
from tools.workstation_oscillator_expression_provenance import source_bundle as oscillator_expression_source_bundle
from tools.workstation_dispatch_slot_provenance import source_bundle as dispatch_slot_source_bundle

POLICY = 'native_dual_rate_runtime_v1'
SOURCES = (
    'rtl/migration/workstation_runtime_counter_cdc.sv',
    'rtl/workstation/workstation_profile_runtime.sv',
    'rtl/workstation/workstation_runtime_audio.sv',
    'rtl/workstation/workstation_runtime_controlled.sv',
    'rtl/services/workstation_audio_clock_service.sv',
    'rtl/services/workstation_controlled_services.sv',
    'rtl/services/workstation_media_preparation.sv',
    'rtl/audio/workstation_audio_render_service.sv',
    'rtl/audio/workstation_rate_pitch_expression.sv',
    'rtl/audio/workstation_runtime_div147.sv',
    'rtl/audio/workstation_runtime_oscillator_engine.sv',
    'rtl/audio/workstation_runtime_scope_vec.sv',
    'rtl/audio/workstation_runtime_render_engines.sv',
    'rtl/audio/workstation_runtime_chorus_effect.sv',
    'rtl/audio/workstation_runtime_spatial_reverb.sv',
    'rtl/audio/workstation_runtime_stereo_effects.sv',
    'rtl/audio/delay_ddr/workstation_runtime_delay_effect_ddr.sv',
    'rtl/audio/delay_ddr/workstation_runtime_delay_ddr_dma.sv',
    'rtl/audio/workstation_audio_clock_monitor.sv',
    'rtl/audio/workstation_sample_rate_switch.sv',
    'rtl/audio/workstation_audio_clock_domain.sv',
    'rtl/audio/workstation_pcm_frame_bridge.sv',
    'rtl/audio/workstation_i2s_serializer.sv',
    'rtl/audio/workstation_final_pcm_router.sv',
    'rtl/audio/workstation_pcm_frame_fanout.sv',
    'rtl/audio/workstation_pcm_observation_bridge.sv',
    'rtl/audio/workstation_observation_consumers.sv',
    'rtl/tf_audio/workstation_tf_frame_bridge.sv',
    'rtl/tf_audio/workstation_tf_runtime_service.sv',
    'rtl/tf_audio/workstation_tf_runtime_byte_fifo.sv',
    'rtl/tf_audio/workstation_tf_runtime_dma.sv',
    'rtl/tf_audio/storage/tf_audio_ddr_path.v',
    'rtl/display_data/display_data_analysis_source.sv',
    'rtl/display_data/workstation_display_runtime.sv',
    'rtl/display_data/display_data_writer.v',
    'rtl/display_data/display_data_reader.v',
    'rtl/display_data/feedback_capture.v',
    'rtl/display_data/output_audio_analysis.v',
    'rtl/display_data/feedback_renderer.v',
    'rtl/display_data/feedback_dashboard.v',
    'rtl/display_data/workstation_contest_brand.sv',
    'rtl/audio/scope_vec/scope_tf_transport.sv',
    'rtl/memory/workstation_runtime_memory_guard.sv',
)
DEPENDENCIES = (
    # Resource-parent music libraries parse this authority even when the
    # independent M provider disables their CNN elaboration.
    'rtl/ddr_address_map.vh',
    'rtl/display_data/feedback_dashboard.provenance.json',
    'rtl/display_data/assets/contest_brand_layout.svh',
    'rtl/display_data/assets/contest_brand_logo_pairs.memh',
    'rtl/display_data/assets/contest_brand_glyphs.memh',
    'rtl/display_data/assets/contest_brand_chunks.memh',
    'rtl/display_data/assets/contest_fpga_logo_original.png',
    'rtl/display_data/assets/contest_brand_sources.json',
    'rtl/display_data/assets/contest_brand_font_OFL.txt',
    'rtl/display_data/assets/contest_brand_layout.json',
    'rtl/display_data/assets/CONTEST_BRAND.md',
    'tools/generate_workstation_contest_brand.py',
    'probes/audio_clock_i2s/probe.json',
    'rtl/workstation/workstation_profile_hdmi.sv',
    'rtl/display_data_layout_pkg.svh',
    'rtl/audio/runtime_spatial_room_preset.svh',
    'rtl/services/workstation_controlled_services.provenance.json',
    'rtl/tf_audio/workstation_tf_runtime_storage.provenance.json',
    'rtl/audio/workstation_runtime_oscillator_engine.provenance.json',
    'rtl/audio/workstation_runtime_oscillator_engine.expression_selection.json',
    'tools/workstation_oscillator_expression_provenance.py',
    'rtl/audio/workstation_runtime_oscillator_engine.release_selection.json',
    'tools/workstation_oscillator_release_provenance.py',
    'tools/workstation_dispatch_slot_provenance.py',
    'tools/workstation_committed_glide.py',
    'tools/workstation_effect_gain_path.py',
    'tools/workstation_effects_reserved_config.py',
    'tools/workstation_brand_chunks.py',
    'tools/workstation_pcm_permission_compare.py',
    'tools/workstation_pcm_bitmap_permission.py',
    'tools/workstation_tf_failure_path.py',
    'rtl/audio/workstation_runtime_scope_vec.provenance.json',
    'rtl/audio/workstation_runtime_chorus_effect.provenance.json',
    'rtl/audio/workstation_runtime_chorus_effect.rate_delay_narrowing.json',
    'tools/workstation_chorus_provenance.py',
    'rtl/audio/workstation_runtime_spatial_reverb.provenance.json',
    'rtl/audio/workstation_runtime_stereo_effects.provenance.json',
    'rtl/audio/workstation_runtime_stereo_effects.delay_fifo_storage.json',
    'tools/workstation_delay_storage_provenance.py',
    'tools/workstation_task3_tf_storage_selection.py',
    'rtl/workstation/workstation_task3_tf_storage_top_reference.json',
    # The shared native top contains the default-off W-media branch. Its exact
    # inverse is also required by delay provenance for independent M profiles.
    'tools/workstation_task3_w_media_profile.py',
    'rtl/workstation/workstation_task3_w_media_top_reference.json',
    'rtl/workstation/workstation_task3_direct_reference.json',
    'tools/workstation_recording_capacity_provenance.py',
    'tools/workstation_recording_format_provenance.py',
    'firmware/ae350/recording_formats.lineage.json',
    'firmware/ae350/ble_business_owner.capacity_lineage.json',
    'rtl/audio/delay_ddr/workstation_runtime_delay_effect_ddr.provenance.json',
    'rtl/audio/delay_ddr/workstation_runtime_delay_ddr_dma.provenance.json',
)
REPLACEMENTS = {
    'src/migration/gw138k_counter_cdc.sv': 'rtl/migration/workstation_runtime_counter_cdc.sv',
    'src/ae350/gw138k_controlled_services.sv': 'rtl/services/workstation_controlled_services.sv',
    'src/storage/tf_audio_ddr_path.v': 'rtl/tf_audio/storage/tf_audio_ddr_path.v',
    'src/memory/display_data_writer.v': 'rtl/display_data/display_data_writer.v',
    'src/memory/display_data_reader.v': 'rtl/display_data/display_data_reader.v',
    'src/video/feedback_capture.v': 'rtl/display_data/feedback_capture.v',
    'src/video/output_audio_analysis.v': 'rtl/display_data/output_audio_analysis.v',
    'src/video/feedback_renderer.v': 'rtl/display_data/feedback_renderer.v',
    'src/video/feedback_dashboard.v': 'rtl/display_data/feedback_dashboard.v',
    'rtl/audio/scope_vec/scope_tf_transport.sv': 'rtl/audio/scope_vec/scope_tf_transport.sv',
}
# Relocation preserves the disabled parent's original bytes. The checked
# source remains the maintained scope owner; no generated RTL is involved.
INSTALL_PATHS = {
    'rtl/audio/scope_vec/scope_tf_transport.sv':
        'rtl/runtime_replacements/scope_tf_transport.sv',
}
# This package is identical to its immutable parent and must remain first in
# the project, before imports. Check the equality, rather than compiling it a
# second time or changing a historical file in place.
UNCHANGED_PARENT_INPUTS = {
    'src/memory/display_data_layout_pkg.sv': 'rtl/display_data_layout_pkg.svh',
}


REPLACED_CDC_PREFIXES = ('u_managed/', 'u_final_output_cdc/', 'u_ble_pcm_cdc/',
                         'u_tf_audio/', 'u_delay_ddr_dma/', 'u_video/u_renderer/')
USB_WRITE_RELEASE_SETUP_SELECTOR = 'u_native_usb/input_owner/queue_write_release_0*/D'
LEGACY_USB_FIRST_STAGE_SETUP = (
    'set_false_path -to [get_pins {u_native_usb/input_owner/settled_sync_0*/D '
    + USB_WRITE_RELEASE_SETUP_SELECTOR + ' u_native_usb/input_owner/panic_sync_0*/D '
    'u_native_usb/input_owner/defaults_sync_0*/D}]')


LEGACY_BLE_RELEASE_RESET = (
    'set_false_path -to [get_pins {u_ble_pcm_cdc/source_release*/CLEAR '
    'u_ble_pcm_cdc/destination_release*/CLEAR}]')
LEGACY_BLE_SDC_SHA256 = '0876e0c5d565ddcc44b1a995535ff990144b45c6d43da11f6bd238ff75ee7826'


def bluetooth_constraints(sdc, *, raw_common_reset=False):
    """Keep BLE payload/UART constraints; replace one reviewed reset query.

    The runtime's BLE release registers share the reviewed source aliases in
    runtime_cdc_bundle. This adapter does not select or filter any other CDC.
    """
    if type(raw_common_reset) is not bool:
        raise ValueError('runtime BLE raw common reset selection must be boolean')
    lines = sdc.splitlines(keepends=True)
    removed = LEGACY_BLE_RELEASE_RESET + '\n'
    if lines.count(removed) != 1:
        raise ValueError('runtime BLE reset constraint missing, duplicated or changed')
    before = hashlib.sha256(sdc.encode()).hexdigest()
    if before != LEGACY_BLE_SDC_SHA256:
        raise ValueError('runtime BLE SDC input identity changed')
    selected = ''.join(line for line in lines if line != removed)
    selectors = ([pattern('u_ble_pcm_cdc', stem, 'CLEAR', True)
                  for stem in ('source_release', 'destination_release')]
                 if raw_common_reset else
                 [pattern(scope, stem, 'CLEAR', True)
                  for _, scope, stem, _, _ in BLE_RELEASE_ALIASES])
    replacement = 'set_false_path -to ' + query(' '.join(selectors))
    return dict(sdc=selected, evidence=dict(
        policy='native_runtime_ble_own_release_v1' if raw_common_reset else 'native_runtime_ble_release_alias_v1',
        input_sha256=before, selected_sha256=hashlib.sha256(selected.encode()).hexdigest(),
        omitted=[dict(constraint=LEGACY_BLE_RELEASE_RESET,
            removed_selectors=['u_ble_pcm_cdc/source_release*/CLEAR',
                               'u_ble_pcm_cdc/destination_release*/CLEAR'],
            reason=('raw-common native runtime keeps actual BLE release pins with exact synthesis suffix selectors'
                    if raw_common_reset else
                    'native runtime uses reviewed shared release aliases; the legacy names are absent in the sealed runtime VG'))],
        replacement=dict(owner='runtime_cdc_bundle', constraint=replacement, selectors=selectors),
        tool_query_resolution_verified=False, physical_cdc_accepted=False))


def shared_constraints(sdc):
    """Remove replaced endpoints while preserving unrelated query members.

    A Tcl object list is a union. Dropping a whole command because one member
    moved also drops valid exceptions for unchanged endpoints. Filter each
    list independently and drop a command only when one of its query sides
    becomes empty. The locked parent bundle uses only these simple queries.
    """
    retained, omitted, adapted = [], [], []
    query = re.compile(r'\[(get_regs|get_pins|get_ports|get_clocks) \{([^{}]+)\}\]')
    for line in sdc.splitlines():
        if 'u_native_usb/input_owner/queue_write_release_0' in line:
            if line != LEGACY_USB_FIRST_STAGE_SETUP:
                raise ValueError('unsupported legacy USB write-release setup constraint: ' + line)
            selected = line.replace(USB_WRITE_RELEASE_SETUP_SELECTOR + ' ', '', 1)
            retained.append(selected)
            adapted.append(dict(constraint=line, selected=selected,
                removed_selectors=[USB_WRITE_RELEASE_SETUP_SELECTOR],
                reason='native stopped-clock fence requires a bounded setup path to the USB write-release first stage; preserve the other legacy endpoints'))
            continue
        if 'tf_run_meta' in line:
            if line != 'set_false_path -to [get_pins {tf_run_meta*/D}]':
                raise ValueError('unsupported legacy TF run constraint: ' + line)
            omitted.append(dict(constraint=line, removed_selectors=['tf_run_meta*/D'],
                reason='native runtime does not instantiate the legacy TF DAC consumer; verify pruning in synthesized netlist',
                empty_query_sides=['get_pins']))
            continue
        if not any(prefix in line for prefix in REPLACED_CDC_PREFIXES):
            retained.append(line)
            continue
        removed, empty = [], []

        def select(match):
            members = match[2].split()
            keep = [member for member in members
                    if not member.startswith(REPLACED_CDC_PREFIXES)]
            removed.extend(member for member in members if member not in keep)
            if not keep:
                empty.append(match[1])
            return '[' + match[1] + ' {' + ' '.join(keep) + '}]'

        selected = query.sub(select, line)
        if not removed or any(prefix in selected for prefix in REPLACED_CDC_PREFIXES):
            raise ValueError('unsupported runtime shared CDC constraint: ' + line)
        evidence = dict(constraint=line, removed_selectors=removed,
                        reason='replaced runtime owner or tagged payload; requires separate endpoint audit')
        if empty:
            omitted.append(dict(**evidence, empty_query_sides=empty))
        else:
            retained.append(selected)
            adapted.append(dict(**evidence, selected=selected))
    return dict(sdc='\n'.join(retained) + ('\n' if retained else ''),
                omitted=omitted, adapted=adapted)


def protocol_constraints(*, ble_raw_enabled=False, business_owner_enabled=False):
    """Bound existing held-word handshakes at their native runtime scopes.

    SUG940 5.4.1/5.4.2: max delay retains setup; only the specified held
    payload paths lose hold. First-stage D exceptions never cover later
    synchronizer stages, functional resets, or whole clock domains.
    """
    if type(ble_raw_enabled) is not bool or type(business_owner_enabled) is not bool:
        raise ValueError('runtime protocol selections must be boolean')
    if business_owner_enabled and not ble_raw_enabled:
        raise ValueError('business mailbox requires selected BLE raw storage')
    lines = []

    def held(source, destination, budget):
        path = '-from [get_pins {' + source + '}] -to [get_pins {' + destination + '}]'
        lines.extend((f'set_max_delay {budget:.3f} ' + path, 'set_false_path -hold ' + path))

    def receiver(scope, first, second, source=None):
        a, b = scope + '/' + first, scope + '/' + second
        origin = ('-from [get_pins {' + scope + '/' + source + '_s*/Q}] ') if source else ''
        lines.extend(('set_false_path ' + origin + '-to [get_pins {' + a + '_s*/D}]',
                      'set_max_delay 2.000 -from [get_pins {' + a + '_s*/Q}] '
                      '-to [get_pins {' + b + '_s*/D}]'))

    # The stream adapter holds its word until the two-stage ACK returns;
    # req_meta -> req_sync -> req_settled precedes the capture/ACK edge.
    for scope, budget in (('u_managed/display', 20.0), ('u_managed/health_snapshot', 13.020),
                          ('u_video/u_applied_parameters_cdc', 20.0)):
        held(scope + '/held_data_*_s*/Q', scope + '/destination_data_*_s*/D', budget)
        receiver(scope, 'req_meta', 'req_sync')
        receiver(scope, 'ack_meta', 'ack_sync')
    # Gowin absorbs the 98 physical-observation held bits into the FIFO's
    # synchronous RAM read outputs. They share the mailbox acceptance CE and
    # cannot update until its ACK returns. Keep this path separate from the
    # 73 ordinary held FFs: the native-protocol audit proves each selected D
    # has exactly one registered SDPX9B DO driver and the exact acceptance CE.
    held('u_managed/observation/frames/*g_small_head.memory_g_small_head.memory_0_*_s/DO*',
         ' '.join(f'u_managed/display/destination_data_{bit}_s*/D' for bit in range(105, 203)), 20.0)
    # TF control is a two-flop toggle exchange, with a further capture edge.
    held('u_tf_audio/held_control_*_s*/Q', 'u_tf_audio/compute_control_*_s*/D', 13.020)
    for stem in ('request_sync', 'ack_sync'):
        receiver('u_tf_audio', stem + '_0', stem + '_1')
    for bit, source in ((0, 'pc_framing_sticky'), (1, 'pc_drop_seen_50')):
        receiver('u_managed', 'pc_health_meta_' + str(bit), 'pc_health_sync_' + str(bit), source)
    # The native APB response stays unchanged after the shared payload/ACK
    # edge until a new request completes the full return trip. Keep setup
    # bounded, and waive only the 33 exact held response hold paths.
    held('u_managed/control_cdc/response_held_*_s*/Q',
         'u_managed/control_cdc/response_local_*_s*/D', 20.0)
    # Registered delay heartbeat and TF quiesce levels. Only the named
    # source-Q -> first-D crossing is asynchronous; later stages stay timed.
    delay = 'u_managed/runtime/service/workstation/runtime_effects.effects/delay_stage'
    dma = 'u_managed/runtime/delay_dma'
    for source_scope, destination_scope in ((delay, dma), (dma, delay)):
        lines.extend(('set_false_path -from [get_pins {' + source_scope + '/heartbeat_counter_4_s*/Q}] '
                      '-to [get_pins {' + destination_scope + '/peer_meta_s*/D}]',
                      'set_max_delay 2.000 -from [get_pins {' + destination_scope + '/peer_meta_s*/Q}] '
                      '-to [get_pins {' + destination_scope + '/peer_sync_s*/D}]'))
    lines.extend(('set_false_path -from [get_pins {u_tf_audio/source_quiesce_s*/Q}] '
                  '-to [get_pins {u_tf_audio/frames/quiesce_sync_0_s*/D}]',
                  'set_max_delay 2.000 -from [get_pins {u_tf_audio/frames/quiesce_sync_0_s*/Q}] '
                  '-to [get_pins {u_tf_audio/frames/quiesce_sync_1_s*/D}]'))
    for scope, stem in (('u_tf_audio/frames', 'quiet_sync'),
                        ('u_tf_audio/frames', 'expected_valid_sync'),
                        ('u_tf_audio/frames', 'quiesce_return_sync'),
                        ('u_tf_audio', 'memory_gate_sync'), ('u_tf_audio', 'memory_quiet_sync'),
                        ('u_tf_audio', 'memory_open_sync')):
        receiver(scope, stem + '_0', stem + '_1')
    # Native DMA holds metadata until restart. The receiving valid now has
    # its own third settled stage before playback can consume the sampled bus.
    held('u_tf_audio/path/g_runtime_dma.u_dma/staged_file_size_*_s*/Q',
         'u_tf_audio/path/file_size_meta_*_s*/D', 10.0)
    for first, second in (('file_size_valid_meta', 'file_size_valid_sync'),
                          ('ddr_error_meta', 'ddr_error_sync'), ('pb_meta', 'pb_sync'),
                          ('pb_done_meta', 'pb_done_sync')):
        receiver('u_tf_audio/path', first, second)
    # Only ACK bits 1/2/4 originate in memory_clk; bits 0/3 are already local.
    for bit in (1, 2, 4):
        receiver('u_tf_audio/path', 'runtime_ack_meta_' + str(bit), 'runtime_ack_sync_' + str(bit))
    # Existing one-word adapters acknowledge only after their local capture.
    for scope in ('u_managed/pc_bytes', 'u_video/u_renderer/u_capture',
                  'u_video/u_runtime_display/observation'):
        receiver(scope, 'ack_meta', 'ack_sync')
    # This is a held loss indication (sticky OR nonzero), not a binary count
    # sampled as a word. Its second stage and fault latch remain normally timed.
    for bit in (0, 1):
        receiver('u_managed/display_observation_health', 'loss_meta_' + str(bit), 'loss_sync_' + str(bit))
    # APB waits for the settled response ACK before launching another word.
    for scope in ('u_clock_control', *(['business_commands'] if business_owner_enabled else [])):
        for source, destination in (('request_held', 'request_local'), ('response_held', 'response_local')):
            held(scope + '/' + source + '_*_s*/Q', scope + '/' + destination + '_*_s*/D', 20.0)
        receiver(scope, 'req_meta', 'req_sync')
        receiver(scope, 'ack_meta', 'ack_sync')
    if ble_raw_enabled:
        scope = 'recording_ble_store/'
        # A return is held through request synchronization and all eight
        # unpack cycles; ACK returns only after the final local write.
        for source, destination in (('return_data', 'unpack_data'), ('return_generation', 'unpack_generation'),
                                    ('return_word', 'unpack_word')):
            held(scope + source + '_*_s*/Q', scope + destination + '_*_s*/D', 10.0)
        for first, second in (('command_req_meta', 'command_req_sync'), ('command_ack_meta', 'command_ack_sync'),
                              ('cancel_meta', 'cancel_sync'), ('status_req_meta', 'status_req_sync'),
                              ('status_ack_meta', 'status_ack_sync'), ('return_req_meta', 'return_req_sync'),
                              ('return_ack_meta', 'return_ack_sync')):
            receiver(scope[:-1], first, second)
        # Status is held until status_ack; completion remains unchanged until
        # a subsequent command, which cannot launch before its ACK returns.
        # Include only their control-domain capture/qualification registers.
        for sources, destinations in (
            (('status_payload_*',), ('committed_frames_o_*', 'memory_drained', 'channel_fault_o',
                                    'failure_code_o_*', 'capture_active', 'cache_valid_o')),
            (('completion_generation_*', 'completion_committed_*', 'completion_kind_*', 'completion_code_*'),
             ('committed_frames_o_*', 'channel_fault_o', 'fetch_fault_o', 'object_fault_o', 'clear_pending',
              'cache_valid_o', 'clear_sent', 'capture_active', 'failure_code_o_*', 'start_done_o',
              'clear_done_o', 'fetch_done_o', 'fetch_active', 'raw_empty'))):
            source = ' '.join(scope + stem + '_s*/Q' for stem in sources)
            destination = ' '.join(scope + stem + '_s*/' + pin for stem in destinations for pin in ('D', 'CE'))
            held(source, destination, 10.0)
    return '\n'.join(lines) + '\n'


def constraints(root, shared_crossings, *, local_panel_enabled=True, ble_raw_enabled=False,
                business_owner_enabled=False):
    """Keep surviving constraints, inventory removed hierarchy, fail closed.

    The new runtime CDC needs a separate endpoint audit after synthesis. No
    old u_managed/FPC constraint is silently rebound to a different owner.
    This is a synthesis checkpoint, never a P&R/deployment authorization.
    """
    root = Path(root)
    clocks = clock_bundle(root, local_panel_enabled=local_panel_enabled)
    probe_path = root / 'probes/audio_clock_i2s/probe.json'
    probe = json.loads(probe_path.read_text())
    if (probe['pins'].get('clk_16m9344') != 'J19' or
            probe['pins'].get('clk_12m288') != 'K18'):
        raise ValueError('reviewed dual-audio reference pins changed')
    shared = shared_constraints(shared_crossings['sdc'])
    runtime_cdc = runtime_cdc_bundle(root, raw_common_reset=True)
    runtime_pcm_cdc = runtime_pcm_cdc_bundle(root)
    owner_reset = usb2_owner_reset_bundle(root)
    chorus_source = chorus_source_bundle(root)
    delay_fifo_storage = delay_storage_source_bundle(root)
    oscillator_expression_source = oscillator_expression_source_bundle(root)
    dispatch_slot_source = dispatch_slot_source_bundle(root)
    bluetooth = bluetooth_constraints(BLUETOOTH_SDC, raw_common_reset=True)
    if runtime_cdc['sdc'].splitlines().count(bluetooth['evidence']['replacement']['constraint']) != 1:
        raise ValueError('runtime BLE reset replacement constraint missing or duplicated')
    selected = 'u_managed/runtime/clocks/selector/CLKOUT'
    guard = 'u_runtime_memory_guard/'
    memory_clock = next(entry for entry in clocks['plan']['generated'] if entry['name'] == 'ddr_ui100')
    memory_period = 1_000_000_000 / memory_clock['frequency_hz']
    # Gray flight bounds belong to runtime_cdc_sdc. These retained exceptions
    # target only the guard's existing first stage and local release inputs.
    guard_reset_sdc = (
        f'set_false_path -to [get_pins {{{guard}open_meta*/D}}]\n'
        f'set_false_path -to [get_pins {{{guard}control_reset_pre*/CLEAR '
        f'{guard}control_reset_n*/CLEAR {guard}memory_reset_pre*/CLEAR '
        f'{guard}memory_reset_n*/CLEAR {guard}availability_release*/CLEAR '
        f'{guard}grant_release*/CLEAR}}]\n'
    )
    audio_sdc = (
        'create_clock -name dac_ref16m9344 -period 59.051398337 [get_ports {clk_16m9344}]\n'
        'create_generated_clock -name selected48 -source [get_ports {clk_12m288}] '
        '-master_clock dac_ref12m288 -divide_by 1 [get_pins {' + selected + '}]\n'
        'create_generated_clock -name selected44 -source [get_ports {clk_16m9344}] '
        '-master_clock dac_ref16m9344 -divide_by 1 -add [get_pins {' + selected + '}]\n'
        'set_false_path -from [get_clocks {selected48}] -to [get_clocks {selected44}]\n'
        'set_false_path -from [get_clocks {selected44}] -to [get_clocks {selected48}]\n'
    )
    return dict(policy=POLICY, sdc=clocks['sdc'] + audio_sdc + guard_reset_sdc + owner_reset['sdc'],
        chorus_source=chorus_source,
        delay_fifo_storage=delay_fifo_storage,
        oscillator_expression_source=oscillator_expression_source,
        dispatch_slot_source=dispatch_slot_source,
        usb2_owner_reset={key: value for key, value in owner_reset.items() if key != 'sdc'},
        runtime_cdc_sdc=runtime_cdc['sdc'] + runtime_pcm_cdc['sdc'] + protocol_constraints(
            ble_raw_enabled=ble_raw_enabled, business_owner_enabled=business_owner_enabled),
        bluetooth_sdc=bluetooth['sdc'], bluetooth_cdc_adaptation=bluetooth['evidence'],
        runtime_cdc={key: value for key, value in runtime_cdc.items() if key != 'sdc'},
        runtime_pcm_cdc={key: value for key, value in runtime_pcm_cdc.items() if key != 'sdc'},
        shared_sdc=shared['sdc'], omitted_shared_constraints=shared['omitted'],
        adapted_shared_constraints=shared['adapted'],
        extra_cst='IO_LOC "clk_16m9344" J19;\nIO_PORT "clk_16m9344" IO_TYPE=LVCMOS33 PULL_MODE=NONE;\n',
        reference_evidence=dict(source='probes/audio_clock_i2s/probe.json', sha256=sha(probe_path)),
        clock_plan_source=clocks['source'], clock_plan_sha256=clocks['source_sha256'],
        clocks_hz=dict(reference48=12288000, reference44=16934400, compute=76800000),
        selected_clock_target=selected, cdc_constraints_complete=False,
        memory_guard_gray=dict(source=guard + 'memory_gray*', destination=guard + 'gray_meta*',
            source_clock='ddr_ui100', source_clock_hz=memory_clock['frequency_hz'],
            max_delay_ns=memory_period, propagation_skew_upper_bound_ns=memory_period,
            skew_bound_method='each_bit_nonnegative_propagation_bounded_by_one_source_period',
            setup_false_path=False, endpoint_and_routed_bound_verified=False),
        physical_gates_passed=False, deployment_allowed=False,
        remaining=['Runtime CDC/Gray/reset/held-payload endpoint inventory and propagation bounds',
                   'Both selected clock modes and switching path routed timing/PLL audit',
                   'Whole workstation resource, feature-preservation and hardware acceptance'])
