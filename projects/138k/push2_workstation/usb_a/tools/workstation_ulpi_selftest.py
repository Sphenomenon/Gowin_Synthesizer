"""Explicit standalone ULPI self-test; build and readback never program a board."""

from pathlib import Path
from datetime import datetime
import argparse
import csv
import fcntl
import json
import os
import re
import runpy
import stat
import subprocess
import xml.etree.ElementTree as ElementTree

from tools.stage_usb_firmware import sha
from tools.workstation_pinout import prepare as prepare_pinout, parse_locations, render_constraints, load_sources
from tools.workstation_custom_board_implementation import ulpi_bypass_constraints
from tools.workstation_hdmi_isolation import gao_configuration as base_gao
from tools.workstation_synthesis_netlist import SynthesisNetlist
from tools.audit_workstation_timing import audit as audit_timing


ROOT = Path(__file__).resolve().parents[1]
TOP = 'workstation_ulpi_selftest_top'
BASE = 'ulpi_selftest'
LEGACY_SCHEMA = 'standalone-ulpi-selftest-v2'
SCHEMA = 'standalone-ulpi-selftest-input-sampler-v3'
SOURCES = ('rtl/workstation/workstation_ulpi_selftest_top.sv',
           'rtl/usb2/workstation_usb3300_host_link.sv', 'rtl/usb2/workstation_usb3300_host_init.sv',
           'rtl/usb2/workstation_ulpi_supervisor.sv', 'rtl/usb2/workstation_ulpi_link.sv')
PORTS = ('clk_50m', *(f'usb2_ulpi_data[{index}]' for index in range(8)),
         'usb2_ulpi_clk', 'usb2_ulpi_dir', 'usb2_ulpi_nxt', 'usb2_ulpi_stp')
LEGACY_FIELDS = (('power_on_count', 'power_count_q', 10), ('reference_cycles', 'reference_cycles_q', 32),
          ('window_edges', 'window_edges_q', 24), ('windows', 'window_count_q', 32),
          ('clock_seen', 'clock_seen_q_1_Q', 1), ('clock_flags', 'clock_flags_q', 5),
          ('snapshot_valid', 'snapshot_valid_q_1_Q', 1), ('snapshot_updates', 'snapshot_updates_q', 32),
          ('status', 'status_q', 88), ('bus', 'bus_sync_q', 11))
FIELDS = LEGACY_FIELDS + (('input_toggles', 'window_input_toggles_q', 19),
                          ('input_high_cycles', 'window_input_high_q', 19))
LEGACY_SIGNALS = tuple(signal if width == 1 else f'{signal}[{bit}]'
                       for _, signal, width in LEGACY_FIELDS for bit in reversed(range(width)))
SIGNALS = tuple(signal if width == 1 else f'{signal}[{bit}]'
                for _, signal, width in FIELDS for bit in reversed(range(width)))


def gao_configuration(user_code):
    document = ElementTree.fromstring(base_gao(user_code))
    core = document.find('AoCore')
    core.set('module_name', TOP)
    core.set('sample_clock', 'clk_50m_d')
    signals = core.find('SignalList')
    signals.clear()
    for signal in SIGNALS:
        ElementTree.SubElement(signals, 'Signal', capture_enable='true').text = signal
    for signal in core.findall('Triggers/Trigger/SignalList/Signal'):
        signal.text = SIGNALS[0]
    return ElementTree.tostring(document, encoding='unicode') + '\n'


