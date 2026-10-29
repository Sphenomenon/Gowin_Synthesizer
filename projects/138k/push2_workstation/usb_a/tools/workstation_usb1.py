"""Explicit USB1 FS candidates for the 138K host and the complete 25K keyboard."""

from datetime import datetime
from pathlib import Path
import fcntl
import fnmatch
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ElementTree

from tools.stage_usb_firmware import sha, stage_usb_firmware, verify_usb2_cpu_vendor
from tools.workstation_baselines import load_baseline
from tools.workstation_pinout import load_sources, parse_locations
from tools.workstation_synthesis_netlist import SynthesisNetlist


HOST_SOURCES = (
    'rtl/usb1/workstation_usb1_clock.sv', 'rtl/usb1/workstation_usb1_phy.sv',
    'rtl/usb1/workstation_usb1_host.sv', 'rtl/usb1/workstation_usb1_diagnostics.sv',
    'rtl/usb1/workstation_usb1_identify_top.sv', 'rtl/usb2/workstation_usb2_cpu_bus.sv',
    *(f'vendor/usb_host_fs_8fc3/src/{name}' for name in
      ('VexRiscv.v', 'simpleuart.v', 'usb_fs_phy.v', 'usbh_core.sv', 'usbh_sie.sv',
       'usbh_fifo.sv', 'usbh_crc5.sv', 'usbh_crc16.sv', 'usbh_host_defs.v')),
)
HELPER_SHA = '3fc6bef9a7086f0920bfa47265b1766854a53f6ca1c0f75084eaf6b6ef4d6258'
HOST_RESET_ASYNC = 'set_false_path -to [get_pins {clock/release_q*_s*/CLEAR}]'


def host_constraints(root, netlist_directory):
    profile = json.loads((root / 'boards/custom_138k/pinout.json').read_text())
    netlists, evidence = load_sources(profile, netlist_directory)
    carrier = netlists['carrier']
    for net, nodes in (
        ('USB_FS_D+_BANK3_H13', ('J1.67', 'R33.2', 'R35.2', 'R37(NC).2')),
        ('USB_FS_D-_BANK3_G13', ('J1.68', 'R34.2', 'R36.2')),
        ('$1N24', ('R33.1', 'USB1.A6', 'USB1.B6')),
        ('$1N23', ('R34.1', 'USB1.A7', 'USB1.B7')),
        ('$1N12', ('R1.2', 'USB1.A5')),
        ('$1N11', ('R2.1', 'USB1.B5')),
        ('GND', ('R1.1', 'R2.2', 'R35.1', 'R36.1')),
        ('+3V3', ('R37(NC).1',)),
        ('+5V', ('F1.2',)),
        ('VBUS1', ('F1.1', 'USB1.A9B4', 'USB1.B9A4')),
    ):
        if not set(nodes).issubset(carrier.nets.get(net, ())):
            raise ValueError('USB1 carrier connectivity drifted: ' + net)
    baseline = load_baseline(root, 'accepted_full83')
    original = baseline.read_bytes('constraints/tang_mega_138k.cst').decode('utf-8-sig')
    ports = {'clk_50m': ['V22'], 'debug_uart_tx': ['U15'], 'usb1_dp': ['H13'], 'usb1_dn': ['G13']}
    locations = parse_locations(original)
    if any(locations.get(port) != balls for port, balls in ports.items()):
        raise ValueError('USB1/core fixed constraints drifted')
    selected = [line for line in original.splitlines()
                if re.match(r'IO_(?:LOC|PORT) "(' + '|'.join(ports) + ')"', line)]
    return '\n'.join(selected) + '\n', dict(
        netlists=evidence, baseline=baseline.evidence(), ports=ports,
        usb1_connector='carrier USB1 Type-C, not USB2 USB3300 and not HDMI USB3',
        host_data_pulldowns='R35/R36 15K to GND in locked netlist; actual assembly not measured',
        electrical_gaps=['CC1/CC2 use R1/R2 5.1K to GND (sink Rd), not a verified Type-C host Rp',
                         'VBUS1 is connected to board +5V through F1; no FPGA-controlled VBUS switch',
                         'R37(NC) 1.5K D+ pull-up must remain unpopulated in host role',
                         '25K USB1 requires its physical 1.5K D+ pull-up; FPGA weak pull-up is not a substitute'],
        hardware_measured=False, electrical_accepted=False)


