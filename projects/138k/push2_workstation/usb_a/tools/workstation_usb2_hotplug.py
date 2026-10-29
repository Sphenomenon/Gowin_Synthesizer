"""Board-level hotplug diagnostic assembled from the existing native USB2 component."""

from pathlib import Path
from hashlib import sha256
from fractions import Fraction
import argparse
import json
import re
import shutil
import xml.etree.ElementTree as ElementTree

from tools.stage_usb_firmware import sha
from tools.workstation_baselines import load_baseline
from tools.workstation_custom_board_implementation import ulpi_bypass_constraints
from tools.workstation_custom_clocks import clock_bundle, shared_cdc_bundle
from tools.workstation_custom_input_cdc import input_cdc_bundle
from tools.workstation_custom_input_cdc import audit_input_fifo
from tools.workstation_custom_timing import INPUTS, audio_pll, audit_resets, constraints as native_timing_constraints
from tools.workstation_custom_usb2_cdc import cdc_bundle, audit_usb2_cdc
from tools.workstation_pinout import prepare as prepare_pinout, parse_locations, render_constraints
from tools.workstation_usb2_soc import prepare as prepare_component
from tools.workstation_timing_constraints import gray_write_alias_constraints
from tools.workstation_resource_timing import event_fifo
from tools.workstation_synthesis_netlist import SynthesisNetlist
from tools.audit_workstation_timing import audit as audit_timing
from tools.workstation_ulpi_selftest import clock_pull_constraints


TOP = 'workstation_usb2_hotplug_top'
BASE = 'usb2_hotplug'
LIVE_SOURCES = ('rtl/workstation/workstation_usb2_hotplug_top.sv',
                'rtl/workstation/workstation_usb2_diagnostic_uart.sv')
CLOCK_SOURCES = ('src/platform/reset_release.v', 'src/ae350/gw138k_cpu_pll_cell.v',
                 'src/migration/gw138k_audio_clock.v', 'vendor/sipeed_dvi/video_pll_init.v')
CLOCKS = ('clk_50m', 'ulpi_60m', 'usb_48m', 'audio_76m8')
FIFO_SOURCE = 'src/usb_host/gw138k_usb_event_fifo.v'
COMPONENT_FIFO = 'support/workstation/' + FIFO_SOURCE
PORTS = ('clk_50m', 'debug_uart_tx', 'pc_uart_rx_i',
         *(f'usb2_ulpi_data[{index}]' for index in range(8)),
         'usb2_ulpi_clk', 'usb2_ulpi_dir', 'usb2_ulpi_nxt', 'usb2_ulpi_stp')
RECIPE_INPUTS = ('build.py', 'tools/workstation_usb2_hotplug.py',
                 'tools/workstation_ulpi_selftest.py',
                 'tools/workstation_custom_board_implementation.py', 'tools/workstation_custom_clocks.py',
                 'tools/workstation_custom_timing.py', 'tools/workstation_custom_usb2_cdc.py',
                 'tools/workstation_custom_input_cdc.py', 'tools/workstation_timing_constraints.py',
                 'tools/workstation_synthesis_netlist.py', 'tools/audit_workstation_timing.py',
                 'tools/audit_clk50_timing.py', 'tools/workstation_resource_timing.py',
                 'boards/custom_138k/clocks.json',
                 'boards/custom_138k/usb2_cdc.json', 'boards/custom_138k/input_cdc.json')


def board_constraints(plan, clock_pull=None):
    selected = []
    for line in render_constraints(plan).splitlines():
        match = re.match(r'IO_(?:LOC|PORT)\s+"([^"]+)"', line)
        if match and match[1] in PORTS:
            selected.append(line)
    payload = ('\n'.join(selected) + '\n').encode()
    if parse_locations(payload.decode()) != {port: plan['ports'][port]['balls'] for port in PORTS}:
        raise ValueError('USB2 diagnostic port subset differs from the resolved board')
    physical, evidence = ulpi_bypass_constraints(payload, plan)
    return clock_pull_constraints(physical, clock_pull), evidence


