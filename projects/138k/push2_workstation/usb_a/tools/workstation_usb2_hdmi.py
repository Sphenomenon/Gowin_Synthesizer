"""Compose the byte-checked D5 HDMI implementation and native USB2 hotplug diagnostic."""

from datetime import datetime
from pathlib import Path
import argparse
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ElementTree

from tools import workstation_hdmi_isolation as hdmi
from tools import workstation_usb2_hotplug as usb
from tools.stage_usb_firmware import sha
from tools.workstation_pinout import parse_locations


TOP = 'workstation_usb2_hdmi_top'
BASE = 'usb2_hdmi'
WRAPPER = 'rtl/workstation/workstation_usb2_hdmi_top.sv'
D5_MANIFEST = '4e7cd38aecdc6de4f1dc3c50bf2b5737c76010bc76bc1a8c9f251dfeb2de2df8'
D5_BITSTREAM = '82a2f3aa1cc6a6b4660cc94bb837a56234397f8c6e859e8d06e30962e5c2e8aa'
SCHEMA = 'usb2-hdmi-hotplug-cpu-observer-v1'
FIELDS = (
    ('reset_released', 'u_usb/usb_reset_n', 1, 0),
    ('generic_midi', 'u_usb/u_native_usb/input_owner/generic_midi', 1, 0),
    ('gw25k', 'u_usb/u_native_usb/input_owner/gw25k', 1, 0),
    ('flags', 'u_usb/flags', 12, 0),
    ('sof_count', 'u_usb/link_snapshot', 32, 5),
    ('telemetry', 'u_usb/telemetry', 224, 0),
    ('events', 'u_usb/event_snapshot', 114, 0),
    ('fault_address', 'u_usb/cpu_fault_address', 32, 0),
    ('canceled_requests', 'u_usb/canceled_requests', 32, 0),
    ('instruction_address', 'u_usb/u_native_usb/host/instruction_address', 32, 0),
)
LOGICAL_SIGNALS = tuple(name if width == 1 else f'{name}[{bit}]'
                        for _, name, width, low in FIELDS for bit in reversed(range(low, low + width)))


def probe_source(name):
    if name == 'u_usb/usb_reset_n':
        return 'u_usb/usb_release[3]'
    match = re.fullmatch(r'u_usb/flags\[(\d+)\]', name)
    if match:
        bit = int(match[1])
        if bit >= 8:
            return f'u_usb/cpu_fault[{bit - 8}]'
        return ('u_usb/link_snapshot[' + str(bit) + ']' if bit < 5 else
                ('u_usb/usb_lock_sync_q[1]', 'u_usb/audio_lock_sync_q[1]', 'u_usb/telemetry[1]')[bit - 5])
    match = re.fullmatch(r'u_usb/telemetry\[(\d+)\]', name)
    if match:
        bit = int(match[1])
        if bit < 32 and bit != 1:
            return int(bit in (0, 8))
        if 96 <= bit < 128:
            return f'u_usb/telemetry_0[{bit}]'
    if name in ('u_usb/u_native_usb/host/instruction_address[0]',
                'u_usb/u_native_usb/host/instruction_address[1]'):
        return 0
    return name


BIT_SOURCES = tuple(probe_source(name) for name in LOGICAL_SIGNALS)
SIGNALS = tuple(dict.fromkeys(source for source in BIT_SOURCES if isinstance(source, str)))
PHY_SCHEMA = 'usb2-hdmi-hotplug-phy-observer-v2'
PORT_SCHEMA = 'usb2-hdmi-hotplug-port-observer-v3'
USB_HOST = 'u_usb/u_native_usb/host/usb'
SUPERVISOR = USB_HOST + '/controller/phy/physical_link/supervisor'
PHY_FIELDS = (
    ('ulpi_heartbeat', SUPERVISOR + '/heartbeat_q', 5, 0),
    ('reference_heartbeat', SUPERVISOR + '/heartbeat_sync_q', 1, 0),
    ('heartbeat_reset_released', SUPERVISOR + '/heartbeat_release_q', 1, 1),
    ('clock_supervisor_state', USB_HOST + '/controller/phy/state_q_0', 3, 0),
    ('clock_failure', USB_HOST + '/clock_failure', 2, 0),
    ('reference_reset_released', USB_HOST + '/reference_release_q', 1, 1),
    ('reference_enabled', USB_HOST + '/enable_ref_q', 1, 1),
    ('link_reset_released', USB_HOST + '/controller/link_reset_n', 1, 0),
    ('source_reset_released', 'u_usb/ulpi_release_q', 1, 1),
    ('destination_reset_released', 'u_usb/cpu_release_q', 1, 1),
    ('link_source_released', 'u_usb/u_diagnostic_link/source_release', 1, 2),
    ('link_destination_released', 'u_usb/u_diagnostic_link/destination_release', 1, 2),
    ('link_request', 'u_usb/u_diagnostic_link/request_toggle', 1, 0),
    ('link_acknowledge', 'u_usb/u_diagnostic_link/acknowledge_toggle', 1, 0),
    ('init_state', USB_HOST + '/controller/state_q_0', 3, 0),
    ('init_stage', USB_HOST + '/init_stage', 5, 0),
    ('init_failure', USB_HOST + '/init_failure', 3, 0),
    ('init_retries', USB_HOST + '/controller/phy/physical_link/initialize_host/stage_retries_q', 8, 0),
    ('port_state', USB_HOST + '/port_state', 5, 0),
    ('port_failure', USB_HOST + '/port_failure', 4, 0),
    ('raw_phy_ready', 'u_usb/phy_ready', 1, 0),
    ('raw_direction', 'usb2_ulpi_dir_d', 1, 0),
    ('raw_next', 'usb2_ulpi_nxt_d', 1, 0),
    ('raw_stop', 'usb2_ulpi_stp_d', 1, 0),
    ('raw_data', 'usb2_ulpi_data_in', 8, 0),
    ('raw_line_state', USB_HOST + '/controller/line_state', 2, 0),
)