def prepare(root, output, user_code, board='138k', netlist_directory=None, riscv_prefix=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    repository = root.parents[3]
    peer = repository / 'projects/25k/example/MIDI_KEYBOARD'
    if board not in ('138k', '25k') or not re.fullmatch(r'[0-9A-Fa-f]{8}', user_code or ''):
        raise ValueError('USB1 needs a board and a new eight-hex UserCode')
    if output.exists():
        raise FileExistsError('USB1 candidate already exists: ' + str(output))
    if output.is_relative_to(root / 'rtl') or output.is_relative_to(peer / 'rtl'):
        raise ValueError('USB1 output must not be written into RTL inputs')
    verify_usb2_cpu_vendor(root)
    helper = peer.parent / 'USB1_FS/clock/pll_init.v'
    if board == '25k' and sha(helper) != HELPER_SHA:
        raise ValueError('locked official PLL_INIT helper drifted')
    if board == '138k':
        if netlist_directory is None:
            raise ValueError('138K USB1 needs the explicit locked carrier netlist directory')
        constraints, pin_evidence = host_constraints(root, netlist_directory)
        sources = [root / name for name in HOST_SOURCES if not name.endswith('.vh')]
        top, device, family = 'workstation_usb1_identify_top', 'GW5AST-LV138PG484AC2/I1', 'GW5AST-138C'
        clock_port, clock_pin, phy_prefix = 'clk_50m', 'clock/pll/PLL_inst/CLKOUT0', 'host/phy/phy*'
        timing = 'create_clock -name clk_50m -period 20.000 [get_ports {clk_50m}]\n'
    else:
        selected = [name for name in (peer / 'sources.f').read_text().splitlines() if name.strip()]
        sources = [peer / name for name in selected if not name.endswith(
            ('midi_usb2_link.v', 'midi_usb_hs_phy.v', 'midi_ulpi_wrapper.v', 'midi_usb2_boot.v'))]
        sources += [root / 'rtl/usb1/workstation_usb1_phy.sv', root / 'vendor/usb_host_fs_8fc3/src/usb_fs_phy.v']
        constraints = '\n'.join(line for line in (peer / 'constraints/midi_keyboard.cst').read_text().splitlines()
                                if not re.search(r'"(?:ulpi_|clk_ulpi60)', line)) + '\n'
        constraints += ('IO_LOC "usb1_dp" L6;\nIO_LOC "usb1_dm" K6;\n'
                        'IO_PORT "usb1_dp" IO_TYPE=LVCMOS33 PULL_MODE=NONE DRIVE=8;\n'
                        'IO_PORT "usb1_dm" IO_TYPE=LVCMOS33 PULL_MODE=NONE DRIVE=8;\n')
        pins = parse_locations(constraints)
        if len({ball for balls in pins.values() for ball in balls}) != len(pins):
            raise ValueError('25K USB1 pin collision')
        pin_evidence = dict(ports=pins, reference='projects/25k/example/USB1_FS/constraints/usb1_device.cst')
        top, device, family = 'midi_keyboard_top', 'GW5A-LV25MG121NC1/I0', 'GW5A-25A'
        clock_port, clock_pin, phy_prefix = 'clk_50mhz', 'usb*/clock/pll/CLKOUT0', 'usb*/phy/phy*'
        timing = '\n'.join(line.replace('clk_ulpi60', 'clk_usb48') for line in
                           (peer / 'constraints/midi_keyboard.sdc').read_text().splitlines()
                           if not (line.startswith('create_clock -name clk_ulpi60') or
                                   (line.startswith('set_') and 'get_ports {ulpi_' in line))) + '\n'
    if board == '25k':
        sources.append(helper)
    source_inputs = [*sources, root / 'vendor/usb_host_fs_8fc3/src/usbh_host_defs.v',
                     root / 'tools/workstation_usb1.py', root / 'tools/stage_usb_firmware.py', root / 'build.py',
                     peer / 'sources.f', peer / 'rtl/usb_board/vendor/usbf_defs.v',
                     root / 'usb1_profile.vh', peer / 'usb1_profile.vh']
    identities = {source.relative_to(repository).as_posix(): sha(source) for source in source_inputs}
    output.mkdir(parents=True, exist_ok=False)
    staged = {}
    def copy_input(source, relative):
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        staged[relative] = sha(target)
        return relative
    staged_sources = [copy_input(source, 'inputs/' + source.relative_to(repository).as_posix()) for source in sources]
    if board == '138k':
        baseline = load_baseline(root, 'resource_rework_route0')
        for name in ('src/ae350/gw138k_cpu_pll_cell.v', 'vendor/sipeed_dvi/video_pll_init.v'):
            relative = 'locked/' + name
            baseline.copy_file(name, output / relative)
            staged[relative] = sha(output / relative)
            staged_sources.append(relative)
    for header in (root / 'vendor/usb_host_fs_8fc3/src/usbh_host_defs.v', peer / 'rtl/usb_board/vendor/usbf_defs.v'):
        copy_input(header, 'inputs/' + header.relative_to(repository).as_posix())
    firmware = None
    if board == '138k':
        firmware = stage_usb_firmware(root, output, output, riscv_prefix, entry='usb1_identify.c')
        staged['push2_usb_a.hex'] = sha(output / 'push2_usb_a.hex')
    else:
        patch = peer / 'rtl/ble_board/rtl8723ds_patch.mem'
        identities[patch.relative_to(repository).as_posix()] = sha(patch)
        copy_input(patch, 'rtl/ble_board/rtl8723ds_patch.mem')
    clock_definition = (f'create_generated_clock -name clk_usb48 -source [get_ports {{{clock_port}}}] '
                        f'-multiply_by 24 -divide_by 25 [get_pins {{{clock_pin}}}]\n')
    first_line, rest = timing.split('\n', 1)
    timing = first_line + '\n' + clock_definition + rest
    for port, register in (('usb1_dp', 'rx_dp_ms'), ('usb1_d' + ('n' if board == '138k' else 'm'), 'rx_dn_ms'),
                           ('usb1_dp usb1_d' + ('n' if board == '138k' else 'm'), 'rxd_ms')):
        timing += f'set_false_path -from [get_ports {{{port}}}] -to [get_pins {{{phy_prefix}/{register}*_s*/D}}]\n'
    if board == '25k':
        timing += ('set_false_path -hold -from [get_pins {usb*/clock/init/rLockOut_s0/Q}] '
                   '-to [get_pins {usb*/clock/release_q*_s*/CLEAR}]\n')
    else:
        timing += HOST_RESET_ASYNC + '\n'
    (output / 'usb1.cst').write_text(constraints)
    (output / 'usb1.sdc').write_text(timing)
    (output / 'usb1_profile.vh').write_text(
        f'`define USB1_BUILD_ID 32\'h{user_code.upper()}\n' + ('`define MIDI_USB1_FS\n' if board == '25k' else ''))
    includes = ['.', 'inputs/' + (root / 'vendor/usb_host_fs_8fc3/src').relative_to(repository).as_posix(),
                'inputs/' + (peer / 'rtl/usb_board/vendor').relative_to(repository).as_posix()]
    tcl = ['cd [file dirname [info script]]', f'set_device -name {family} {device}',
           f'set_option -top_module {top}', 'set_option -output_base_name usb1_candidate',
           'set_option -verilog_std sysv2017', 'set_option -synthesis_tool gowinsynthesis',
           'set_option -timing_driven 1', 'set_option -cst_warn_to_error 1',
           'set_option -use_cpu_as_gpio 1', 'set_option -use_sspi_as_gpio 1',
           'set_option -use_jtag_as_gpio 0', 'set_option -use_ready_as_gpio 1', 'set_option -use_done_as_gpio 1',
           'set_option -bit_security 0', 'set_option -gen_text_timing_rpt 1',
           f'set_option -user_code {user_code.upper()}', 'set_option -include_path {' + ';'.join(includes) + '}']
    if board == '138k':
        tcl += ['set_option -global_freq 48']
    tcl += ['add_file {' + name + '}' for name in staged_sources]
    tcl += ['add_file usb1.cst', 'add_file usb1.sdc', 'run syn']
    (output / 'synthesis.tcl').write_text('\n'.join(tcl) + '\n')
    for name in ('usb1.cst', 'usb1.sdc', 'synthesis.tcl', 'usb1_profile.vh'):
        staged[name] = sha(output / name)
    for relative, expected in identities.items():
        if sha(repository / relative) != expected:
            raise ValueError('USB1 source changed during preparation: ' + relative)
    metadata = dict(schema=1, identity=f'usb1-fs-{board}-{user_code.upper()}', board=board,
                    user_code=user_code.upper(), top_module=top, device=device,
                    source_policy='explicit_native_usb1_and_locked_vendor', high_speed_allowed=False,
                    full_workstation=False, complete_keyboard=board == '25k',
                    source_sha256=identities, staged_sha256=staged, source_paths=staged_sources,
                    firmware=firmware, pin_evidence=pin_evidence, clock_hz=48000000,
                    support_baseline=baseline.evidence() if board == '138k' else None,
                    prepared_at=datetime.now().astimezone().isoformat(), validation_stage='prepare_only',
                    hardware_validated=False, sram_programmed=False, flash_programmed=False,
                    deployment_allowed=False)
    metadata['git_head'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repository, text=True).strip()
    metadata['input_manifest_sha256'] = hashlib.sha256(json.dumps(identities, sort_keys=True).encode()).hexdigest()
    (output / 'usb1_inputs.json').write_text(json.dumps(metadata, indent=2) + '\n')
    return output, metadata


def audit_input_samplers(netlist, timing, board):
    prefix = 'host/phy/phy*' if board == '138k' else 'usb*/phy/phy*'
    negative = 'usb1_dn' if board == '138k' else 'usb1_dm'
    result = {}
    for ports, register in (('usb1_dp', 'rx_dp_ms'), (negative, 'rx_dn_ms'),
                            ('usb1_dp ' + negative, 'rxd_ms')):
        pattern = prefix + '/' + register + '*_s*'
        cells = [name for name, cell in netlist.cells.items()
                 if fnmatch.fnmatchcase(name, pattern) and cell['kind'].startswith('DFF')]
        expected = f'set_false_path -from [get_ports {{{ports}}}] -to [get_pins {{{pattern}/D}}]'
        if len(cells) != 1 or timing.splitlines().count(expected) != 1:
            raise ValueError('USB1 input sampler constraint must match exactly one first-stage DFF: ' + register)
        result[register] = cells[0] + '/D'
    return result


def audit_reset_release(netlist, timing):
    stages = [f'clock/release_q_{index}_s0' for index in range(3)]
    actual_stages = [name for name in netlist.cells if fnmatch.fnmatchcase(name, 'clock/release_q*_s*')]
    sources = [f'clock/pll/u_pll_init/state_{index}_s0' for index in range(3)]
    actual = [name for name in netlist.cells if fnmatch.fnmatchcase(name, 'clock/pll/u_pll_init/state_*_s0')]
    if (timing.splitlines().count(HOST_RESET_ASYNC) != 1 or set(sources) != set(actual) or
            set(stages) != set(actual_stages)):
        raise ValueError('USB1 reset asynchronous-control exception is missing or PLL source drifted')
    for index, name in enumerate(stages):
        cell = netlist.cells.get(name, {})
        if cell.get('kind') != 'DFFCE' or cell.get('parameters', {}).get('INIT') != "1'b0":
            raise ValueError('USB1 reset release must retain three initialized synchronizer stages')
        if (netlist.pin(name, 'CLEAR') != netlist.pin(stages[0], 'CLEAR') or
                netlist.pin(name, 'CLK') != netlist.pin(stages[0], 'CLK') or
                netlist.pin(name, 'CE') != netlist.pin(stages[0], 'D') or
                (index != 0 and netlist.pin(name, 'D') != netlist.pin(stages[index-1], 'Q'))):
            raise ValueError('USB1 reset release synchronizer connectivity drifted')
    if not netlist.pin(stages[0], 'D').endswith('/VCC'):
        raise ValueError('USB1 reset release must shift a constant one')
    return dict(stages=stages, asynchronous_reset_sources=[source + '/Q' for source in sources],
                exception=HOST_RESET_ASYNC, release_cycles=3)


def audit_synthesis(output, metadata):
    output = Path(output)
    text = (output / 'impl/gwsynthesis/usb1_candidate.vg').read_text()
    netlist = SynthesisNetlist(text, metadata['top_module'])
    samplers = audit_input_samplers(netlist, (output / 'usb1.sdc').read_text(), metadata['board'])
    reset_release = None
    if metadata['board'] == '138k':
        reset_release = audit_reset_release(netlist, (output / 'usb1.sdc').read_text())
    cells = list(netlist.cells.values())
    counts = {kind: sum(cell['kind'] == kind for cell in cells) for kind in ('PLL', 'PLLA', 'SDPB', 'SDPX9B', 'pROM', 'RAM16SDP4')}
    registers = sum(cell['kind'].startswith('DFF') for cell in cells)
    report = ElementTree.parse(output / 'impl/gwsynthesis/usb1_candidate_syn_rsc.xml').getroot()
    if report.get('name') != metadata['top_module']:
        raise ValueError('USB1 synthesized top does not match candidate')
    resources = {}
    for key in ('T_Register', 'T_Alu', 'T_Lut', 'T_Bsram', 'T_Ssram'):
        match = re.fullmatch(r'(\d+)\(\d+\)', report.get(key, '0(0)'))
        if match is None:
            raise ValueError('USB1 malformed resource count: ' + key)
        resources[key] = int(match[1])
    if (resources['T_Register'] != registers or resources['T_Bsram'] != counts['SDPB'] + counts['SDPX9B'] + counts['pROM'] or
            resources['T_Ssram'] != counts['RAM16SDP4']):
        raise ValueError('USB1 synthesis resource report/netlist mismatch')
    kind = 'PLL' if metadata['board'] == '138k' else 'PLLA'
    plls = [cell for cell in cells if cell['kind'] in ('PLL', 'PLLA')]
    if len(plls) != 1 or plls[0]['kind'] != kind or any(plls[0]['parameters'].get(key) != value for key, value in (
        ('IDIV_SEL', '1'), ('FBDIV_SEL', '1'), ('MDIV_SEL', '24'), ('ODIV0_SEL', '25'),
        ('MDIV_FRAC_SEL', '0'), ('ODIV0_FRAC_SEL', '0'), ('CLKOUT1_EN', '"FALSE"'))):
        raise ValueError('USB1 synthesized PLL must produce exactly 48 MHz from 50 MHz')
    kinds = {cell['kind'] for cell in cells}
    expected = {'VexRiscv', 'usbh_core', 'usb_fs_phy'} if metadata['board'] == '138k' else {
        'midi_usb1_link', 'midi_usb_bridge', 'midi_usb_fs_state', 'usb_fs_phy', 'midi_ble_link',
        'midi_touch_frontend', 'gw138k_panel_performance', 'midi_landscape_display', 'panel_display_endpoint', 'midi_ws2812'}
    if not expected.issubset(kinds) or any('ulpi' in name.lower() or 'usb_hs_phy' in name for name in kinds):
        raise ValueError('USB1 feature/FS-only structural gate failed')
    rom_sha256 = None
    if metadata['board'] == '138k':
        planes = []
        for byte_lane in range(4):
            for bit_lane in range(8):
                cell = netlist.cells.get(f'host/bus/memory_{byte_lane}_memory_{byte_lane}_0_{bit_lane}_s', {})
                params = cell.get('parameters', {})
                if cell.get('kind') != 'SDPB' or any(params.get('BIT_WIDTH_' + str(port)) != '1' for port in (0, 1)):
                    raise ValueError('USB1 CPU RAM must retain 32 16Kx1 planes')
                value = 0
                for name, encoded in params.items():
                    if name.startswith('INIT_RAM_'):
                        index = int(name.removeprefix('INIT_RAM_'), 16)
                        match = re.fullmatch(r"256'h([0-9a-fA-F]+)", encoded)
                        if index >= 64 or match is None:
                            raise ValueError('USB1 CPU ROM initialization is malformed')
                        value |= int(match[1], 16) << (256 * index)
                planes.append(value)
        reconstructed = bytearray(65536)
        for word in range(16384):
            for byte_lane in range(4):
                reconstructed[word * 4 + byte_lane] = sum(((planes[byte_lane * 8 + bit] >> word) & 1) << bit for bit in range(8))
        expected_rom = b''.join(int(word, 16).to_bytes(4, 'little') for word in (output / 'push2_usb_a.hex').read_text().splitlines())
        if reconstructed != expected_rom:
            raise ValueError('USB1 synthesized CPU ROM differs from compiled identify firmware')
        rom_sha256 = hashlib.sha256(reconstructed).hexdigest()
    return dict(resources=resources, pll_48mhz_verified=True, feature_structure_verified=True,
                netlist_rom_sha256=rom_sha256, synthesis_bsram_is_not_physical_count=True,
                input_sampler_constraint_pins=samplers, reset_release_chain=reset_release)


def build(output):
    output = Path(output).resolve()
    metadata = json.loads((output / 'usb1_inputs.json').read_text())
    for relative, expected in metadata['staged_sha256'].items():
        if sha(output / relative) != expected:
            raise ValueError('USB1 staged input drifted: ' + relative)
    if (output / 'impl').exists() or (output / 'synthesis.log').exists():
        raise FileExistsError('USB1 synthesis evidence already exists; prepare a fresh candidate')
    with open(Path(tempfile.gettempdir()) / 'gw-usb1-build.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with (output / 'synthesis.log').open('w') as log:
            result = subprocess.run(['gw_sh', 'synthesis.tcl'], cwd=output, stdout=log, stderr=subprocess.STDOUT)
    netlist = output / 'impl/gwsynthesis/usb1_candidate.vg'
    resource = output / 'impl/gwsynthesis/usb1_candidate_syn_rsc.xml'
    log_text = (output / 'synthesis.log').read_text(errors='replace')
    if (result.returncode or not netlist.is_file() or not resource.is_file() or
            re.search(r'(?m)^\s*ERROR\s*(?:\(|:)', log_text)):
        raise ValueError('USB1 synthesis failed; inspect ' + str(output / 'synthesis.log'))
    audit = audit_synthesis(output, metadata)
    for relative, expected in metadata['staged_sha256'].items():
        if sha(output / relative) != expected:
            raise ValueError('USB1 staged input changed during synthesis: ' + relative)
    verification = dict(identity=metadata['identity'], source_manifest_sha256=sha(output / 'usb1_inputs.json'),
                        validation_stage='synthesis_only', synthesis_passed=True, **audit,
                        audit_recipe_sha256=sha(Path(__file__)),
                        synthesis_log_sha256=sha(output / 'synthesis.log'),
                        netlist_sha256=sha(netlist), resource_sha256=sha(resource),
                        routed_timing_verified=False, cdc_verified=False, pll_physical_verified=False,
                        bitstream=None, hardware_validated=False, sram_programmed=False,
                        flash_programmed=False, deployment_allowed=False)
    (output / 'synthesis_verification.json').write_text(json.dumps(verification, indent=2) + '\n')
    return verification
