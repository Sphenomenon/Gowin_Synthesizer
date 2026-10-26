"""Prepare an offline whole-workstation GAO experiment from the C1102515 netlist."""

from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / 'out/workstation_physical_20261025_c1102515'
PARENT_INPUT_SHA = '8194351ae1421a84bb3e93900a36de6b134aa21aa7d6d25ef66adb6af996559f'
PARENT_FS_SHA = 'c5006e8f511fed84ced3cd284dabcb8a47359fadd4f64b4f34fdafc6ec880f68'
NETLIST = 'custom_138k_integration.vg'
TOP_MODULE = 'workstation_custom_138k_top'
USER_CODE = 'C11025E1'
SAMPLE_CLOCK = 'clk_50m_d'
SIGNALS = (
    'reset_n',
    *(f'memory_flags[{bit}]' for bit in range(7, -1, -1)),
    *(f'video_diagnostics[{bit}]' for bit in range(13, 7, -1)),
    *(f'video_diagnostics[{bit}]' for bit in range(31, 15, -1)),
    *(f'video_diagnostics[{bit}]' for bit in range(39, 31, -1)),
    *(f'video_diagnostics[{bit}]' for bit in range(71, 63, -1)),
    *(f'video_diagnostics[{bit}]' for bit in range(103, 95, -1)),
    'debug_uart_tx_d',
    'u_runtime/flags_sync[1]', 'u_runtime/flags_sync[0]',
    *(f'u_runtime/sample_sync[{bit}]' for bit in range(3, -1, -1)),
    'u_runtime/state[1]', 'u_runtime/state[0]',
)


def digest(source):
    return hashlib.sha256(Path(source).read_bytes()).hexdigest()


def verify_signals(netlist):
    bodies = {}
    for module in (TOP_MODULE, 'gw138k_push_performance_uart'):
        match = re.search(r'^module ' + re.escape(module) + r'\s*\(.*?^endmodule',
                          netlist, re.M | re.S)
        if match is None:
            raise ValueError('synthesis module missing: ' + module)
        bodies[module] = match[0]
    if not re.search(r'\bgw138k_push_performance_uart\s+u_runtime\s*\(', bodies[TOP_MODULE]):
        raise ValueError('runtime observation instance changed')
    for signal in (SAMPLE_CLOCK, *SIGNALS):
        module = 'gw138k_push_performance_uart' if signal.startswith('u_runtime/') else TOP_MODULE
        local = signal.removeprefix('u_runtime/')
        name = re.fullmatch(r'(\w+)(?:\[(\d+)\])?', local)
        declaration = re.search(r'^(?:wire|reg)\s+(?:\[(\d+):(\d+)\]\s+)?' +
                                re.escape(name[1]) + r'\s*;', bodies[module], re.M)
        if declaration is None:
            raise ValueError('observation signal missing: ' + signal)
        if name[2] is not None:
            bounds = declaration.groups()
            if None in bounds or not min(map(int, bounds)) <= int(name[2]) <= max(map(int, bounds)):
                raise ValueError('observation bit missing: ' + signal)


