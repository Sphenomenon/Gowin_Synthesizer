"""Standalone custom-138K USB device loopback; build never programs hardware."""

import argparse
import csv
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import xml.etree.ElementTree as ElementTree

from tools.audit_workstation_timing import audit as audit_timing
from tools.stage_usb_firmware import sha
from tools.workstation_custom_board_implementation import ulpi_bypass_constraints
from tools.workstation_hdmi_isolation import gao_configuration as base_gao
from tools.workstation_pinout import parse_locations, prepare as prepare_pinout, render_constraints
from tools.workstation_ulpi_selftest import PORTS, clock_pin_binding, clock_pull_constraints


ROOT = Path(__file__).resolve().parents[1]
TOP = 'workstation_usb2_device_probe_top'
BASE = 'usb2_device_probe'
TOP_SOURCE = 'rtl/workstation/' + TOP + '.sv'
PEER_SOURCES = tuple('rtl/usb_board/' + name for name in (
    'midi_usb2_link.v', 'midi_usb_async_fifo.v', 'midi_usb_bridge.v', 'midi_usb_device.v',
    'midi_usb_hs_phy.v', 'midi_usb_fs_state.v', 'midi_usb2_debug.v',
    'vendor/midi_ulpi_wrapper.v', 'vendor/midi_usb2_boot.v',
    'vendor/usbf_sie_tx.v', 'vendor/usbf_sie_rx.v', 'vendor/usbf_crc16.v',
))
DESCRIPTOR_SOURCE = 'rtl/usb_board/generated/usb_composite_desc_rom.v'


def gao_configuration(user_code):
    document = ElementTree.fromstring(base_gao(user_code))
    core = document.find('AoCore')
    core.set('module_name', TOP)
    signals = core.find('SignalList')
    signals.clear()
    for index in reversed(range(384)):
        ElementTree.SubElement(signals, 'Signal', capture_enable='true').text = f'status_50mhz[{index}]'
    core.find('Triggers/Trigger/SignalList/Signal').text = 'status_50mhz[0]'
    return ElementTree.tostring(document, encoding='unicode') + '\n'


def timing_constraints():
    lines = [
        'create_clock -name clk_50m -period 20.000 [get_ports {clk_50m}]',
        'create_clock -name ulpi_60m -period 16.666667 [get_ports {usb2_ulpi_clk}]',
        'set_input_delay -clock ulpi_60m -max 5.500 [get_ports {usb2_ulpi_data[*] usb2_ulpi_dir usb2_ulpi_nxt}]',
        'set_input_delay -clock ulpi_60m -min 1.500 [get_ports {usb2_ulpi_data[*] usb2_ulpi_dir usb2_ulpi_nxt}]',
        'set_output_delay -clock ulpi_60m -max 5.500 [get_ports {usb2_ulpi_data[*] usb2_ulpi_stp}]',
        'set_output_delay -clock ulpi_60m -min -0.500 [get_ports {usb2_ulpi_data[*] usb2_ulpi_stp}]',
    ]
    targets = ('u_device*/bridge/*/rd_gray_w1_*_s0/D u_device*/bridge/*/wr_gray_r1_*_s0/D '
               'u_device*/bridge/hs_sync_0_s0/D '
               'u_device*/attach_delay.ready_sync_0_s0/D '
               'u_device*/debug_monitor/gray_meta_*_s0/D '
               'u_device*/debug_monitor/request_meta_s0/D u_device*/debug_monitor/ack_meta_s0/D '
               'u_device*/debug_monitor/snapshot_50_*_s0/D '
               'observations*.native_monitor/gray_meta_*_s0/D '
               'observations*.native_monitor/request_meta_s0/D observations*.native_monitor/ack_meta_s0/D '
               'observations*.native_monitor/snapshot_50_*_s0/D')
    lines += [f'set_max_delay 15.000 -from [get_clocks {{clk_50m ulpi_60m}}] -to [get_pins {{{targets}}}]',
              f'set_false_path -hold -from [get_clocks {{clk_50m ulpi_60m}}] -to [get_pins {{{targets}}}]']
    release_pins = ('u_device*/reset_sync_*_s*/CLEAR u_device*/reset_sync_*_s*/PRESET '
                    'u_device*/bridge/*/wr_release_*_s*/CLEAR u_device*/bridge/*/rd_release_*_s*/CLEAR '
                    'u_device*/bridge/online_release_*_s*/CLEAR '
                    'u_device*/bridge/control_release_*_s*/CLEAR u_device*/bridge/hs_sync_*_s*/CLEAR '
                    'u_device*/attach_delay.reset_release_*_s*/CLEAR')
    lines.append(f'set_false_path -to [get_pins {{{release_pins}}}]')
    for kind in ('setup', 'hold', 'recovery', 'removal'):
        lines.append(f'report_timing -{kind} -max_paths 2000 -max_common_paths 1')
    return '\n'.join(lines) + '\n'


