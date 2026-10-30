"""Explicit dual-rate inputs for the existing native workstation preparation.

Only the reviewed workstation profile opts in. This module selects versioned
owners and composes constraints; it never generates RTL or runs implementation.
"""
from pathlib import Path
import json
import re

from tools.stage_usb_firmware import sha
from tools.workstation_custom_clocks import clock_bundle
from tools.workstation_runtime_cdc import runtime_cdc_bundle

POLICY = 'native_dual_rate_runtime_v1'
SOURCES = (
    'rtl/workstation/workstation_profile_runtime.sv',
    'rtl/workstation/workstation_runtime_audio.sv',
    'rtl/workstation/workstation_runtime_controlled.sv',
    'rtl/services/workstation_audio_clock_service.sv',
    'rtl/services/workstation_controlled_services.sv',
    'rtl/services/workstation_media_preparation.sv',
    'rtl/audio/workstation_audio_render_service.sv',
    'rtl/audio/workstation_rate_pitch_expression.sv',
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
    'rtl/audio/scope_vec/scope_tf_transport.sv',
    'rtl/memory/workstation_runtime_memory_guard.sv',
)
DEPENDENCIES = (
    'rtl/memory/RUNTIME_MEMORY_GUARD_CONTRACT.md',
    'probes/audio_clock_i2s/probe.json',
    'rtl/workstation/workstation_profile_hdmi.sv',
    'rtl/display_data_layout_pkg.svh',
    'rtl/audio/runtime_spatial_room_preset.svh',
    'rtl/services/workstation_controlled_services.provenance.json',
    'rtl/services/AUDIO_CLOCK_SERVICE_CONTRACT.md',
    'rtl/services/MEDIA_STOP_POLICY.md',
    'rtl/services/MEDIA_PREPARATION_CONTRACT.md',
    'rtl/bluetooth/WORKSTATION_BLE_SEAL_CONTRACT.md',
    'rtl/tf_audio/workstation_tf_runtime_storage.provenance.json',
    'rtl/tf_audio/WORKSTATION_TF_RUNTIME_SERVICE_CONTRACT.md',
    'rtl/tf_audio/WORKSTATION_TF_FRAME_BRIDGE_CONTRACT.md',
    'rtl/audio/workstation_runtime_oscillator_engine.provenance.json',
    'rtl/audio/workstation_runtime_scope_vec.provenance.json',
    'rtl/audio/workstation_runtime_chorus_effect.provenance.json',
    'rtl/audio/workstation_runtime_spatial_reverb.provenance.json',
    'rtl/audio/workstation_runtime_stereo_effects.provenance.json',
    'rtl/audio/delay_ddr/workstation_runtime_delay_effect_ddr.provenance.json',
    'rtl/audio/delay_ddr/workstation_runtime_delay_ddr_dma.provenance.json',
)
REPLACEMENTS = {
    'src/ae350/gw138k_controlled_services.sv': 'rtl/services/workstation_controlled_services.sv',
    'src/storage/tf_audio_ddr_path.v': 'rtl/tf_audio/storage/tf_audio_ddr_path.v',
    'src/memory/display_data_writer.v': 'rtl/display_data/display_data_writer.v',
    'src/memory/display_data_reader.v': 'rtl/display_data/display_data_reader.v',
    'src/video/feedback_capture.v': 'rtl/display_data/feedback_capture.v',
    'src/video/output_audio_analysis.v': 'rtl/display_data/output_audio_analysis.v',
    'src/video/feedback_renderer.v': 'rtl/display_data/feedback_renderer.v',
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


def constraints(root, shared_crossings):
    """Keep surviving constraints, inventory removed hierarchy, fail closed.

    The new runtime CDC needs a separate endpoint audit after synthesis. No
    old u_managed/FPC constraint is silently rebound to a different owner.
    This is a synthesis checkpoint, never a P&R/deployment authorization.
    """
    root = Path(root)
    clocks = clock_bundle(root)
    probe_path = root / 'probes/audio_clock_i2s/probe.json'
    probe = json.loads(probe_path.read_text())
    if (probe['pins'].get('clk_16m9344') != 'J19' or
            probe['pins'].get('clk_12m288') != 'K18'):
        raise ValueError('reviewed dual-audio reference pins changed')
    shared = shared_constraints(shared_crossings['sdc'])
    runtime_cdc = runtime_cdc_bundle(root)
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
    return dict(policy=POLICY, sdc=clocks['sdc'] + audio_sdc + guard_reset_sdc,
        runtime_cdc_sdc=runtime_cdc['sdc'],
        runtime_cdc={key: value for key, value in runtime_cdc.items() if key != 'sdc'},
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
