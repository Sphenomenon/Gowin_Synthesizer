"""Headless native USB2 host diagnostic; preparation and build never program hardware."""

import argparse
import csv
from copy import deepcopy
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import runpy
import subprocess
import xml.etree.ElementTree as ElementTree

from tools import workstation_usb2_hotplug as hotplug
from tools.stage_usb_firmware import sha
from tools.workstation_hdmi_isolation import gao_configuration as base_gao
from tools.workstation_ulpi_selftest import clock_pin_binding


ROOT = Path(__file__).resolve().parents[1]
HOST = 'u_native_usb/host/usb'
FIELDS = (
    ('state_history', HOST + '/state_history_q', 19),
    ('failure_history', HOST + '/failure_history_q', 16),
    ('attempts', HOST + '/attempts_q', 16),
    ('last_failure', HOST + '/last_failure_q', 4),
    ('last_failure_state', HOST + '/last_failure_state_q', 5),
    ('last_failure_function', HOST + '/last_failure_function_q', 8),
    ('received_peak', HOST + '/received_peak_q', 32),
    ('transmitted_peak', HOST + '/transmitted_peak_q', 32),
    ('sof_peak', HOST + '/sof_peak_q', 32),
    ('port_state', HOST + '/port_state', 5),
    ('port_failure', HOST + '/port_failure', 4),
    ('function_control', HOST + '/unused_function', 8),
    ('init_stage', HOST + '/init_stage', 5),
    ('init_failure', HOST + '/init_failure', 3),
    ('line_state', HOST + '/controller/line_state', 2),
    ('high_speed', 'high_speed', 1),
    ('connected', HOST + '/connected', 1),
    ('traffic_enabled', 'traffic_enable', 1),
    ('phy_ready', 'phy_ready', 1),
)
SIGNALS = tuple(signal if width == 1 else f'{signal}[{bit}]'
                for _, signal, width in FIELDS for bit in reversed(range(width)))
OWNER = 'u_native_usb/input_owner'
CPU_FIELDS = (
    ('connected', 'telemetry[1]', 1),
    ('generic_midi', OWNER + '/generic_midi', 1),
    ('gw25k', OWNER + '/gw25k', 1),
    ('cpu_fault', 'cpu_fault', 4),
    ('received_events', 'telemetry', 32, 32),
    ('out_errors', 'telemetry', 32, 192),
    ('in_diagnostics', 'telemetry', 32, 160),
    ('milliseconds', 'u_native_usb/host/bus/milliseconds_q', 32),
)
CPU_SIGNALS = tuple(signal if width == 1 else f'{signal}[{bit}]'
                    for _, signal, width, *offset in CPU_FIELDS
                    for bit in reversed(range(offset[0] if offset else 0, (offset[0] if offset else 0) + width)))
RECOVERY_FIELDS = tuple((name, HOST + '/' + name + '_q', width) for name, width in (
    ('recovery_count', 16), ('active_count', 16), ('recovery_aborts', 16), ('command_count', 16),
    ('recovery_exit_ticks', 32), ('recovery_exit_sofs', 32), ('recovery_exit_state', 5),
    ('recovery_exit_flags', 8), ('recovery_exit_rxcmd', 8), ('recovery_exit_function', 8),
    ('last_sof_token', 16), ('last_command', 32), ('last_result', 24),
))
RECOVERY_SIGNALS = tuple(f'{signal}[{bit}]' for _, signal, width in RECOVERY_FIELDS
                         for bit in reversed(range(width)))


def gao_configuration(user_code):
    document = ElementTree.fromstring(base_gao(user_code))
    core = document.find('AoCore')
    core.set('module_name', hotplug.TOP)
    core.set('sample_clock', 'usb2_ulpi_clk_d')
    signals = core.find('SignalList')
    signals.clear()
    for name in SIGNALS:
        ElementTree.SubElement(signals, 'Signal', capture_enable='true').text = name
    core.find('Triggers/Trigger/SignalList/Signal').text = HOST + '/status_release_q[1]'
    cpu = deepcopy(core)
    cpu.set('index', '1')
    cpu.set('sample_clock', 'usb_clk')
    signals = cpu.find('SignalList')
    signals.clear()
    for name in CPU_SIGNALS:
        ElementTree.SubElement(signals, 'Signal', capture_enable='true').text = name
    cpu.find('Triggers/Trigger/SignalList/Signal').text = 'usb_release[3]'
    document.insert(list(document).index(core) + 1, cpu)
    recovery = deepcopy(core)
    recovery.set('index', '2')
    signals = recovery.find('SignalList')
    signals.clear()
    for name in RECOVERY_SIGNALS:
        ElementTree.SubElement(signals, 'Signal', capture_enable='true').text = name
    document.insert(list(document).index(cpu) + 1, recovery)
    return ElementTree.tostring(document, encoding='unicode') + '\n'


