"""Explicit native-board integration preparation; never P&R or deployment."""

from pathlib import Path
import importlib
import json
import shutil
import sys
import xml.etree.ElementTree as ElementTree

from tools.stage_usb_firmware import sha, stage_usb2_cpu_firmware
from tools.workstation_pinout import prepare as prepare_pinout
from tools.workstation_usb2_input import NATIVE_INPUT_SOURCES, LOCKED_INPUT_SOURCES
from tools.workstation_usb2_soc import SOC_SOURCE_PATHS
from tools.workstation_custom_clocks import clock_bundle, shared_cdc_bundle
from tools.workstation_custom_usb2_cdc import cdc_bundle
from tools.workstation_custom_input_cdc import input_cdc_bundle
from tools.workstation_bluetooth import prepare as prepare_bluetooth, stage_business, SDC as BLUETOOTH_SDC
from tools.workstation_board_peripherals import prepare as prepare_peripherals, reviewed_profile, LCD_SDC, local_panel_bundle
from tools.workstation_custom_timing import apply as adapt_timing, constraints as timing_constraints
from tools.workstation_custom_flash import prepare as prepare_model_flash, SDC as MODEL_FLASH_SDC
from tools.workstation_video_mode import apply as apply_video_mode, PROFILES_720
from tools.workstation_ble_storage_cdc import constraints as storage_constraints


IDENTITY = 'custom138k-native-integration-20261027-a26'
NATIVE_OVERLAYS = {
    'src/memory/ddr_address_map.vh': 'rtl/ddr_address_map.vh',
    'rtl/audio/scope_vec/scope_control_player.sv': 'rtl/audio/scope_vec/scope_control_player.sv',
    'rtl/music/music_async_fifo.sv': 'rtl/music/music_async_fifo.sv',
}
FPC_AUDIO_CST = 'boards/custom_138k/audio.cst'
DISPLAY_CST = 'boards/custom_138k/display.cst'
DDR_CST = 'boards/custom_138k/ddr.cst'
FPC_AUDIO_SDC = (
    'set_max_delay 10.000 -from [get_regs {u_fpc_audio/u_samples/held_data*}] '
    '-to [get_regs {u_fpc_audio/u_samples/destination_data*}]\n'
    'set_false_path -hold -from [get_regs {u_fpc_audio/u_samples/held_data*}] '
    '-to [get_regs {u_fpc_audio/u_samples/destination_data*}]\n'
    'set_false_path -to [get_pins {u_fpc_audio/u_samples/req_meta*/D u_fpc_audio/u_samples/ack_meta*/D '
    'u_fpc_audio/reference_sync_0*/D}]\n'
    'set_false_path -to [get_pins {u_fpc_audio/u_samples/source_release*/CLEAR '
    'u_fpc_audio/u_samples/destination_release*/CLEAR u_fpc_audio/release_pipe*/CLEAR u_fpc_audio/pll_release*/CLEAR '
    'u_fpc_audio/reference_*/CLEAR}]\n'
)
NATIVE_SOURCES = (*SOC_SOURCE_PATHS, *NATIVE_INPUT_SOURCES,
                  'rtl/workstation/workstation_custom_138k_top.sv',
                  'rtl/audio/workstation_fpc_audio.sv',
                  'rtl/clock/workstation_ae350_rtc.sv',
                  'rtl/display_data/workstation_lcd.sv',
                  'rtl/bluetooth/workstation_bluetooth.sv',
                  'rtl/bluetooth/gw138k_ble_status_uart.v',
                  'rtl/memory/workstation_ddr_bist.v',
                  'rtl/display_data/workstation_custom_dvi.sv')
# Only the explicit workstation profile migrates this composition boundary.
# The included implementation and provenance remain in the staged closure;
# only its wrapper and admission module are direct compilation entries.
PROFILE_SOURCES = ('rtl/workstation/workstation_profile_hdmi.sv',
                   'rtl/display_data/workstation_ddr_scan_window.sv')
PROFILE_DEPENDENCIES = ('rtl/workstation/workstation_hdmi_display.sv',
                        'rtl/workstation/workstation_hdmi_display.provenance.json')
REPLACED_INPUTS = {
    'src/memory/ddr3_bist.v': 'rtl/memory/workstation_ddr_bist.v',
    'src/usb_a/VexRiscv.v': 'vendor/usb_host_fs_8fc3/src/VexRiscv.v',
    'src/usb_a/simpleuart.v': 'vendor/usb_host_fs_8fc3/src/simpleuart.v',
    'src/usb_a/push2_usb_a_control.sv': 'rtl/push2_usb_a_control.sv',
    'src/push2/push2_controls.sv': 'rtl/audio/push2_controls.sv',
    'src/push2/push2_lights.sv': 'rtl/push2/push2_lights.sv',
    'src/push2/push2_led_tx.sv': 'rtl/push2/push2_led_tx.sv',
    'src/push2/push2_playlist_hold.sv': 'rtl/push2/push2_playlist_hold.sv',
    'src/usb_a/push2_song_menu.sv': 'rtl/push2/push2_song_menu.sv',
    'src/usb_a/push2_score_guide.sv': 'rtl/push2/push2_score_guide.sv',
    'src/push2/push2_song_screen.sv': 'rtl/push2/push2_song_screen.sv',
    'src/push2/push2_surface_pixels.sv': 'rtl/display_data/push2_surface_pixels.sv',
}
EXCLUDED_INPUTS = ('src/push2/gw138k_push_workstation_top.v', 'src/usb_a/iosys2.v',
                   'vendor/sipeed_dvi/dvi_tx_top.v', 'vendor/sipeed_dvi/dvi_tx_tmds_phy.v',
                   'vendor/sipeed_dvi/dvi_tx_clk_drv.v',
                   'constraints/tang_mega_138k.cst', 'constraints/tang_mega_138k.sdc')


def source_snapshot(root, extra_inputs=()):
    """Inventory the preparation inputs, including inactive maintained RTL.

    This captures drift during preparation and verification. The reviewed
    profile separately locks every actual source owner and build dependency.
    """
    root = Path(root).resolve()
    selected = [root / name for name in ('build.py', 'firmware.c', 'gw25k_panel.h', *extra_inputs)]
    for directory in ('rtl', 'tools', 'drivers/usb2', 'boards/custom_138k', 'baselines'):
        selected += [source for source in (root / directory).rglob('*') if source.is_file()
                     and source.suffix in ('.py', '.sv', '.v', '.vh', '.svh', '.mem', '.json', '.c', '.h', '.cst')]
    for source in selected:
        if not source.is_file() or not source.resolve().is_relative_to(root):
            raise FileNotFoundError('missing or escaping native-board snapshot input: ' + str(source))
    return {source.relative_to(root).as_posix(): sha(source) for source in sorted(set(selected))}