PORT_FIELDS = (
    ('state_history', USB_HOST + '/state_history_q', 19, 0),
    ('failure_history', USB_HOST + '/failure_history_q', 16, 0),
    ('attempts', USB_HOST + '/attempts_q', 16, 0),
    ('last_failure', USB_HOST + '/last_failure_q', 4, 0),
    ('last_failure_state', USB_HOST + '/last_failure_state_q', 5, 0),
    ('last_failure_function', USB_HOST + '/last_failure_function_q', 8, 0),
    ('received_peak', USB_HOST + '/received_peak_q', 32, 0),
    ('transmitted_peak', USB_HOST + '/transmitted_peak_q', 32, 0),
    ('sof_peak', USB_HOST + '/sof_peak_q', 32, 0),
)


def observer_layout(profile='owner'):
    if profile not in ('owner', 'phy', 'port'):
        raise ValueError('unknown USB2/HDMI observer profile: ' + profile)
    fields = FIELDS + (PHY_FIELDS if profile != 'owner' else ()) + (PORT_FIELDS if profile == 'port' else ())
    logical = tuple(name if width == 1 and low == 0 else f'{name}[{bit}]'
                    for _, name, width, low in fields for bit in reversed(range(low, low + width)))
    sources = tuple(probe_source(name) for name in logical)
    return dict(schema=PORT_SCHEMA if profile == 'port' else PHY_SCHEMA if profile == 'phy' else SCHEMA, fields=fields, sources=sources,
                signals=tuple(dict.fromkeys(source for source in sources if isinstance(source, str))))


def prefixed_constraints(text, prefix):
    def replace(match):
        objects = match[2]
        braces = objects.startswith('{')
        names = objects[1:-1] if braces else objects
        renamed = ' '.join(prefix + name for name in names.split())
        return match[1] + ('{' + renamed + '}' if braces else renamed)
    return re.sub(r'(\[get_(?:pins|cells|nets|regs)\s+)(\{[^}]*\}|[^\]\s]+)', replace, text)


def validate_d5(baseline):
    baseline = Path(baseline).resolve()
    if sha(baseline / 'inputs.json') != D5_MANIFEST:
        raise ValueError('HDMI baseline is not the accepted C11028D5 manifest')
    manifest = json.loads((baseline / 'inputs.json').read_text())
    if manifest['user_code'] != '0xC11028D5' or sha(baseline / 'impl/pnr/ao_0.fs') != D5_BITSTREAM:
        raise ValueError('HDMI D5 rollback identity changed')
    for name, expected in manifest['input_sha256'].items():
        path = baseline / name
        if not path.resolve().is_relative_to(baseline) or sha(path) != expected:
            raise ValueError('HDMI D5 input changed: ' + name)
    return manifest


def source_composition(output, display, native):
    selected, modules, omitted = [], {}, []
    paths = [*('hdmi/' + name for name in display['enabled_inputs']),
             *('usb/' + name for name in native['source_paths'])]
    for name in paths:
        path = output / name
        names = re.findall(r'^\s*module\s+(\w+)', path.read_text(), re.MULTILINE)
        collisions = {modules[module] for module in names if module in modules}
        if collisions:
            if len(collisions) != 1 or sha(output / next(iter(collisions))) != sha(path):
                raise ValueError('nonidentical RTL module collision: ' + name)
            omitted.append(dict(path=name, identical_to=next(iter(collisions)), sha256=sha(path)))
            continue
        modules.update({module: name for module in names})
        selected.append(name)
    return [*selected, WRAPPER], omitted


