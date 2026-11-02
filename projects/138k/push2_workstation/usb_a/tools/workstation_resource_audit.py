"""Offline audit of the explicit a27 resource candidate; never board acceptance."""
from pathlib import Path
import json
import re
import xml.etree.ElementTree as ET

from tools.stage_usb_firmware import sha
from tools.workstation_custom_board import (IDENTITY, NATIVE_SOURCES, NATIVE_OVERLAYS,
    REPLACED_INPUTS, EXCLUDED_INPUTS, FPC_AUDIO_SDC, BLUETOOTH_SDC)
from tools.workstation_usb2_input import LOCKED_INPUT_SOURCES
from tools.workstation_custom_board_audit import (ROOT, TOP, SHARED_TOP, FEATURES, DISALLOWED,
    check_files, check_ports, hierarchy, audit_delay_fifo_storage, audit_native_feedback,
    audit_native_receivers, audit_master_volume)
from tools.workstation_custom_clocks import audit_clocks, shared_cdc_bundle, audit_shared_cdc
from tools.workstation_custom_usb2_cdc import cdc_bundle, audit_usb2_cdc
from tools.workstation_custom_input_cdc import input_cdc_bundle, audit_input_fifo
from tools.workstation_custom_timing import INPUTS, constraints, audit_resets
from tools.workstation_custom_flash import SDC as FLASH_SDC
from tools.workstation_board_peripherals import LCD_SDC
from tools.workstation_usb2_bridge_audit import audit_bridge_resets
from tools.workstation_synthesis_netlist import SynthesisNetlist
from tools.workstation_memory import clock_estimates
from tools.workstation_ble_storage_cdc import constraints as storage_constraints, audit as audit_storage_cdc


from tools.workstation_usb_cpu_rom import check_banked_rom