def prepare(output, netlist_directory, user_code):
    output, native = hotplug.prepare(ROOT, output, netlist_directory, user_code, ulpi_clock_pull='NONE')
    (output / 'host_probe.gao').write_text(gao_configuration(user_code.upper()))
    (output / 'host_probe_io.sdc').write_text((output / 'usb2_hotplug.sdc').read_text() +
        'set_input_delay -clock ulpi_60m -max 5.500 [get_ports {usb2_ulpi_data[*] usb2_ulpi_dir usb2_ulpi_nxt}]\n'
        'set_input_delay -clock ulpi_60m -min 1.500 [get_ports {usb2_ulpi_data[*] usb2_ulpi_dir usb2_ulpi_nxt}]\n'
        'set_output_delay -clock ulpi_60m -max 5.500 [get_ports {usb2_ulpi_data[*] usb2_ulpi_stp}]\n'
        'set_output_delay -clock ulpi_60m -min -0.500 [get_ports {usb2_ulpi_data[*] usb2_ulpi_stp}]\n')
    commands = ['set root [file normalize [file dirname [info script]]]', 'cd $root',
                f'set_device {native["device"]} -device_version C',
                f'set_option -top_module {hotplug.TOP}', f'set_option -output_base_name {hotplug.BASE}',
                'set_option -verilog_std sysv2017', 'set_option -include_path $root']
    commands += [f'add_file -type verilog [file join $root {name}]' for name in native['source_paths']]
    commands += ['add_file -type cst [file join $root usb2_hotplug.cst]']
    commands += ['add_file -type sdc [file join $root host_probe_io.sdc]',
                 'add_file -type gao [file join $root host_probe.gao]',
                 f'set_option -user_code {user_code.upper()}', 'set_option -bit_security 0',
                 'set_option -secure_mode 0', 'set_option -timing_driven 1',
                 'set_option -gen_text_timing_rpt 1', 'set_option -gen_sdf 1',
                 'set_option -gen_verilog_sim_netlist 1', 'set_option -correct_hold_violation 1',
                 'set_option -place_option 2', 'set_option -route_option 1',
                 'set_option -replicate_resources 0',
                 'set_option -use_mspi_as_gpio 1', 'set_option -use_cpu_as_gpio 1']
    (output / 'host_probe.tcl').write_text('\n'.join([*commands, 'run all']) + '\n')
    manifest = dict(schema='headless-native-usb2-host-probe-v1', user_code=native['user_code'],
                    native_manifest_sha256=sha(output / 'hotplug_inputs.json'),
                    source_policy='existing_headless_hotplug_component_with_native_ULPI_clocked_GAO',
                    builder_sha256=sha(Path(__file__)), signals=SIGNALS, fields=FIELDS,
                    cpu_signals=CPU_SIGNALS, cpu_fields=CPU_FIELDS,
                    recovery_signals=RECOVERY_SIGNALS, recovery_fields=RECOVERY_FIELDS,
                    inputs={name: sha(output / name) for name in ('host_probe.gao', 'host_probe.tcl', 'host_probe_io.sdc')},
                    sample_clock='ulpi_60m', high_speed_allowed=True,
                    hardware_programmed=False, flash_written=False)
    (output / 'host_probe_inputs.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def verify_inputs(output):
    manifest = json.loads((output / 'host_probe_inputs.json').read_text())
    if sha(output / 'hotplug_inputs.json') != manifest['native_manifest_sha256']:
        raise ValueError('native host manifest changed')
    native = json.loads((output / 'hotplug_inputs.json').read_text())
    for name, expected in {**native['staged_input_sha256'], **manifest['inputs']}.items():
        if sha(output / name) != expected:
            raise ValueError('host probe input changed: ' + name)
    return manifest


def build(output):
    output = Path(output).resolve()
    verify_inputs(output)
    started = datetime.now().astimezone().isoformat()
    with (output / 'build.log').open('x') as log:
        completed = subprocess.run(['gw_sh', str(output / 'host_probe.tcl')], cwd=output,
                                   stdout=log, stderr=subprocess.STDOUT)
    result = dict(started_at=started, finished_at=datetime.now().astimezone().isoformat(),
                  returncode=completed.returncode, hardware_programmed=False)
    (output / 'build_result.json').write_text(json.dumps(result, indent=2) + '\n')
    if completed.returncode:
        raise RuntimeError('host probe build failed: ' + str(output / 'build.log'))
    return audit(output)


def audit(output):
    output = Path(output).resolve()
    result = json.loads((output / 'build_result.json').read_text())
    if result['returncode']:
        raise ValueError('cannot audit a failed host build')
    verify_inputs(output)
    result['audit'] = hotplug.audit(ROOT, output, bitstream_path=output / 'impl/pnr/ao_0.fs')
    result['clock_pin'] = clock_pin_binding((output / f'impl/pnr/{hotplug.BASE}.pin.html').read_text(), 'C18', 'NONE')
    manifest = json.loads((output / 'host_probe_inputs.json').read_text())
    header = (output / 'impl/pnr/ao_0.fs').read_text()[:4096].upper()
    if '//USERCODE: ' + manifest['user_code'].upper() not in header or '//GAOCRC: ' + manifest['user_code'][-4:] not in header:
        raise ValueError('host probe bitstream identity differs')
    result['passed'] = result['audit']['timing_closed']
    result['checker_sha256'] = sha(Path(__file__))
    (output / 'host_probe_audit.json').write_text(json.dumps(result, indent=2) + '\n')
    if not result['passed']:
        raise ValueError('host probe routed timing did not close')
    return result


def decode_csv(path, core=0):
    fields, signals = ((FIELDS, SIGNALS), (CPU_FIELDS, CPU_SIGNALS), (RECOVERY_FIELDS, RECOVERY_SIGNALS))[core]
    rows = [[value.strip() for value in row if value.strip()]
            for row in csv.reader(Path(path).read_text().splitlines(), skipinitialspace=True)]
    header = next((index for index, row in enumerate(rows) if row and row[0].startswith('time unit:')), None)
    if header is None or rows[header][1:] != list(signals):
        raise ValueError('host probe CSV signal order differs')
    samples = []
    for row in rows[header + 1:]:
        if not row:
            continue
        if len(row) != len(signals) + 1 or int(row[0]) != len(samples) or any(value not in ('0', '1') for value in row[1:]):
            raise ValueError('invalid host probe sample')
        sample, offset = {}, 1
        for name, _, width, *_ in fields:
            sample[name] = int(''.join(row[offset:offset + width]), 2)
            offset += width
        samples.append(sample)
    if len(samples) != 1024:
        raise ValueError('incomplete host probe capture')
    last = samples[-1]
    if core != 0:
        return dict(samples=len(samples), first=samples[0], last=last)
    return dict(samples=len(samples), first=samples[0], last=last,
                states_seen=[state for state in range(19) if last['state_history'] & (1 << state)],
                failures_seen=[code for code in range(1, 16) if last['failure_history'] & (1 << code)],
                counter_scope='maximum_single_attempt_since_global_reset_not_sum',
                enumeration_verified=False, application_communication_verified=False)


def capture(candidate, output):
    candidate, output = Path(candidate).resolve(), Path(output).resolve()
    manifest = verify_inputs(candidate)
    helper = runpy.run_path(str(ROOT / 'reports/hdmi_usb3_20261025/capture_ddr_jtag.py'))
    if sha(helper['BINARY']) != '4717a2afa56893861de161207bc2c4f094f53227099763ebfa2f0025ab72515b' or sha(helper['RECIPE']) != '901f1c40d4679c54e1246226c33c2d33850c2a55bbebed496ed9c69f4b87de66':
        raise ValueError('verified GAO runtime changed')
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
                raise ValueError('GAO socket active or foreign')
            socket.unlink()
        command = ['timeout', '--kill-after=5s', '60s', 'gdb', '-nx', '-q', '-batch', '-x',
                   str(helper['RECIPE']), '--args', str(helper['BINARY']), '-local', '-gao',
                   str(candidate / 'host_probe.gao'), '-out', str(output / 'capture'), '-cable', 'FT2CH', '-location', '54']
        started = datetime.now().astimezone().isoformat()
        with (output / 'gdb.log').open('x') as log:
            completed = subprocess.run(command, env=environment, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, timeout=75)
        if completed.returncode:
            raise RuntimeError('host GAO capture failed: ' + str(output / 'gdb.log'))
        core_count = len(ElementTree.parse(candidate / 'host_probe.gao').getroot().findall('AoCore'))
        if core_count not in (2, 3):
            raise ValueError('unexpected host probe core count')
        files = [output / f'capture_core{core}_window0.csv' for core in range(core_count)]
        if not all(path.is_file() for path in files):
            raise ValueError('expected every configured host probe capture window')
        helper['identity'](output / 'identity_after.log', manifest['user_code'])
        result = decode_csv(files[0])
        result['cpu'] = decode_csv(files[1], core=1)
        if core_count == 3:
            result['recovery'] = decode_csv(files[2], core=2)
        owner = result['cpu']['last']
        result['device_kind'] = ('none' if not owner['connected'] else 'gw25k' if owner['gw25k'] else
                                 'midi' if owner['generic_midi'] else 'push')
        result['enumeration_verified'] = bool(owner['connected'] and not owner['cpu_fault'])
        result['application_communication_verified'] = bool(result['enumeration_verified'] and owner['received_events'])
        result.update(started_at=started, finished_at=datetime.now().astimezone().isoformat(),
                      user_code=manifest['user_code'], hardware_programmed=False,
                      csv_sha256={path.name: sha(path) for path in files}, decoder_sha256=sha(Path(__file__)),
                      cross_core_atomic_snapshot=False)
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    preparation = commands.add_parser('prepare')
    preparation.add_argument('--output', type=Path, required=True)
    preparation.add_argument('--netlist-dir', type=Path, required=True)
    preparation.add_argument('--user-code', required=True)
    compilation = commands.add_parser('build')
    compilation.add_argument('candidate', type=Path)
    checking = commands.add_parser('audit')
    checking.add_argument('candidate', type=Path)
    observation = commands.add_parser('capture')
    observation.add_argument('candidate', type=Path)
    observation.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = (prepare(args.output, args.netlist_dir, args.user_code) if args.command == 'prepare'
              else build(args.candidate) if args.command == 'build' else audit(args.candidate)
              if args.command == 'audit' else capture(args.candidate, args.output))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
