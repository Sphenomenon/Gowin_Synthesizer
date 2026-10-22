"""Explicit native-board integration preparation; never P&R or deployment."""

from pathlib import Path
import importlib
import json
import shutil
import sys
import xml.etree.ElementTree as ElementTree

from tools.stage_usb_firmware import sha, stage_usb2_cpu_firmware
from tools.workstation_pinout import prepare as prepare_pinout
from tools.workstation_usb2_input import NATIVE_INPUT_SOURCES, LOCKED_INPUT_SOURCES
from tools.workstation_usb2_soc import SOC_SOURCE_PATHS
from tools.workstation_custom_clocks import clock_bundle


NATIVE_SOURCES = (*SOC_SOURCE_PATHS, *NATIVE_INPUT_SOURCES,
                  'rtl/workstation/workstation_custom_138k_top.sv',
                  'rtl/display_data/workstation_custom_dvi.sv')
REPLACED_INPUTS = {
    'src/usb_a/VexRiscv.v': 'vendor/usb_host_fs_8fc3/src/VexRiscv.v',
    'src/usb_a/simpleuart.v': 'vendor/usb_host_fs_8fc3/src/simpleuart.v',
    'src/usb_a/push2_usb_a_control.sv': 'rtl/push2_usb_a_control.sv',
    'src/push2/push2_controls.sv': 'rtl/audio/push2_controls.sv',
    'src/push2/push2_lights.sv': 'rtl/push2/push2_lights.sv',
    'src/push2/push2_led_tx.sv': 'rtl/push2/push2_led_tx.sv',
    'src/push2/push2_playlist_hold.sv': 'rtl/push2/push2_playlist_hold.sv',
    'src/usb_a/push2_song_menu.sv': 'rtl/push2/push2_song_menu.sv',
    'src/usb_a/push2_score_guide.sv': 'rtl/push2/push2_score_guide.sv',
    'src/push2/push2_song_screen.sv': 'rtl/push2/push2_song_screen.sv',
    'src/push2/push2_surface_pixels.sv': 'rtl/display_data/push2_surface_pixels.sv',
}
EXCLUDED_INPUTS = ('src/push2/gw138k_push_workstation_top.v', 'src/usb_a/iosys2.v',
                   'vendor/sipeed_dvi/dvi_tx_top.v', 'vendor/sipeed_dvi/dvi_tx_tmds_phy.v',
                   'vendor/sipeed_dvi/dvi_tx_clk_drv.v',
                   'constraints/tang_mega_138k.cst', 'constraints/tang_mega_138k.sdc')