def constraints(output):
    display = (output / 'hdmi/display.cst').read_text()
    display = display.replace('"u_display/', '"u_hdmi/u_display/')
    native = (output / 'usb/usb2_hotplug.cst').read_text()
    locations = parse_locations(display)
    lines = display.splitlines()
    for line in native.splitlines():
        match = re.match(r'IO_LOC\s+"([^"]+)"', line)
        if match and match[1] in locations:
            if parse_locations(line)[match[1]] != locations[match[1]]:
                raise ValueError('incompatible shared board port: ' + match[1])
            continue
        if line not in lines:
            lines.append(line)
    cst = '\n'.join(lines) + '\n'
    if parse_locations(cst) != {**locations, **parse_locations(native)}:
        raise ValueError('composed board locations changed')
    sdc = []
    for name, prefix in (('hdmi/display.sdc', 'u_hdmi/'), ('usb/usb2_hotplug.sdc', 'u_usb/')):
        for line in prefixed_constraints((output / name).read_text(), prefix).splitlines():
            if line.startswith('report_timing ') or line in sdc:
                continue
            sdc.append(line)
    sdc += [f'report_timing -{kind} -max_paths 2000 -max_common_paths 1'
            for kind in ('setup', 'hold', 'recovery', 'removal')]
    return cst, '\n'.join(sdc) + '\n'


def observer_trigger_signal(profile, trigger):
    if trigger == 'reset':
        return SIGNALS[0]
    if trigger == 'clock-failure' and profile == 'phy':
        return USB_HOST + '/clock_failure[0]'
    raise ValueError('clock-failure trigger requires the explicit phy observer')


def gao_configuration(user_code, observer_profile='owner', observer_trigger='reset'):
    layout = observer_layout(observer_profile)
    document = ElementTree.fromstring(hdmi.gao_configuration(user_code))
    core = document.find('AoCore')
    core.set('module_name', TOP)
    core.set('sample_clock', 'u_usb/usb_clk')
    signals = core.find('SignalList')
    signals.clear()
    for name in layout['signals']:
        ElementTree.SubElement(signals, 'Signal', capture_enable='true').text = name
    core.find('Triggers/Trigger/SignalList/Signal').text = observer_trigger_signal(observer_profile, observer_trigger)
    return ElementTree.tostring(document, encoding='unicode') + '\n'