def mailbox_constraints(prefix, release_aliases=None):
    release_aliases = release_aliases or {}
    lines = []
    for source, first, second in (('request_toggle', 'req_meta', 'req_sync'),
                                  ('acknowledge_toggle', 'ack_meta', 'ack_sync')):
        lines += [f'set_false_path -from [get_pins {{{prefix}/{source}*_s*/Q}}] -to [get_pins {{{prefix}/{first}*_s*/D}}]',
                  f'set_max_delay -from [get_pins {{{prefix}/{first}*_s*/Q}}] -to [get_pins {{{prefix}/{second}*_s*/D}}] 2.000']
    lines += [f'set_max_delay -from [get_pins {{{prefix}/held_data_*_s*/Q}}] -to [get_pins {{{prefix}/destination_data_*_s*/D}}] 16.000',
              f'set_false_path -hold -from [get_pins {{{prefix}/held_data_*_s*/Q}}] -to [get_pins {{{prefix}/destination_data_*_s*/D}}]']
    for stem in ('source_release', 'destination_release'):
        lines.append(f'set_false_path -to [get_pins {{{prefix}/{stem}_*_s*/CLEAR}}]')
        for stage in range(2):
            origin = f'{prefix}/{stem}_{stage}_s*/Q'
            target = f'{prefix}/{stem}_{stage + 1}_s*/D'
            if stem in release_aliases:
                origin = f'{release_aliases[stem]}_{stage}_s*/Q'
                if stage == 0:
                    target = f'{release_aliases[stem]}_1_s*/D'
            lines.append(f'set_max_delay -from [get_pins {{{origin}}}] -to [get_pins {{{target}}}] 2.000')
    return '\n'.join(lines) + '\n'


def timing_constraints(root, output):
    clocks = clock_bundle(root)
    selected = []
    for line in clocks['sdc'].splitlines():
        match = re.search(r'-name (\S+)', line)
        if match and match[1] in CLOCKS:
            selected.append(line)
    if len(selected) != len(CLOCKS):
        raise ValueError('USB2 diagnostic clock subset changed')
    shared = shared_cdc_bundle(output / 'support')
    for line in shared['sdc'].splitlines():
        selectors = re.findall(r'\[(?:get_regs|get_pins) \{([^}]+)\}\]', line)
        if selectors and all(name.startswith(('u_native_usb/', 'u_audio_clock/', 'u_usb_pll/', 'usb_release'))
                             for group in selectors for name in group.split()):
            selected.append(line)
    selected += [line for line in native_timing_constraints().splitlines() if 'u_memory/' not in line]
    text = '\n'.join(selected) + '\n' + cdc_bundle(root)['sdc'] + input_cdc_bundle(root)['sdc']
    for prefix in ('u_diagnostic_snapshot', 'u_diagnostic_link'):
        aliases = dict(source_release='u_native_usb/host/usb/bridge/ulpi_release_q',
                       destination_release='u_native_usb/host/cpu_release_q') if prefix == 'u_diagnostic_link' else {}
        text += mailbox_constraints(prefix, aliases)
    for stem in ('audio_lock_sync_q', 'usb_lock_sync_q', 'link_release_q'):
        text += f'set_false_path -to [get_pins {{{stem}_*_s*/CLEAR}}]\n'
        text += f'set_max_delay -from [get_pins {{{stem}_0_s*/Q}}] -to [get_pins {{{stem}_1_s*/D}}] 2.000\n'
        if stem != 'link_release_q':
            text += f'set_false_path -to [get_pins {{{stem}_0_s*/D}}]\n'
    text += ('set_false_path -to [get_pins {link_level_meta_q_*_s*/D}]\n'
             'set_max_delay -from [get_pins {link_level_meta_q_*_s*/Q}] -to [get_pins {link_level_sync_q_*_s*/D}] 2.000\n')
    return text


