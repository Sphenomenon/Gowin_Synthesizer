#!/usr/bin/env python3
"""Build an isolated GW138K BLE candidate or overlay BLE onto a staged workstation.

Only creates fresh result directories. Does not program hardware or update the
current-workstation record. Full bitstream builds require a unique UserCode.
"""
from pathlib import Path
from datetime import datetime
import argparse
import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

from rtl8723ds_ble_sources import ROOT, RTL_NAMES, ADAPTATIONS, sha, stage_vendor

RTL = ROOT / 'rtl/bluetooth'
CANONICAL = ROOT.parent / 'results/workstation_20260911_174045_306332/Prj1'


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Expected one workstation integration anchor: ' + old[:100])
    return text.replace(old, new)


def hashes(stage):
    return {str(p.relative_to(stage)): sha(p) for p in sorted(stage.rglob('*'))
            if p.is_file() and not set(p.relative_to(stage).parts).intersection(
                {'impl', 'build', '__pycache__'}) and not p.name.endswith('.user')}


def add_file(files, stage, path, kind='file.verilog'):
    name = path.relative_to(stage).as_posix()
    if not any(f.get('path') == name for f in files):
        ET.SubElement(files, 'File', path=name, type=kind, enable='1')


def prepare(stage, profile, base, compact_hci=False, compact_h5=False):
    upstream_hashes = {}
    if profile == 'workstation':
        record = base.parent / 'workstation_inputs.json'
        if not record.is_file():
            raise ValueError('Workstation base must have ../workstation_inputs.json')
        upstream_hashes = json.loads(record.read_text())
        for name, digest in upstream_hashes.items():
            if sha(base / name) != digest:
                raise ValueError('Workstation baseline input drift: ' + name)
        shutil.copytree(base, stage, ignore=shutil.ignore_patterns(
            'impl', 'build', '*.user', '__pycache__'))
        tree = ET.parse(stage / 'Prj1.gprj')
        files = tree.find('FileList')
        top = stage / 'src/push2/gw138k_push_workstation_top.v'
        text = replace_once(top.read_text(), '    input wire button1_n,',
            '    input wire button1_n,\n'
            '    input wire ble_module_uart_tx,\n'
            '    inout wire ble_module_uart_rx,ble_module_bt_dis,ble_module_wl_dis,\n'
            '    output wire ble_status_uart_tx,')
        integration = '''
    // Independent BLE clock-domain island, fixed 50 MHz and original test service.
    wire ble_tx_value,ble_bt_value,ble_active;
    wire [767:0] ble_debug;
    gw138k_ble_link u_ble (
        .clk(clk_50m),.resetn(button1_n),.enable(1'b1),
        .module_uart_tx(ble_module_uart_tx),.module_uart_rx_value(ble_tx_value),
        .module_bt_dis_value(ble_bt_value),.outputs_active(ble_active),
        .initialized(),.connected(),.subscribed(),.failed(),.debug(ble_debug));
    assign ble_module_uart_rx=ble_active ? ble_tx_value : 1'bz;
    assign ble_module_bt_dis=ble_active ? ble_bt_value : 1'bz;
    assign ble_module_wl_dis=ble_active ? 1'b0 : 1'bz;
    gw138k_ble_status_uart u_ble_status (
        .clk(clk_50m),.resetn(button1_n),.debug(ble_debug),.serial_out(ble_status_uart_tx));
'''
        text = replace_once(text, '    wire reset_n;', integration + '    wire reset_n;')
        top.write_text(text)
        cst = stage / 'constraints/tang_mega_138k.cst'
        # Reject collisions with any original FPGA pad before adding the overlay.
        occupied = set()
        for loc in re.findall(r'IO_LOC\s+"[^\"]+"\s+([^;]+);', cst.read_text()):
            occupied.update(re.findall(r'[A-Z]+\d+', loc))
        for pin in ('AA20', 'AA21', 'AA19', 'AB20', 'AB21'):
            if pin in occupied:
                raise ValueError('BLE pin collides with workstation: ' + pin)
        cst.write_text(cst.read_text() + '\n' + (RTL / 'constraints/ble_io.cst').read_text()
            + '\n// J8 pin 9, PMOD1_IO2, separate BLE status 115200 8N1 UART.\n'
            + 'IO_LOC "ble_status_uart_tx" AB21;\n'
            + 'IO_PORT "ble_status_uart_tx" IO_TYPE=LVCMOS33 PULL_MODE=UP DRIVE=8 BANK_VCCIO=3.3;\n')
        sdc = stage / 'constraints/tang_mega_138k.sdc'
        additions = (RTL / 'constraints/ble.sdc').read_text().splitlines()
        additions = [line.replace('debug_uart_tx}', 'ble_status_uart_tx}') for line in additions
                     if not line.startswith('create_clock') and 'button1_n' not in line]
        sdc.write_text(sdc.read_text() + '\n# BLE overlay on existing clk50.\n' + '\n'.join(additions) + '\n')
        top_name = 'gw138k_push_workstation_top'
        output_name = 'Prj1'
    else:
        stage.mkdir(parents=True)
        (stage / 'constraints').mkdir()
        cst = stage / 'constraints/ble.cst'
        cst.write_text((RTL / 'constraints/ble_board.cst').read_text()
                       + (RTL / 'constraints/ble_io.cst').read_text())
        shutil.copy2(RTL / 'constraints/ble.sdc', stage / 'constraints/ble.sdc')
        project = ET.Element('Project')
        ET.SubElement(project, 'Template').text = 'FPGA'
        ET.SubElement(project, 'Version').text = '5'
        ET.SubElement(project, 'Device', name='GW5AST-138C',
                      pn='GW5AST-LV138PG484AC2/I1').text = 'gw5ast138c-006'
        files = ET.SubElement(project, 'FileList')
        tree = ET.ElementTree(project)
        add_file(files, stage, cst, 'file.cst')
        add_file(files, stage, stage / 'constraints/ble.sdc', 'file.sdc')
        top_name = 'gw138k_ble_board_top'
        output_name = 'ble138k'
        (stage / 'scripts').mkdir()
    vendor = stage / 'vendor/rtl8723ds_ble'
    for path in stage_vendor(vendor, compact_hci=compact_hci, compact_h5=compact_h5):
        add_file(files, stage, path)
    shutil.copytree(RTL, stage / 'rtl/bluetooth', dirs_exist_ok=True)
    for path in sorted((stage / 'rtl/bluetooth').glob('*.v')):
        if profile == 'standalone' or path.name != 'gw138k_ble_board_top.v':
            add_file(files, stage, path)
    if profile == 'standalone':
        uart = stage / 'rtl/bluetooth/uart_tx.v'
        shutil.copy2(CANONICAL / 'src/control/uart_tx.v', uart)
        add_file(files, stage, uart)
    tree.write(stage / 'Prj1.gprj', encoding='UTF-8', xml_declaration=True)
    return upstream_hashes, top_name, output_name


