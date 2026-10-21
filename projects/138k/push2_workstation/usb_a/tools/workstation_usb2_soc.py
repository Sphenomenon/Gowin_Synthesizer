"""Explicit native CPU/USB2 component preparation, never board deployment."""

from pathlib import Path
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ElementTree

from tools.stage_usb_firmware import sha, stage_usb2_cpu_firmware, verify_usb2_cpu_vendor


SOC_SOURCE_PATHS = tuple('rtl/usb2/' + name for name in (
    'workstation_ulpi_link.sv', 'workstation_ulpi_supervisor.sv',
    'workstation_usb2_host_controller.sv', 'workstation_usb2_host_mac.sv',
    'workstation_usb2_host_phy.sv', 'workstation_usb2_host_port.sv',
    'workstation_usb3300_host_init.sv', 'workstation_usb3300_host_link.sv',
    'workstation_usb2_cpu_bridge.sv', 'workstation_usb2_host_mmio.sv',
    'workstation_usb2_cpu_bus.sv', 'workstation_usb2_soc.sv',
)) + ('vendor/usb_host_fs_8fc3/src/VexRiscv.v', 'vendor/usb_host_fs_8fc3/src/simpleuart.v')
PROBE_ENTRY = 'sim/usb2/cpu_enumeration.c'
PREPARATION_INPUTS = (
    'build.py', 'tools/workstation_usb2_soc.py', 'tools/stage_usb_firmware.py',
    'boards/custom_138k/pinout.json', 'vendor/usb_host_fs_8fc3/inputs.json',
    'vendor/usb_host_fs_8fc3/firmware/start.S', 'vendor/usb_host_fs_8fc3/firmware/baremetal.ld',
    'drivers/usb2/workstation_usb2_host.c', 'drivers/usb2/workstation_usb2_host.h',
    'drivers/usb2/workstation_usb2_cpu_port.c', 'drivers/usb2/workstation_usb2_cpu_port.h',
    PROBE_ENTRY,
)
WORKSTATION_INPUTS = (
    'firmware.c', 'gw25k_panel.h', 'drivers/usb2/workstation_usb2_backend.c',
    'drivers/usb2/workstation_usb2_backend.h', 'vendor/usb_host_fs_8fc3/firmware/minlibc.c',
    'vendor/usb_host_fs_8fc3/firmware/minlibc.h', 'vendor/usb_host_fs_8fc3/firmware/usb/usb_core.c',
    'vendor/usb_host_fs_8fc3/firmware/usb/usb_core.h', 'vendor/usb_host_fs_8fc3/firmware/usb/usb_defs.h',
    'vendor/usb_host_fs_8fc3/firmware/usb/usb_hw.h',
)


def soc_sources(root):
    root = Path(root)
    verify_usb2_cpu_vendor(root)
    sources = [root / relative for relative in SOC_SOURCE_PATHS]
    for source in sources:
        if not source.is_file():
            raise FileNotFoundError('missing explicit USB2 SoC source: ' + str(source))
    return sources


