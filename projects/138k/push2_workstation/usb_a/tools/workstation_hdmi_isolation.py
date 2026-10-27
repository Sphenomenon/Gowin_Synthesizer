"""Small native UI/DDR diagnostic; never selects a complete-workstation profile."""

from datetime import datetime
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

from tools.workstation_baselines import load_baseline
from tools.workstation_custom_clocks import clock_bundle, shared_cdc_bundle
from tools.workstation_pinout import prepare as prepare_pinout, render_constraints
from tools.workstation_resource_timing import dashboard, diagnostics, raster, scanout_request, slot_payload
from tools.workstation_timing_constraints import gray_write_alias_constraints
from tools.audit_workstation_timing import audit as audit_timing


TOP = 'workstation_hdmi_probe_top'
BASE = 'hdmi_isolation'
CLOCKS = ('clk_50m', 'ddr_mem400', 'ddr_ui100', 'video_ref49', 'video_serial742', 'video_pixel148')
LOCKED_SOURCES = (
    'src/memory/display_data_layout_pkg.sv',
    'src/memory/ddr3_bist.v', 'src/memory/ddr3_platform.v', 'src/memory/ddr_recovery_guard.v',
    'src/memory/ddr_frame_writer.v', 'src/memory/display_data_writer.v', 'src/memory/display_data_reader.v',
    'src/memory/ddr_address_map_guard.v', 'src/platform/reset_release.v', 'src/platform/video_clock_1080p.v',
    'src/video/audio_analysis_rom.v', 'src/video/feedback_capture.v', 'src/video/feedback_dashboard.v',
    'src/video/feedback_renderer.v', 'src/video/feedback_wave_align.v', 'src/video/hdmi_display.v',
    'src/video/output_audio_analysis.v', 'src/video/output_audio_capture.v',
    'src/video/video_font_5x7.v', 'src/video/video_runtime_diagnostics.v', 'src/video/video_timing_1080p.v',
    'src/ae350/gw138k_view_select.sv', 'src/ae350/gw138k_ddr_arbiter.sv',
    'rtl/timing/basic_pitch_ddr_client_queues.sv', 'rtl/timing/basic_pitch_ddr_arbiter_pipeline.sv',
    'vendor/gowin_ddr3/ddr3_memory_interface.v', 'vendor/gowin_ddr3/ddr3_pll.v',
    'vendor/gowin_ddr3/ddr3_pll_init.v', 'vendor/gowin_ddr3/ddr3_pll_primitive.v',
    'vendor/sipeed_dvi/dvi_tx_tmds_enc.v', 'vendor/sipeed_dvi/video_pll_1080p_gw5a.v',
    'vendor/sipeed_dvi/video_pll_init.v',
)
LIVE_SOURCES = (
    'rtl/memory/workstation_sdp.sv', 'rtl/memory/workstation_sdp_banked.sv',
    'rtl/display_data/workstation_custom_dvi.sv', 'rtl/display_data/workstation_hdmi_demo.sv',
    'rtl/display_data/workstation_hdmi_isolation.sv',
)
ADAPTATIONS = {
    'src/video/feedback_dashboard.v': dashboard,
    'src/video/video_runtime_diagnostics.v': diagnostics,
    'src/video/video_timing_1080p.v': raster,
    'rtl/timing/basic_pitch_ddr_client_queues.sv': slot_payload,
}
SIGNALS = ('reset_n', *(f'debug_status[{bit}]' for bit in reversed(range(63))))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def gao_configuration(user_code):
    document = ET.Element('GAO_CONFIG')
    ET.SubElement(document, 'Version').text = '3.0'
    ET.SubElement(document, 'Mode').text = 'Standard'
    core = ET.SubElement(document, 'AoCore', index='0', sample_clock='clk_50m_d', trig_type='0',
                         storage_depth='1024', window_num='1', capture_amount='1024', implementation='0',
                         trigger_pos='0', module_name=TOP, force_trigger_by_falling_edge='false',
                         capture_init_data_enabled='false')
    signals = ET.SubElement(core, 'SignalList')
    for signal in SIGNALS:
        ET.SubElement(signals, 'Signal', capture_enable='true').text = signal
    triggers = ET.SubElement(core, 'Triggers')
    matches = ET.SubElement(core, 'MatchUnits')
    for index in range(16):
        trigger = ET.SubElement(triggers, 'Trigger', index=str(index))
        if index == 0:
            ET.SubElement(ET.SubElement(trigger, 'SignalList'), 'Signal').text = 'reset_n'
        match = ET.SubElement(matches, 'MatchUnit', index=str(index), enabled=str(int(index == 0)),
                              match_type='0', counter_enable='0', counter_width='2', counter='2',
                              countinuous='0', func='0', value0='1' if index == 0 else '',
                              value1='1' if index == 0 else '')
        if index == 0:
            match.set('trigger', '0')
    ET.SubElement(ET.SubElement(document, 'Expressions', type='Static'), 'Expression').text = 'M0'
    ET.SubElement(document, 'GAO_ID').text = user_code[-4:]
    return ET.tostring(document, encoding='unicode')