def audit(output):
    output = Path(output).resolve()
    manifest = output / 'integration_inputs.json'
    meta = json.loads(manifest.read_text())
    stage = output / 'workstation/Prj1'
    mode = meta.get('hdmi', {}).get('mode')
    identity = IDENTITY if mode=='1080p60' else IDENTITY+'-'+str(mode)
    logic_only = meta.get('source_policy') == 'native_logic_only_on_resource_timing'
    if (mode not in ('1080p60', '720p30', '720p60') or meta.get('identity') != identity or meta.get('top_module') != TOP or
            meta.get('validation_stage') != 'integration_prepare_only' or
            meta.get('synthesis_allowed') is not True or
            meta.get('source_policy') not in ('native_logic_only_on_resource_timing', 'explicit_native_board_on_resource_timing')):
        raise ValueError('resource candidate policy changed')
    for flag in DISALLOWED:
        if meta.get(flag) is not False:
            raise ValueError('synthesis is not hardware acceptance: '+flag)
    if meta.get('bitstream_sha256') is not None or meta.get('board_netlists_checked') is logic_only:
        raise ValueError('candidate deployment or board provenance changed')
    check_files(ROOT, meta['source_snapshot_sha256'], 'source snapshot')
    check_files(stage, meta['staged_input_sha256'], 'staged input')
    check_files(ROOT.parents[3], meta['bluetooth']['source_snapshot_sha256'], 'BLE source')
    required = {*NATIVE_SOURCES, SHARED_TOP, *NATIVE_OVERLAYS.values(), 'tools/workstation_custom_board.py',
                'tools/workstation_resource_audit.py', 'tools/workstation_custom_board_audit.py',
                'tools/workstation_static_checks.py', 'tools/stage_usb_firmware.py', 'build.py'}
    if not required.issubset(meta['source_snapshot_sha256']):
        raise ValueError('source snapshot lost required provenance')
    if set(meta['copied_sources_sha256']) != {*NATIVE_SOURCES, SHARED_TOP}:
        raise ValueError('native source inventory changed')
    check_files(ROOT, meta['copied_sources_sha256'], 'native source')
    check_files(stage, meta['copied_sources_sha256'], 'copied source')
    support = set(LOCKED_INPUT_SOURCES)-set(REPLACED_INPUTS)
    if set(meta['shared_resource_support_sha256']) != support:
        raise ValueError('locked support inventory changed')
    check_files(stage, meta['shared_resource_support_sha256'], 'locked support')
    if set(meta['native_source_overlays']) != set(NATIVE_OVERLAYS):
        raise ValueError('native overlay inventory changed')
    for destination, source in NATIVE_OVERLAYS.items():
        record = meta['native_source_overlays'][destination]
        if (record['source'] != source or record['after'] != sha(ROOT/source) or
                record['after'] != sha(stage/destination) or not re.fullmatch('[0-9a-f]{64}', record['before'])):
            raise ValueError('native overlay provenance changed: '+destination)
    if sha(output/'parent_prepare_metadata.json') != meta['parent_prepare_metadata_sha256']:
        raise ValueError('locked reconstruction evidence changed')
    for relative, record in meta['native_timing_adaptations'].items():
        if record['before'] != INPUTS[relative] or record['after'] != sha(stage/relative):
            raise ValueError('timing adaptation changed: '+relative)
    if set(meta['native_timing_adaptations']) != set(INPUTS):
        raise ValueError('timing adaptation inventory changed')
    selected = [entry.get('path') for entry in ET.parse(stage/'Prj1.gprj').find('FileList') if entry.get('enable') == '1']
    if selected != meta['enabled_inputs'] or len(selected) != len(set(selected)):
        raise ValueError('compiler input inventory changed')
    closure = {*selected, SHARED_TOP, 'usb2_cpu.hex', 'Prj1.gprj', 'scripts/build.tcl',
               'scripts/custom_board_synthesis.tcl', *(f'usb2_cpu_bank{i}.hex' for i in range(3))}
    if not closure.issubset(meta['staged_input_sha256']):
        raise ValueError('compiler closure lost identity')
    if any(selected.count(p) != 1 for p in (*NATIVE_SOURCES, *support, *meta['bluetooth']['sources'])):
        raise ValueError('required native compilation source missing')
    if set(meta['replaced_compilation_inputs']) != {*REPLACED_INPUTS, *EXCLUDED_INPUTS}:
        raise ValueError('replacement inventory changed')
    for relative, record in meta['replaced_compilation_inputs'].items():
        if relative in selected or record['sha256'] != sha(stage/relative):
            raise ValueError('disabled historical input changed: '+relative)
    script = (stage/'scripts/custom_board_synthesis.tcl').read_text()
    if (script.count('run syn\n') != 1 or re.search(r'\brun\s+pnr\b', script) or
            f'set_option -top_module {TOP}\n' not in script or
            not (stage/'scripts/build.tcl').read_text().startswith('error ')):
        raise ValueError('synthesis-only flow changed')
    if logic_only:
        if meta['pinout_sha256'] is not None or any(p.endswith('.cst') for p in selected) or meta['electrical_status'] != 'not_checked':
            raise ValueError('logic-only flow must not claim board pinout validation')
        ports = None
    else:
        pinout = output/'pinout/pinout.json'
        if sha(pinout) != meta['pinout_sha256']:
            raise ValueError('board pinout identity changed')
        ports = check_ports(stage, json.loads(pinout.read_text()))
    firmware = meta['firmware']
    if firmware['firmware_profile'] != 'workstation' or firmware['isa'] != 'rv32i' or firmware['abi'] != 'ilp32' or firmware['high_speed_allowed'] != meta['high_speed_allowed']:
        raise ValueError('business firmware profile changed')
    log = output/'synthesis.log'
    log_text = log.read_text()
    if re.search(r'(?m)^ERROR\b', log_text) or log_text.count('GowinSynthesis finish') != 1:
        raise ValueError('Gowin synthesis incomplete or failed')
    base = stage/'impl/gwsynthesis/custom_138k_integration'
    vg = base.with_suffix('.vg')
    report = base.with_name(base.name+'_syn_rsc.xml')
    text = vg.read_text()
    totals, rows = hierarchy(ET.parse(report).getroot(), cpu_ram_bytes=49152)
    native = SynthesisNetlist(text, TOP)
    if re.search(r'^module\s+(iosys2|gw138k_push_workstation_top)\s*\(', text, re.M):
        raise ValueError('legacy workstation top reappeared')
    rom = check_banked_rom(stage, native, firmware)
    store = 'u_bluetooth/g_store.u_store'
    recorder = 'u_bluetooth/u_core/application/command_endpoint/recording'
    if (rows.get(store, {}).get('Bsram') != 4 or rows.get(store+'/u_responses', {}).get('Ssram') != 64 or rows.get(recorder, {}).get('Bsram') != 4 or
            rows['u_native_usb/host/bus']['self_bsram'] != 24 or
            rows.get('u_native_usb/host/usb/bridge', {}).get('Bsram') != 2):
        raise ValueError('PCM download cache, recorder packet buffer or CPU/USB RAM mapping changed')
    if not {'u_music_ble_memory', store+'/u_commands', store+'/u_responses', 'u_lcd', 'u_fpc_audio'}.issubset(rows):
        raise ValueError('DDR PCM composition or display/audio feature missing')
    for port in ('ble_memory_address', 'ble_memory_data', 'ble_memory_write'):
        def connected_bits(scope):
            width = native.ranges[native.frames[scope]['kind']].get(port)
            return ([native.canonical(scope, f'{port}[{bit}]') for bit in range(width[1], width[0]+1)]
                    if width else [native.pin(scope, port)])
        if connected_bits(store) != connected_bits('u_music_ble_memory'):
            raise ValueError('BLE DDR store bypasses shared memory arbiter: '+port)
    shared = shared_cdc_bundle(stage)
    if meta['shared_cdc_adaptation'] != {k:v for k,v in shared.items() if k != 'sdc'}:
        raise ValueError('shared CDC adaptation changed')
    extra = cdc_bundle(ROOT)['sdc']+input_cdc_bundle(ROOT)['sdc']+FPC_AUDIO_SDC+BLUETOOTH_SDC+LCD_SDC+shared['sdc']+constraints()+FLASH_SDC+storage_constraints()
    clocks = audit_clocks(ROOT, stage, text, extra_sdc=extra, hdmi_mode=meta['hdmi']['mode'])
    checks = dict(shared_cdc=audit_shared_cdc(stage, text), usb2_cdc=audit_usb2_cdc(ROOT,text,clocks),
        input_fifo=audit_input_fifo(ROOT,text,clocks), bridge_resets=audit_bridge_resets(text,TOP),
        usb_resets=audit_resets(text,clocks,feedback_source_clock='audio_76m8'),
        receivers=audit_native_receivers(text,clocks,True), master_volume=audit_master_volume(text),
        feedback=audit_native_feedback(text,clocks), delay=audit_delay_fifo_storage(text,rows),
        ble_storage_cdc=audit_storage_cdc(text,clocks))
    return dict(identity=identity, validation_stage='resource_candidate_logic_synthesis_only',
        integration_inputs_sha256=sha(manifest), auditor_sha256=sha(Path(__file__)),
        netlist_sha256=sha(vg), resource_report_sha256=sha(report), synthesis_log_sha256=sha(log),
        enabled_inputs=len(selected), source_snapshot_entries=len(meta['source_snapshot_sha256']),
        resources=totals, synthesis_bsram_equivalent=totals['Bsram'], cpu_rom=rom,
        features={name:dict(instance=path,**rows[path]) for name,path in FEATURES.items()},
        top_level_resources={path:value for path,value in rows.items() if path and '/' not in path},
        pcm_store=dict(instance=store,**rows[store]), explicit_clock_audit=clocks, checks=checks,
        synthesis_clock_estimates=clock_estimates(base.with_name(base.name+'_syn.rpt.html')),
        synthesis_warnings=len(re.findall(r'(?m)^WARN\s+\(',log_text)), port_coverage=ports,
        board_netlists_checked=not logic_only, physical_bsram_count=None, place_route_verified=False,
        timing_closed=False, hardware_tested=False, deployment_allowed=False, release_ready=False, bitstream_sha256=None)