def prepare(root, netlist_directory, output, riscv_prefix=None, allow_high_speed=True):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError('custom-board output already exists: ' + str(output))
    clocks = clock_bundle(root)
    selected = [root / name for name in ('build.py', 'firmware.c', 'gw25k_panel.h')]
    for directory in ('rtl', 'tools', 'drivers/usb2', 'boards/custom_138k', 'baselines'):
        selected += [source for source in (root / directory).rglob('*') if source.is_file()
                     and source.suffix in ('.py', '.sv', '.v', '.vh', '.svh', '.mem', '.json', '.c', '.h')]
    for relative in (*NATIVE_SOURCES, 'rtl/workstation/gw138k_push_workstation_top.v'):
        if not (root / relative).is_file():
            raise FileNotFoundError('missing native-board source: ' + relative)
        selected.append(root / relative)
    snapshot = {str(source.relative_to(root)): sha(source) for source in selected}
    pinout_output, pinout = prepare_pinout(root, netlist_directory, output / 'pinout')
    sys.path.insert(0, str(root / 'tools'))
    builder = importlib.import_module('build_resource_rework')
    if builder.ROOT.resolve() != root:
        raise ValueError('resource builder root does not match explicit custom-board root')
    parent_output, stage, parent_metadata = builder.prepare(timing_fixes=True, output_directory=output / 'workstation')
    (stage / 'scripts/build.tcl').write_text(
        'error "This native-board integration stage is synthesis-only; P&R and deployment are not authorized or validated."\n')
    (parent_output / 'build_metadata.json').write_text(json.dumps(dict(
        candidate='custom138k-native-integration-20261022-a3',
        source_policy='explicit_native_board_on_resource_timing', validation_stage='integration_prepare_incomplete',
        place_route_allowed=False, deployment_allowed=False, release_ready=False, hardware_tested=False), indent=2) + '\n')
    (output / 'parent_prepare_metadata.json').write_text(json.dumps(parent_metadata, indent=2) + '\n')
    project = stage / 'Prj1.gprj'
    tree = ElementTree.parse(project)
    files = tree.find('FileList')
    paths = [entry.get('path') for entry in files]
    if len(paths) != len(set(paths)):
        raise ValueError('duplicate native-board parent compilation inputs')
    replacements = {}
    for relative in (*REPLACED_INPUTS, *EXCLUDED_INPUTS):
        entries = [entry for entry in files if entry.get('path') == relative and entry.get('enable') == '1']
        if len(entries) != 1:
            raise ValueError('native-board parent selection drift: ' + relative)
        replacements[relative] = dict(sha256=sha(stage / relative), replacement=REPLACED_INPUTS.get(relative))
        entries[0].set('enable', '0')
    copied = {}
    for relative in (*NATIVE_SOURCES, 'rtl/workstation/gw138k_push_workstation_top.v'):
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, destination)
        copied[relative] = sha(destination)
        if copied[relative] != snapshot[relative]:
            raise ValueError('native-board copied source identity changed: ' + relative)
        if relative in NATIVE_SOURCES:
            if relative in paths:
                raise ValueError('native-board source already selected by parent: ' + relative)
            ElementTree.SubElement(files, 'File', path=relative, type='file.verilog', enable='1')
    support = {}
    for relative in LOCKED_INPUT_SOURCES:
        if sum(entry.get('path') == relative and entry.get('enable') == '1' for entry in files) != 1:
            raise ValueError('native-board shared support selection drift: ' + relative)
        support[relative] = sha(stage / relative)
    firmware = stage_usb2_cpu_firmware(root, stage / 'native_usb_firmware', root / 'firmware.c', riscv_prefix,
                                       workstation=True, allow_high_speed=allow_high_speed)
    shutil.copyfile(stage / 'native_usb_firmware/usb2_cpu.hex', stage / 'usb2_cpu.hex')
    shutil.copyfile(pinout_output / 'custom_138k.locations.cst', stage / 'constraints/custom_138k.locations.cst')
    (stage / 'constraints/custom_138k.sdc').write_text(clocks['sdc'])
    ElementTree.SubElement(files, 'File', path='constraints/custom_138k.locations.cst', type='file.cst', enable='1')
    ElementTree.SubElement(files, 'File', path='constraints/custom_138k.sdc', type='file.sdc', enable='1')
    tree.write(project, encoding='UTF-8', xml_declaration=True)
    (stage / 'scripts/custom_board_synthesis.tcl').write_text(
        'set root [file normalize [file join [file dirname [info script]] ..]]\n'
        'cd $root\nopen_project Prj1.gprj\n'
        'set_option -top_module workstation_custom_138k_top\n'
        'set_option -output_base_name custom_138k_integration\n'
        'set_option -verilog_std sysv2017\nset_option -timing_driven 1\nrun syn\n')
    enabled = [entry.get('path') for entry in files if entry.get('enable') == '1']
    if len(enabled) != len(set(enabled)):
        raise ValueError('native-board duplicate selected input')
    for relative, expected in snapshot.items():
        if sha(root / relative) != expected:
            raise ValueError('native-board source snapshot changed during preparation: ' + relative)
    for relative, record in replacements.items():
        if sha(stage / relative) != record['sha256']:
            raise ValueError('native-board excluded historical input changed: ' + relative)
    staged = {str(source.relative_to(stage)): sha(source) for source in stage.rglob('*')
              if source.is_file() and 'impl' not in source.relative_to(stage).parts}
    metadata = dict(schema=1, identity='custom138k-native-integration-20261022-a3',
                    top_module='workstation_custom_138k_top', source_policy='explicit_native_board_on_resource_timing',
                    validation_stage='integration_prepare_only', device=pinout['device'],
                    firmware=firmware, high_speed_allowed=bool(allow_high_speed),
                    source_snapshot_sha256=snapshot, copied_sources_sha256=copied,
                    replaced_compilation_inputs=replacements, shared_resource_support_sha256=support,
                    parent_prepare_metadata_sha256=sha(output / 'parent_prepare_metadata.json'),
                    pinout_sha256=sha(pinout_output / 'pinout.json'), enabled_inputs=enabled,
                    staged_input_sha256=staged, native_usb=True, legacy_usb_host_elaborated=False,
                    tmds_polarity_inverted=[True, True, True, True], cec_behavior='released_high_impedance',
                    audio_pin_behavior='high_impedance_pending_actual_dac_identity',
                    uart_default='existing_workstation_reports',
                    electrical_blocked=pinout['electrical_check']['status']=='blocked',
                    synthesis_allowed=True, place_route_allowed=False, io_electrical_complete=False,
                    timing_constraints_complete=False, hardware_tested=False,
                    clock_plan_source=clocks['source'], clock_plan_sha256=clocks['source_sha256'],
                    deployment_allowed=False, release_ready=False, bitstream_sha256=None,
                    remaining_gaps=['USB3300/TXS electrical compatibility', 'DAC identity and driver',
                                    'BLE pin map and business backend', 'complete IO/CDC/timing/PLL/P&R gates',
                                    'real external peripheral and hardware acceptance'])
    (parent_output / 'build_metadata.json').write_text(json.dumps(dict(
        candidate=metadata['identity'],source_policy=metadata['source_policy'],
        validation_stage='integration_prepare_only',place_route_allowed=False,deployment_allowed=False,
        release_ready=False,hardware_tested=False),indent=2)+'\n')
    (parent_output / 'workstation_inputs.json').write_text(json.dumps(staged,indent=2)+'\n')
    (output / 'integration_inputs.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    return output, metadata