def display_sdc(root, stage):
    clock_lines = [line for line in clock_bundle(root)['sdc'].splitlines()
                   if any('-name ' + name + ' ' in line for name in CLOCKS)]
    if len(clock_lines) != len(CLOCKS):
        raise ValueError('isolated display clock inventory changed')
    crossings = []
    for line in shared_cdc_bundle(stage)['sdc'].splitlines():
        queries = re.findall(r'\[get_(?:pins|regs|nets)\s+\{([^}]+)\}\]', line)
        targets = [target for query in queries for target in query.split()]
        if targets and all(target.startswith(('u_video/', 'u_memory/')) for target in targets):
            crossings.append(line)
    if not crossings:
        raise ValueError('display DDR/CDC constraints missing')
    phy = 'u_memory/u_ddr3/gw3_top/u_ddr_phy_top'
    lines = clock_lines + crossings + [
        f'set_min_delay 0.800 -from [get_pins {{{phy}/ddr_init_internal_r_s0/Q}}] '
        f'-to [get_pins {{{phy}/wloadn_3_s0/D}}]',
    ]
    lines = [line.replace('u_video/', 'u_display/u_video/').replace('u_memory/', 'u_display/u_memory/')
             for line in lines]
    lines += [f'report_timing -{kind} -max_paths 2000 -max_common_paths 1'
              for kind in ('setup', 'hold', 'recovery', 'removal')]
    return '\n'.join(lines) + '\n'


