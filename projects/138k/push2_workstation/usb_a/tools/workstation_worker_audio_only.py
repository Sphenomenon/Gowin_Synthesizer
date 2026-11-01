"""Explicit W21 audio-only source/constraint selection; no generated RTL.

Keep immutable reconstruction evidence and the original clock/timing budgets.
Retired selectors must additionally be absent from the actual VG/VO audit.
"""
from pathlib import Path
import hashlib
import re

POLICY = 'worker_audio_only_no_display_no_recording_v1'
TOOL = 'tools/workstation_worker_audio_only.py'
PRIMITIVES = 'rtl/workstation/workstation_worker_audio_primitives.sv'
MEMORY = 'rtl/memory/workstation_audio_memory.sv'
HCI_PROVIDER = 'rtl/bluetooth/hci_owner/workstation_hci_audio_provider.sv'
CONTROLLED='rtl/workstation/workstation_worker_runtime_controlled.sv'
SOURCES = (MEMORY,CONTROLLED)
DEPENDENCIES = (TOOL, PRIMITIVES, HCI_PROVIDER,'rtl/ddr_address_map.vh',
    'rtl/bluetooth/hci_owner/workstation_hci_bluetooth.sv',
    'rtl/bluetooth/hci_owner/workstation_hci_native_core.v',
    'rtl/workstation/workstation_runtime_controlled.sv',
    'rtl/audio/workstation_observation_consumers.sv')

RETIRED_SOURCE_PREFIXES = (
    'rtl/display_data/', 'src/video/', 'src/storage/', 'rtl/tf_audio/',
    'vendor/sipeed_dvi/', 'rtl/bluetooth/cpu_owner/',
    'rtl/push2/', 'src/usb_a/push2_screen_',
)
RETIRED_SOURCES = (
    'constraints/p11.gsc',
    'legacy_audio.sv', 'src/memory/display_data_layout_pkg.sv',
    'rtl/workstation/workstation_runtime_controlled.sv',
    'rtl/audio/workstation_observation_consumers.sv',
    'src/memory/ddr_frame_writer.v', 'src/platform/video_clock.v',
    'src/platform/video_clock_1080p.v', 'src/ae350/gw138k_ui_services.sv',
    'src/ae350/gw138k_ui_workstation_top.v', 'src/ae350/gw138k_view_select.sv',
    'src/ae350/gw138k_ahb_ddr.sv', 'src/memory/tf_audio_ddr_command_buffer.sv',
    'rtl/workstation/workstation_profile_hdmi.sv',
    'rtl/audio/workstation_runtime_oscillator_engine.sv',
    'rtl/audio/workstation_runtime_scope_vec.sv',
    'rtl/audio/workstation_runtime_render_engines.sv',
    'rtl/audio/workstation_rate_pitch_expression.sv',
    'rtl/audio/workstation_runtime_div147.sv',
    'rtl/audio/scope_vec/scope_control_player.sv',
    'rtl/audio/scope_vec/scope_vec_engine.sv',
    'rtl/audio/scope_vec/scope_dac_select.sv',
    'rtl/audio/scope_vec/scope_tf_transport.sv',
    'rtl/runtime_replacements/scope_tf_transport.sv',
    'rtl/music/tf_playlist_bridge.sv',
    'rtl/services/workstation_playback_service.sv',
    'rtl/services/workstation_business_mailbox.sv',
    'rtl/bluetooth/hci_owner/workstation_hci_ble_bridge.v',
    'native_bluetooth/ble_protocol_command.v', 'native_bluetooth/bt_acl_bridge.v',
    'native_bluetooth/bt_gatt.v', 'native_bluetooth/bt_hci_init.v',
    'native_bluetooth/bt_verilog_core.v',
)
RETIRED_SELECTORS = (
    'u_video/', 'u_ui_control/', 'u_ui_services/', 'u_cpu_ddr/',
    'u_managed/display/', 'u_managed/display_observation_health/',
    'u_ble_pcm_cdc/', 'recording_ble_store/', 'recording_authority/',
    'recording_owner8/', 'recording_memory_release', 'recording_channel_meta',
    'recording_channel_ready50', 'u_bluetooth/u_core/application/',
    'u_bluetooth/u_core/acl_bridge/',
)
RETIRED_CLOCKS = ('video_ref49', 'video_serial742', 'video_pixel148')
SYNTH_MIDI_SELECTORS = ('u_managed/midi_uart/', 'u_managed/midi_bytes/', 'u_managed/midi_drops/')
RETIRED_SEQUENCE_CE = tuple(
    f'u_managed/runtime/serializer/current_sequence_{bit}_s*/CE' for bit in range(32))
REBIND = (('u_video/u_bist/', 'u_audio_memory/u_bist/'),
          ('u_video/u_arbiter/', 'u_audio_memory/u_arbiter/'),
          ('u_video/flags_meta', 'u_audio_memory/flags_meta'),
          ('u_video/flags_sync', 'u_audio_memory/flags_sync'))