def prepare(root, output, netlist_directory, user_code, baseline, riscv_prefix=None, allow_high_speed=True,
            observer_profile='owner', observer_trigger='reset'):
    root, output = Path(root).resolve(), Path(output).resolve()
    layout = observer_layout(observer_profile)
    trigger_signal = observer_trigger_signal(observer_profile, observer_trigger)
    accepted = validate_d5(baseline)
    if not re.fullmatch(r'[0-9A-Fa-f]{8}', user_code or '') or user_code.upper() == 'C11028D5':
        raise ValueError('USB2/HDMI integration requires a new eight-hex UserCode')
    if output.exists():
        raise FileExistsError('USB2/HDMI output already exists: ' + str(output))
    user_code = user_code.upper()
    inputs = {name: sha(root / name) for name in
              (WRAPPER, 'tools/workstation_usb2_hdmi.py', 'build.py')}
    _, display = hdmi.prepare(root, netlist_directory, output / 'hdmi', user_code)
    for name in (*accepted['enabled_inputs'], 'display.cst', 'display.sdc'):
        if name not in display['input_sha256'] or sha(output / 'hdmi' / name) != accepted['input_sha256'][name]:
            raise ValueError('display implementation differs from accepted D5: ' + name)
    if list(display['enabled_inputs']) != accepted['enabled_inputs']:
        raise ValueError('display source selection differs from accepted D5')
    _, native = usb.prepare(root, output / 'usb', netlist_directory, user_code, riscv_prefix, allow_high_speed)
    destination = output / WRAPPER
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / WRAPPER, destination)
    sources, omitted = source_composition(output, display, native)
    shutil.copyfile(output / 'usb/usb2_cpu.hex', output / 'usb2_cpu.hex')
    shutil.copyfile(output / 'hdmi/hdmi_isolation_config.vh', output / 'hdmi_isolation_config.vh')
    address_map = output / 'src/memory/ddr_address_map.vh'
    address_map.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(output / 'hdmi/src/memory/ddr_address_map.vh', address_map)
    cst, sdc = constraints(output)
    (output / 'integration.cst').write_text(cst)
    (output / 'integration.sdc').write_text(sdc)
    (output / 'integration.gao').write_text(gao_configuration(user_code, observer_profile, observer_trigger))
    common = ['set root [file normalize [file dirname [info script]]]', 'cd $root',
              f'set_device {native["device"]} -device_version C',
              'set_option -synthesis_tool gowinsynthesis', f'set_option -top_module {TOP}',
              f'set_option -output_base_name {BASE}', 'set_option -verilog_std sysv2017',
              'set_option -use_cpu_as_gpio 1', 'set_option -use_mspi_as_gpio 1',
              'set_option -include_path $root']
    common += [f'add_file -type verilog [file join $root {name}]' for name in sources]
    common += [f'add_file -type {kind} [file join $root integration.{kind}]' for kind in ('cst', 'sdc', 'gao')]
    common += [f'set_option -user_code {user_code}', 'set_option -bit_security 0', 'set_option -secure_mode 0',
               'set_option -gen_text_timing_rpt 1', 'set_option -gen_sdf 1',
               'set_option -gen_verilog_sim_netlist 1', 'set_option -timing_driven 1',
               'set_option -correct_hold_violation 1', 'set_option -place_option 2',
               'set_option -route_option 1', 'set_option -replicate_resources 0']
    for name, flow in (('run.tcl', 'all'), ('synthesis.tcl', 'syn')):
        (output / name).write_text('\n'.join([*common, 'run ' + flow]) + '\n')
    for name, expected in inputs.items():
        if sha(root / name) != expected:
            raise ValueError('integration source changed during preparation: ' + name)
    manifest = dict(schema=1, identity='custom138k-usb2-hdmi-' + user_code, user_code='0x' + user_code,
                    top_module=TOP, source_policy='byte_identical_accepted_D5_display_plus_native_USB2_hotplug',
                    hdmi_baseline_manifest_sha256=D5_MANIFEST, rollback_bitstream_sha256=D5_BITSTREAM,
                    hdmi_implementation_byte_identical=True, source_snapshot_sha256=inputs,
                    child_manifests_sha256={name: sha(output / name) for name in
                                            ('hdmi/inputs.json', 'usb/hotplug_inputs.json')},
                    enabled_inputs=sources, source_paths=sources, identical_duplicate_sources_omitted=omitted,
                    observer_profile=observer_profile, signal_schema=layout['schema'], signals=layout['signals'],
                    observer_trigger=observer_trigger, observer_trigger_signal=trigger_signal,
                    fields=layout['fields'], logical_bit_sources=layout['sources'],
                    raw_phy_sample_policy='CPU-clock samples of existing PHY/reference nets; not a runtime CDC contract',
                    observer_alias_policy='checked_E2_synthesis_commands_alias_and_existing_reset_bit; constants reconstructed',
                    sample_clock='u_usb/usb_clk', storage_depth=1024, gao_file='integration.gao',
                    gao_configuration_id=user_code[-4:], high_speed_allowed=bool(allow_high_speed),
                    firmware=native['firmware'], electrical_check=native['electrical_check'],
                    full_workstation=False, hardware_tested=False, sram_programmed=False,
                    flash_programmed=False, validation_stage='USB2_HDMI_prepared',
                    input_sha256={str(path.relative_to(output)): sha(path) for path in output.rglob('*') if path.is_file()})
    (output / 'inputs.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return output, manifest


def build(output):
    output = Path(output).resolve()
    manifest = json.loads((output / 'inputs.json').read_text())
    for name, expected in manifest['input_sha256'].items():
        if sha(output / name) != expected:
            raise ValueError('integration input changed: ' + name)
    started = datetime.now().astimezone()
    command = ['gw_sh', str(output / 'run.tcl')]
    with (output / 'build.log').open('x') as log:
        result = subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT)
    finished = datetime.now().astimezone()
    outputs = (f'impl/gwsynthesis/{BASE}.vg', 'impl/pnr/ao_0.fs', f'impl/pnr/{BASE}.vo',
               f'impl/pnr/{BASE}.sdf', f'impl/pnr/{BASE}.rpt.txt', f'impl/pnr/{BASE}_tr_content.html')
    missing = [name for name in outputs if not (output / name).is_file()]
    record = dict(identity=manifest['identity'], command=command, returncode=result.returncode or int(bool(missing)),
                  tool_returncode=result.returncode, missing_outputs=missing,
                  started_at=started.isoformat(), finished_at=finished.isoformat(),
                  elapsed_seconds=(finished - started).total_seconds(), hardware_tested=False,
                  output_sha256={name: sha(output / name) for name in outputs if (output / name).is_file()})
    (output / 'build_result.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    arguments = parser.parse_args()
    result = build(arguments.output)
    print(json.dumps(result, indent=2))
    raise SystemExit(result['returncode'])
