#!/usr/bin/env python3
"""Reproducible CPU/USB2 component inputs and strict profile separation."""

from pathlib import Path
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ElementTree


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import stage_usb_firmware as staging
from tools import workstation_usb2_soc as preparation


class ComponentPreparation(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='workstation-usb2-prepare-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'minimal_checkout'
        self.output = self.base / 'component'
        vendor_paths = json.loads((ROOT / 'vendor/usb_host_fs_8fc3/inputs.json').read_text())
        inputs = set((*preparation.SOC_SOURCE_PATHS, *preparation.PREPARATION_INPUTS, *preparation.WORKSTATION_INPUTS,
                      *('vendor/usb_host_fs_8fc3/' + relative for relative in vendor_paths)))
        self.original = {relative: staging.sha(ROOT / relative) for relative in inputs}
        for relative in inputs:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)

    def test_explicit_minimal_checkout_compiles_rv32i_and_self_contained_project(self):
        with patch.object(staging.subprocess, 'run', wraps=subprocess.run) as commands:
            output, metadata = preparation.prepare(self.root, self.output)
        self.assertEqual(output, self.output)
        self.assertEqual(metadata['firmware']['isa'], 'rv32i')
        self.assertEqual(metadata['firmware']['abi'], 'ilp32')
        self.assertEqual(metadata['firmware_role'], 'simulation_enumeration_probe')
        self.assertEqual(metadata['validation_stage'], 'component_prepare_only')
        self.assertTrue(metadata['synthesis_allowed'])
        for key in ('place_route_allowed', 'deployment_allowed', 'release_ready', 'workstation_integrated', 'hardware_tested'):
            self.assertFalse(metadata[key], key)
        self.assertLess(metadata['firmware']['static_ram_end'], 60000)
        self.assertGreater(metadata['firmware']['firmware_bytes'], 0)
        self.assertEqual(len((output / 'usb2_cpu.hex').read_text().splitlines()), 16384)
        self.assertEqual(staging.sha(output / 'usb2_cpu.hex'), metadata['firmware']['rom_sha256'])
        self.assertEqual(json.loads((output / 'component_inputs.json').read_text()), metadata)
        for relative, expected in metadata['staged_input_sha256'].items():
            self.assertEqual(staging.sha(output / relative), expected, relative)
        for relative, expected in self.original.items():
            self.assertEqual(staging.sha(self.root / relative), expected, relative)
        project = ElementTree.parse(output / 'usb2_soc.gprj')
        project_paths = [element.attrib['path'] for element in project.find('FileList')]
        self.assertEqual(project_paths, [*preparation.SOC_SOURCE_PATHS, 'usb2_soc.sdc'])
        self.assertEqual(len(set(preparation.SOC_SOURCE_PATHS)), 14)
        self.assertFalse(any(Path(relative).is_absolute() for relative in project_paths))
        self.assertTrue(all((output / relative).is_file() for relative in project_paths))
        constraints = (output / 'usb2_soc.sdc').read_text()
        self.assertEqual(constraints.count('create_clock'), 3)
        self.assertNotIn('false_path', constraints)
        self.assertTrue((output / 'synthesis.tcl').read_text().endswith('run syn\n'))
        self.assertTrue(metadata['firmware']['compiler_version'])
        compiler_commands = [call.args[0] for call in commands.call_args_list
                             if call.args[0][0].endswith('-gcc') and '--version' not in call.args[0]]
        self.assertEqual(len(compiler_commands), 5)
        for command in compiler_commands:
            self.assertIn('-march=rv32i', command)
            self.assertIn('-mabi=ilp32', command)
        self.assertIn('-Wl,-e,_start,--gc-sections,--build-id=none,-T,baremetal.ld', compiler_commands[-1])
        with self.assertRaises(FileExistsError):
            preparation.prepare(self.root, self.output)

    def test_missing_native_input_fails_without_output_or_fallback(self):
        (self.root / 'rtl/usb2/workstation_usb2_cpu_bus.sv').unlink()
        with self.assertRaisesRegex(FileNotFoundError, 'missing explicit USB2 SoC source'):
            preparation.prepare(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_workstation_profiles_compile_business_firmware_without_probe(self):
        for high_speed in (True, False):
            with self.subTest(high_speed=high_speed):
                output = self.base / ('workstation-hs' if high_speed else 'workstation-fs')
                with patch.object(staging.subprocess, 'run', wraps=subprocess.run) as commands:
                    _, metadata = preparation.prepare(self.root, output, firmware_profile='workstation',
                                                      allow_high_speed=high_speed)
                self.assertEqual(metadata['firmware_role'], 'workstation_application')
                self.assertEqual(metadata['firmware_profile'], 'workstation')
                self.assertEqual(metadata['high_speed_allowed'], high_speed)
                self.assertTrue(metadata['business_firmware_selected'])
                for key in ('requires_external_probe_service', 'workstation_integrated', 'place_route_allowed',
                            'deployment_allowed', 'release_ready', 'hardware_tested'):
                    self.assertFalse(metadata[key], key)
                self.assertNotIn(preparation.PROBE_ENTRY, metadata['input_sha256'])
                for relative in preparation.WORKSTATION_INPUTS:
                    self.assertEqual(metadata['input_sha256'][relative], self.original[relative])
                firmware = metadata['firmware']
                self.assertEqual(firmware['firmware_profile'], 'workstation')
                self.assertEqual(firmware['high_speed_allowed'], high_speed)
                self.assertEqual(firmware['isa'], 'rv32i')
                self.assertLess(firmware['static_ram_end'], 60000)
                self.assertEqual(staging.sha(output / 'usb2_cpu.hex'), firmware['rom_sha256'])
                compile_commands = [call.args[0] for call in commands.call_args_list if '-c' in call.args[0]]
                self.assertEqual(len(compile_commands), 7)
                for command in compile_commands:
                    self.assertIn('-DWORKSTATION_USB2_NATIVE', command)
                    self.assertEqual('-DWORKSTATION_USB2_FORCE_FS' in command, not high_speed)
                    self.assertIn('-march=rv32i', command)
                    self.assertIn('-O2', command)
                    if '/vendor/' not in command[command.index('-c') + 1]:
                        self.assertIn('-Werror', command)
                self.assertFalse((output / 'impl').exists())

    def test_workstation_missing_backend_does_not_fall_back_to_probe(self):
        (self.root / 'drivers/usb2/workstation_usb2_backend.c').unlink()
        with self.assertRaises(FileNotFoundError):
            preparation.prepare(self.root, self.output, firmware_profile='workstation')
        self.assertFalse(self.output.exists())

    def test_workstation_input_drift_is_rejected(self):
        def compile_and_change(*arguments, **keywords):
            result = staging.stage_usb2_cpu_firmware(*arguments, **keywords)
            source = self.root / 'drivers/usb2/workstation_usb2_backend.c'
            source.write_bytes(source.read_bytes() + b'\n')
            return result

        with patch.object(preparation, 'stage_usb2_cpu_firmware', side_effect=compile_and_change):
            with self.assertRaisesRegex(ValueError, 'input changed during preparation'):
                preparation.prepare(self.root, self.output, firmware_profile='workstation')
        self.assertFalse((self.output / 'component_inputs.json').exists())

    def test_invalid_firmware_profiles_fail_without_output(self):
        for profile, high_speed in (('unknown', True), ('probe', False)):
            with self.subTest(profile=profile, high_speed=high_speed):
                with self.assertRaises(ValueError):
                    preparation.prepare(self.root, self.output, firmware_profile=profile, allow_high_speed=high_speed)
                self.assertFalse(self.output.exists())

    def test_vendor_manifest_selected_and_unused_bytes_are_locked(self):
        for relative in ('inputs.json', 'src/VexRiscv.v', 'firmware/minlibc.c'):
            with self.subTest(relative=relative):
                source = self.root / 'vendor/usb_host_fs_8fc3' / relative
                original = source.read_bytes()
                source.write_bytes(original + b'\n')
                try:
                    with self.assertRaisesRegex(ValueError, 'identity changed|immutable vendor source changed'):
                        preparation.prepare(self.root, self.output)
                    self.assertFalse(self.output.exists())
                finally:
                    source.write_bytes(original)

    def test_source_drift_during_compile_fails_before_manifest(self):
        def compile_and_change(*arguments, **keywords):
            result = staging.stage_usb2_cpu_firmware(*arguments, **keywords)
            source = self.root / 'rtl/usb2/workstation_ulpi_link.sv'
            source.write_bytes(source.read_bytes() + b'\n')
            return result

        with patch.object(preparation, 'stage_usb2_cpu_firmware', side_effect=compile_and_change):
            with self.assertRaisesRegex(ValueError, 'input changed during preparation'):
                preparation.prepare(self.root, self.output)
        self.assertFalse((self.output / 'component_inputs.json').exists())

    def test_wrong_board_device_fails_before_output(self):
        source = self.root / 'boards/custom_138k/pinout.json'
        profile = json.loads(source.read_text())
        profile['device'] = 'not-the-checked-device'
        source.write_text(json.dumps(profile))
        with self.assertRaisesRegex(ValueError, 'checked custom-138k device'):
            preparation.prepare(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_staged_source_drift_during_compile_is_not_relabelled_as_input(self):
        def compile_and_change(*arguments, **keywords):
            result = staging.stage_usb2_cpu_firmware(*arguments, **keywords)
            source = self.output / 'rtl/usb2/workstation_usb2_cpu_bus.sv'
            source.write_bytes(source.read_bytes() + b'\n')
            return result

        with patch.object(preparation, 'stage_usb2_cpu_firmware', side_effect=compile_and_change):
            with self.assertRaisesRegex(ValueError, 'staged source identity changed'):
                preparation.prepare(self.root, self.output)
        self.assertFalse((self.output / 'component_inputs.json').exists())

    @unittest.skipUnless(shutil.which('gw_sh'), 'gw_sh is required for CPU ROM and RAM mapping')
    def test_gowin_component_maps_exact_rom_and_block_rams(self):
        preparation.prepare(self.root, self.output)
        execution = subprocess.run(['gw_sh', str(self.output / 'synthesis.tcl')], cwd=self.output,
                                   text=True, capture_output=True, timeout=180)
        self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
        warnings = [line for line in execution.stdout.splitlines() if line.startswith('WARN')]
        self.assertTrue(all('/vendor/usb_host_fs_8fc3/' in line for line in warnings), warnings)
        self.assertNotIn('ERROR', execution.stdout + execution.stderr)
        result = preparation.audit_component_synthesis(self.output)
        self.assertEqual(result['sdpb_primitives'], 38)
        self.assertEqual(result['verified_rom_words'], 16384)
        self.assertFalse(result['hardware_tested'])
        netlist = self.output / 'impl/gwsynthesis/usb2_soc_component.vg'
        original = netlist.read_text()
        pattern = r"(defparam memory_0_memory_0_0_0_s\.INIT_RAM_00=256'h)([0-9A-Fa-f])"
        changed, count = re.subn(pattern, lambda match: match[1] + ('0' if match[2] != '0' else '1'), original)
        self.assertEqual(count, 1)
        netlist.write_text(changed)
        with self.assertRaisesRegex(ValueError, 'synthesized ROM mismatch'):
            preparation.audit_component_synthesis(self.output)
        netlist.write_text(original)
        rom = self.output / 'usb2_cpu.hex'
        rom.write_text('00000000\n' + rom.read_text()[9:])
        with self.assertRaisesRegex(ValueError, 'synthesis input identity changed'):
            preparation.audit_component_synthesis(self.output)
        print(f'PASS Gowin USB2 CPU component: {result["sdpb_primitives"]} SDPB, '
              f'{result["registers"]} registers, {result["verified_rom_words"]} exact ROM words, no P&R')

    def test_static_ram_limit_is_not_relaxed_for_probe(self):
        with patch.object(staging, 'static_memory_end', return_value=60000):
            with self.assertRaisesRegex(ValueError, 'leave stack space'):
                preparation.prepare(self.root, self.output)
        self.assertFalse((self.output / 'component_inputs.json').exists())

    def test_cli_rejects_ambiguous_profiles_and_missing_output(self):
        entry = [sys.executable, str(ROOT / 'build.py')]
        component = ['--prepare-usb2-soc', '--usb2-soc-output', str(self.output)]
        invalid = [
            ['--prepare-usb2-soc'], ['--usb2-soc-output', str(self.output)],
            ['--usb2-firmware-profile', 'workstation'], ['--usb2-full-speed-only'],
            component + ['--usb2-full-speed-only'],
            *(component + extra for extra in (
                ['--current-workstation'], ['--cnn-timing85'], ['--resource-rework'], ['--resource-timing'],
                ['--prepare-only'], ['--synthesis-only'], ['--reuse-synthesis', str(self.base)],
                ['--prepare-pinout', 'custom-138k'], ['--netlist-dir', str(self.base)],
                ['--pinout-output', str(self.base)], ['--user-code', 'C110FFFF'],
                ['--tf-audio-kind', 'mp3'], ['--place-option', '2'], ['--max-fanout', '128'],
                ['--replicate-resources'], ['--no-update-latest'],
            )),
        ]
        for arguments in invalid:
            with self.subTest(arguments=arguments):
                execution = subprocess.run(entry + arguments, text=True, capture_output=True, timeout=30)
                self.assertEqual(execution.returncode, 2, execution.stdout + execution.stderr)
                self.assertIn('error:', execution.stderr)
                self.assertFalse(self.output.exists())

    def test_cli_prepares_probe_without_changing_latest_or_implementing_board(self):
        latest = {source: source.read_bytes() for source in ROOT.glob('LATEST*.json')}
        execution = subprocess.run([sys.executable, str(ROOT / 'build.py'), '--prepare-usb2-soc',
                                    '--usb2-soc-output', str(self.output)], text=True, capture_output=True, timeout=60)
        self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
        summary = json.loads(execution.stdout.splitlines()[-1])
        self.assertEqual(summary['sources'], 14)
        self.assertEqual(summary['validation_stage'], 'component_prepare_only')
        self.assertFalse(summary['deployment_allowed'])
        self.assertTrue((self.output / 'component_inputs.json').is_file())
        self.assertFalse((self.output / 'impl').exists())
        self.assertFalse(list(self.output.rglob('*.cst')))
        self.assertFalse(list(self.output.rglob('*.fs')))
        self.assertEqual({source: source.read_bytes() for source in ROOT.glob('LATEST*.json')}, latest)

    def test_cli_explicit_workstation_fs_policy(self):
        execution = subprocess.run([sys.executable, str(ROOT / 'build.py'), '--prepare-usb2-soc',
                                    '--usb2-soc-output', str(self.output), '--usb2-firmware-profile', 'workstation',
                                    '--usb2-full-speed-only'], text=True, capture_output=True, timeout=60)
        self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
        metadata = json.loads((self.output / 'component_inputs.json').read_text())
        self.assertEqual(metadata['firmware_profile'], 'workstation')
        self.assertFalse(metadata['high_speed_allowed'])
        self.assertTrue(metadata['business_firmware_selected'])
        self.assertFalse(metadata['workstation_integrated'])
        self.assertFalse(metadata['deployment_allowed'])
        self.assertFalse((self.output / 'impl').exists())


if __name__ == '__main__':
    unittest.main()