def reserved_usercodes():
    used = set()
    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if 'usercode' in key.lower().replace('_', ''):
                    if isinstance(item, str) and re.fullmatch(r'0x[0-9a-fA-F]{8}', item):
                        used.add(int(item, 16))
                    elif isinstance(item, int) and not isinstance(item, bool):
                        used.add(item)
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    records = list(ROOT.glob('*.json')) + list((ROOT / 'reports').glob('*.json'))
    for record in records:
        visit(json.loads(record.read_text()))
    for record in (ROOT / 'results').rglob('*metadata.json'):
        if record.name == 'ble_build_metadata.json':
            result_path = record.parent / 'ble_build_result.json'
            if result_path.exists() and not json.loads(result_path.read_text()).get('bitstream'):
                continue  # Failed attempt, no candidate bitstream released.
        try:
            visit(json.loads(record.read_text()))
        except (ValueError, UnicodeError):
            continue
    return used


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare-only', action='store_true')
    mode.add_argument('--synthesis-only', action='store_true')
    mode.add_argument('--full', action='store_true')
    parser.add_argument('--compact-h5', action='store_true', help='Mirror H5 header probes to infer single-read frame RAM')
    parser.add_argument('--compact-hci', action='store_true', help='Use validated single-write HCI parameter RAM to reduce LUT/FF pressure')
    parser.add_argument('--profile', choices=('standalone', 'workstation'), default='standalone')
    parser.add_argument('--workstation-base', type=Path, help='Verified staged Prj1 folder; defaults to LATEST_WORKSTATION build')
    parser.add_argument('--user-code', help='Unique eight hex digits, required for --full')
    parser.add_argument('--route-option', type=int, choices=(0, 1, 2), help='Override Gowin routing algorithm (2 is the GW5AST-138 family default)')
    parser.add_argument('--pnr-from', type=Path, help='Stage verified identical synthesis inputs/netlist before PNR; Gowin may re-synthesize')
    args = parser.parse_args()
    if args.pnr_from and not args.full:
        parser.error('--pnr-from requires --full')
    if args.full:
        if args.user_code is None or re.fullmatch('[0-9a-fA-F]{8}', args.user_code) is None or int(args.user_code, 16) == 0:
            parser.error('--full requires a nonzero eight-digit --user-code')
        used = reserved_usercodes()
        if int(args.user_code, 16) in used:
            parser.error('UserCode already belongs to a recorded board or BLE build')
    elif args.user_code is not None:
        parser.error('--user-code is only supported with --full')
    if args.profile == 'standalone' and args.workstation_base is not None:
        parser.error('--workstation-base requires --profile workstation')
    base = None
    if args.profile == 'workstation':
        if args.workstation_base:
            base = args.workstation_base.resolve()
        else:
            latest = json.loads((ROOT / 'LATEST_WORKSTATION.json').read_text())
            base = ROOT / latest['build'] / 'Prj1'
    output = ROOT / 'results' / datetime.now().strftime('ble_' + args.profile + '_%Y%m%d_%H%M%S_%f')
    stage = output / 'Prj1'
    upstream, top_name, output_name = prepare(stage, args.profile, base, compact_hci=args.compact_hci, compact_h5=args.compact_h5)
    flow = 'pnr' if args.pnr_from else ('syn' if args.synthesis_only else 'all')
    tcl = stage / 'scripts/build.tcl'
    if args.profile == 'standalone':
        text = '''set root [file normalize [file join [file dirname [info script]] ..]]
cd $root
open_project [file join $root Prj1.gprj]
set_option -verilog_std v2001
set_option -use_sspi_as_gpio 1
set_option -use_mspi_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -timing_driven 1
set_option -correct_hold_violation 1
set_option -place_option 2
set_option -route_option 1
set_option -gen_text_timing_rpt 1
set_option -gen_verilog_sim_netlist 1
'''
    else:
        text = tcl.read_text()
        text = re.sub(r'(?m)^set_option -(?:user_code|inc_pnr).*\n', '', text)
        # Retain baseline options, remove its run/flow control tail.
        text = text[:text.index('set flow all')]
    if args.route_option is not None:
        text = re.sub(r'(?m)^set_option -route_option .*$', 'set_option -route_option ' + str(args.route_option), text)
    text += f'set_option -top_module {top_name}\nset_option -output_base_name {output_name}\n'
    if args.full:
        text += 'set_option -user_code ' + args.user_code.upper() + '\n'
    text += f'run {flow}\n'
    tcl.write_text(text)
    before = hashes(stage)
    changed = sorted(name for name, digest in upstream.items() if before.get(name) != digest)
    expected = {'Prj1.gprj', 'src/push2/gw138k_push_workstation_top.v',
                'constraints/tang_mega_138k.cst', 'constraints/tang_mega_138k.sdc', 'scripts/build.tcl'}
    if args.profile == 'workstation' and not set(changed) <= expected:
        raise ValueError('Unexpected workstation baseline change: ' + str(changed))
    metadata = {'schema_version': 1, 'profile': args.profile, 'device': 'GW5AST-LV138PG484AC2/I1',
                'base': str(base) if base else None, 'user_code': '0x' + args.user_code.upper() if args.full else None,
                'top_module': top_name, 'flow': 'prepare' if args.prepare_only else flow,
                'upstream_adaptations': ADAPTATIONS, 'compact_hci': args.compact_hci, 'compact_h5': args.compact_h5, 'changed_baseline_inputs': changed,
                'hardware_programmed': False, 'workstation_record_updated': False,
                'route_option': int(re.search(r'set_option -route_option (\d+)', text)[1])}
    if args.pnr_from:
        previous = args.pnr_from.resolve()
        old_metadata = json.loads((previous / 'ble_build_metadata.json').read_text())
        old_result = json.loads((previous / 'ble_build_result.json').read_text())
        old_inputs = json.loads((previous / 'workstation_inputs.json').read_text())
        if old_result['exit_code'] != 0 or not old_result['inputs_unchanged']:
            raise ValueError('Cannot reuse failed or modified synthesis')
        for key in ('profile', 'device', 'top_module', 'compact_hci', 'compact_h5'):
            if old_metadata.get(key, False) != metadata[key]:
                raise ValueError('Synthesis reuse profile/device/top differs: ' + key)
        # Documentation can be added independently; all synthesis/ROM/project/
        # pin/clock inputs must be exactly equal. UserCode is a PNR option.
        def synthesis_inputs(values):
            return {name: digest for name, digest in values.items()
                    if name != 'scripts/build.tcl' and not name.endswith('.md')}
        if synthesis_inputs(before) != synthesis_inputs(old_inputs):
            raise ValueError('Synthesis reuse input hashes differ')
        for name, digest in old_inputs.items():
            if sha(previous / 'Prj1' / name) != digest:
                raise ValueError('Reused synthesis input tree drifted: ' + name)
        def options(text):
            return '\n'.join(line for line in text.splitlines()
                if not line.startswith(('set_option -user_code', 'set_option -route_option', 'run ')))
        if options(tcl.read_text()) != options((previous / 'Prj1/scripts/build.tcl').read_text()):
            raise ValueError('Synthesis reuse options differ')
        old_synthesis = previous / 'Prj1/impl/gwsynthesis'
        if not (old_synthesis / (output_name + '.vg')).is_file():
            raise ValueError('Reusable Gowin synthesis netlist missing')
        shutil.copytree(old_synthesis, stage / 'impl/gwsynthesis')
        metadata['reused_synthesis'] = str(previous)
        metadata['reused_netlist_sha256'] = sha(old_synthesis / (output_name + '.vg'))
    (output / 'ble_build_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    (output / 'workstation_inputs.json').write_text(json.dumps(before, indent=2) + '\n')
    print('BLE_BUILD=' + str(output), flush=True)
    if args.prepare_only:
        return
    tool = shutil.which('gw_sh')
    if tool is None:
        raise SystemExit('gw_sh is not on PATH; prepared project is retained')
    env = os.environ.copy()
    env.pop('PRJ1_FLOW', None)
    with (output / 'gowin.log').open('w') as log:
        process = subprocess.run([tool, 'scripts/build.tcl'], cwd=stage, env=env,
                                 stdout=log, stderr=subprocess.STDOUT)
    after = hashes(stage)
    if args.pnr_from:
        final_netlist = stage / 'impl/gwsynthesis' / (output_name + '.vg')
        metadata['staged_reference_netlist_preserved'] = (
            final_netlist.exists() and sha(final_netlist) == metadata['reused_netlist_sha256'])
        (output / 'ble_build_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    stable = before == after
    fs = stage / 'impl/pnr' / (output_name + '.fs')
    result = {'exit_code': process.returncode, 'inputs_unchanged': stable,
              'bitstream': str(fs) if fs.exists() else None,
              'bitstream_sha256': sha(fs) if fs.exists() else None,
              'hardware_programmed': False}
    (output / 'ble_build_result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if process.returncode != 0 or not stable:
        raise SystemExit(1)
    if args.full and not fs.exists():
        raise SystemExit('Gowin returned success without producing a bitstream')


if __name__ == '__main__':
    main()
