"""Independent full83 CNN demonstration on the custom carrier, without graphics.

This is an explicit configuration of the existing native preparation. It never
programs a board, selects a latest pointer, or edits an immutable baseline.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET

NAME = 'custom138k-workstation-cnn-demo-v1'
PROVIDER = 'rtl/workstation/workstation_profile_cnn_demo.sv'
SOURCES = (PROVIDER, 'rtl/workstation/workstation_cnn_demo_audio.sv',
    'rtl/workstation/workstation_cnn_demo_adapter.sv',
    'rtl/workstation/workstation_cnn_demo_model_loader.sv',
    'rtl/memory/workstation_cnn_demo_memory.sv',
    'rtl/audio/workstation_runtime_oscillator_engine.sv',
    'rtl/audio/workstation_runtime_div147.sv',
    'rtl/control/workstation_parameters.sv',
    'rtl/timing/gw138k_level_cdc.sv',
    'rtl/music/basic_pitch_flash_io_guard.sv',
    'rtl/audio/gw138k_event_workstation.sv')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def retained(name, accepted_music):
    if name.startswith('rtl/music/'):
        if Path(name).name in ('basic_pitch_uart_model_loader.sv', 'basic_pitch_uart_rx.sv'):
            return False
        return name in accepted_music and not Path(name).name.startswith(('blocking_', 'music_ddr_engine', 'music_upload_', 'basic_pitch_tf_board'))
    if name.startswith('src/storage/'):
        return '/mp3/' not in name and '/tang_mp3/audio/' not in name and not any(x in name for x in ('tf_mp3_', 'tf_flac_', 'tf_sd_audio_pcm_player', 'common/sync_rom'))
    if name.startswith('src/audio/'):
        return True
    if name.startswith('src/usb_a/'):
        return 'push2_screen_' in name or name.endswith('gw138k_usb_lifecycle_merge.sv')
    if name.startswith(('rtl/usb2/', 'rtl/push2/')):
        return True
    exact = {
        'rtl/workstation/workstation_usb2_input.sv', 'rtl/workstation/workstation_usb2_service_adapter.sv',
        'src/usb_host/gw138k_usb_event_fifo.v',
        'src/video/video_font_5x7.v',
        'src/control/uart_tx.v', 'src/memory/ddr3_platform.v',
        'src/memory/ddr_recovery_guard.v', 'src/platform/reset_release.v',
        'src/memory/ddr_address_map_guard.v', 'src/memory/tf_audio_ddr_command_buffer.sv',
        'src/migration/gw138k_audio_clock.v', 'src/migration/gw138k_stream_cdc.sv',
        'src/migration/gw138k_counter_cdc.sv',
        'src/ae350/gw138k_cpu_pll_cell.v', 'src/ae350/gw138k_event_arbiter.sv',
        'src/ae350/gw138k_three_event_arbiter.sv',
        'src/push2/gw138k_push_performance_uart.sv', 'src/push2/push2_midi_rx.sv',
        'rtl/audio/scope_vec/scope_tf_control.sv', 'rtl/audio/scope_vec/scope_tf_transport.sv',
        'rtl/audio/scope_vec/scope_dac_select.sv',
        'rtl/audio/workstation_output_router.sv', 'rtl/audio/workstation_frame_delivery.sv',
        'rtl/control/workstation_session.sv', 'rtl/control/workstation_parameters.sv',
        'rtl/services/workstation_playback_service.sv',
        'rtl/timing/basic_pitch_ddr_arbiter_pipeline.sv',
        'rtl/timing/basic_pitch_ddr_client_queues.sv',
        'rtl/memory/workstation_sdp.sv', 'rtl/memory/workstation_sdp_banked.sv',
        'rtl/audio/push2_controls.sv', 'rtl/push2_usb_a_control.sv',
        'rtl/display_data/push2_surface_pixels.sv', 'rtl/audio/workstation_fpc_audio.sv',
        'rtl/memory/workstation_ddr_bist.v',
        'vendor/usb_host_fs_8fc3/src/VexRiscv.v', 'vendor/usb_host_fs_8fc3/src/simpleuart.v',
        'vendor/sipeed_dvi/video_pll_init.v',
        'constraints/custom_138k.cst', 'constraints/custom_138k.sdc',
    }
    return name in exact or name.startswith('vendor/gowin_ddr3/')


def minimal_constraints(payload):
    """Retire only endpoints belonging to explicitly absent demo hardware.

    Mixed selector lists retain the live endpoints and their original budgets.
    The full native constraint source and all frozen profiles stay untouched.
    """
    retired_prefixes = (
        'u_lcd/', 'u_bluetooth/', 'u_ble_pcm_cdc/', 'u_cpu_pll/', 'u_rtc/',
        'core_reset_pipe', 'u_cpu_ddr/', 'u_ui_control/', 'u_runtime/',
        'u_video/u_clock/', 'u_video/u_renderer/', 'u_video/u_scanout/',
        'u_video/u_diagnostics/', 'u_video/u_dvi/', 'u_video/ui_reset_pipe',
        'u_video/source_reset_pipe', 'u_video/pixel_reset_pipe',
        'u_managed/u_control_cdc/', 'u_managed/u_midi_drop_cdc/',
        'u_managed/u_audio/u_pc_rx/', 'u_managed/u_audio/u_pc_cdc/',
        'u_managed/u_audio/pc_health_meta', 'u_managed/effect_mask_meta', 'u_managed/effect_order_meta',
        'u_managed/u_audio/u_workstation/effects/',
        'u_display_push_cdc/', 'u_service_push_cdc/',
        'u_music/model_memory_meta', 'u_music/model_memory_ready',
    )
    retired_clocks = ('lcd_pixel31m5', 'video_ref49', 'video_serial742',
                      'video_pixel148', 'cpu_ram50', 'cpu_core100', 'cpu_rtc_bound')
    changes, lines = [], []
    for line in payload.splitlines():
        if any(re.search(r'\b'+clock+r'\b', line) for clock in retired_clocks):
            changes.append(dict(original=line, replacement=None)); continue
        empty = False
        def selector(match):
            nonlocal empty
            tokens = match[2].split()
            live = [x for x in tokens if not x.startswith(retired_prefixes)]
            if not live: empty = True
            return '['+match[1]+' {'+' '.join(live)+'}]'
        updated = re.sub(r'\[(get_(?:pins|regs|clocks|ports)) \{([^}]+)\}\]', selector, line)
        if empty: updated = None
        if line != updated: changes.append(dict(original=line, replacement=updated))
        if updated is not None: lines.append(updated)
    lines += [
        'set_false_path -to [get_pins {u_video/memory_release*/CLEAR}]',
        'set_max_delay 2.000 -from [get_regs {u_video/memory_release_0*}] -to [get_regs {u_video/memory_release_1*}]',
        'set_max_delay 2.000 -from [get_regs {u_video/memory_release_1*}] -to [get_regs {u_video/memory_release_2*}]',
        'set_max_delay 20.000 -from [get_regs {u_cnn_status_push_cdc/held_data*}] -to [get_regs {u_cnn_status_push_cdc/destination_data*}]',
        'set_false_path -hold -from [get_regs {u_cnn_status_push_cdc/held_data*}] -to [get_regs {u_cnn_status_push_cdc/destination_data*}]',
        'set_false_path -to [get_pins {u_cnn_status_push_cdc/req_meta*/D u_cnn_status_push_cdc/ack_meta*/D u_cnn_status_push_cdc/source_release*/CLEAR u_cnn_status_push_cdc/destination_release*/CLEAR}]',
        'set_false_path -to [get_pins {u_cnn_error_sync/meta*/D}]',
        'set_max_delay 2.000 -from [get_regs {u_cnn_error_sync/meta*}] -to [get_regs {u_cnn_error_sync/sync*}]',
    ]
    return '\n'.join(lines)+'\n', changes


def prepare(root, netlists, output, riscv_prefix=None):
    from tools.workstation_custom_board import prepare as native_prepare
    from tools.workstation_baselines import load_baseline
    root, output = Path(root).resolve(), Path(output).resolve()
    # Native board code is the single pin/USB/DAC authority. Its intermediate
    # preparation is not this candidate's final compiler source selection.
    output, parent = native_prepare(root, netlists, output, riscv_prefix)
    stage = output / 'workstation/Prj1'
    accepted = load_baseline(root, 'accepted_full83')
    for name in accepted.music:
        accepted.copy_file(name, stage / name)
    # Explicit six-file historical timing selection. Arithmetic/model inputs
    # stay on the accepted full83 lineage; this is a new candidate identity.
    import sys
    sys.path.insert(0, str(root/'tools'))
    from workstation_sources import timing85_cnn_inputs
    from workstation_cnn_cdc import transform as synchronize_model_diagnostics
    timing85 = load_baseline(root, 'timing85')
    selected_music = timing85_cnn_inputs(root, accepted.music)
    for name in selected_music:
        timing85.copy_file(name, stage/name)
    link = stage/'rtl/music/basic_pitch_workstation_link.sv'
    link_before = sha(link)
    link.write_text(synchronize_model_diagnostics(link.read_text()))
    # Only this explicit configuration substitutes the startup loader. Keep
    # the pinned pipeline arithmetic byte-for-byte apart from these two module
    # references, and fail if the historical source or exact anchors drift.
    pipeline = stage/'rtl/music/basic_pitch_pcm_pipeline.sv'
    pipeline_before = sha(pipeline)
    if pipeline_before != selected_music['rtl/music/basic_pitch_pcm_pipeline.sv']:
        raise ValueError('CNN-DEMO startup pipeline input drift')
    loader_anchor = 'basic_pitch_uart_model_loader u_model_loader ('
    if pipeline.read_text().count(loader_anchor) != 2:
        raise ValueError('CNN-DEMO startup loader anchor drift')
    pipeline.write_text(pipeline.read_text().replace(loader_anchor,
        'workstation_cnn_demo_model_loader u_model_loader ('))
    tree = ET.parse(stage / 'Prj1.gprj')
    files = tree.find('FileList')
    retired = {}
    for entry in files:
        name = entry.get('path')
        if entry.get('enable') == '1' and not retained(name, accepted.music):
            retired[name] = sha(stage / name)
            entry.set('enable', '0')
    for name in SOURCES:
        dest = stage / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, dest)
        existing=[x for x in files if x.get('path')==name]
        if existing:
            if len(existing)!=1:raise ValueError('duplicate source path: '+name)
            existing[0].set('enable','1')
            retired.pop(name,None)
        else:ET.SubElement(files, 'File', path=name, type='file.verilog', enable='1')
    # This compiler wrapper contains only basic instrument primitives. The
    # source bytes are inherited, never regenerated by text extraction.
    primitive = 'rtl/workstation/workstation_cnn_demo_primitives.sv'
    shutil.copyfile(root / primitive, stage / primitive)
    files.insert(0, ET.Element('File', path=primitive, type='file.verilog', enable='1'))
    shutil.copyfile(root / 'rtl/workstation/gw138k_push_workstation_top.v', stage / 'rtl/workstation/gw138k_push_workstation_top.v')
    script=stage/'scripts/custom_board_synthesis.tcl'
    script.write_text(script.read_text().replace('open_project Prj1.gprj\n','open_project Prj1.gprj\nset_option -include_path $root\n',1))
    # Shared headers retain the current authoritative allocation map. The
    # accepted CNN offsets are checked separately in the provenance report.
    shutil.copyfile(root / 'rtl/ddr_address_map.vh', stage / 'rtl/ddr_address_map.vh')
    shutil.copyfile(root / 'rtl/ddr_address_map.vh', stage / 'src/memory/ddr_address_map.vh')
    sdc = stage / 'constraints/custom_138k.sdc'
    sdc_text, constraint_retirement = minimal_constraints(sdc.read_text())
    sdc.write_text(sdc_text)
    ET.indent(tree, space='  ')
    tree.write(stage / 'Prj1.gprj', encoding='utf-8', xml_declaration=True)
    compiled = {x.get('path'):sha(stage/x.get('path')) for x in files if x.get('enable')=='1'}
    manifest = {p.relative_to(stage).as_posix():sha(p) for p in stage.rglob('*') if p.is_file() and 'impl' not in p.parts}
    model = stage / 'rtl/music/weights/cnn_ddr_blob.mem'
    import struct, binascii
    blob = struct.pack('<52239H', *[int(x,16) for x in model.read_text().splitlines()])
    if binascii.crc32(blob)&0xffffffff != 0xAF01A61B:
        raise ValueError('CNN-DEMO model differs from accepted model E')
    data = dict(schema=1, name=NAME, revision=3, parent_native_identity=parent['identity'],
        source_policy='accepted_full83_locked_timing85_six_files_synchronized_diagnostics_embedded_model_custom_carrier_minimal_audio',
        configuration=dict(song='TRAVLER',format='wav',sample_rate_hz=48000,
            model_crc32='AF01A61B',model_bytes=len(blob),model_sha256=hashlib.sha256(blob).hexdigest(),
            model_load='configuration_BSRAM_ROM_to_DDR_automatic',model_UART_required=False,
            model_ready='status_E_after_DDR_readback_CRC',hdmi=False,ae350=False,
            visualization_fft=False,cnn_cqt=True,effects=False,bluetooth=False,recording=False),
        accepted_baseline=accepted.evidence(),accepted_music_sha256=accepted.music,
        timing_baseline=timing85.evidence(),timing_music_sha256=selected_music,
        temporary_overlay=dict(file='rtl/music/basic_pitch_workstation_link.sv',
            before_sha256=link_before,after_sha256=sha(link),
            owner='tools/workstation_cnn_cdc.py',owner_sha256=sha(root/'tools/workstation_cnn_cdc.py'),
            exit_plan='promote synchronized diagnostics into versioned full83 maintenance source after demo validation; preserve locked baselines'),
        startup_loader_overlay=dict(file='rtl/music/basic_pitch_pcm_pipeline.sv',
            before_sha256=pipeline_before,after_sha256=sha(pipeline),anchor=loader_anchor,replacements=2,
            replacement='workstation_cnn_demo_model_loader u_model_loader (',
            implementation='rtl/workstation/workstation_cnn_demo_model_loader.sv',
            owner_sha256=sha(root/'tools/workstation_cnn_demo.py'),
            scope='startup only; unchanged inference and DDR allocation',
            exit_plan='retain explicit demo loader selection; promote pipeline composition when CNN maintenance sources migrate'),
        board_source_inputs=json.loads((output/'pinout/pinout.json').read_text())['source_inputs'],
        compiled_sha256=compiled,retired_compilation_sha256=retired,
        constraint_retirement=constraint_retirement,
        staged_sha256=manifest,hardware_tested=False,sram_deployed=False,flash_deployed=False,
        static_timing_closed=False)
    data['identity']=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()[:16]
    (output/'cnn_demo.json').write_text(json.dumps(data,indent=2)+'\n')
    return output,data


def physical_reset_constraints(sdc, netlist):
    """Resolve only the reset merging observed in this minimal composition.

    The status mailbox shares the song mailbox's release chains in reverse
    clock order. Check actual reset connectivity before selecting those cells;
    missing or newly changed topology must fail rather than waive a constraint.
    """
    retired = 'u_managed/u_audio/reset_50_pipe'
    if any(name.startswith(retired) for name in netlist.cells):
        raise ValueError('retired PC reset chain remains in CNN demo')
    token = retired + '*/CLEAR'
    if sdc.count(token) != 1:
        raise ValueError('retired PC reset selector anchor drift')
    sdc = sdc.replace(token + ' ', '', 1)
    aliases = {}
    for source, target, first, clock in (
        ('source_release', 'destination_release', 'ack_meta', 'clk_50m'),
        ('destination_release', 'source_release', 'req_meta', 'usb_clk'),
    ):
        old = 'u_cnn_status_push_cdc/' + source
        new = 'u_song_command_cdc/' + target
        if any(name.startswith(old) for name in netlist.cells):
            raise ValueError('CNN status release merging changed: ' + old)
        clear = netlist.pin('u_cnn_status_push_cdc/' + first + '_s0', 'CLEAR')
        drivers = [name for name, cell in netlist.cells.items()
                   if cell['kind'] == 'INV' and netlist.pin(name, 'O') == clear]
        last = new + '_2_s0'
        if len(drivers) != 1 or netlist.pin(drivers[0], 'I') != netlist.pin(last, 'Q'):
            raise ValueError('CNN status release alias connectivity changed: ' + old)
        for stage in range(3):
            cell = new + '_' + str(stage) + '_s0'
            if netlist.pin(cell, 'CLK') != clock:
                raise ValueError('CNN status release alias clock changed: ' + cell)
            if stage and netlist.pin(cell, 'D') != netlist.pin(new + '_' + str(stage-1) + '_s0', 'Q'):
                raise ValueError('CNN status release alias chain changed: ' + cell)
        old_token = old + '*/CLEAR'
        if sdc.count(old_token) != 1:
            raise ValueError('CNN status reset selector anchor drift')
        sdc = sdc.replace(old_token, new + '*/CLEAR', 1)
        for stage in range(2):
            sdc += f'set_max_delay 2.000 -from [get_regs {{{new}_{stage}_s*}}] -to [get_regs {{{new}_{stage+1}_s*}}]\n'
        aliases[old] = dict(actual=new, clock=clock, clear_driver=drivers[0])
    for first, second in (('req_meta', 'req_sync'), ('req_sync', 'req_settled'),
                          ('ack_meta', 'ack_sync')):
        sdc += f'set_max_delay 2.000 -from [get_regs {{u_cnn_status_push_cdc/{first}*}}] -to [get_regs {{u_cnn_status_push_cdc/{second}*}}]\n'
    return sdc, dict(retired_absent_selector=token, merged_release_aliases=aliases)


def prepare_physical(candidate, output, user_code, ddr_reference=None):
    """Run the explicit demo source/resource gate and prepare a fresh P&R.

    Full native feature-preservation audits deliberately require graphics and
    FX. This narrow profile checks its actual retained and retired hierarchy.
    No routed, timing, CDC or hardware acceptance is inherited here.
    """
    from tools.workstation_custom_board_implementation import implementation_script, ulpi_bypass_constraints
    from tools.workstation_synthesis_netlist import SynthesisNetlist
    candidate, output = Path(candidate).resolve(), Path(output).resolve()
    data = json.loads((candidate / 'cnn_demo.json').read_text())
    stage = candidate / 'workstation/Prj1'
    # Include files, memory images and non-project-listed headers are release
    # inputs too. Verify the complete prepared closure before consuming VG.
    for name, expected in data['staged_sha256'].items():
        if sha(stage/name) != expected: raise ValueError('demo input drift: '+name)
    log = (candidate/'synthesis.log').read_text()
    if re.search(r'^ERROR\b', log, re.M) or log.count('GowinSynthesis finish') != 1:
        raise ValueError('demo full synthesis did not pass')
    base = stage/'impl/gwsynthesis/custom_138k_integration'
    xml = ET.parse(base.with_name(base.name+'_syn_rsc.xml')).getroot()
    rows = {}
    def walk(node, path=''):
        rows[path] = dict(node.attrib)
        for child in node: walk(child, (path+'/' if path else '')+child.get('name'))
    walk(xml)
    required = ('u_native_usb/host', 'u_native_usb/input_owner',
        'u_tf_audio/u_path/u_file_reader', 'u_tf_audio/u_path/u_decoder/g_wav.u_wav',
        'u_music/u_basic_pitch/u_cqt', 'u_music/u_basic_pitch/g_ddr_weights.u_weight_cache',
        'u_music/u_basic_pitch/g_ddr_weights.u_model_loader',
        'u_music/u_basic_pitch/g_ddr_plane.g_plane_cache.u_plane_cache',
        'u_music/u_basic_pitch/g_full_dp.u_cnn_stream/u_viterbi',
        'u_score_push_cdc', 'u_output_router', 'u_fpc_audio',
        'u_managed/u_audio/u_workstation/cnn_demo_instrument.engine')
    if any(name not in rows for name in required):
        raise ValueError('required demo feature missing: '+str([x for x in required if x not in rows]))
    forbidden = ('u_lcd', 'u_cpu', 'u_bluetooth', 'u_runtime', 'u_video/u_renderer',
        'u_video/u_scanout', 'u_video/u_clock', 'u_video/u_dvi', 'u_delay_dma',
        'u_managed/u_audio/u_workstation/effects', 'u_managed/u_audio/u_extensions')
    if any(name.startswith(forbidden) for name in rows):
        raise ValueError('retired feature remains in demo synthesis')
    if int(xml.get('T_Bsram').split('(')[0]) > 340:
        raise ValueError('demo synthesis equivalent BSRAM budget exceeded')
    vg = base.with_suffix('.vg')
    netlist = SynthesisNetlist(vg.read_text(), 'workstation_custom_138k_top')
    plls = [name for name, cell in netlist.cells.items() if cell['kind']=='PLL']
    if set(plls) != {'u_audio_clock/g_hardware.u_pll/PLL_inst',
        'u_usb_pll/PLL_inst', 'u_memory/u_pll/u_pll_0/PLL_inst'}:
        raise ValueError('demo PLL inventory changed: '+str(plls))
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(vg, output/vg.name)
    # CPU PLL is absent. All IO locations, surviving PLL and DDR locations stay.
    cst = (stage/'constraints/custom_138k.cst').read_bytes()
    removed = b'INS_LOC "u_cpu_pll/PLL_inst" PLL_R[0];\n'
    if cst.count(removed) != 1: raise ValueError('CPU PLL retirement anchor drift')
    cst = cst.replace(removed, b'', 1)
    cst, ulpi = ulpi_bypass_constraints(cst, json.loads((candidate/'pinout/pinout.json').read_text()))
    sdc = (stage/'constraints/custom_138k.sdc').read_text()
    # These observers feed only retired displays and were actually swept.
    retired = ('u_final_output_cdc/', 'u_managed/u_audio/u_display_cdc/',
               'u_managed/effect_mask_meta', 'u_managed/effect_order_meta')
    lines = [line for line in sdc.splitlines() if not any(x in line for x in retired)]
    physical_sdc, reset_aliases = physical_reset_constraints('\n'.join(lines)+'\n', netlist)
    (output/'physical.sdc').write_text(physical_sdc)
    ddr_placement = None
    if ddr_reference is not None:
        from tools.workstation_custom_board_implementation import ddr_launch_capture_region_constraints
        reference = Path(ddr_reference).resolve()
        cst, ddr_placement = ddr_launch_capture_region_constraints(
            cst, (output/'physical.sdc').read_bytes(), reference.read_text(), far_regions=True)
        ddr_placement['reference_VO'] = str(reference)
        ddr_placement['reference_VO_sha256'] = sha(reference)
    # The measured first route put the 50MHz clock on generic fabric. Select
    # the established custom-carrier global buffer, keeping its 20ns budget.
    if 'wire clk_50m_d;' not in vg.read_text(): raise ValueError('50MHz clock net changed')
    cst += b'\nCLOCK_LOC "clk_50m_d" BUFG[8] = CLK;\n'
    (output/'physical.cst').write_bytes(cst)
    from tools.workstation_demo_audit import audit_sdc_selectors
    selector_audit = audit_sdc_selectors((output/'physical.sdc').read_text(), netlist)
    (output/'run.tcl').write_text(implementation_script(user_code))
    evidence = dict(schema=1, identity='cnn-demo-'+user_code.upper(),user_code=user_code.upper(),
        candidate_identity=data['identity'],candidate_manifest_sha256=sha(candidate/'cnn_demo.json'),
        synthesis_netlist_sha256=sha(vg),source_stage=str(stage),
        required_features={x:rows[x] for x in required},retired_features=list(forbidden),
        synthesis_resources=rows[''],pll_instances=plls,ulpi_adaptation=ulpi,
        ddr_placement=ddr_placement,clock_50m_global_buffer=8,
        visible_sdc_selector_audit=selector_audit,reset_selector_adaptation=reset_aliases,
        cst_retirement=removed.decode(),sdc_retired_display_observers=list(retired),
        pnr_passed=False,static_timing_closed=False,cdc_passed=False,hardware_tested=False,
        sram_deployed=False,flash_deployed=False)
    evidence['input_sha256']={p.name:sha(p) for p in output.iterdir() if p.is_file()}
    (output/'physical_inputs.json').write_text(json.dumps(evidence,indent=2)+'\n')
    return evidence