def peer_inputs(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text())
    if not manifest.get('passed') or not manifest.get('timing', {}).get('passed'):
        raise ValueError('Device core requires a successful routed peer manifest')
    snapshot = manifest_path.parent.parent / 'source_snapshot'
    for name, expected in manifest['sha256'].items():
        if sha(snapshot / name) != expected:
            raise ValueError('Frozen peer input changed: ' + name)
    for artifact in manifest['artifacts']:
        if sha(Path(artifact['path'])) != artifact['sha256']:
            raise ValueError('Peer artifact differs from successful build')
    return snapshot, manifest


def prepare(root, netlist_directory, peer_manifest, output, user_code):
    root, output = Path(root).resolve(), Path(output).resolve()
    if not re.fullmatch(r'[0-9a-fA-F]{8}', user_code or '') or user_code.upper() in ('C11028D5', 'C11028E5'):
        raise ValueError('Device probe requires a new eight-hex UserCode')
    if output.exists():
        raise FileExistsError(str(output))
    snapshot, peer = peer_inputs(peer_manifest)
    output.mkdir(parents=True)
    _, plan = prepare_pinout(root, netlist_directory, output / 'pinout')
    selected = [line for line in render_constraints(plan).splitlines()
                if (match := re.match(r'IO_(?:LOC|PORT)\s+"([^"]+)"', line)) and match[1] in PORTS]
    physical, electrical = ulpi_bypass_constraints(('\n'.join(selected) + '\n').encode(), plan)
    physical = clock_pull_constraints(physical, 'NONE')
    locations = {port: plan['ports'][port]['balls'] for port in PORTS}
    if parse_locations(physical.decode()) != locations:
        raise ValueError('Probe locations differ from the locked board plan')
    sources = [TOP_SOURCE]
    for name in (TOP_SOURCE,):
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, destination)
    selected_peer = (*PEER_SOURCES, 'rtl/usb_board/vendor/usbf_defs.v',
                     'tools/decode_usb2_debug.py', 'tools/generate_usb_descriptors.py')
    for name in selected_peer:
        destination = output / 'peer' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(snapshot / name, destination)
        if sha(destination) != peer['sha256'][name]:
            raise ValueError('Peer copy differs: ' + name)
    first_party = root.parents[2] / '25k/example/MIDI_KEYBOARD'
    overrides = {}
    for name, reason in {
        'rtl/usb_board/midi_usb_async_fifo.v': 'synchronize pointer reset release per FIFO clock domain',
        'rtl/usb_board/midi_usb2_link.v': 'native observer and explicit attach delay with local synchronized reset release and registered ready',
        'rtl/usb_board/midi_usb2_events.v': 'passive native RXCMD, SE0 and byte statistics',
    }.items():
        shutil.copyfile(first_party / name, output / 'peer' / name)
        overrides[name] = dict(source=str(first_party / name), sha256=sha(first_party / name),
                               frozen_baseline_sha256=peer['sha256'].get(name), reason=reason)
    sources += ['peer/' + name for name in PEER_SOURCES]
    sources.append('peer/rtl/usb_board/midi_usb2_events.v')
    generator = runpy.run_path(str(snapshot / 'tools/generate_usb_descriptors.py'))
    descriptors = generator['build'](0xfb9a, 0xfb9b)
    for mapping in descriptors.values():
        mapping[0x0301] = generator['string']('GW138K Lab')
        mapping[0x0302] = generator['string']('GW138K USB2 Loopback')
        mapping[0x0303] = generator['string'](user_code.upper())
    generator['validate'](descriptors)
    descriptor = output / 'peer' / DESCRIPTOR_SOURCE
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    descriptor.write_text(generator['emit_rom'](descriptors))
    sources.append('peer/' + DESCRIPTOR_SOURCE)
    (output / 'usb2_debug_profile.vh').write_text('`define MIDI_USB2_DIAGNOSTICS\n`define MIDI_USB2_PROBE\n')
    (output / 'probe.cst').write_bytes(physical)
    (output / 'probe.sdc').write_text(timing_constraints())
    (output / 'probe.gao').write_text(gao_configuration(user_code.upper()))
    common = ['set root [file dirname [file normalize [info script]]]',
              f'set_device {plan["device"]} -device_version C',
              'set_option -synthesis_tool gowinsynthesis', f'set_option -top_module {TOP}',
              f'set_option -output_base_name {BASE}', 'set_option -verilog_std sysv2017',
              'set_option -use_cpu_as_gpio 1', 'set_option -use_mspi_as_gpio 1',
              'set_option -include_path {peer/rtl/usb_board/vendor .}',
              *[f'add_file -type verilog [file join $root {name}]' for name in sources],
              *[f'add_file -type {kind} [file join $root probe.{kind}]' for kind in ('cst', 'sdc', 'gao')],
              f'set_option -user_code {user_code.upper()}', 'set_option -bit_security 0',
              'set_option -secure_mode 0', 'set_option -gen_text_timing_rpt 1',
              'set_option -gen_verilog_sim_netlist 1', 'set_option -timing_driven 1',
              'set_option -correct_hold_violation 1', 'set_option -place_option 2',
              'set_option -route_option 1']
    (output / 'run.tcl').write_text('\n'.join([*common, 'run all']) + '\n')
    manifest = dict(schema='custom138k-usb2-device-loopback-v1', identity='custom138k-device-' + user_code.upper(),
                    user_code='0x' + user_code.upper(), device=plan['device'], top_module=TOP,
                    source_policy='versioned_probe_FIFO_reset_and_native_observer_plus_hash_checked_frozen_25k_device_core',
                    source_paths=sources, peer_manifest=str(Path(peer_manifest).resolve()),
                    peer_manifest_sha256=sha(Path(peer_manifest)), peer_user_code=peer['user_code'],
                    peer_frozen_inputs_verified=len(peer['sha256']),
                    first_party_overrides=overrides,
                    top_source_sha256=sha(root / TOP_SOURCE), tool_sha256=sha(Path(__file__)),
                    port_locations=locations, electrical_check=plan['electrical_check'], io_standard=electrical,
                    sample_clock='clk_50m_d', storage_depth=1024, status_width=384,
                    usb=dict(vid='fb9a', pid='fb9b', product='GW138K USB2 Loopback',
                             attach_delay_reference_cycles=12500000,
                             midi_out=1, midi_in=129, bulk_out=2, bulk_in=130,
                             identity_usage='local_laboratory_unallocated', high_speed_packet_bytes=512),
                    omitted_subsystems=['HDMI', 'DDR', 'CPU', 'audio', 'USB_host'],
                    full_workstation=False, hardware_tested=False, flash_written=False,
                    integration_criteria='temporary direct-PC device diagnostic; production remains USB host',
                    rollback='restore hash-checked C11028E5 SRAM image or cold-boot unchanged Flash',
                    input_sha256={str(path.relative_to(output)): sha(path)
                                  for path in output.rglob('*') if path.is_file()})
    (output / 'inputs.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    return output, manifest


def audit(output):
    output = Path(output).resolve()
    manifest = json.loads((output / 'inputs.json').read_text())
    if parse_locations((output / 'probe.cst').read_text()) != manifest['port_locations']:
        raise ValueError('Physical probe ports changed')
    binding = clock_pin_binding((output / f'impl/pnr/{BASE}.pin.html').read_text(), 'C18', 'NONE')
    timing = audit_timing(output, report_path=output / f'impl/pnr/{BASE}_tr_content.html',
                          targets=dict(clk_50m=50.0, ulpi_60m=60.0, tck_pad_i=20.0))
    bitstream = output / 'impl/pnr/ao_0.fs'
    header = bitstream.read_text()[:2500]
    if ('//UserCode: ' + manifest['user_code']).upper() not in header.upper() or '//GAOCRC: ' + manifest['user_code'][-4:] not in header:
        raise ValueError('Probe bitstream identity differs')
    result = dict(identity=manifest['identity'], timing=timing, clock_pin=binding,
                  bitstream=str(bitstream), bitstream_sha256=sha(bitstream),
                  passed=timing['timing_closed'], hardware_tested=False)
    (output / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def build(output):
    output = Path(output).resolve()
    manifest = json.loads((output / 'inputs.json').read_text())
    for name, expected in manifest['input_sha256'].items():
        if sha(output / name) != expected:
            raise ValueError('Staged probe input changed: ' + name)
    started = datetime.now().astimezone()
    command = ['gw_sh', str(output / 'run.tcl')]
    with (output / 'build.log').open('x') as log:
        completed = subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT)
    result = dict(started_at=started.isoformat(), finished_at=datetime.now().astimezone().isoformat(),
                  command=command, returncode=completed.returncode, hardware_tested=False)
    (output / 'build_result.json').write_text(json.dumps(result, indent=2) + '\n')
    if completed.returncode:
        raise RuntimeError('Probe build failed: ' + str(output / 'build.log'))
    result['audit'] = audit(output)
    (output / 'build_result.json').write_text(json.dumps(result, indent=2) + '\n')
    if not result['audit']['passed']:
        raise RuntimeError('Probe routed timing did not close: ' + str(output / 'audit.json'))
    return result


def read_samples(path, width):
    header = None
    data_seen = False
    values = []
    signals = [f'status_50mhz[{index}]' for index in reversed(range(width))]
    with Path(path).open(encoding='utf-8-sig', newline='') as source:
        for row in csv.reader(source):
            row = [cell.strip() for cell in row]
            while row and not row[-1]:
                row.pop()
            if not row:
                continue
            if not data_seen:
                data_seen = row == ['Data:']
                continue
            if header is None:
                if not row[0].startswith('time unit:') or row[1:] != signals:
                    raise ValueError('CSV lacks the complete ordered probe status bits')
                header = row
                continue
            if len(row) != len(header) or any(cell not in ('0', '1') for cell in row[1:]):
                raise ValueError('Probe CSV column count or binary sample changed')
            values.append(int(''.join(row[1:]), 2))
    if len(values) != 1024:
        raise ValueError('Expected one full 1024-sample probe window')
    return values


def decode_usb_status(values, phy_fields):
    runs = []
    for sample, value in enumerate(values):
        key = ((value >> 6) & 3, value >> 8, (value >> 1) & 1, (value >> 2) & 15)
        if not runs or runs[-1]['key'] != key:
            runs.append(dict(key=key, count=1, sample=sample))
        else:
            runs[-1]['count'] += 1
    cycles = []
    for index in range(len(runs) - 3):
        group = runs[index:index + 4]
        if ([run['key'][0] for run in group] != [0, 1, 2, 3]
                or any(run['count'] != 8 for run in group)
                or len({run['key'][2:] for run in group}) != 1
                or group[3]['key'][1] != 0x55aa33):
            continue
        payloads = [run['key'][1] for run in group]
        fields = phy_fields(payloads[0] | ((payloads[1] >> 16) << 24))
        flags = group[0]['key'][3]
        fields.update(online=bool(flags & 8), hs_active=bool(flags & 4),
                      control_online=bool(flags & 2), source_clock_alive=bool(flags & 1),
                      phy_clock_ticks_per_ms=payloads[2] & 255,
                      phy_clock_quantized_hz=(payloads[2] & 255) * 256000,
                      midi_tx_accepted_words16=payloads[1] & 65535,
                      midi_rx_accepted_words16=payloads[2] >> 8)
        cycles.append(dict(first_sample=group[0]['sample'], fields=fields))
    if not cycles:
        raise ValueError('No complete coherent USB status page cycle')
    return dict(latest=cycles[-1]['fields'], complete_page_cycles=len(cycles))


def decode(values, decoder, width=160):
    if len(values) != 1024:
        raise ValueError('Expected one full 1024-sample probe window')
    if width not in (160, 384) or any(not 0 <= value < 1 << width for value in values):
        raise ValueError('Probe status width differs')
    usb = decode_usb_status([value & 0xffffffff for value in values], decoder['phy_fields'])
    latest = values[-1]
    result = dict(usb=usb['latest'], complete_page_cycles=usb['complete_page_cycles'],
                reference_cycles=(latest >> 128) & 0xffffffff,
                bulk_rx_bytes=(latest >> 64) & 0xffffffff,
                bulk_tx_bytes=(latest >> 96) & 0xffffffff,
                midi_rx_words=(latest >> 32) & 65535, midi_tx_words=(latest >> 48) & 65535)
    if width == 384:
        native = [decode_usb_status([(value >> (160 + 32 * index)) & 0xffffffff for value in values],
                                   lambda word: dict(raw_status=word))['latest']['raw_status']
                  for index in range(7)]
        result['native'] = dict(states_seen=native[0] >> 24, lines_seen=(native[0] >> 20) & 15,
                                flags_seen=(native[0] >> 16) & 15,
                                raw_se0_max_cycles=native[1] & 0xffffff, raw_se0_runs=native[1] >> 24,
                                utmi_se0_max_cycles=native[2] & 0xffffff, utmi_se0_runs=native[2] >> 24,
                                rxcmd_count=native[3] & 0xffffff, last_rxcmd=f'{native[3] >> 24:02X}',
                                phy_rx_bytes=native[4] & 0xffffff, last_phy_data=f'{native[4] >> 24:02X}',
                                utmi_rx_bytes=native[5] & 0xffffff, last_utmi_data=f'{native[5] >> 24:02X}',
                                link_nxt_count=native[6] & 0xffffff, raw_flags=native[6] >> 24,
                                independently_coherent_mailboxes=True)
    return result


def capture(candidate, output):
    candidate, output = Path(candidate).resolve(), Path(output).resolve()
    manifest = json.loads((candidate / 'inputs.json').read_text())
    helper = runpy.run_path(str(ROOT / 'reports/hdmi_usb3_20261025/capture_ddr_jtag.py'))
    if sha(helper['BINARY']) != '4717a2afa56893861de161207bc2c4f094f53227099763ebfa2f0025ab72515b':
        raise ValueError('GAO binary differs from verified Linux WINUSB recipe')
    if sha(helper['RECIPE']) != '901f1c40d4679c54e1246226c33c2d33850c2a55bbebed496ed9c69f4b87de66':
        raise ValueError('GAO recipe differs from verified Linux WINUSB recipe')
    for name in ['probe.gao', 'peer/tools/decode_usb2_debug.py']:
        if sha(candidate / name) != manifest['input_sha256'][name]:
            raise ValueError('Probe capture input changed: ' + name)
    output.mkdir(parents=True, exist_ok=False)
    with Path('/tmp/gw138k_20261025.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        helper['identity'](output / 'identity_before.log', manifest['user_code'])
        environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_OPENGL='software',
                           LD_LIBRARY_PATH=str(helper['BINARY'].parents[1] / 'lib'),
                           LD_PRELOAD='/usr/lib64/libstdc++.so.6:/usr/lib64/libz.so.1:/usr/lib64/libfreetype.so.6',
                           TMPDIR=str(helper['TEMPORARY']))
        socket = helper['TEMPORARY'] / 'gao1'
        if socket.exists():
            listeners = subprocess.run(['ss', '-xlpn'], text=True, capture_output=True, check=True).stdout
            if str(socket) in listeners or socket.lstat().st_uid != os.getuid():
                raise ValueError('GAO socket is active or foreign')
            socket.unlink()
        command = ['timeout', '--kill-after=5s', '60s', 'gdb', '-nx', '-q', '-batch', '-x',
                   str(helper['RECIPE']), '--args', str(helper['BINARY']), '-local', '-gao',
                   str(candidate / 'probe.gao'), '-out', str(output / 'capture'), '-cable', 'FT2CH', '-location', '54']
        started = datetime.now().astimezone().isoformat()
        with (output / 'gdb.log').open('x') as log:
            result = subprocess.run(command, env=environment, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, timeout=75)
        if result.returncode:
            raise RuntimeError('GAO capture failed: ' + str(output / 'gdb.log'))
        files = list(output.glob('capture_core*_window*.csv'))
        if len(files) != 1:
            raise ValueError('Expected one device probe GAO CSV')
        helper['identity'](output / 'identity_after.log', manifest['user_code'])
        decoder = runpy.run_path(str(candidate / 'peer/tools/decode_usb2_debug.py'))
        width = manifest['status_width']
        values = read_samples(files[0], width)
        record = decode(values, decoder, width)
        record.update(started_at=started, finished_at=datetime.now().astimezone().isoformat(),
                      identity=manifest['identity'], operation='read_only_GAO',
                      hardware_programmed=False, csv_sha256=sha(files[0]),
                      host_decoder_sha256=sha(Path(__file__)),
                      gao_configuration_sha256=sha(candidate / 'probe.gao'))
        (output / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
        return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    preparation = commands.add_parser('prepare')
    preparation.add_argument('--netlist-dir', type=Path, required=True)
    preparation.add_argument('--peer-manifest', type=Path, required=True)
    preparation.add_argument('--output', type=Path, required=True)
    preparation.add_argument('--user-code', required=True)
    compilation = commands.add_parser('build')
    compilation.add_argument('candidate', type=Path)
    observation = commands.add_parser('capture')
    observation.add_argument('candidate', type=Path)
    observation.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        output, manifest = prepare(ROOT, args.netlist_dir, args.peer_manifest, args.output, args.user_code)
        result = dict(output=str(output), identity=manifest['identity'])
    elif args.command == 'build':
        result = build(args.candidate)
    else:
        result = capture(args.candidate, args.output)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