def timing_constraints():
    lines = ['create_clock -name clk_50m -period 20.000 [get_ports {clk_50m}]',
             'create_clock -name ulpi_60m -period 16.666667 [get_ports {usb2_ulpi_clk}]']
    for source, destination in (('ulpi_gray_q*', 'gray_meta_q*'), ('ulpi_count_q_23', 'gray_meta_q_23'),
                                ('request_q*', 'request_meta_q*'),
                                ('acknowledge_q*', 'acknowledge_meta_q*'),
                                ('u_phy/supervisor/heartbeat_q*', 'u_phy/supervisor/heartbeat_meta_q*')):
        lines += [f'set_max_delay -from [get_pins {{{source}_s*/Q}}] -to [get_pins {{{destination}_s*/D}}] 12.000',
                  f'set_false_path -hold -from [get_pins {{{source}_s*/Q}}] -to [get_pins {{{destination}_s*/D}}]']
    for first, second in (('gray_meta_q*', 'gray_sync_q*'), ('request_meta_q*', 'request_sync_q*'),
                           ('acknowledge_meta_q*', 'acknowledge_sync_q*'), ('bus_meta_q*', 'bus_sync_q*'),
                           ('u_phy/supervisor/heartbeat_meta_q*', 'u_phy/supervisor/heartbeat_sync_q*'),
                           ('clock_input_meta_q*', 'clock_input_sync_q*')):
        lines.append(f'set_max_delay -from [get_pins {{{first}_s*/Q}}] -to [get_pins {{{second}_s*/D}}] 2.000')
    lines += ['set_max_delay -from [get_pins {status_held_q*_s*/Q}] -to [get_pins {status_q*_s*/D}] 16.000',
              'set_false_path -hold -from [get_pins {status_held_q*_s*/Q}] -to [get_pins {status_q*_s*/D}]',
              'set_false_path -to [get_pins {bus_meta_q*_s*/D}]']
    lines.append('set_false_path -to [get_pins {clock_input_meta_q*_s*/D}]')
    for release in ('ulpi_release_q*', 'u_phy/supervisor/heartbeat_release_q*', 'u_phy/supervisor/release_q*'):
        lines.append(f'set_false_path -to [get_pins {{{release}_s*/CLEAR}}]')
    for kind in ('setup', 'hold', 'recovery', 'removal'):
        lines.append(f'report_timing -{kind} -max_paths 2000 -max_common_paths 1')
    return '\n'.join(lines) + '\n'


def clock_pull_constraints(physical, clock_pull):
    if clock_pull is None:
        return physical
    if clock_pull not in ('NONE', 'UP', 'DOWN'):
        raise ValueError('unsupported self-test ULPI clock pull')
    anchor = b'IO_PORT "usb2_ulpi_clk" IO_TYPE=LVCMOS33;'
    if physical.count(anchor) != 1:
        raise ValueError('self-test ULPI clock IO property anchor changed')
    replacement = f'IO_PORT "usb2_ulpi_clk" IO_TYPE=LVCMOS33 PULL_MODE={clock_pull};'.encode()
    return physical.replace(anchor, replacement)


def clock_probe_constraints(physical, carrier):
    network = carrier.same('FPC2.8', 'J1.15')
    if carrier.ball('FPC2.8', 2) != 'C17' or set(carrier.nets[network]) != {'FPC2.8', 'J1.15'}:
        raise ValueError('external clock probe FPC2.8/C17 connectivity changed')
    anchor = b'IO_LOC "usb2_ulpi_clk" C18;'
    if physical.count(anchor) != 1:
        raise ValueError('external clock probe location anchor changed')
    return physical.replace(anchor, b'IO_LOC "usb2_ulpi_clk" C17;')


def clock_pin_binding(report, ball, pull):
    rows = [re.findall(r'<td[^>]*>\s*(.*?)\s*</td>', row, re.S)
            for row in re.findall(r'<tr[^>]*>(.*?)</tr>', report, re.S)]
    matches = [row for row in rows if row and row[0] == 'usb2_ulpi_clk']
    if len(matches) != 1:
        raise ValueError('physical clock input pin report row missing or duplicated')
    row = matches[0]
    if len(row) < 10 or row[2] != ball + '/2' or row[4] != 'in' or row[7] != 'LVCMOS33':
        raise ValueError('physical clock pin binding or input electrical mode changed')
    if pull != 'vendor_default' and row[9] != pull:
        raise ValueError('physical clock input pull differs from the selected experiment')
    return dict(ball=ball, bank=2, direction=row[4], io_type=row[7], pull=row[9], clock_function=row[6])