QUERY = re.compile(r'\[(get_regs|get_pins|get_ports|get_clocks) \{([^{}]+)\}\]')
MEMORY_SDC = (
    'set_false_path -to [get_pins {u_audio_memory/memory_release*/CLEAR}]\n'
    'set_max_delay 2.000 -from [get_regs {u_audio_memory/memory_release_0*}] -to [get_pins {u_audio_memory/memory_release_1*/D}]\n'
    'set_max_delay 2.000 -from [get_regs {u_audio_memory/memory_release_1*}] -to [get_pins {u_audio_memory/memory_release_2*/D}]\n'
    'set_false_path -to [get_pins {u_audio_memory/flags_meta*/D}]\n'
    'set_max_delay 2.000 -from [get_regs {u_audio_memory/flags_meta*}] -to [get_pins {u_audio_memory/flags_sync*/D}]\n'
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def retired_source(path):
    # This shared PLL analog initializer also owns the audio PLL startup;
    # its historical directory name does not make it a video clock owner.
    if path == 'vendor/sipeed_dvi/video_pll_init.v':
        return False
    music_retired=path.startswith('rtl/music/') and path not in ('rtl/music/music_async_fifo.sv','rtl/music/basic_pitch_flash_io_guard.sv')
    return music_retired or path in RETIRED_SOURCES or path.startswith(RETIRED_SOURCE_PREFIXES)


def select_sources(stage, files):
    """Disable the exact inactive compilation entries, preserving their bytes."""
    stage = Path(stage)
    retired = {}
    for entry in files:
        path = entry.get('path')
        if entry.get('enable') == '1' and retired_source(path):
            if path == 'constraints/p11.gsc':
                active = [line for line in (stage / path).read_text().splitlines()
                          if line.strip() and not line.lstrip().startswith('//')]
                expected = 'INS "u_video/u_clock/g_hardware.u_pll/u_reference/u_pll_init/enable_r" syn_preserve = 1;'
                if active != [expected]:
                    raise ValueError('W retired video-only synthesis constraint identity changed')
            retired[path] = sha(stage / path)
            entry.set('enable', '0')
    if 'legacy_audio.sv' not in retired:
        raise ValueError('W audio-only original primitive wrapper missing')
    # The package must precede all importers, as in the immutable wrapper.
    from xml.etree import ElementTree
    position = next(i for i, entry in enumerate(files) if entry.get('path') == 'legacy_audio.sv')
    files.insert(position, ElementTree.Element('File', path=PRIMITIVES, type='file.verilog', enable='1'))
    return dict(policy=POLICY, retired_compilation_sha256=retired,
        primitive_provider=PRIMITIVES, primitive_provider_sha256=sha(stage / PRIMITIVES),
        rtl_text_generation=False, physical_retirement_verified=False)


def constraints(text, *, retire_synth_midi=False):
    """Remove absent endpoints and preserve every surviving query member."""
    if type(retire_synth_midi) is not bool:
        raise ValueError('W synth MIDI retirement selection must be explicit boolean')
    retired_selectors = RETIRED_SELECTORS + (SYNTH_MIDI_SELECTORS if retire_synth_midi else ())
    selected, changes = [], []
    for index, line in enumerate(text.splitlines()):
        removed, rebound, empty = [], [], []
        def query(match):
            keep = []
            for original in match[2].split():
                member = original
                for old, new in REBIND:
                    if member.startswith(old):
                        member = new + member[len(old):]
                        break
                if (member.startswith(retired_selectors) or
                        (match[1] == 'get_pins' and member in RETIRED_SEQUENCE_CE) or
                        (match[1] == 'get_clocks' and member in RETIRED_CLOCKS)):
                    removed.append(original)
                else:
                    keep.append(member)
                    if member != original:
                        rebound.append(dict(original=original, selected=member, query=match[1]))
            if not keep:
                empty.append(match[1])
            return '[' + match[1] + ' {' + ' '.join(keep) + '}]'
        output = QUERY.sub(query, line)
        if removed or rebound:
            changes.append(dict(line_index=index, selected_line_index=len(selected), original=line, selected=None if empty else output,
                removed_selectors=removed, rebound_selectors=rebound))
        if not empty:
            selected.append(output)
    result = '\n'.join(selected) + '\n' + MEMORY_SDC
    if 'u_video/' in result or any('{'+clock+'}' in result for clock in RETIRED_CLOCKS):
        raise ValueError('retired video timing endpoint survived W audio-only selection')
    return result, dict(policy=POLICY, original_sha256=hashlib.sha256(text.encode()).hexdigest(),
        selected_sha256=hashlib.sha256(result.encode()).hexdigest(), changes=changes,
        added_memory_lines=MEMORY_SDC.splitlines(), clocks_or_budgets_relaxed=False,
        netlist_retirement_required=True, physical_cdc_accepted=False,
        **(dict(synth_midi_retired=True) if retire_synth_midi else {}))


def restore_constraints(selected, evidence):
    if evidence.get('policy') != POLICY or not selected.endswith(MEMORY_SDC):
        raise ValueError('W audio-only timing evidence missing')
    result = selected[:-len(MEMORY_SDC)].splitlines()
    for change in reversed(evidence['changes']):
        if change['selected'] is None:
            result.insert(change['selected_line_index'], change['original'])
        else:
            if result[change['selected_line_index']] != change['selected']:
                raise ValueError('W audio-only timing inverse drift')
            result[change['selected_line_index']] = change['original']
    original = '\n'.join(result) + '\n'
    checked, expected = constraints(original, retire_synth_midi=evidence.get('synth_midi_retired', False))
    if checked != selected or expected != evidence:
        raise ValueError('W audio-only timing selection or complete evidence changed')
    return original


def cst(text):
    """Retire only the old video helper region, retaining every pin mapping."""
    lines = text.splitlines(keepends=True)
    return ''.join(line for line in lines if not (
        line.startswith('GROUP workstation_reference_pll_helper =') or
        line.startswith('GRP_LOC workstation_reference_pll_helper ')))