def prepare(root, output, riscv_prefix=None, firmware_profile='probe', allow_high_speed=True, component='soc'):
    root, output = Path(root).resolve(), Path(output).resolve()
    if firmware_profile not in ('probe', 'workstation'):
        raise ValueError('unknown USB2 firmware profile: ' + str(firmware_profile))
    if firmware_profile != 'workstation' and not allow_high_speed:
        raise ValueError('full-speed-only policy requires workstation firmware')
    if component not in ('soc', 'workstation-input'):
        raise ValueError('unknown USB2 component: ' + str(component))
    if component == 'workstation-input' and firmware_profile != 'workstation':
        raise ValueError('workstation-input requires explicit workstation firmware')
    if output.exists():
        raise FileExistsError('USB2 component output already exists: ' + str(output))
    sources = soc_sources(root)
    bundle = None
    if component == 'workstation-input':
        from tools.workstation_usb2_input import input_bundle
        bundle = input_bundle(root)
        sources += [root / relative for relative in bundle['native_paths']]
    selected_inputs = tuple(relative for relative in PREPARATION_INPUTS if relative != PROBE_ENTRY)
    selected_inputs += WORKSTATION_INPUTS if firmware_profile == 'workstation' else (PROBE_ENTRY,)
    inputs = {relative: sha(root / relative) for relative in (*SOC_SOURCE_PATHS, *selected_inputs)}
    if bundle:
        inputs.update(bundle['input_sha256'])
    source_paths = tuple(str(source.relative_to(root)) for source in sources)
    staged_expected = {relative: inputs[relative] for relative in source_paths}
    if bundle:
        staged_expected.update({relative: hashlib.sha256(payload).hexdigest()
                                for relative, payload in bundle['payloads'].items()})
        source_paths += tuple(bundle['payloads'])
    top = 'workstation_usb2_input' if bundle else 'workstation_usb2_soc'
    device = json.loads((root / 'boards/custom_138k/pinout.json').read_text())['device']
    if device != 'GW5AST-LV138PG484AC2/I1':
        raise ValueError('USB2 component requires the checked custom-138k device')
    output.mkdir(parents=True, exist_ok=False)
    for source in sources:
        destination = output / source.relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if sha(destination) != inputs[str(source.relative_to(root))]:
            raise ValueError('USB2 staged source identity changed: ' + str(source))
    if bundle:
        for relative, payload in bundle['payloads'].items():
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
    application = firmware_profile == 'workstation'
    firmware = stage_usb2_cpu_firmware(root, output / 'firmware', root / ('firmware.c' if application else PROBE_ENTRY),
                                      riscv_prefix, workstation=application, allow_high_speed=allow_high_speed)
    shutil.copyfile(output / 'firmware/usb2_cpu.hex', output / 'usb2_cpu.hex')
    if sha(output / 'usb2_cpu.hex') != firmware['rom_sha256']:
        raise ValueError('USB2 staged ROM identity changed')
    clocks = (
        'create_clock -name cpu_48 -period 20.833333 [get_ports {clk_cpu}]\n'
        'create_clock -name reference_50 -period 20.000 [get_ports {clk_ref}]\n'
        'create_clock -name ulpi_60 -period 16.666667 [get_ports {clk_ulpi}]\n')
    if bundle:
        clocks += 'create_clock -name audio_76_8 -period 13.020833 [get_ports {clk_audio}]\n'
    (output / 'usb2_soc.sdc').write_text(clocks)
    project = ElementTree.Element('Project')
    ElementTree.SubElement(project, 'Template').text = 'FPGA'
    ElementTree.SubElement(project, 'Version').text = '5'
    ElementTree.SubElement(project, 'Device', name='GW5AST-138C', pn=device).text = 'gw5ast138c-006'
    files = ElementTree.SubElement(project, 'FileList')
    for relative in source_paths:
        ElementTree.SubElement(files, 'File', path=relative, type='file.verilog', enable='1')
    ElementTree.SubElement(files, 'File', path='usb2_soc.sdc', type='file.sdc', enable='1')
    ElementTree.ElementTree(project).write(output / 'usb2_soc.gprj', encoding='UTF-8', xml_declaration=True)
    (output / 'synthesis.tcl').write_text(
        'cd [file dirname [info script]]\nopen_project usb2_soc.gprj\n'
        'set_option -top_module ' + top + '\n'
        'set_option -output_base_name usb2_soc_component\n'
        'set_option -verilog_std sysv2017\nset_option -timing_driven 1\nrun syn\n')
    verify_usb2_cpu_vendor(root)
    for relative, expected in inputs.items():
        if sha(root / relative) != expected:
            raise ValueError('USB2 component input changed during preparation: ' + relative)
    if bundle:
        repeated = input_bundle(root)
        if repeated != bundle:
            raise ValueError('USB2 input-owner sources changed during preparation')
    for relative, expected in staged_expected.items():
        if sha(output / relative) != expected:
            raise ValueError('USB2 staged source identity changed: ' + relative)
    staged_paths = (*source_paths, 'usb2_cpu.hex', 'usb2_soc.sdc', 'usb2_soc.gprj', 'synthesis.tcl')
    metadata = dict(
        schema=1, identity='custom138k-usb2-input-component-v1' if bundle else
                          'custom138k-usb2-workstation-component-v1' if application else 'custom138k-usb2-soc-component-v1',
        top_module=top, component=component, source_paths=list(source_paths), device=device, firmware_profile=firmware_profile,
        high_speed_allowed=bool(allow_high_speed),
        validation_stage='component_prepare_only', source_policy='explicit_native_input_owner_and_locked_support' if bundle
                                                                else 'explicit_native_rtl_and_locked_cpu_vendor',
        firmware_role='workstation_application' if application else 'simulation_enumeration_probe',
        requires_external_probe_service=not application, business_firmware_selected=application,
        input_owner_integrated=bool(bundle), input_owner_provenance=bundle['provenance'] if bundle else None,
        workstation_integrated=False, synthesis_allowed=True, place_route_allowed=False,
        hardware_tested=False, deployment_allowed=False, release_ready=False,
        clocks_hz=dict(cpu=48000000, reference=50000000, ulpi=60000000),
        input_sha256=inputs, firmware=firmware,
        staged_input_sha256={relative: sha(output / relative) for relative in staged_paths},
    )
    (output / 'component_inputs.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    return output, metadata


def audit_component_synthesis(output):
    output = Path(output)
    manifest = output / 'component_inputs.json'
    metadata = json.loads(manifest.read_text())
    if metadata['identity'] not in ('custom138k-usb2-soc-component-v1', 'custom138k-usb2-workstation-component-v1') or metadata['top_module'] != 'workstation_usb2_soc':
        raise ValueError('not the explicit USB2 CPU component')
    for relative, expected in metadata['staged_input_sha256'].items():
        if sha(output / relative) != expected:
            raise ValueError('USB2 synthesis input identity changed: ' + relative)
    for relative in SOC_SOURCE_PATHS:
        if metadata['staged_input_sha256'][relative] != metadata['input_sha256'][relative]:
            raise ValueError('USB2 copied source does not match its original input: ' + relative)
    netlist = output / 'impl/gwsynthesis/usb2_soc_component.vg'
    text = netlist.read_text()
    block_rams = re.findall(r'^\s*SDPB\s+(\S+)\s*\(', text, re.M)
    registers = re.findall(r'^\s*DFF[A-Z0-9_]*\s+\S+\s*\(', text, re.M)
    planes = []
    memory_names = set()
    for byte_lane in range(4):
        for bit_lane in range(8):
            instance = f'memory_{byte_lane}_memory_{byte_lane}_0_{bit_lane}_s'
            memory_names.add(instance)
            for port in (0, 1):
                if f'defparam {instance}.BIT_WIDTH_{port}=1;' not in text:
                    raise ValueError('USB2 CPU RAM is not the expected 16Kx1 bit-plane mapping')
            chunks = re.findall(r'defparam ' + instance + r"\.INIT_RAM_([0-9A-Fa-f]{2})=256'h([0-9A-Fa-f]+);", text)
            if len({index for index, _ in chunks}) != len(chunks) or any(int(index, 16) >= 64 for index, _ in chunks):
                raise ValueError('USB2 CPU ROM has invalid initialization chunks')
            value = sum(int(value, 16) << (int(index, 16) * 256) for index, value in chunks)
            planes.append(value.to_bytes(2048, 'little'))
    expected_rams = memory_names | {
        'RegFilePlugin_regFile_RegFilePlugin_regFile_0_0_s', 'RegFilePlugin_regFile_RegFilePlugin_regFile_0_0_s0',
        'receive_memory_receive_memory_0_0_s', 'transmit_memory_transmit_memory_0_0_s',
        'transmit_buffer_transmit_buffer_0_0_s', 'receive_buffer_receive_buffer_0_0_s',
    }
    if len(block_rams) != 38 or set(block_rams) != expected_rams or len(registers) >= 2304:
        raise ValueError('USB2 component RAM/register resource gate failed')
    words = [int(word, 16) for word in (output / 'usb2_cpu.hex').read_text().splitlines()]
    if len(words) != 16384:
        raise ValueError('USB2 CPU ROM is not 64 KiB')
    for index, expected in enumerate(words):
        actual = sum(((plane[index >> 3] >> (index & 7)) & 1) << bit for bit, plane in enumerate(planes))
        if actual != expected:
            raise ValueError(f'USB2 synthesized ROM mismatch at word {index}')
    return dict(validation_stage='component_synthesis_only', component_inputs_sha256=sha(manifest),
                netlist_sha256=sha(netlist), sdpb_primitives=len(block_rams), registers=len(registers),
                verified_rom_words=len(words), rom_sha256=sha(output / 'usb2_cpu.hex'),
                place_route_verified=False, hardware_tested=False, deployment_allowed=False)