def prepare(root, netlist_directory, output, user_code, dynamic=True):
    root, output = Path(root).resolve(), Path(output).resolve()
    if not re.fullmatch(r'[0-9A-Fa-f]{8}', user_code):
        raise ValueError('display isolation requires a new eight-hex UserCode')
    user_code = user_code.upper()
    if output.exists():
        raise FileExistsError('display output already exists: ' + str(output))
    baseline = load_baseline(root, 'resource_rework_route0')
    output.mkdir(parents=True)
    pinout_output, pinout = prepare_pinout(root, netlist_directory, output / 'pinout')
    payloads = {name: baseline.read_bytes(name) for name in LOCKED_SOURCES}
    evidence = {}
    for name, transform in ADAPTATIONS.items():
        original = payloads[name]
        payloads[name] = transform(original.decode()).encode()
        evidence[name] = dict(transform=transform.__name__, before=hashlib.sha256(original).hexdigest(),
                              after=hashlib.sha256(payloads[name]).hexdigest())
    selected = (*LIVE_SOURCES, 'rtl/display_data/video_ddr_scanout.v', 'rtl/ddr_address_map.vh',
                'boards/custom_138k/display.cst', 'boards/custom_138k/ddr.cst',
                'boards/custom_138k/hdmi_isolation.cst',
                'boards/custom_138k/clocks.json', 'tools/workstation_hdmi_isolation.py',
                'tools/workstation_resource_timing.py', 'tools/workstation_timing_constraints.py',
                'tools/workstation_custom_clocks.py',
                'tools/audit_workstation_timing.py', 'tools/audit_clk50_timing.py',
                'tools/workstation_pinout.py', 'boards/custom_138k/pinout.json', 'build.py')
    snapshot = {name: digest(root / name) for name in selected}
    payloads.update({name: (root / name).read_bytes() for name in LIVE_SOURCES})
    payloads['src/video/video_ddr_scanout.v'] = scanout_request(
        (root / 'rtl/display_data/video_ddr_scanout.v').read_text()).encode()
    payloads['src/memory/ddr_address_map.vh'] = (root / 'rtl/ddr_address_map.vh').read_bytes()
    payloads['constraints/tang_mega_138k.sdc'] = (
        baseline.read_bytes('constraints/tang_mega_138k.sdc').decode() + gray_write_alias_constraints()).encode()
    payloads['vendor/sipeed_dvi/LICENSE'] = baseline.read_bytes('vendor/sipeed_dvi/LICENSE')
    payloads['hdmi_isolation_config.vh'] = f'`define HDMI_ISOLATION_DYNAMIC {int(dynamic)}\n'.encode()
    sources = (*LOCKED_SOURCES, 'src/video/video_ddr_scanout.v', *LIVE_SOURCES)
    for name, payload in payloads.items():
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    ports = {port for port in pinout['ports'] if port.startswith(('ddr_', 'tmds_')) or
             port in ('clk_50m', 'hdmi_hpd', 'hdmi_cec')}
    location_lines = [line for line in render_constraints(pinout).splitlines()
                      if (match := re.match(r'IO_(?:LOC|PORT)\s+"([^"]+)"', line)) and match[1] in ports]
    locations = '\n'.join(location_lines) + '\n'
    physical = (locations + (root / 'boards/custom_138k/display.cst').read_text() + '\n' +
                (root / 'boards/custom_138k/ddr.cst').read_text().replace('"u_memory/', '"u_display/u_memory/') +
                '\n' + (root / 'boards/custom_138k/hdmi_isolation.cst').read_text().replace('"u_memory/', '"u_display/u_memory/'))
    (output / 'display.cst').write_text(physical)
    (output / 'display.sdc').write_text(display_sdc(root, output))
    (output / 'display.gao').write_text(gao_configuration(user_code))
    common = [
        'set root [file normalize [file dirname [info script]]]', 'cd $root',
        f'set_device {pinout["device"]} -device_version C',
        'set_option -synthesis_tool gowinsynthesis', f'set_option -top_module {TOP}',
        f'set_option -output_base_name {BASE}', 'set_option -verilog_std sysv2017',
        'set_option -use_cpu_as_gpio 1', 'set_option -use_mspi_as_gpio 1',
        'set_option -include_path $root',
    ]
    common += [f'add_file -type verilog [file join $root {name}]' for name in sources]
    common += ['add_file -type cst [file join $root display.cst]',
               'add_file -type sdc [file join $root display.sdc]',
               'add_file -type gao [file join $root display.gao]',
               f'set_option -user_code {user_code}', 'set_option -bit_security 0',
               'set_option -secure_mode 0', 'set_option -gen_text_timing_rpt 1',
               'set_option -gen_sdf 1', 'set_option -gen_verilog_sim_netlist 1',
               'set_option -timing_driven 1', 'set_option -correct_hold_violation 1',
               'set_option -place_option 2', 'set_option -route_option 1',
               'set_option -replicate_resources 0']
    for name, flow in (('run.tcl', 'all'), ('synthesis.tcl', 'syn')):
        (output / name).write_text('\n'.join(common + ['run ' + flow]) + '\n')
    manifest = dict(schema=1, identity='custom138k-hdmi-isolation-' + user_code,
                    user_code='0x' + user_code, top_module=TOP, dynamic_input=dynamic,
                    source_policy='native resource baseline UI/DDR and native timing adapters; no full workstation preparation',
                    source_baseline=baseline.evidence(), source_snapshot_sha256=snapshot,
                    enabled_inputs=sources, display_adaptations=evidence,
                    implementation=dict(place_option=2, route_option=1, replicate_resources=False,
                                        automatic_hold_repair=True,
                                        ddr_initialization_placement='boards/custom_138k/hdmi_isolation.cst'),
                    port_locations={port: pinout['ports'][port]['balls'] for port in sorted(ports)},
                    excluded_subsystems=['AE350', 'USB', 'BLE', 'CNN', 'TF', 'synthesizer', 'LCD'],
                    data_entry='workstation_hdmi_isolation sample/PCM/status/effect and native UI/DDR client ports',
                    gao_file='display.gao', gao_configuration_id=user_code[-4:],
                    signal_schema='hdmi-isolation-memory-video-counters-64-v1', signals=SIGNALS,
                    sample_clock='clk_50m_d', storage_depth=1024,
                    validation_stage='prepared', hardware_acceptance=False, sram_programmed=False,
                    flash_accessed=False, release_ready=False, full_workstation=False,
                    prepared_at=datetime.now().astimezone().isoformat(),
                    input_sha256={str(path.relative_to(output)): digest(path) for path in output.rglob('*') if path.is_file()})
    (output / 'inputs.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return output, manifest


def build(output, synthesis_only=False):
    output = Path(output).resolve()
    manifest = json.loads((output / 'inputs.json').read_text())
    for name, expected in manifest['input_sha256'].items():
        if digest(output / name) != expected:
            raise ValueError('display input changed: ' + name)
    script = 'synthesis.tcl' if synthesis_only else 'run.tcl'
    started = datetime.now().astimezone()
    result = dict(identity=manifest['identity'], started_at=started.isoformat(),
                  command=['gw_sh', str(output / script)], synthesis_only=synthesis_only,
                  hardware_acceptance=False, sram_programmed=False, flash_accessed=False, release_ready=False)
    with (output / 'build.log').open('w') as log:
        process = subprocess.run(result['command'], cwd=output, stdout=log, stderr=subprocess.STDOUT)
    outputs = [f'impl/gwsynthesis/{BASE}.vg']
    if not synthesis_only:
        outputs += ['impl/pnr/ao_0.fs', f'impl/pnr/{BASE}_tr_content.html', f'impl/pnr/{BASE}.vo',
                    f'impl/pnr/{BASE}.sdf', f'impl/pnr/{BASE}.rpt.txt']
    missing = [name for name in outputs if not (output / name).is_file()]
    finished = datetime.now().astimezone()
    result.update(returncode=process.returncode or int(bool(missing)), tool_returncode=process.returncode,
                  missing_outputs=missing, finished_at=finished.isoformat(),
                  elapsed_seconds=(finished - started).total_seconds(),
                  output_sha256={name: digest(output / name) for name in outputs if (output / name).is_file()})
    if not result['returncode'] and not synthesis_only:
        timing = audit_timing(output, report_path=output / f'impl/pnr/{BASE}_tr_content.html',
                              targets={'clk_50m': 50.0, 'ddr_mem400': 400.0,
                                       'ddr_ui100': 100.0, 'video_pixel148': 148.5})
        (output / 'timing.json').write_text(json.dumps(timing, indent=2) + '\n')
        result['timing_closed'] = timing['timing_closed']
        result['timing_problems'] = timing['problems']
        result['global_worst_ns'] = timing['global_worst_ns']
    (output / 'build_result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result