def prepare(root, netlist_directory, output, riscv_prefix=None, allow_high_speed=True, hdmi_mode='1080p60',
            *, workstation_profile=None, logic_only=False):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError('custom-board output already exists: ' + str(output))
    if workstation_profile is not None:
        from tools.workstation_profile import load as load_profile
        profile = load_profile(root, workstation_profile, allow_high_speed=allow_high_speed, hdmi_mode=hdmi_mode)
    else:
        profile = None
    if logic_only and profile is not None:
        raise ValueError('logic-only is limited to the unprofiled native resource experiment')
    resource_optimization = profile is not None and profile['configuration'].get('native_resource_optimization', False)
    if type(resource_optimization) is not bool:
        raise ValueError('native resource optimization selection must be boolean')
    if resource_optimization:
        raise ValueError('full native resource optimization requires an independently integrated backend')
    ram_bytes = 65536 if profile is None else profile['configuration'].get('usb2_cpu_ram_bytes', 65536)
    if type(ram_bytes) is not int or ram_bytes not in (49152, 65536):
        raise ValueError('USB CPU RAM profile capacity must be 48 or 64 KiB')
    if resource_optimization:
        from tools.workstation_static_checks import validate_cues
        validate_cues(root / 'rtl/audio/scope_vec/data/scene_controls.mem', 69)
    runtime = profile is not None and profile['configuration'].get('audio_policy') == 'native_dual_rate_runtime_v1'
    local_panel_enabled = True
    if runtime:
        from tools.workstation_profile import specification, recognition_metadata, CPU_BUSINESS_NAME
        selected_provider = specification(profile['name'])['provider']
        recognition = recognition_metadata(profile)
        local_panel_enabled = specification(profile['name']).get('local_panel_enabled', True)
    native_sources = (*NATIVE_SOURCES, *PROFILE_SOURCES) if workstation_profile is not None else NATIVE_SOURCES
    profile_dependencies = PROFILE_DEPENDENCIES if workstation_profile is not None else ()
    if runtime:
        from tools.workstation_runtime_profile import SOURCES, DEPENDENCIES
        native_sources = tuple(source for source in native_sources if source not in (
            'rtl/workstation/workstation_custom_138k_top.sv', 'rtl/audio/workstation_fpc_audio.sv',
            'rtl/workstation/workstation_profile_hdmi.sv')) + SOURCES
        profile_dependencies += DEPENDENCIES
        if selected_provider != 'rtl/workstation/workstation_profile_runtime.sv':
            native_sources = tuple(selected_provider if source == 'rtl/workstation/workstation_profile_runtime.sv' else source
                                   for source in native_sources)
            profile_dependencies += ('rtl/workstation/workstation_profile_runtime.sv',)
    recording_selected=runtime and specification(profile['name']).get('recording_enabled',False)
    ble_raw_selected=runtime and specification(profile['name']).get('ble_recording_storage_enabled',False)
    business_selected=runtime and specification(profile['name']).get('business_owner_enabled',False)
    business_telemetry_alias_selected=business_selected and profile['name']==CPU_BUSINESS_NAME
    hci_selected=business_selected and specification(profile['name']).get('hci_shared_owner_enabled',False)
    classic_selected=hci_selected and specification(profile['name']).get('classic_runtime_enabled',False)
    demo_role=specification(profile['name']).get('demo_role') if runtime else None
    audio_only=runtime and specification(profile['name']).get('worker_audio_only',False)
    media_worker=runtime and specification(profile['name']).get('worker_media',False)
    tf_direct=runtime and specification(profile['name']).get('tf_direct_enabled',False)
    paired_role=specification(profile['name']).get('paired_role') if runtime else None
    paired_worker=paired_role=='W'
    phone_batch_worker=paired_worker and specification(profile['name']).get('phone_batch',False)
    ddr_aliases_selected=False
    if profile is not None and profile['configuration'].get('ddr_map_alias_policy') is not None:
        from tools import workstation_ddr_map_aliases as ddr_aliases
        ddr_aliases_selected=ddr_aliases.configured(profile['configuration'])
        if not runtime or demo_role != 'M' or recording_selected or paired_role is not None:
            raise ValueError('DDR include alias repair requires explicit independent M')
        profile_dependencies += ddr_aliases.DEPENDENCIES
    from tools import workstation_task3_w_usb_retirement as usb_retirement
    usb_retired=usb_retirement.configured({} if profile is None else profile['configuration'])
    if usb_retired:
        if not phone_batch_worker:
            raise ValueError('USB retirement requires explicit paired W phone batch composition')
        profile_dependencies += usb_retirement.DEPENDENCIES
    from tools import workstation_local_stream_release as local_stream
    local_stream_selected = local_stream.configured({} if profile is None else profile['configuration'])
    if local_stream_selected:
        if not phone_batch_worker:
            raise ValueError('local stream release requires paired W phone batch')
        profile_dependencies += local_stream.DEPENDENCIES
        profile_dependencies += ('tools/workstation_task3_w_preboard_cdc.py',)
    if paired_role is not None:
        from tools import workstation_task3_paired_board as paired_board
        paired_helper=paired_board.role_helper(paired_role)
    lease_source_policy = None if profile is None else profile['configuration'].get('m_phone_lease_source_policy')
    if lease_source_policy is not None:
        from tools import workstation_task3_m_phone_lease_source as lease_source
        if paired_role != 'M' or not lease_source.configured(profile['configuration']):
            raise ValueError('phone lease source register requires paired M')
        profile_dependencies += (lease_source.TOOL,)
    if tf_direct:
        from tools.workstation_task3_tf_direct import SOURCES as DIRECT_SOURCES, RETIRED_SOURCES, UNSELECTED_WORKER_SOURCES, DEPENDENCIES as DIRECT_DEPENDENCIES, POLICY as DIRECT_POLICY
        from tools.workstation_task3_tf_storage_selection import configuration_selection
        configuration_selection(profile['configuration'])
        if (recognition['music_analysis_enabled'] or not specification(profile['name']).get('tf_menu_enabled',False)
                or demo_role!='M' or profile['configuration'].get('tf_policy')!=DIRECT_POLICY):
            raise ValueError('direct TF requires the explicit native M/no-CNN/menu composition')
        native_sources=tuple(source for source in native_sources if source not in (*RETIRED_SOURCES,*UNSELECTED_WORKER_SOURCES))+DIRECT_SOURCES
        profile_dependencies+=(*DIRECT_DEPENDENCIES,*RETIRED_SOURCES)
    from tools import workstation_effects_reserved_config as effects_reservation
    from tools import workstation_fetch_range as fetch_range
    fetch_range_selected = fetch_range.configured({} if profile is None else profile['configuration'])
    if fetch_range_selected:
        profile_dependencies += (fetch_range.TOOL, fetch_range.MANIFEST)
        if profile['configuration'][fetch_range.KEY]==fetch_range.CAPTURE_POLICY:
            profile_dependencies += (fetch_range.CAPTURE_MANIFEST,)
    from tools import workstation_event_admission as event_admission
    event_admission_selected = event_admission.configured({} if profile is None else profile['configuration'])
    if event_admission_selected:
        profile_dependencies += (event_admission.TOOL, event_admission.MANIFEST)
    from tools import workstation_plot_coordinates as plot_coordinates
    plot_coordinates_selected = plot_coordinates.configured({} if profile is None else profile['configuration'])
    if plot_coordinates_selected:
        profile_dependencies += (plot_coordinates.TOOL, plot_coordinates.MANIFEST)
    from tools import workstation_reader_response_reuse as reader_reuse
    reader_reuse_selected = reader_reuse.configured({} if profile is None else profile['configuration'])
    if reader_reuse_selected:
        profile_dependencies += (reader_reuse.TOOL, reader_reuse.MANIFEST)
    effects_reserved = effects_reservation.configured({} if profile is None else profile['configuration'])
    if effects_reserved:
        native_sources += (effects_reservation.DISPATCH,)
        profile_dependencies += (effects_reservation.TOOL,)
    from tools import workstation_task3_tf_tail_reset as tail_reset
    from tools import workstation_tf_compute_local_release as tf_compute_reset
    from tools import workstation_ble_completion_publication as completion_publication
    from tools import workstation_inner_event_queue as inner_event_queue
    inner_queue_selected=inner_event_queue.configured({} if profile is None else profile['configuration'])
    if inner_queue_selected:
        profile_dependencies += (inner_event_queue.TOOL,inner_event_queue.MANIFEST)
    from tools import workstation_ble_pack_cofactor as pack_cofactor
    pack_selected=pack_cofactor.configured({} if profile is None else profile['configuration'])
    if pack_selected:
        profile_dependencies += (pack_cofactor.TOOL,pack_cofactor.MANIFEST)
    from tools import workstation_native_fault_cofactor as native_fault_cofactor
    native_fault_selected=native_fault_cofactor.configured({} if profile is None else profile['configuration'])
    if native_fault_selected:
        profile_dependencies += (native_fault_cofactor.TOOL,native_fault_cofactor.MANIFEST)

    from tools import workstation_ble_terminal_tuple as terminal_tuple
    tuple_selected=terminal_tuple.configured({} if profile is None else profile['configuration'])
    if tuple_selected:
        profile_dependencies += (terminal_tuple.TOOL,terminal_tuple.MANIFEST)
    from tools import workstation_ble_terminal_cofactor as terminal_cofactor
    terminal_selected=terminal_cofactor.configured({} if profile is None else profile['configuration'])
    if terminal_selected:
        profile_dependencies += (terminal_cofactor.TOOL,terminal_cofactor.MANIFEST)
    from tools import workstation_delay_watchdog_retime as delay_watchdog
    delay_watchdog_selected=delay_watchdog.configured({} if profile is None else profile['configuration'])
    if delay_watchdog_selected:
        profile_dependencies += (delay_watchdog.TOOL,delay_watchdog.MANIFEST)
    completion_selected=completion_publication.configured({} if profile is None else profile['configuration'])
    if completion_selected:
        profile_dependencies += (completion_publication.TOOL,completion_publication.MANIFEST)
    tf_compute_selected=tf_compute_reset.configured({} if profile is None else profile['configuration'])
    if tf_compute_selected:
        profile_dependencies += (tf_compute_reset.TOOL,tf_compute_reset.MANIFEST)
    tail_reset_selected = tail_reset.configured({} if profile is None else profile['configuration'])
    if tail_reset_selected:
        if paired_role != 'M' or not tf_direct:
            raise ValueError('TF tail local reset requires paired DIRECT M')
        profile_dependencies += (tail_reset.TOOL, tail_reset.MANIFEST)
    from tools import workstation_task3_demand_identity_compare as demand_identity
    demand_identity_selected=demand_identity.configured({} if profile is None else profile['configuration'])
    if demand_identity_selected:
        if paired_role != 'M':
            raise ValueError('demand identity grouping requires paired M')
        profile_dependencies += (demand_identity.TOOL,)
    from tools import workstation_task3_capture_compare as capture_compare
    capture_compare_selected=capture_compare.configured({} if profile is None else profile['configuration'])
    if capture_compare_selected:
        if paired_role != 'M':
            raise ValueError('capture ordering grouping requires paired M')
        profile_dependencies += (capture_compare.TOOL,)
    if demo_role is not None:
        from tools.workstation_performance_reset import DEMO_TIMING_TOOL
        profile_dependencies += (DEMO_TIMING_TOOL, 'tools/workstation_demo_boundary_cdc.py')
        if demo_role == 'W' and not audio_only:
            from tools.workstation_w_return_mailbox_cdc import TOOL as RETURN_MAILBOX_TOOL
            profile_dependencies += (RETURN_MAILBOX_TOOL,)
        from tools.workstation_usb_fifo_reset import POLICY as FIFO_RESET_POLICY
        if profile['configuration'].get('usb_fifo_reset_policy') != FIFO_RESET_POLICY:
            raise ValueError('new DEMO prepare requires explicit USB FIFO local-reset policy')
    from tools.workstation_ae350_memory import selection as memory_selection, SOURCE as BOOT_MEMORY_SOURCE, PARENT as PARENT_BOOT_MEMORY
    ae350_memory = memory_selection(profile['configuration'] if profile is not None else {})
    from tools import workstation_task3_w_banked96 as banked96
    if banked96.configured(profile['configuration'] if profile is not None else {}):
        BOOT_MEMORY_SOURCE=banked96.SOURCE
        profile_dependencies+=banked96.DEPENDENCIES
    expanded_boot = ae350_memory['boot_rom_bytes'] != 16384
    if expanded_boot:
        native_sources += (BOOT_MEMORY_SOURCE,)
    if recording_selected and not media_worker:
        from tools.workstation_recording_policy import SOURCES as RECORDING_SOURCES, DEPENDENCIES as RECORDING_DEPENDENCIES
        native_sources += RECORDING_SOURCES
        profile_dependencies += RECORDING_DEPENDENCIES
        from tools.workstation_recording_policy import PROVIDER as RECORDING_PROVIDER
        if selected_provider != RECORDING_PROVIDER:
            profile_dependencies += (RECORDING_PROVIDER,)
    if ble_raw_selected:
        from tools.workstation_ble_recording_policy import SOURCES as BLE_RAW_SOURCES, DEPENDENCIES as BLE_RAW_DEPENDENCIES
        native_sources += BLE_RAW_SOURCES
        profile_dependencies += BLE_RAW_DEPENDENCIES
    if business_selected:
        from tools.workstation_cpu_business import selection as cpu_selection
        _,cpu_sources,cpu_dependencies=cpu_selection(hci_selected,audio_only=audio_only)
        native_sources += cpu_sources
        profile_dependencies += cpu_dependencies
    if classic_selected or paired_role=='M':
        from tools.workstation_ae350_pcm import SOURCES as PCM_SOURCES,DEPENDENCIES as PCM_DEPENDENCIES
        native_sources += PCM_SOURCES
        profile_dependencies += PCM_DEPENDENCIES
    if classic_selected:
        from tools.workstation_classic_runtime import DEPENDENCIES as CLASSIC_DEPENDENCIES
        profile_dependencies += CLASSIC_DEPENDENCIES
        if ae350_memory['boot_rom_bytes']==98304:
            from tools.workstation_classic_runtime import ROM96_DEPENDENCIES
            profile_dependencies += ROM96_DEPENDENCIES
    panel = local_panel_bundle(local_panel_enabled)
    if not local_panel_enabled:
        native_sources = tuple(source for source in native_sources if source not in panel['retired_sources'])
    if demo_role=='W':
        native_sources=tuple('rtl/workstation/workstation_worker_usb.sv' if source=='rtl/push2_usb_a_control.sv' else source for source in native_sources)
        profile_dependencies += ('rtl/push2_usb_a_control.sv',
                                 'rtl/workstation/workstation_profile_classic_runtime_v1.sv')
    if demo_role is not None:
        profile_dependencies += ('tools/workstation_demo_policy.py',)
        from tools.workstation_usb_fifo_reset import SOURCE as FIFO_RESET_SOURCE, TOOL as FIFO_RESET_TOOL
        native_sources += (FIFO_RESET_SOURCE,)
        profile_dependencies += (FIFO_RESET_TOOL,)
    if audio_only:
        from tools.workstation_worker_audio_only import SOURCES as AUDIO_SOURCES, DEPENDENCIES as AUDIO_DEPENDENCIES, retired_source
        native_sources=tuple(x for x in native_sources if not retired_source(x))+AUDIO_SOURCES
        profile_dependencies+=AUDIO_DEPENDENCIES
    if media_worker:
        if paired_worker:
            MEDIA_SOURCES,MEDIA_DEPENDENCIES,retired_source=paired_helper.SOURCES,paired_helper.DEPENDENCIES,paired_helper.retired_source
        else:
            from tools.workstation_task3_w_media_profile import SOURCES as MEDIA_SOURCES,DEPENDENCIES as MEDIA_DEPENDENCIES,retired_source
        # The explicit resource parent already compiles current music owners.
        native_sources=tuple(dict.fromkeys((*[s for s in native_sources if not retired_source(s)],
            *[s for s in MEDIA_SOURCES if not s.startswith('rtl/music/')])) )
        profile_dependencies+=MEDIA_DEPENDENCIES
    if paired_role is not None:
        role_sources=tuple(p for p in paired_helper.SOURCES if not p.startswith('rtl/music/')) if paired_role=='M' else ()
        native_sources=tuple(dict.fromkeys((*native_sources,*role_sources,*paired_board.SOURCES)))
        profile_dependencies+=(*paired_helper.DEPENDENCIES,*paired_board.DEPENDENCIES)
        if phone_batch_worker:
            profile_dependencies+=paired_helper.BATCH_DEPENDENCIES
    tf_contact_policy = None if profile is None else profile['configuration'].get('tf_contact_policy')
    if tf_contact_policy is not None:
        if paired_role != 'M' or not tf_direct:
            raise ValueError('actual SD contacts require explicit paired M direct TF')
        from tools.workstation_task3_tf_contacts import POLICY as TF_CONTACT_POLICY, DEPENDENCIES as TF_CONTACT_INPUTS
        if tf_contact_policy != TF_CONTACT_POLICY:
            raise ValueError('unknown task3 TF contact policy')
        profile_dependencies += TF_CONTACT_INPUTS
    if len(native_sources) != len(set(native_sources)):
        raise ValueError('duplicate native-board selected source owner')
    telemetry_release = profile is not None and profile['name']=='custom138k-workstation-task3-m-preboard-v1'
    if telemetry_release:
        native_sources+=('rtl/telemetry/gw138k_push_performance_uart.sv',)
        profile_dependencies+=('rtl/telemetry/gw138k_push_performance_uart.provenance.json',)
    extra_inputs = list(dict.fromkeys((*native_sources, *profile_dependencies,
                                     'rtl/workstation/gw138k_push_workstation_top.v')))
    clocks = clock_bundle(root, hdmi_mode, local_panel_enabled=local_panel_enabled)
    crossings = cdc_bundle(root)
    input_crossings = input_cdc_bundle(root)
    reviewed_profile(root)
    for relative in extra_inputs:
        if not (root / relative).is_file():
            raise FileNotFoundError('missing native-board source: ' + relative)
    if workstation_profile is not None:
        from tools.stage_ae350_firmware import selected_inputs
        extra_inputs += ['firmware/ae350/' + name for name in selected_inputs(recording_selected, ae350_memory['memory_profile'], business_selected,headless_worker=audio_only)]
        if classic_selected:
            from tools.workstation_classic_runtime import firmware_inputs
            extra_inputs += firmware_inputs(root,headless_worker=audio_only)
    snapshot = source_snapshot(root, extra_inputs)
    if logic_only:
        output.mkdir(parents=True)
        pinout_output = None
        pinout = dict(device='GW5AST-LV138PG484AC2/I1', electrical_check=dict(status='not_checked'))
    else:
        pinout_output, pinout = prepare_pinout(root, netlist_directory, output / 'pinout',
            **({'tf_contact_policy': tf_contact_policy} if tf_contact_policy is not None else {}))
    sys.path.insert(0, str(root / 'tools'))
    builder = importlib.import_module('build_resource_rework')
    if builder.ROOT.resolve() != root:
        raise ValueError('resource builder root does not match explicit custom-board root')
    parent_output, stage, parent_metadata = builder.prepare(timing_fixes=True, output_directory=output / 'workstation',**({'native_cnn_parameters':True} if paired_role is not None else {}))
    if workstation_profile is not None:
        from tools.workstation_profile import prepare_ae350
        ae350_firmware = prepare_ae350(root, output, stage, riscv_prefix, recording_api=recording_selected,
            business_owner=business_selected,classic_runtime=classic_selected,worker_demo=demo_role=='W',headless_worker=audio_only,media_worker=media_worker,paired_worker=paired_worker,
            **({'phone_batch':True}if phone_batch_worker else{}), **ae350_memory)
    native_timing = adapt_timing(stage, resource_optimized=resource_optimization)
    demo_fifo_reset = None
    if demo_role is not None:
        from tools.workstation_usb_fifo_reset import prepare as prepare_fifo_reset
        demo_fifo_reset = prepare_fifo_reset(root, stage, enabled=True)
    (stage / 'scripts/build.tcl').write_text(
        'error "This native-board integration stage is synthesis-only; P&R and deployment are not authorized or validated."\n')
    (parent_output / 'build_metadata.json').write_text(json.dumps(dict(
        candidate=IDENTITY,
        source_policy='explicit_native_board_on_resource_timing', validation_stage='integration_prepare_incomplete',
        place_route_allowed=False, deployment_allowed=False, release_ready=False, hardware_tested=False), indent=2) + '\n')
    (output / 'parent_prepare_metadata.json').write_text(json.dumps(parent_metadata, indent=2) + '\n')
    project = stage / 'Prj1.gprj'
    tree = ElementTree.parse(project)
    files = tree.find('FileList')
    video_mode=(dict(mode='disabled_worker_media' if media_worker else 'disabled_worker_audio_only',display_elaborated=False) if (audio_only or media_worker) else apply_video_mode(root, stage, files, hdmi_mode))
    paths = [entry.get('path') for entry in files]
    if len(paths) != len(set(paths)):
        raise ValueError('duplicate native-board parent compilation inputs')
    if tf_direct:
        # The resource parent also enumerates maintained music libraries.
        # W task modules belong only to a later explicit W role; preserve the
        # staged parent bytes but do not compile these moving worker inputs.
        for entry in files:
            if entry.get('path') in UNSELECTED_WORKER_SOURCES:
                entry.set('enable', '0')
    replacements = {}
    replaced_inputs = dict(REPLACED_INPUTS)
    if telemetry_release:
        provenance=json.loads((root/'rtl/telemetry/gw138k_push_performance_uart.provenance.json').read_text())
        source=provenance['source'];parent=provenance['parent']
        text=(root/source).read_text()
        if (sha(stage/parent)!=provenance['parent_sha256'] or
                sha(root/source)!=provenance['source_sha256'] or text.count(provenance['new'])!=1 or
                text.replace(provenance['new'],provenance['old'],1).encode()!=(stage/parent).read_bytes()):
            raise ValueError('preboard telemetry local-release source lineage drift')
        replaced_inputs[parent]=source
    if expanded_boot:
        replaced_inputs[PARENT_BOOT_MEMORY] = BOOT_MEMORY_SOURCE
    install_paths, unchanged_parent_inputs = {}, {}
    if workstation_profile is not None:
        replaced_inputs['src/video/hdmi_display.v'] = 'rtl/workstation/workstation_profile_hdmi.sv'
    if runtime:
        from tools.workstation_runtime_profile import REPLACEMENTS, INSTALL_PATHS, UNCHANGED_PARENT_INPUTS
        replaced_inputs.update(REPLACEMENTS)
        install_paths.update(INSTALL_PATHS)
        unchanged_parent_inputs.update(UNCHANGED_PARENT_INPUTS)
    checked_parent_inputs = {}
    for relative, owner in unchanged_parent_inputs.items():
        if paths.count(relative) != 1 or not any(entry.get('path') == relative and entry.get('enable') == '1' for entry in files):
            raise ValueError('native-board unchanged parent selection drift: ' + relative)
        if sha(stage / relative) != snapshot[owner]:
            raise ValueError('native-board unchanged parent differs from maintained dependency: ' + relative)
        checked_parent_inputs[relative] = dict(source=owner, sha256=snapshot[owner])
    for relative in (*replaced_inputs, *EXCLUDED_INPUTS):
        entries = [entry for entry in files if entry.get('path') == relative and entry.get('enable') == '1']
        if len(entries) != 1:
            raise ValueError('native-board parent selection drift: ' + relative)
        owner = replaced_inputs.get(relative)
        replacements[relative] = dict(sha256=sha(stage / relative), replacement=owner,
                                     selected_destination=install_paths.get(owner, owner))
        entries[0].set('enable', '0')
    copied = {}
    copied_destinations = {}
    for relative in dict.fromkeys((*native_sources, *profile_dependencies, 'rtl/workstation/gw138k_push_workstation_top.v')):
        target = install_paths.get(relative, relative)
        if target in copied_destinations.values():
            raise ValueError('native-board ambiguous copied destination: ' + target)
        if target in paths:
            raise ValueError('native-board copied source would overwrite parent input: ' + target)
        destination = stage / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, destination)
        copied[relative] = sha(destination)
        copied_destinations[relative] = target
        if copied[relative] != snapshot[relative]:
            raise ValueError('native-board copied source identity changed: ' + relative)
        if relative in native_sources:
            ElementTree.SubElement(files, 'File', path=target, type='file.verilog', enable='1')
    from tools.stage_usb_firmware import select_usb2_cpu_ram
    usb2_cpu_ram_selection = select_usb2_cpu_ram(root, stage, ram_bytes)
    recording_address_map=None
    if recording_selected:
        from tools.workstation_recording_policy import install_address_map
        recording_address_map=install_address_map(root,stage)
    runtime_ddr_aliases=ddr_aliases.install(root,stage) if ddr_aliases_selected else None
    overlays = {}
    if resource_optimization:
        for destination, source in NATIVE_OVERLAYS.items():
            before = sha(stage / destination)
            shutil.copyfile(root / source, stage / destination)
            overlays[destination] = dict(source=source, before=before, after=sha(stage / destination))
    support = {}
    for relative in LOCKED_INPUT_SOURCES:
        if relative in replaced_inputs:
            continue
        if sum(entry.get('path') == relative and entry.get('enable') == '1' for entry in files) != 1:
            raise ValueError('native-board shared support selection drift: ' + relative)
        support[relative] = sha(stage / relative)
    firmware = stage_usb2_cpu_firmware(root, stage / 'native_usb_firmware', root / 'firmware.c', riscv_prefix,
                                       workstation=True, allow_high_speed=allow_high_speed,worker_demo=demo_role=='W', ram_bytes=ram_bytes)
    shutil.copyfile(stage / 'native_usb_firmware/usb2_cpu.hex', stage / 'usb2_cpu.hex')
    if ram_bytes == 49152:
        for bank in range(3):
            shutil.copyfile(stage / f'native_usb_firmware/usb2_cpu_bank{bank}.hex', stage / f'usb2_cpu_bank{bank}.hex')
    if logic_only:
        bluetooth = stage_business(root, stage, resource_optimized=resource_optimization)
    else:
        bluetooth = prepare_bluetooth(root, netlist_directory, stage, pinout_output, pinout,
            relative_rom_paths=runtime)
    if runtime:
        bluetooth['capture_source'] = 'runtime_physical_frame_observation_48k_only'
    ble_raw_adaptation=None
    if business_selected:
        from tools.workstation_cpu_business import prepare as prepare_cpu_business
        ble_raw_adaptation=prepare_cpu_business(root,stage,shared_hci=hci_selected,audio_only=audio_only)
        bluetooth['sources'].remove('native_bluetooth/ble_recording.v')
    elif ble_raw_selected:
        from tools.workstation_bluetooth_ddr import prepare as prepare_ble_raw
        ble_raw_adaptation=prepare_ble_raw(root,stage,enabled=True)
    if logic_only:
        peripherals = reviewed_profile(root)
        model_flash = dict(read_only=True, use_flash_weights=True, board_pads_checked=False)
    else:
        peripherals = prepare_peripherals(root, pinout_output, pinout, stage, local_panel_enabled=local_panel_enabled)
        if not local_panel_enabled:
            peripherals['local_panel_enabled'] = False
        model_flash = prepare_model_flash(root, pinout_output, pinout, stage)
    audio_source_selection=None
    if audio_only:
        from tools.workstation_worker_audio_only import select_sources,retired_source
        bluetooth['sources']=[x for x in bluetooth['sources'] if not retired_source(x)]
    for relative in bluetooth['sources']:
        ElementTree.SubElement(files, 'File', path=relative, type='file.verilog', enable='1')
    if audio_only:
        audio_source_selection=select_sources(stage,files)
    media_source_selection=None
    if media_worker:
        if paired_worker:select_media_sources=paired_helper.select_sources
        else:
            from tools.workstation_task3_w_media_profile import select_sources as select_media_sources
        media_source_selection=select_media_sources(stage,files)
    task3_paired_selection=None
    local_stream_selection = local_stream.select(stage, files,
        {} if profile is None else profile['configuration'])
    usb_retirement_selection=usb_retirement.select_sources(stage,files,
        {} if profile is None else profile['configuration'])
    if paired_role is not None:
        top_path=stage / paired_board.TOP
        top_path.write_text(paired_helper.apply_top(root,top_path.read_text()))
        task3_paired_selection=paired_board.prepare_top(root,stage,paired_role)
        if lease_source_policy is not None:
            lease_source.prepare(stage,profile['configuration'])
    task3_tail_reset = tail_reset.select(stage, profile['configuration']) if tail_reset_selected else None
    task3_tf_compute_reset=tf_compute_reset.select(stage,profile['configuration']) if tf_compute_selected else None
    raw_completion_publication=completion_publication.select(stage,profile['configuration']) if completion_selected else None
    inner_event_buffer=inner_event_queue.select(stage,profile['configuration']) if inner_queue_selected else None
    raw_terminal_cofactor=terminal_cofactor.select(stage,profile['configuration']) if terminal_selected else None
    raw_terminal_tuple=terminal_tuple.select(stage,profile['configuration']) if tuple_selected else None
    raw_pack_cofactor=pack_cofactor.select(stage,profile['configuration']) if pack_selected else None
    native_fault_receipt=native_fault_cofactor.select(stage,profile['configuration']) if native_fault_selected else None
    if raw_pack_cofactor is not None:
        raw_pack_cofactor=pack_cofactor.evidence(stage,profile['configuration'])
        raw_terminal_tuple=terminal_tuple.evidence(stage,profile['configuration'])

    if raw_terminal_cofactor is not None:
        # Every receipt binds final compiler bytes after all selections.
        raw_terminal_cofactor=terminal_cofactor.evidence(stage,profile['configuration'])
        raw_completion_publication=completion_publication.evidence(stage,profile['configuration'])
    raw_fetch_range = fetch_range.select(stage,profile['configuration']) if fetch_range_selected else None
    if raw_fetch_range is not None:
        # Rebind the existing layered receipts to the final compiler bytes.
        raw_pack_cofactor=pack_cofactor.evidence(stage,profile['configuration'])
        raw_terminal_tuple=terminal_tuple.evidence(stage,profile['configuration'])
        raw_terminal_cofactor=terminal_cofactor.evidence(stage,profile['configuration'])
        raw_completion_publication=completion_publication.evidence(stage,profile['configuration'])
        native_fault_receipt=native_fault_cofactor.evidence(stage,profile['configuration'])
    delay_watchdog_retime=delay_watchdog.select(stage,profile['configuration']) if delay_watchdog_selected else None
    reader_reuse_evidence = reader_reuse.select(stage, profile['configuration']) if reader_reuse_selected else None
    plot_coordinates_evidence = plot_coordinates.select(stage, profile['configuration']) if plot_coordinates_selected else None
    event_admission_evidence = event_admission.select(stage, profile['configuration']) if event_admission_selected else None
    if demand_identity_selected:
        demand_identity.select(stage,profile['configuration'])
    if capture_compare_selected:
        capture_compare.select(stage,profile['configuration'])
    effects_reservation_evidence = effects_reservation.select(stage, {} if profile is None else profile['configuration'])
    combined_cst = ''
    if not logic_only:
        shutil.copyfile(pinout_output / 'custom_138k.locations.cst', stage / 'constraints/custom_138k.locations.cst')
        shutil.copyfile(root / FPC_AUDIO_CST, stage / 'constraints/custom_138k.audio.cst')
        shutil.copyfile(root / 'boards/custom_138k/bluetooth.cst', stage / 'constraints/custom_138k.bluetooth.cst')
        shutil.copyfile(root / DISPLAY_CST, stage / 'constraints/custom_138k.display.cst')
        shutil.copyfile(root / DDR_CST, stage / 'constraints/custom_138k.ddr.cst')
        # Gowin selects a single active CST when opening a project. Keep the
        # reviewed components as evidence, but select only their complete union.
        combined_cst = ''.join((stage / ('constraints/custom_138k.' + part + '.cst')).read_text() + '\n'
                               for part in ('locations', 'audio', 'bluetooth', 'display', 'peripherals', 'model_flash', 'ddr'))
    shared_crossings = shared_cdc_bundle(stage)
    runtime_constraints = None
    if runtime:
        from tools.workstation_runtime_profile import constraints
        runtime_constraints = constraints(root, shared_crossings, local_panel_enabled=local_panel_enabled,
            ble_raw_enabled=ble_raw_selected, business_owner_enabled=business_selected)
        combined_cst += runtime_constraints['extra_cst']
        selected_sdc = runtime_constraints['sdc'] + runtime_constraints['runtime_cdc_sdc'] + crossings['sdc'] + input_crossings['sdc'] + runtime_constraints['bluetooth_sdc'] + panel['sdc'] + runtime_constraints['shared_sdc'] + timing_constraints(runtime_reset=True, recording_authority=ble_raw_selected) + MODEL_FLASH_SDC
    else:
        selected_sdc = clocks['sdc'] + crossings['sdc'] + input_crossings['sdc'] + FPC_AUDIO_SDC + BLUETOOTH_SDC + LCD_SDC + shared_crossings['sdc'] + timing_constraints() + MODEL_FLASH_SDC
    if resource_optimization:
        selected_sdc += storage_constraints()
    if classic_selected:
        from tools.workstation_classic_runtime import cdc_bundle as classic_cdc_bundle
        selected_sdc += classic_cdc_bundle()['sdc']
    business_telemetry_reset=None
    if business_telemetry_alias_selected:
        from tools.workstation_cpu_business import telemetry_reset_constraints
        selected_sdc,business_telemetry_reset=telemetry_reset_constraints(selected_sdc)
    demo_runtime_timing = None
    demo_boundary_cdc = None
    if demo_role is not None:
        from tools.workstation_performance_reset import (
            select_demo_timing, M_RELEASE_TIMING_POLICY, W_RETURN_TIMING_POLICY, DEMO_TIMING_POLICY)
        selected_sdc, demo_runtime_timing = select_demo_timing(stage, selected_sdc, demo_role,
            policy=DEMO_TIMING_POLICY if (audio_only or media_worker) else W_RETURN_TIMING_POLICY if demo_role == 'W' else M_RELEASE_TIMING_POLICY)
        from tools.workstation_demo_boundary_cdc import select_demo_boundary
        selected_sdc, demo_boundary_cdc = select_demo_boundary(stage, selected_sdc, demo_role)
    if runtime:
        from tools.workstation_recognition_policy import adapt_constraints
        selected_sdc, recognition_constraints = adapt_constraints(selected_sdc, recognition['music_analysis_enabled'],
            tf_menu_enabled=specification(profile['name']).get('tf_menu_enabled', False))
        recognition['constraints'] = recognition_constraints
    demo_constraints = None
    if demo_role is not None:
        from tools.workstation_demo_policy import adapt_constraints as demo_adapt_constraints
        selected_sdc, demo_constraints = demo_adapt_constraints(selected_sdc, demo_role,
            tf_playback_enabled=specification(profile['name']).get('tf_menu_enabled', False))
    audio_constraints=None
    if audio_only:
        from tools.workstation_worker_audio_only import constraints as audio_sdc,cst as audio_cst
        selected_sdc,audio_constraints=audio_sdc(selected_sdc)
        combined_cst=audio_cst(combined_cst)
    media_constraints=None
    if media_worker:
        if paired_worker:media_sdc=paired_helper.constraints
        else:
            from tools.workstation_task3_w_media_profile import constraints as media_sdc
        from tools.workstation_worker_audio_only import cst as headless_cst
        selected_sdc,media_constraints=media_sdc(selected_sdc)
        combined_cst=headless_cst(combined_cst)
    task3_tf_direct_cdc=None
    if tf_direct:
        from tools.workstation_task3_tf_direct import adapt_constraints as direct_constraints
        selected_sdc,task3_tf_direct_cdc=direct_constraints(root,selected_sdc,
            revision=profile['configuration']['tf_sdc_revision'])
    task3_paired_sdc=task3_paired_cst=None
    if paired_role is not None:
        selected_sdc,task3_paired_sdc=paired_board.adapt_constraints(root,selected_sdc,paired_role,
            midi_release_policy=profile['configuration'].get('midi_release_policy'),
            cnn_ready_policy=profile['configuration'].get('cnn_ready_sdc_policy'))
        combined_cst,task3_paired_cst=paired_board.adapt_cst(root,combined_cst)
    from tools.workstation_ae350_clock_placement import compose as compose_ae350_clock
    usb_retirement_constraints=None
    if usb_retired:
        selected_sdc,usb_retirement_constraints=usb_retirement.adapt_constraints(selected_sdc)
    ae350_clock_placement = None
    if not logic_only:
        combined_cst, ae350_clock_placement = compose_ae350_clock(root, stage, combined_cst)
    if not logic_only:
        (stage / 'constraints/custom_138k.cst').write_text(combined_cst)
        ElementTree.SubElement(files, 'File', path='constraints/custom_138k.cst', type='file.cst', enable='1')
    from tools import workstation_task3_w_preboard_cdc as preboard_cdc
    selected_sdc, preboard_cdc_evidence = preboard_cdc.select(selected_sdc,
        {} if profile is None else profile['configuration'])
    (stage / 'constraints/custom_138k.sdc').write_text(selected_sdc)
    ElementTree.SubElement(files, 'File', path='constraints/custom_138k.sdc', type='file.sdc', enable='1')
    tree.write(project, encoding='UTF-8', xml_declaration=True)
    from tools.workstation_ae350_rtc import prepared as prepare_ae350_rtc
    ae350_rtc = prepare_ae350_rtc(root, stage)
    (stage / 'scripts/custom_board_synthesis.tcl').write_text(
        'set root [file normalize [file join [file dirname [info script]] ..]]\n'
        'cd $root\nopen_project Prj1.gprj\n'
        'set_option -top_module workstation_custom_138k_top\n'
        'set_option -output_base_name custom_138k_integration\n'
        'set_option -verilog_std sysv2017\nset_option -timing_driven 1\n'+
        ('set_option -include_path $root\n' if media_worker else '')+'run syn\n')
    enabled = [entry.get('path') for entry in files if entry.get('enable') == '1']
    if len(enabled) != len(set(enabled)):
        raise ValueError('native-board duplicate selected input')
    if source_snapshot(root, extra_inputs) != snapshot:
        raise ValueError('native-board source snapshot changed during preparation')
    for relative, record in replacements.items():
        if sha(stage / relative) != record['sha256']:
            raise ValueError('native-board excluded historical input changed: ' + relative)
    staged = {source.relative_to(stage).as_posix(): sha(source) for source in stage.rglob('*')
              if source.is_file() and 'impl' not in source.relative_to(stage).parts}
    metadata = dict(schema=1, identity=(specification(profile['name'])['integration_identity'] if runtime else
                    PROFILES_720[hdmi_mode]['identity'] if hdmi_mode in PROFILES_720 else IDENTITY),
                    hdmi=video_mode,
                    native_timing_adaptations=native_timing,
                    model_flash=model_flash,
                    top_module='workstation_custom_138k_top', source_policy='native_logic_only_on_resource_timing' if logic_only else 'explicit_native_board_on_resource_timing',
                    validation_stage='integration_prepare_only', device=pinout['device'],
                    firmware=firmware, high_speed_allowed=bool(allow_high_speed),
                    bluetooth=bluetooth, peripherals=peripherals,
                    source_snapshot_sha256=snapshot, copied_sources_sha256=copied,
                    source_snapshot_extra_inputs=extra_inputs,
                    copied_source_destinations=copied_destinations,
                    unchanged_parent_inputs=checked_parent_inputs,
                    replaced_compilation_inputs=replacements, shared_resource_support_sha256=support,
                    parent_prepare_metadata_sha256=sha(output / 'parent_prepare_metadata.json'),
                    pinout_sha256=None if logic_only else sha(pinout_output / 'pinout.json'), enabled_inputs=enabled,
                    staged_input_sha256=staged, native_usb=not usb_retired, legacy_usb_host_elaborated=False,
                    tmds_polarity_inverted=[True, True, True, True], cec_behavior='released_high_impedance',
                    audio_pin_behavior='ak4493_i2s32_48k_mclk256fs_final_master_volume',
                    audio_clock_policy='direct_12m288_reference_with_50m_watchdog_no_DAC_PLL',
                    volume_control='Push_CC71_or_CC79_and_25K_encoder1_to_authoritative_CC7',
                    volume_application='post_effects_post_source_selection_once_before_I2S_and_BLE',
                    delay_fifo_storage='two_65x512_banked_BSRAM_FIFOs_same_capacity_latency_and_gray_protocol',
                    lcd_behavior=('800x480_shared_performance_snapshot_no_audio_backpressure'
                                  if local_panel_enabled else panel['output_behavior']),
                    uart_default='existing_workstation_reports',
                    electrical_blocked=pinout['electrical_check']['status']=='blocked',
                    synthesis_allowed=True, place_route_allowed=False, io_electrical_complete=False,
                    timing_constraints_complete=False, hardware_tested=False,
                    clock_plan_source=clocks['source'], clock_plan_sha256=clocks['source_sha256'],
                    ae350_core_clock_placement=ae350_clock_placement, ae350_rtc=ae350_rtc,
                    usb2_cdc_plan_source=crossings['source'], usb2_cdc_plan_sha256=crossings['source_sha256'],
                    input_cdc_plan_source=input_crossings['source'], input_cdc_plan_sha256=input_crossings['source_sha256'],
                    shared_cdc_adaptation={key: value for key, value in shared_crossings.items() if key != 'sdc'},
                    deployment_allowed=False, release_ready=False, bitstream_sha256=None,
                    remaining_gaps=['USB3300/TXS electrical compatibility', 'physical FPC DAC/audio acceptance',
                                    'physical BLE pairing/recording/download acceptance', 'complete IO/CDC/timing/PLL/P&R gates',
                                    'real external peripheral and hardware acceptance'])
    if usb2_cpu_ram_selection is not None:
        metadata['usb2_cpu_ram_selection'] = usb2_cpu_ram_selection
    if runtime_ddr_aliases is not None:
        metadata['runtime_ddr_aliases'] = runtime_ddr_aliases
    if preboard_cdc_evidence is not None:
        metadata['task3_w_preboard_cdc'] = preboard_cdc_evidence
    if effects_reservation_evidence is not None:
        metadata['effects_reserved_configuration'] = effects_reservation_evidence
    if local_stream_selection is not None:
        metadata['local_stream_release'] = local_stream_selection
    if usb_retired:
        metadata['task3_w_usb_retirement']=dict(selection=usb_retirement_selection,
            constraints=usb_retirement_constraints)
    if resource_optimization:
        metadata.update(board_netlists_checked=not logic_only, native_source_overlays=overlays,
                        electrical_status=pinout['electrical_check']['status'])
    if recording_selected:
        from tools.workstation_recording_policy import metadata as recording_metadata
        if media_worker:
            if paired_worker:media_recording_metadata=paired_helper.recording_metadata
            else:
                from tools.workstation_task3_w_media_profile import recording_metadata as media_recording_metadata
            metadata['recording']=dict(media_recording_metadata(root),address_map=recording_address_map)
        else:metadata['recording']=dict(recording_metadata(ble_raw_ddr=ble_raw_selected),address_map=recording_address_map)
    if ble_raw_selected:
        from tools.workstation_ble_recording_policy import metadata as ble_recording_metadata
        if business_selected:
            from tools.workstation_cpu_business import metadata as ble_recording_metadata
        if media_worker:
            if paired_worker:raw_metadata=paired_helper.raw_metadata
            else:
                from tools.workstation_task3_w_media_profile import raw_metadata
            metadata['ble_recording_storage']=dict(raw_metadata(root),adaptation=ble_raw_adaptation)
        else:metadata['ble_recording_storage']=dict(ble_recording_metadata(),adaptation=ble_raw_adaptation)
    if audio_only:
        from tools.workstation_worker_audio_only import POLICY as AUDIO_POLICY
        metadata['worker_audio_only']=dict(policy=AUDIO_POLICY,sources=audio_source_selection,
            constraints=audio_constraints,hci=ble_raw_adaptation,recording_enabled=False,display_enabled=False)
    if media_worker:
        metadata['worker_media']=dict(policy=paired_helper.POLICY if paired_worker else 'task3_w_media_headless_board_v1',sources=media_source_selection,
            constraints=media_constraints,LCD_link_ready=False,software_tap_default_open=False,
            physical_M_tap_connected=False,full_HCI_Classic_GATT=True)
        metadata['scan_window']=dict(policy='disabled_worker_media_v1',enabled=False)
    if business_telemetry_alias_selected:
        metadata['business_cpu_telemetry_reset_cdc']=business_telemetry_reset
    if demo_fifo_reset is not None:
        metadata['demo_usb_fifo_write_reset'] = demo_fifo_reset
    if demo_runtime_timing is not None:
        metadata['demo_runtime_timing'] = demo_runtime_timing
    if demo_boundary_cdc is not None:
        metadata['demo_boundary_cdc'] = demo_boundary_cdc
    if not local_panel_enabled:
        metadata['local_panel'] = panel
    if workstation_profile is not None:
        metadata['scan_window'] = dict(policy='native_admission_v1', enabled=True,
            provider='rtl/workstation/workstation_profile_hdmi.sv',
            implementation='rtl/workstation/workstation_hdmi_display.sv',
            admission='rtl/display_data/workstation_ddr_scan_window.sv',
            provenance_sha256=sha(stage / 'rtl/workstation/workstation_hdmi_display.provenance.json'),
            physical_deadlines_verified=False, d01_complete=False, d04_complete=False)
        if runtime:
            metadata['scan_window'].update(compilation_provider=selected_provider,
                                            provider_selection='included_with_runtime_macro')
    if media_worker:
        metadata['scan_window']=dict(policy='disabled_worker_media_v1',enabled=False)
        metadata['bluetooth']['capture_source']=('typed_M_final_tap_over_budget_gated_LCD; never_W_local_DAC' if paired_worker else 'software_M_final_tap_aperture; physical_LCD_down; never_W_local_DAC')
    if audio_only:
        metadata['scan_window']=dict(policy='disabled_worker_audio_only_v1',enabled=False)
        metadata['bluetooth']['capture_source']='absent_audio_only_no_recording'
        metadata['remaining_gaps']=['physical A2DP/SBC/D/25K/DAC acceptance','complete IO/CDC/timing/PLL/P&R gates','streaming Pitch remains unimplemented']
    if runtime:
        from tools.workstation_runtime_counter import metadata as counter_metadata
        metadata['runtime_audio'] = {key: value for key, value in runtime_constraints.items()
                                     if key not in ('sdc', 'runtime_cdc_sdc', 'bluetooth_sdc', 'shared_sdc', 'extra_cst')}
        metadata['runtime_audio'].update(reserve_zero_epoch=True, initial_stream_epoch=1,
            top_provider=selected_provider,
            common_parameter_owner='u_managed/runtime/service/workstation/parameters',
            clock_service_address='0xf8030000', legacy_capture_rate_hz=None if audio_only else 48000,
            tf_policy=profile['configuration'].get('tf_policy',
                'manual_matching_rate_no_resampling_no_automatic_clock_request'),
            media_preparation_policy=profile['configuration'].get('media_preparation_policy','seal_record_stop_score_tf_ble_v1'),
            media_preparation_owner='u_media_preparation',
            held_notes_policy='preserve; no implicit MIDI/PANIC',
            media_failure_categories=dict(**({} if audio_only else dict(local_recording=9,ble_seal=10)),backend_admission=11,
                **({'ddr_recording_seal':12} if recording_selected else {})),
            display_metadata_minor=1, counter_cdc=counter_metadata(root))
        metadata['recognition'] = recognition
        metadata['audio_pin_behavior']='ak4493s_i2s32_dual_rate_output_paced_final_pcm'
        metadata['audio_clock_policy']='qualified_12m288_or_16m9344_native_DCS'
        metadata['volume_application']=('once_in_runtime_final_pcm_before_I2S' if audio_only else 'once_in_runtime_final_pcm_before_I2S_display_and_BLE')
    if paired_role is not None:
        metadata['task3_paired']=task3_paired_selection
        if task3_tail_reset is not None:
            metadata['task3_tf_tail_reset'] = task3_tail_reset
        if task3_tf_compute_reset is not None:
            metadata['task3_tf_compute_reset']=task3_tf_compute_reset
        if raw_completion_publication is not None:
            metadata['raw_completion_publication']=raw_completion_publication
        if inner_event_buffer is not None:
            metadata['inner_event_queue']=inner_event_buffer
        if raw_pack_cofactor is not None:
            metadata['raw_pack_cofactor']=raw_pack_cofactor
        if native_fault_receipt is not None:
            metadata['native_fault_cofactor']=native_fault_receipt

        if raw_terminal_tuple is not None:
            metadata['raw_terminal_tuple']=raw_terminal_tuple
        if raw_terminal_cofactor is not None:
            metadata['raw_terminal_cofactor']=raw_terminal_cofactor
        if delay_watchdog_retime is not None:
            metadata['delay_watchdog_retime']=delay_watchdog_retime
        if raw_fetch_range is not None:
            metadata['raw_fetch_range'] = raw_fetch_range
        if event_admission_evidence is not None:
            metadata['combined_event_admission'] = event_admission_evidence
        if plot_coordinates_evidence is not None:
            metadata['display_plot_coordinates'] = plot_coordinates_evidence
        if reader_reuse_evidence is not None:
            metadata['display_reader_response_reuse'] = reader_reuse_evidence
        metadata['task3_paired_sdc']=task3_paired_sdc
        metadata['task3_paired_cst']=task3_paired_cst
        metadata['lcd_behavior']=paired_board.LCD_BEHAVIOR
        metadata['remaining_gaps']+=['LCD cable power/VCCIO/continuity and physical CDC review',
            'measured LCD throughput/RTT/jitter/congestion before business grant',
            'cold-start nonce/session provisioning and complete paired hardware acceptance']
        if paired_role=='M':
            batch=paired_helper.selected_batch_source_evidence(root,stage,profile['configuration'],selected_provider)
            if batch is not None:
                metadata['task3_phone_batch']=batch
    (parent_output / 'build_metadata.json').write_text(json.dumps(dict(
        candidate=metadata['identity'],source_policy=metadata['source_policy'],
        validation_stage='integration_prepare_only',place_route_allowed=False,deployment_allowed=False,
        release_ready=False,hardware_tested=False),indent=2)+'\n')
    (parent_output / 'workstation_inputs.json').write_text(json.dumps(staged,indent=2)+'\n')
    if workstation_profile is not None:
        from tools.workstation_profile import attach as attach_profile
        metadata['ae350_firmware'] = ae350_firmware
        if demo_constraints is not None:
            metadata['demo_constraint_retirement'] = demo_constraints
        if task3_tf_direct_cdc is not None:
            metadata['task3_tf_direct_cdc'] = task3_tf_direct_cdc
            from tools.workstation_task3_tf_storage_selection import prepared_selection
            metadata['task3_tf_direct_storage'] = prepared_selection(root,stage,profile['configuration'])
        if classic_selected:
            from tools.workstation_classic_runtime import prepare_selection
            metadata['classic_runtime']=prepare_selection(root,stage,output,physical_rom_bytes=ae350_memory['boot_rom_bytes'],selected_provider=selected_provider if demo_role=='W' else None,headless_worker=audio_only,media_worker=media_worker,paired_worker=paired_worker,
                paired_sdc_evidence=task3_paired_sdc,usb_retirement_constraints=usb_retirement_constraints,preboard_cdc=preboard_cdc_evidence,
                **({'phone_batch':True}if phone_batch_worker else{}))
        attach_profile(root, output, metadata, workstation_profile)
    (output / 'integration_inputs.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    return output, metadata