def prepare(root, netlist_directory, output, user_code, clock_pull=None, clock_probe=False):
    root, output = Path(root).resolve(), Path(output).resolve()
    if not re.fullmatch(r'[0-9A-Fa-f]{8}', user_code or '') or user_code.upper() in ('C11028D5', 'C11028E5', 'C11028E6'):
        raise ValueError('ULPI self-test requires a distinct eight-hex UserCode')
    if output.exists():
        raise FileExistsError('self-test output exists: ' + str(output))
    user_code = user_code.upper()
    output.mkdir(parents=True)
    _, plan = prepare_pinout(root, netlist_directory, output / 'pinout')
    selected = [line for line in render_constraints(plan).splitlines()
                if (match := re.match(r'IO_(?:LOC|PORT)\s+"([^"]+)"', line)) and match[1] in PORTS]
    physical, electrical = ulpi_bypass_constraints(('\n'.join(selected) + '\n').encode(), plan)
    locations = {port: plan['ports'][port]['balls'] for port in PORTS}
    route = dict(mode='native', ball='C18', connection='U2.14--U5.2--U5.13--J1.92')
    if clock_probe:
        profile = json.loads((root / 'boards/custom_138k/pinout.json').read_text())
        netlists, _ = load_sources(profile, netlist_directory)
        physical = clock_probe_constraints(physical, netlists['carrier'])
        locations['usb2_ulpi_clk'] = ['C17']
        route = dict(mode='external_probe', ball='C17', connection='FPC2.8--J1.15',
                     normally_owned_by='dac_pdn_n', requires_amplifier_cable_disconnected=True,
                     requires_temporary_CLKOUT_probe_wire=True,
                     remove_probe_before_loading_non_diagnostic_firmware=True)
        if clock_pull is None:
            clock_pull = 'NONE'
    physical = clock_pull_constraints(physical, clock_pull)
    if parse_locations(physical.decode()) != locations:
        raise ValueError('self-test locations differ from the locked board plan')
    snapshot = {name: sha(root / name) for name in (*SOURCES, 'build.py', 'tools/workstation_ulpi_selftest.py',
                                                 'boards/custom_138k/pinout.json')}
    for name in SOURCES:
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((root / name).read_bytes())
    (output / 'selftest.cst').write_bytes(physical)
    (output / 'selftest.sdc').write_text(timing_constraints())
    (output / 'selftest.gao').write_text(gao_configuration(user_code))
    common = ['set root [file dirname [file normalize [info script]]]',
              f'set_device {plan["device"]} -device_version C', 'set_option -synthesis_tool gowinsynthesis',
              f'set_option -top_module {TOP}', f'set_option -output_base_name {BASE}',
              'set_option -verilog_std sysv2017', 'set_option -use_cpu_as_gpio 1',
              'set_option -use_mspi_as_gpio 1']
    common += [f'add_file -type verilog [file join $root {name}]' for name in SOURCES]
    common += [f'add_file -type {kind} [file join $root selftest.{kind}]' for kind in ('cst', 'sdc', 'gao')]
    common += [f'set_option -user_code {user_code}', 'set_option -bit_security 0', 'set_option -secure_mode 0',
               'set_option -gen_text_timing_rpt 1', 'set_option -gen_sdf 1',
               'set_option -gen_verilog_sim_netlist 1', 'set_option -timing_driven 1',
               'set_option -correct_hold_violation 1', 'set_option -place_option 2', 'set_option -route_option 1']
    for filename, flow in (('run.tcl', 'all'), ('synthesis.tcl', 'syn')):
        (output / filename).write_text('\n'.join([*common, 'run ' + flow]) + '\n')
    for name, expected in snapshot.items():
        if sha(root / name) != expected:
            raise ValueError('self-test source changed during prepare: ' + name)
    manifest = dict(schema=SCHEMA, identity='custom138k-ulpi-selftest-' + user_code, user_code='0x' + user_code,
                    top_module=TOP, device=plan['device'], source_policy='versioned_native_ulpi_only_no_overlays',
                    source_paths=SOURCES, source_snapshot_sha256=snapshot, ports=list(PORTS),
                    fields=FIELDS, signals=SIGNALS, sample_clock='clk_50m_d', storage_depth=1024,
                    observer_alias_policy='actual_synthesis_unique_register_drivers_and_physical_input_buffers',
                    reference_hz=50000000, window_ref_cycles=500000, startup_clock_timeout_ms=100,
                    clock_input_pull=clock_pull or 'vendor_default',
                    clock_input_route=route, port_locations=locations,
                    expected_vendor_id=0x0424, expected_product_id=0x0004,
                    electrical_check=plan['electrical_check'], io_standard=electrical,
                    omitted_subsystems=['HDMI', 'DDR', 'CPU', 'audio', 'USB_MAC', 'enumeration', 'firmware', 'PLL'],
                    validation_stage='standalone_ulpi_selftest_prepared', full_workstation=False,
                    hardware_tested=False, full_electrical_acceptance=False,
                    integration_criteria='diagnostic only; retire after physical fault isolation; retain production profiles',
                    rollback='hash-checked C11028E5 SRAM image; Flash untouched',
                    input_sha256={str(entry.relative_to(output)): sha(entry) for entry in output.rglob('*') if entry.is_file()})
    (output / 'inputs.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return output, manifest


def audit(output):
    output = Path(output).resolve()
    manifest = json.loads((output / 'inputs.json').read_text())
    route = manifest.get('clock_input_route', dict(mode='native', ball='C18'))
    locations = parse_locations((output / 'selftest.cst').read_text())
    if locations.get('usb2_ulpi_clk') != [route['ball']]:
        raise ValueError('clock input location differs from the selected physical route')
    if 'port_locations' in manifest and locations != manifest['port_locations']:
        raise ValueError('self-test physical locations differ from the staged manifest')
    binding = clock_pin_binding((output / f'impl/pnr/{BASE}.pin.html').read_text(),
                                route['ball'], manifest.get('clock_input_pull', 'vendor_default'))
    netlist = SynthesisNetlist((output / f'impl/gwsynthesis/{BASE}.vg').read_text(), TOP)
    drivers = {}
    for name, cell in netlist.cells.items():
        if cell['kind'].startswith('DFF'):
            drivers.setdefault(netlist.pin(name, 'Q'), []).append(name)
    bindings = {}
    input_clocks = {}
    for port in ('clk_50m', 'usb2_ulpi_clk'):
        buffer = port + '_ibuf'
        if netlist.cells[buffer]['kind'] != 'IBUF' or netlist.pin(buffer, 'I') != port:
            raise ValueError('self-test physical clock input changed: ' + port)
        input_clocks[port] = netlist.pin(buffer, 'O')
    for signal in SIGNALS:
        cells = drivers.get(netlist.canonical('', signal), [])
        if len(cells) != 1 or netlist.pin(cells[0], 'CLK') != input_clocks['clk_50m']:
            raise ValueError('observer is not a unique reference-clock register: ' + signal)
        bindings[signal] = cells[0]
    for signal, driver in (('clock_seen_q_1_Q', 'clock_seen_q_s0'),
                           ('snapshot_valid_q_1_Q', 'snapshot_valid_q_s0')):
        if bindings[signal] != driver:
            raise ValueError('self-test sticky probe alias changed: ' + signal)
    counters = [name for name, cell in netlist.cells.items()
                if cell['kind'].startswith('DFF') and netlist.pin(name, 'Q') == 'ulpi_count_q[0]']
    if len(counters) != 1 or netlist.pin(counters[0], 'CLK') != input_clocks['usb2_ulpi_clk']:
        raise ValueError('independent counter not driven by the physical ULPI input')
    sampler = 'clock_input_meta_q_s0'
    if (netlist.pin(sampler, 'D') != input_clocks['usb2_ulpi_clk'] or
            netlist.pin(sampler, 'CLK') != input_clocks['clk_50m']):
        raise ValueError('clock input sampler must observe the physical clock in the reference domain')
    if any(cell['kind'].startswith(('PLL', 'rPLL')) for cell in netlist.cells.values()):
        raise ValueError('standalone self-test unexpectedly contains a PLL')
    timing = audit_timing(output, report_path=output / f'impl/pnr/{BASE}_tr_content.html',
                          targets=dict(clk_50m=50.0, ulpi_60m=60.0, tck_pad_i=20.0))
    record = dict(identity=manifest['identity'], structural_checks_passed=True, observer_bindings=bindings,
                  independent_counter=counters[0], physical_clock_inputs=input_clocks,
                  input_sampler=sampler,
                  clock_input_route=route, clock_input_pin_binding=binding,
                  timing=timing, bitstream_sha256=sha(output / 'impl/pnr/ao_0.fs'),
                  input_manifest_sha256=sha(output / 'inputs.json'), hardware_tested=False)
    (output / 'integration_audit.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


def build(output, synthesis_only=False):
    output = Path(output).resolve()
    manifest = json.loads((output / 'inputs.json').read_text())
    for name, expected in manifest['input_sha256'].items():
        if sha(output / name) != expected:
            raise ValueError('staged self-test input changed: ' + name)
    started = datetime.now().astimezone()
    command = ['gw_sh', str(output / ('synthesis.tcl' if synthesis_only else 'run.tcl'))]
    with (output / 'build.log').open('x') as log:
        completed = subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT)
    finished = datetime.now().astimezone()
    outputs = [f'impl/gwsynthesis/{BASE}.vg']
    if not synthesis_only:
        outputs += ['impl/pnr/ao_0.fs', f'impl/pnr/{BASE}.vo', f'impl/pnr/{BASE}_tr_content.html']
    missing = [name for name in outputs if not (output / name).is_file()]
    record = dict(identity=manifest['identity'], command=command, returncode=completed.returncode or int(bool(missing)),
                  tool_returncode=completed.returncode, missing_outputs=missing, started_at=started.isoformat(),
                  finished_at=finished.isoformat(), elapsed_seconds=(finished-started).total_seconds(),
                  hardware_tested=False, output_sha256={name: sha(output / name) for name in outputs if (output / name).is_file()})
    (output / 'build_result.json').write_text(json.dumps(record, indent=2) + '\n')
    if record['returncode'] == 0 and not synthesis_only:
        audit(output)
    return record


def decode(values, window_ref_cycles=500000):
    fields = FIELDS if len(values) == len(SIGNALS) else LEGACY_FIELDS
    if len(values) != sum(width for _, _, width in fields) or any(value not in (0, 1) for value in values):
        raise ValueError('expected the complete binary self-test observer')
    words, offset = {}, 0
    for name, _, width in fields:
        words[name] = int(''.join(str(bit) for bit in values[offset:offset+width]), 2)
        offset += width
    status, flags = words['status'], words['clock_flags']
    words['reset_released'] = words['power_on_count'] == 1023
    words.update(vendor_id=(status >> 32) & 65535, product_id=(status >> 48) & 65535,
                 init_stage=(status >> 4) & 31, init_failure=(status >> 9) & 15,
                 init_last_data=(status >> 21) & 255, init_last_error=(status >> 29) & 7,
                 init_retries=(status >> 13) & 255, clock_failure=(flags >> 3) & 3,
                 stp=(words['bus'] >> 10) & 1, direction=(words['bus'] >> 9) & 1,
                 next=(words['bus'] >> 8) & 1, data=words['bus'] & 255,
                 ulpi_hz=words['window_edges'] * 50000000 / window_ref_cycles)
    expected_edges = window_ref_cycles * 6 / 5
    frequency_ok = words['windows'] >= 2 and abs(words['window_edges'] - expected_edges) <= expected_edges / 100
    valid_status = bool(words['snapshot_valid'])
    completed = valid_status and status & 1 and not status & 6 and words['init_stage'] == 17
    identity_ok = words['vendor_id'] == 0x0424 and words['product_id'] == 0x0004
    controls_ok = (status >> 64) & 0xffffff == 0x061041
    stage = ('reset' if not words['reset_released'] else
             'ulpi_clock_not_observed' if words['windows'] >= 2 and not words['clock_seen'] else
             'ulpi_clock_failed' if flags & 4 else
             'measuring_clock' if words['windows'] < 2 else
             'ulpi_frequency_out_of_range' if not frequency_ok else
             'waiting_for_snapshot' if not valid_status else
             'ulpi_init_failed' if status & 6 else
             'passed' if completed and identity_ok and controls_ok and flags & 3 == 3 else 'initializing_phy')
    words.update(stage=stage, passed=stage == 'passed', scratch_patterns_verified=stage == 'passed',
                 clock_frequency_ok=frequency_ok, snapshot_observed=valid_status,
                 enumeration_tested=False, hardware_acceptance=False)
    words['input_sampler_present'] = fields == FIELDS
    if words['input_sampler_present']:
        words.update(reference_sampled_transition_hz=words['input_toggles'] * 50000000 / window_ref_cycles,
                     reference_sampled_high_fraction=words['input_high_cycles'] / window_ref_cycles)
    return words


def observer_signals(manifest):
    schema = manifest.get('schema', SCHEMA)
    signals = {SCHEMA: SIGNALS, LEGACY_SCHEMA: LEGACY_SIGNALS}.get(schema)
    if signals is None or manifest.get('signals', list(signals)) != list(signals):
        raise ValueError('not the explicit standalone ULPI observer layout')
    return signals


def decode_csv(path, manifest):
    signals = observer_signals(manifest)
    with Path(path).open(newline='') as stream:
        rows = csv.reader(stream, skipinitialspace=True)
        header = next(rows, [])
        if header == ['Data:']:
            header = next(rows, [])
        if header[1:-1] != list(signals) or header[-1] != '':
            raise ValueError('self-test CSV layout changed')
        samples = []
        for row in rows:
            if not row:
                continue
            if len(row) != len(signals) + 2 or row[-1] != '' or row[0] != str(len(samples)):
                raise ValueError('invalid or noncontiguous self-test sample row')
            samples.append(decode([int(bit) for bit in row[1:-1]], manifest['window_ref_cycles']))
    if len(samples) != manifest['storage_depth']:
        raise ValueError('incomplete self-test capture')
    reference_active = samples[0]['reference_cycles'] != samples[-1]['reference_cycles']
    snapshots_active = samples[0]['snapshot_updates'] != samples[-1]['snapshot_updates']
    if not reference_active or (samples[-1]['passed'] and not snapshots_active):
        raise ValueError('inactive reference clock or stale successful snapshot')
    return dict(samples=len(samples), first=samples[0], last=samples[-1],
                reference_active=reference_active, snapshots_active=snapshots_active,
                csv_sha256=sha(Path(path)))


def capture(candidate, output):
    candidate, output = Path(candidate).resolve(), Path(output).resolve()
    manifest = json.loads((candidate / 'inputs.json').read_text())
    if 'schema' not in manifest or 'signals' not in manifest:
        raise ValueError('not the explicit standalone ULPI observer')
    observer_signals(manifest)
    for name, expected in manifest['input_sha256'].items():
        if sha(candidate / name) != expected:
            raise ValueError('staged self-test input changed: ' + name)
    helper = runpy.run_path(str(ROOT / 'reports/hdmi_usb3_20261025/capture_ddr_jtag.py'))
    if (sha(helper['BINARY']) != '4717a2afa56893861de161207bc2c4f094f53227099763ebfa2f0025ab72515b' or
            sha(helper['RECIPE']) != '901f1c40d4679c54e1246226c33c2d33850c2a55bbebed496ed9c69f4b87de66'):
        raise ValueError('validated GAO binary or WINUSB recipe changed')
    output.mkdir(parents=True, exist_ok=False)
    with Path('/tmp/gw138k_20261025.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        helper['identity'](output / 'identity_before.log', manifest['user_code'])
        socket = helper['TEMPORARY'] / 'gao1'
        if socket.exists():
            listeners = subprocess.run(['ss', '-xlpn'], capture_output=True, text=True, check=True).stdout
            if not stat.S_ISSOCK(socket.lstat().st_mode) or socket.lstat().st_uid != os.getuid() or str(socket) in listeners:
                raise ValueError('GAO socket is foreign or active')
            socket.unlink()
        environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_OPENGL='software',
                           LD_LIBRARY_PATH=str(helper['BINARY'].parents[1] / 'lib'),
                           LD_PRELOAD='/usr/lib64/libstdc++.so.6:/usr/lib64/libz.so.1:/usr/lib64/libfreetype.so.6',
                           TMPDIR=str(helper['TEMPORARY']))
        command = ['timeout', '--kill-after=5s', '60s', 'gdb', '-nx', '-q', '-batch', '-x', str(helper['RECIPE']),
                   '--args', str(helper['BINARY']), '-local', '-gao', str(candidate / 'selftest.gao'),
                   '-out', str(output / 'capture'), '-cable', 'FT2CH', '-location', '54']
        started = helper['timestamp']()
        with (output / 'gdb.log').open('x') as log:
            completed = subprocess.run(command, env=environment, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, timeout=75)
        files = list(output.glob('capture_core*_window*.csv'))
        if completed.returncode or len(files) != 1:
            raise ValueError('self-test GAO capture failed or produced an unexpected CSV inventory')
        record = decode_csv(files[0], manifest)
        helper['identity'](output / 'identity_after.log', manifest['user_code'])
        record.update(identity=manifest['identity'], started_at=started, finished_at=helper['timestamp'](),
                      gao_sha256=sha(candidate / 'selftest.gao'), decoder_sha256=sha(Path(__file__)),
                      hardware_programmed=False, operation='read_only_GAO_capture')
        (output / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
        return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--capture-output', type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(capture(arguments.candidate, arguments.capture_output), indent=2))
