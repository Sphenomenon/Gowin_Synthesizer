#!/usr/bin/env python3
"""Native production CPU to the existing workstation input owner."""

from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_usb2_soc import prepare
from tools import workstation_usb2_soc as preparation
from tools import workstation_usb2_input as input_sources
from tools.stage_usb_firmware import sha
from test_workstation_usb2_application import MODEL_INPUTS, midi_sources


INPUT_SIMULATION_SOURCES = (*MODEL_INPUTS[:-1], 'sim/usb2/tb_workstation_usb2_input_25k.sv')


class NativeInput(unittest.TestCase):
    def test_production_cpu_with_real_owner_fifo_and_25k(self):
        self.assertIsNotNone(shutil.which('verilator'), 'Verilator is required for native input execution')
        device, peer_sources = midi_sources()
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-input-execution-') as directory:
            base = Path(directory)
            if os.environ.get('GW138K_USB2_INPUT_EVIDENCE'):
                base = Path(os.environ['GW138K_USB2_INPUT_EVIDENCE']).resolve()
                base.mkdir(parents=True, exist_ok=False)
            for high_speed in (1, 0):
                with self.subTest(high_speed=high_speed):
                    self.run_native_input(base, high_speed, device, peer_sources)

    def run_native_input(self, base, high_speed, device, peer_sources):
        stage, metadata = prepare(ROOT, base / f'hs_{high_speed}', firmware_profile='workstation',
                                  allow_high_speed=bool(high_speed), component='workstation-input')
        originals = [*(ROOT / relative for relative in INPUT_SIMULATION_SOURCES), *peer_sources,
                     device / 'rtl/usb_board/vendor/usbf_defs.v', Path(__file__),
                     Path(__file__).with_name('test_workstation_usb2_application.py')]
        identities = {source: sha(source) for source in originals}
        copies = {}
        for source, digest in identities.items():
            target = stage / 'simulation' / source.relative_to(ROOT.parents[3])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            self.assertEqual(sha(target), digest, str(source))
            copies[source] = target
        evidence = dict(schema=1, validation_stage='native_input_owner_simulation', high_speed=bool(high_speed),
                        firmware=metadata['firmware'], component_manifest_sha256=sha(stage / 'component_inputs.json'),
                        simulation_input_sha256={str(source.relative_to(ROOT.parents[3])): digest
                                                 for source, digest in identities.items()},
                        verilator_version=subprocess.check_output(['verilator', '--version'], text=True).strip(),
                        service_boundary='actual_push2_usb_a_control_and_event_fifo_cdc',
                        audio_sink='backpressured_stream_checker_not_dsp', display_sink='modeled_tile_completion',
                        hardware_tested=False, deployment_allowed=False, release_ready=False)
        command = ['verilator', '--binary', '--timing', '--timescale-override', '1ns/1ps', '-Wno-fatal', '-j', '4',
                   '--top-module', 'tb_workstation_usb2_input_25k', '--Mdir', str(stage / 'obj'), '-o', 'simulation',
                   f'-GHIGH_SPEED={high_speed}', '-I' + str(copies[device / 'rtl/usb_board/vendor/usbf_defs.v'].parent),
                   *(str(stage / relative) for relative in metadata['source_paths']),
                   *(str(copies[ROOT / relative]) for relative in INPUT_SIMULATION_SOURCES),
                   *(str(copies[source]) for source in peer_sources)]
        compilation = subprocess.run(command, text=True, capture_output=True, timeout=180)
        (stage / 'compilation.log').write_text(compilation.stdout + compilation.stderr)
        evidence['compilation'] = dict(command=command, returncode=compilation.returncode,
                                       log_sha256=sha(stage / 'compilation.log'))
        (stage / 'input_evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
        self.assertEqual(compilation.returncode, 0, compilation.stdout[-4000:] + compilation.stderr[-4000:])
        execution = subprocess.run([str(stage / 'obj/simulation')], cwd=stage,
                                   text=True, capture_output=True, timeout=600)
        (stage / 'execution.log').write_text(execution.stdout + execution.stderr)
        evidence['execution'] = dict(returncode=execution.returncode, log_sha256=sha(stage / 'execution.log'))
        evidence['source_unchanged'] = all(sha(source) == digest for source, digest in identities.items())
        evidence['component_unchanged'] = all(sha(stage / relative) == digest
                                             for relative, digest in metadata['staged_input_sha256'].items())
        evidence['preparation_inputs_unchanged'] = all(sha(ROOT / relative) == digest
                                                      for relative, digest in metadata['input_sha256'].items())
        (stage / 'input_evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
        self.assertTrue(evidence['source_unchanged'], 'simulation sources changed during execution')
        self.assertTrue(evidence['component_unchanged'], 'staged component changed during execution')
        self.assertTrue(evidence['preparation_inputs_unchanged'], 'component inputs changed during execution')
        self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
        self.assertIn(f'PASS workstation_usb2_input_25k: HS={high_speed}', execution.stdout)
        print(execution.stdout.strip(), flush=True)

    def test_service_adapter_acknowledgment_cancellation_and_session_loss(self):
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-services-') as directory:
            executable = Path(directory) / 'services'
            compilation = subprocess.run(['iverilog', '-g2012', '-s', 'tb_workstation_usb2_service_adapter',
                '-o', str(executable), str(ROOT / 'rtl/workstation/workstation_usb2_service_adapter.sv'),
                str(ROOT / 'sim/usb2/tb_workstation_usb2_service_adapter.sv')],
                text=True, capture_output=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
            execution = subprocess.run(['vvp', str(executable)], text=True, capture_output=True, timeout=10)
            self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
            self.assertIn('PASS workstation_usb2_service_adapter:', execution.stdout)
            print(execution.stdout.strip(), flush=True)

    def test_explicit_input_component_selects_existing_owner_and_locked_support(self):
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-input-prepare-') as directory:
            stage, metadata = prepare(ROOT, Path(directory) / 'stage', firmware_profile='workstation',
                                      component='workstation-input')
            self.assertEqual(json.loads((stage / 'component_inputs.json').read_text()), metadata)
            self.assertEqual(metadata['top_module'], 'workstation_usb2_input')
            self.assertTrue(metadata['input_owner_integrated'])
            self.assertFalse(metadata['workstation_integrated'])
            self.assertFalse(metadata['deployment_allowed'])
            self.assertFalse(metadata['place_route_allowed'])
            self.assertEqual(len(metadata['source_paths']), 29)
            provenance = metadata['input_owner_provenance']
            self.assertEqual(provenance['baseline']['name'], 'resource_rework_route0')
            self.assertEqual(len(provenance['locked_sources']), 4)
            for relative, expected in metadata['staged_input_sha256'].items():
                self.assertEqual(sha(stage / relative), expected, relative)
            self.assertIn('rtl/push2_usb_a_control.sv', metadata['source_paths'])
            self.assertIn('support/workstation/src/usb_host/gw138k_usb_event_fifo.v', metadata['source_paths'])
            self.assertNotIn('sim/usb2/cpu_enumeration.c', metadata['input_sha256'])
            self.assertEqual((stage / 'usb2_soc.sdc').read_text().count('create_clock'), 4)
            self.assertEqual(metadata['clocks_hz']['audio'], 76800000)
            self.assertFalse((stage / 'impl').exists())

    def test_staged_owner_and_locked_support_drift_are_rejected(self):
        for relative in ('rtl/push2_usb_a_control.sv', 'support/workstation/src/usb_host/gw138k_usb_event_fifo.v'):
            with self.subTest(source=relative), tempfile.TemporaryDirectory(prefix='workstation-usb2-input-drift-') as directory:
                output = Path(directory) / 'stage'
                compile_firmware = preparation.stage_usb2_cpu_firmware

                def compile_and_change(*arguments, **keywords):
                    result = compile_firmware(*arguments, **keywords)
                    source = output / relative
                    source.write_bytes(source.read_bytes() + b'\n')
                    return result

                with patch.object(preparation, 'stage_usb2_cpu_firmware', side_effect=compile_and_change):
                    with self.assertRaisesRegex(ValueError, 'staged source identity changed'):
                        prepare(ROOT, output, firmware_profile='workstation', component='workstation-input')
                self.assertFalse((output / 'component_inputs.json').exists())

    def test_input_owner_bundle_drift_and_missing_support_do_not_fall_back(self):
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-input-bundle-') as directory:
            output = Path(directory) / 'missing'
            with patch.object(input_sources, 'input_bundle', side_effect=FileNotFoundError('missing locked support')):
                with self.assertRaisesRegex(FileNotFoundError, 'missing locked support'):
                    prepare(ROOT, output, firmware_profile='workstation', component='workstation-input')
            self.assertFalse(output.exists())
            first = input_sources.input_bundle(ROOT)
            changed = {**first, 'input_sha256': {**first['input_sha256'], 'rtl/push2_usb_a_control.sv': '0' * 64}}
            output = Path(directory) / 'drift'
            with patch.object(input_sources, 'input_bundle', side_effect=(first, changed)):
                with self.assertRaisesRegex(ValueError, 'input-owner sources changed'):
                    prepare(ROOT, output, firmware_profile='workstation', component='workstation-input')
            self.assertFalse((output / 'component_inputs.json').exists())

    @unittest.skipUnless(shutil.which('gw_sh'), 'gw_sh is required for native input synthesis')
    def test_gowin_native_input_exact_rom_resources_and_drift_rejection(self):
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-input-synthesis-') as directory:
            stage, metadata = prepare(ROOT, Path(directory) / 'stage', firmware_profile='workstation',
                                      component='workstation-input')
            execution = subprocess.run(['gw_sh', str(stage / 'synthesis.tcl')], cwd=stage,
                                       text=True, capture_output=True, timeout=180)
            self.assertEqual(execution.returncode, 0, execution.stdout[-4000:] + execution.stderr[-4000:])
            self.assertNotIn('ERROR', execution.stdout + execution.stderr)
            result = preparation.audit_component_synthesis(stage)
            self.assertTrue(result['input_owner_integrated'])
            self.assertEqual(result['register_limit_exclusive'], 4096)
            self.assertEqual(result['sdpb_primitives'], 38)
            self.assertEqual(result['sdpx9b_primitives'], 1)
            self.assertEqual(result['synthesis_bsram_equivalent'], 39)
            self.assertEqual(result['synthesis_ssram'], 82)
            self.assertEqual(result['verified_rom_words'], 16384)
            self.assertFalse(result['deployment_allowed'])
            netlist = stage / 'impl/gwsynthesis/usb2_soc_component.vg'
            original = netlist.read_text()
            pattern = r"(defparam memory_0_memory_0_0_0_s\.INIT_RAM_00=256'h)([0-9A-Fa-f])"
            changed, count = re.subn(pattern, lambda match: match[1] + ('0' if match[2] != '0' else '1'), original)
            self.assertEqual(count, 1)
            netlist.write_text(changed)
            with self.assertRaisesRegex(ValueError, 'synthesized ROM mismatch'):
                preparation.audit_component_synthesis(stage)
            netlist.write_text(original + ''.join(f'\nDFF resource_guard_{index} (.Q());'
                                                  for index in range(4096 - result['registers'])))
            with self.assertRaisesRegex(ValueError, 'resource gate failed'):
                preparation.audit_component_synthesis(stage)
            netlist.write_text(original)
            for changed in (original.replace('SDPX9B storage_storage_0_0_s', 'OTHER storage_storage_0_0_s'),
                            original + '\nSDPX9B unexpected_fifo (.Q());\n'):
                netlist.write_text(changed)
                with self.assertRaisesRegex(ValueError, 'FIFO RAM resource gate failed'):
                    preparation.audit_component_synthesis(stage)
            changed, count = re.subn(r'^module workstation_usb2_input\s*\(', 'module unexpected_top (', original, flags=re.M)
            self.assertEqual(count, 1)
            netlist.write_text(changed)
            with self.assertRaisesRegex(ValueError, 'synthesized top module mismatch'):
                preparation.audit_component_synthesis(stage)
            netlist.write_text(original)
            resource_report = stage / 'impl/gwsynthesis/usb2_soc_component_syn_rsc.xml'
            original_resource = resource_report.read_text()
            resource_report.write_text(original_resource.replace('T_Bsram="39(0)"', 'T_Bsram="38(0)"'))
            with self.assertRaisesRegex(ValueError, 'resource report does not match'):
                preparation.audit_component_synthesis(stage)
            resource_report.write_text(original_resource)
            manifest = stage / 'component_inputs.json'
            for field, value in (('top_module', 'workstation_usb2_soc'),
                                 ('source_paths', metadata['source_paths'][:-1])):
                manifest.write_text(json.dumps({**metadata, field: value}))
                with self.assertRaises(ValueError):
                    preparation.audit_component_synthesis(stage)
            manifest.write_text(json.dumps(metadata))
            copied_owner = stage / 'rtl/push2_usb_a_control.sv'
            copied_owner.write_bytes(copied_owner.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'synthesis input identity changed'):
                preparation.audit_component_synthesis(stage)
            print(f'PASS Gowin native input: {result["sdpb_primitives"]} SDPB + {result["sdpx9b_primitives"]} SDPX9B, '
                  f'{result["synthesis_bsram_equivalent"]} synthesis BSRAM, {result["registers"]} registers, '
                  f'{result["verified_rom_words"]} exact ROM words; ROM, resources, source policy and drift negatives')

    def test_lint_native_composition_keeps_legacy_warnings_separate(self):
        self.assertIsNotNone(shutil.which('verilator'), 'Verilator is required for native input lint')
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-input-lint-') as directory:
            stage, metadata = prepare(ROOT, Path(directory) / 'stage', firmware_profile='workstation',
                                      component='workstation-input')
            command = ['verilator', '--lint-only', '--timing', '--timescale-override', '1ns/1ps', '-Wall', '-Wno-fatal',
                       '--top-module', 'workstation_usb2_input', *(str(stage / relative) for relative in metadata['source_paths'])]
            execution = subprocess.run(command, cwd=stage, text=True, capture_output=True, timeout=60)
            self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
            warnings = re.findall(r'^%Warning-([^:]+): ([^:]+):\d+:\d+: ([^\n]+)', execution.stderr, re.M)
            native_warnings = [(code, str(Path(source).relative_to(stage)), message)
                               for code, source, message in warnings
                               if '/rtl/workstation/' in source or '/rtl/usb2/' in source]
            self.assertEqual(len(native_warnings), 1, native_warnings)
            code, source, message = native_warnings[0]
            self.assertEqual((code, source), ('SYNCASYNCNET', 'rtl/usb2/workstation_usb2_soc.sv'))
            self.assertIn('host.cpu_reset_n', message)
            self.assertNotIn('%Warning-VARHIDDEN', execution.stderr)
            print(f'PASS native input lint: no composition/adapter warnings; {len(warnings)} inherited owner/vendor warnings')

    def test_input_component_requires_business_firmware(self):
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-input-invalid-') as directory:
            output = Path(directory) / 'stage'
            for profile in ('probe', 'unknown'):
                with self.subTest(profile=profile), self.assertRaises(ValueError):
                    prepare(ROOT, output, firmware_profile=profile, component='workstation-input')
                self.assertFalse(output.exists())
            execution = subprocess.run([sys.executable, str(ROOT / 'build.py'), '--usb2-component', 'workstation-input'],
                                       text=True, capture_output=True, timeout=30)
            self.assertEqual(execution.returncode, 2)
            self.assertIn('require --prepare-usb2-soc', execution.stderr)


if __name__ == '__main__':
    unittest.main()