def prepare(output, parent=PARENT):
    output = Path(output).resolve()
    parent = Path(parent).resolve()
    if output.exists():
        raise ValueError('a new experiment output is required')
    if digest(parent / 'physical_inputs.json') != PARENT_INPUT_SHA:
        raise ValueError('C1102515 physical-input identity changed')
    original = json.loads((parent / 'physical_inputs.json').read_text())
    for relative, expected in original['input_sha256'].items():
        if digest(parent / relative) != expected:
            raise ValueError('C1102515 input changed: ' + relative)
    if digest(parent / 'impl/pnr/custom_138k_integration.fs') != PARENT_FS_SHA:
        raise ValueError('C1102515 rollback bitstream changed')
    verify_signals((parent / NETLIST).read_text())
    script = (parent / 'run.tcl').read_text()
    replacements = {
        'set_option -user_code C1102515\n': f'set_option -user_code {USER_CODE}\n',
        f'add_file -type netlist [file join $root {NETLIST}]\n':
            f'add_file -type netlist [file join $root {NETLIST}]\n'
            'add_file -type gao [file join $root workstation.gao]\n',
    }
    for anchor, replacement in replacements.items():
        if script.count(anchor) != 1:
            raise ValueError('physical Tcl anchor changed: ' + anchor.strip())
        script = script.replace(anchor, replacement)
    configuration = ET.Element('GAO_CONFIG')
    ET.SubElement(configuration, 'Version').text = '3.0'
    ET.SubElement(configuration, 'Mode').text = 'Standard'
    core = ET.SubElement(configuration, 'AoCore', index='0', sample_clock=SAMPLE_CLOCK,
                         trig_type='0', storage_depth='1024', window_num='1', capture_amount='1024',
                         implementation='0', trigger_pos='0', module_name=TOP_MODULE,
                         force_trigger_by_falling_edge='false', capture_init_data_enabled='false')
    capture = ET.SubElement(core, 'SignalList')
    for signal in SIGNALS:
        ET.SubElement(capture, 'Signal', capture_enable='true').text = signal
    triggers = ET.SubElement(core, 'Triggers')
    matches = ET.SubElement(core, 'MatchUnits')
    for index in range(16):
        trigger = ET.SubElement(triggers, 'Trigger', index=str(index))
        match = ET.SubElement(matches, 'MatchUnit', index=str(index), enabled='1' if index == 0 else '0',
                              match_type='0', counter_enable='0', counter_width='2', counter='2',
                              countinuous='0', func='0', value0='1' if index == 0 else '',
                              value1='1' if index == 0 else '')
        if index == 0:
            ET.SubElement(ET.SubElement(trigger, 'SignalList'), 'Signal').text = 'reset_n'
            match.set('trigger', '0')
    ET.SubElement(ET.SubElement(configuration, 'Expressions', type='Static'), 'Expression').text = 'M0'
    ET.SubElement(configuration, 'GAO_ID').text = '0010010111100001'
    output.mkdir(parents=True)
    for relative in (NETLIST, 'physical.cst', 'physical.sdc'):
        shutil.copyfile(parent / relative, output / relative)
    (output / 'run.tcl').write_text(script)
    ET.ElementTree(configuration).write(output / 'workstation.gao', encoding='UTF-8', xml_declaration=True)
    record = dict(
        schema=1, identity='workstation-hdmi-jtag-observation-' + USER_CODE, user_code='0x' + USER_CODE,
        source_policy='reuse exact C1102515 synthesis netlist and unchanged CST/SDC; post-synthesis GAO; P&R only',
        preparation_script_sha256=digest(__file__), parent=str(parent),
        parent_physical_inputs_sha256=PARENT_INPUT_SHA,
        reused_synthesis_netlist_sha256=original['input_sha256'][NETLIST],
        rollback_fs_sha256=PARENT_FS_SHA, exact_tcl_adaptations=replacements,
        sample_clock=SAMPLE_CLOCK, signals=list(SIGNALS), storage_depth=1024,
        truncated_counter_bits=dict(vblank=8, rendered_frames=8, underruns=8, audio_sample_gray=4),
        entire_workstation_resynthesized=False, tool_native_incremental_synthesis_claimed=False,
        implementation_started=False, implementation_verified=False, hardware_tested=False,
        sram_programmed=False, flash_programmed=False, deployment_authorized=False, release_ready=False,
        limitations=['Preparation checks declarations, not final GAO routing or physical resource use.',
                     'Repeated captures are needed to assess counter progress; low counter bits wrap.',
                     'sample_sync is Gray-coded, not binary; do not decode it as a sample count.',
                     'Original candidate timing acceptance does not transfer to this changed candidate.'],
        rollback='retain C1102515 in SRAM; restore original hash-checked FS only with explicit authorization',
        retirement='remove this temporary probe after locating the failing stage; never replace accepted build profiles',
        input_sha256={source.name: digest(source) for source in sorted(output.iterdir()) if source.is_file()},
    )
    (output / 'inputs.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output), indent=2))