def prepare(root, output, netlist_directory, user_code, riscv_prefix=None, allow_high_speed=True,
            ulpi_clock_pull=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    if netlist_directory is None or not user_code or not re.fullmatch(r'[0-9A-Fa-f]{8}', user_code):
        raise ValueError('workstation-hotplug requires --netlist-dir and an eight-hex --user-code')
    if output.exists():
        raise FileExistsError('USB2 hotplug output already exists: ' + str(output))
    if output.is_relative_to(Path(netlist_directory).resolve()):
        raise ValueError('USB2 diagnostic output must not modify netlist inputs')
    inputs = {name: sha(root / name) for name in (*LIVE_SOURCES, *RECIPE_INPUTS)}
    baseline = load_baseline(root, 'resource_rework_route0')
    payloads = {name: baseline.read_bytes(name) for name in (*CLOCK_SOURCES, 'constraints/tang_mega_138k.sdc')}
    payloads['constraints/tang_mega_138k.sdc'] += gray_write_alias_constraints().encode()
    payloads[FIFO_SOURCE] = event_fifo(baseline.read_bytes(FIFO_SOURCE).decode()).encode()
    audio_source = 'src/migration/gw138k_audio_clock.v'
    if sha256(payloads[audio_source]).hexdigest() != INPUTS[audio_source]:
        raise ValueError('USB2 diagnostic audio clock adaptation input changed')
    payloads[audio_source] = audio_pll(payloads[audio_source].decode()).encode()
    _, plan = prepare_pinout(root, netlist_directory, output / 'pinout')
    constraints, electrical = board_constraints(plan, ulpi_clock_pull)
    _, component = prepare_component(root, output / 'component', riscv_prefix,
                                     firmware_profile='workstation', allow_high_speed=allow_high_speed,
                                     component='workstation-input')
    sources = ['support/' + FIFO_SOURCE if name == COMPONENT_FIFO else 'component/' + name
               for name in component['source_paths']]
    for name in LIVE_SOURCES:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
        sources.append(name)
    for name, payload in payloads.items():
        target = output / 'support' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        if name in CLOCK_SOURCES:
            sources.append('support/' + name)
    shutil.copyfile(output / 'component/usb2_cpu.hex', output / 'usb2_cpu.hex')
    (output / 'usb2_hotplug.cst').write_bytes(constraints)
    (output / 'usb2_hotplug.sdc').write_text(timing_constraints(root, output))
    project = ElementTree.Element('Project')
    ElementTree.SubElement(project, 'Template').text = 'FPGA'
    ElementTree.SubElement(project, 'Version').text = '5'
    ElementTree.SubElement(project, 'Device', name='GW5AST-138C', pn=plan['device']).text = 'gw5ast138c-006'
    files = ElementTree.SubElement(project, 'FileList')
    for name in sources:
        ElementTree.SubElement(files, 'File', path=name, type='file.verilog', enable='1')
    for suffix in ('cst', 'sdc'):
        ElementTree.SubElement(files, 'File', path='usb2_hotplug.' + suffix, type='file.' + suffix, enable='1')
    ElementTree.ElementTree(project).write(output / 'usb2_hotplug.gprj', encoding='UTF-8', xml_declaration=True)
    options = ('cd [file dirname [info script]]\nopen_project usb2_hotplug.gprj\n'
               f'set_option -top_module {TOP}\nset_option -output_base_name {BASE}\n'
               'set_option -verilog_std sysv2017\nset_option -timing_driven 1\n'
               'set_option -use_mspi_as_gpio 1\nset_option -use_cpu_as_gpio 1\n'
               f'set_option -user_code {user_code.upper()}\n'
               'set_option -bit_security 0\nset_option -secure_mode 0\n'
               'set_option -bit_encrypt 0\nset_option -bit_compress 0\n'
               'set_option -gen_text_timing_rpt 1\nset_option -gen_sdf 1\n'
               'set_option -gen_verilog_sim_netlist 1\nset_option -correct_hold_violation 1\n')
    (output / 'synthesis.tcl').write_text(options + 'run syn\n')
    (output / 'implementation.tcl').write_text(options + 'run syn\nrun pnr\n')
    for name, expected in inputs.items():
        if sha(root / name) != expected:
            raise ValueError('USB2 hotplug source changed during preparation: ' + name)
    for name, expected in component['input_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('USB2 component source changed during diagnostic preparation: ' + name)
    for name in LIVE_SOURCES:
        if sha(output / name) != inputs[name]:
            raise ValueError('USB2 hotplug staged source changed: ' + name)
    staged = {str(path.relative_to(output)): sha(path) for path in output.rglob('*') if path.is_file()}
    metadata = dict(schema=1, identity='custom138k-usb2-hotplug-' + user_code.upper(),
                    user_code='0x' + user_code.upper(), top_module=TOP, device=plan['device'],
                    source_policy='existing_native_input_component_plus_board_diagnostic_wrapper',
                    validation_stage='standalone_diagnostic_prepared', high_speed_allowed=bool(allow_high_speed),
                    firmware_profile='workstation', firmware=component['firmware'], source_paths=sources,
                    clocks_hz={name: next(entry['frequency_hz'] for entry in
                              (*clock_bundle(root)['plan']['primary'], *clock_bundle(root)['plan']['generated'])
                              if entry['name'] == name) for name in CLOCKS},
                    ports=list(PORTS), input_sha256=inputs, staged_input_sha256=staged,
                    component_inputs_sha256=sha(output / 'component/component_inputs.json'),
                    clock_baseline=baseline.evidence(), audio_clock_transform='checked_existing_audio_pll',
                    event_fifo_transform='existing_native_resource_timing_event_fifo',
                    electrical_check=plan['electrical_check'], ulpi_io_type_adaptation=electrical,
                    ulpi_clock_pull=ulpi_clock_pull,
                    diagnostic_sink='always_ready_18bit_event_counter_not_DSP',
                    diagnostic_feedback='audio_domain_event_counter_in_held_note_region_other_bits_zero',
                    omitted_subsystems=['DSP', 'DDR', 'CNN', 'HDMI', 'BLE', 'TF', 'LCD', 'AE350'],
                    integration_criteria='rerun_native_mixed_hotplug_and_full_workstation_before_integration',
                    synthesis_allowed=True, place_route_allowed=True, external_ulpi_timing_complete=False,
                    workstation_integrated=False, hardware_tested=False, deployment_allowed=False, release_ready=False)
    (output / 'hotplug_inputs.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    return output, metadata


def audit(root, output, *, primary_nets=None, bitstream_path=None):
    root, output = Path(root), Path(output)
    metadata = json.loads((output / 'hotplug_inputs.json').read_text())
    if (metadata.get('top_module') != TOP or not re.fullmatch(r'custom138k-usb2-hotplug-[0-9A-F]{8}', metadata.get('identity', '')) or
            metadata.get('source_policy') != 'existing_native_input_component_plus_board_diagnostic_wrapper'):
        raise ValueError('not an explicit USB2 hotplug diagnostic')
    for name, expected in metadata['staged_input_sha256'].items():
        path = output / name
        if not path.resolve().is_relative_to(output.resolve()) or sha(path) != expected:
            raise ValueError('USB2 diagnostic staged input changed: ' + name)
    component = json.loads((output / 'component/component_inputs.json').read_text())
    expected_sources = [*('support/' + FIFO_SOURCE if name == COMPONENT_FIFO else 'component/' + name
                         for name in component['source_paths']), *LIVE_SOURCES,
                        *('support/' + name for name in CLOCK_SOURCES)]
    if metadata['source_paths'] != expected_sources or component.get('component') != 'workstation-input':
        raise ValueError('USB2 diagnostic composition changed')
    plan = json.loads((output / 'pinout/pinout.json').read_text())
    if board_constraints(plan, metadata.get('ulpi_clock_pull'))[0] != (output / 'usb2_hotplug.cst').read_bytes():
        raise ValueError('USB2 diagnostic board constraints changed')
    if timing_constraints(root, output) != (output / 'usb2_hotplug.sdc').read_text():
        raise ValueError('USB2 diagnostic timing constraints changed')
    text = (output / f'impl/gwsynthesis/{BASE}.vg').read_text()
    netlist = SynthesisNetlist(text, TOP)
    clock_plan = clock_bundle(root)['plan']
    primary_nets = {} if primary_nets is None else primary_nets
    primary = {entry['name'] for entry in clock_plan['primary'] if entry['name'] in CLOCKS}
    if set(primary_nets) - primary or any(not isinstance(net, str) or not net for net in primary_nets.values()):
        raise ValueError('USB2 diagnostic primary-clock binding is invalid')
    clocks = {entry['name']: dict(net=primary_nets.get(entry['name'], entry['port']), frequency_hz=entry['frequency_hz'])
              for entry in clock_plan['primary'] if entry['name'] in CLOCKS}
    for entry in clock_plan['generated']:
        if entry['name'] not in CLOCKS:
            continue
        instance, pin = entry['pin'].rsplit('/', 1)
        cell = netlist.cells[instance]
        parameters = cell['parameters']
        if (cell['kind'] != 'PLL' or pin != 'CLKOUT0' or
                netlist.pin(instance, 'CLKIN') != clocks[entry['source']]['net'] or
                parameters['IDIV_SEL'] != '1' or parameters['FBDIV_SEL'] != '1' or
                parameters['CLKOUT0_EN'] != '"TRUE"' or parameters['CLKFB_SEL'] != '"INTERNAL"' or
                any(parameters[key] != '"FALSE"' for key in
                    ('DYN_IDIV_SEL', 'DYN_FBDIV_SEL', 'DYN_MDIV_SEL', 'DYN_ODIV0_SEL'))):
            raise ValueError('USB2 diagnostic PLL wiring or static mode changed')
        multiplier = Fraction(int(parameters['MDIV_SEL'])) + Fraction(int(parameters['MDIV_FRAC_SEL']), 8)
        divisor = Fraction(int(parameters['ODIV0_SEL'])) + Fraction(int(parameters['ODIV0_FRAC_SEL']), 8)
        frequency = clocks[entry['source']]['frequency_hz'] * multiplier / divisor
        if frequency != entry['frequency_hz']:
            raise ValueError('USB2 diagnostic PLL frequency differs from its constraints')
        clocks[entry['name']] = dict(net=netlist.pin(instance, pin), frequency_hz=int(frequency))
    clock_evidence = dict(clocks=clocks)
    bridge = audit_usb2_cdc(root, text, clock_evidence, top=TOP)
    fifo = audit_input_fifo(root, text, clock_evidence, top=TOP)
    resets = audit_resets(text, clock_evidence, top=TOP, feedback_source_clock='audio_76m8')
    aliases = {}
    for stem, original in (('source_release', 'u_native_usb/host/usb/bridge/ulpi_release_q'),
                           ('destination_release', 'u_native_usb/host/cpu_release_q')):
        third = 'u_diagnostic_link/' + stem + '_2_s0'
        second = original + '_1_s0'
        if (netlist.pin(third, 'D') != netlist.pin(second, 'Q') or
                netlist.pin(third, 'CLK') != netlist.pin(second, 'CLK') or
                netlist.pin(third, 'CLEAR') != netlist.pin(second, 'CLEAR')):
            raise ValueError('USB2 diagnostic reset-prefix synthesis alias changed: ' + stem)
        aliases[stem] = dict(shared_first_two_stages=original, third_stage=third)
    timing = audit_timing(output, report_path=output / f'impl/pnr/{BASE}_tr_content.html',
                          targets={name: clocks[name]['frequency_hz'] / 1000000 for name in CLOCKS})
    bitstream = output / f'impl/pnr/{BASE}.fs' if bitstream_path is None else Path(bitstream_path)
    if not bitstream.resolve().is_relative_to(output.resolve()):
        raise ValueError('USB2 diagnostic bitstream is outside its candidate')
    result = dict(identity=metadata['identity'], stage='standalone_diagnostic_routed_audit',
                  input_sha256=sha(output / 'hotplug_inputs.json'), clock_audit=clock_evidence,
                  bridge_cdc=bridge, event_fifo_cdc=fifo, native_reset_audit=resets,
                  diagnostic_reset_aliases=aliases, timing=timing,
                  bitstream_sha256=sha(bitstream), timing_closed=timing['timing_closed'],
                  full_workstation=False, hardware_tested=False)
    (output / 'hotplug_audit.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    arguments = parser.parse_args()
    result = audit(Path(__file__).resolve().parents[1], arguments.output)
    print(json.dumps(dict(identity=result['identity'], timing_closed=result['timing_closed'],
                          worst_ns=result['timing']['global_worst_ns'],
                          bitstream_sha256=result['bitstream_sha256']), indent=2))
    raise SystemExit(0 if result['timing_closed'] else 1)
