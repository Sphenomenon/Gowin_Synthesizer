#!/usr/bin/env python3
"""Actual production workstation C through native USB2 into 25K MIDI/PL RTL."""

from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_usb2_soc import prepare, SOC_SOURCE_PATHS
from tools.stage_usb_firmware import sha


MODEL_INPUTS = tuple('sim/usb2/' + name for name in (
    'usb3300_register_model.sv', 'usb3300_packet_model.sv', 'usb3300_host_model.sv',
    'tb_workstation_usb2_application_25k.sv',
))


def midi_sources():
    device = ROOT.parents[2] / '25k/example/MIDI_KEYBOARD'
    return device, [device / relative for relative in (
        'rtl/usb_board/midi_usb_device.v', 'rtl/usb_board/midi_usb_hs_phy.v',
        'rtl/usb_board/generated/usb_composite_desc_rom.v', 'rtl/usb_board/vendor/usbf_sie_tx.v',
        'rtl/usb_board/vendor/usbf_sie_rx.v', 'rtl/usb_board/vendor/usbf_crc16.v',
        'rtl/control/panel_display_endpoint.v',
    )]


class NativeApplication(unittest.TestCase):
    def test_phy_model_keeps_pullup_during_full_speed_fallback(self):
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-pullup-') as directory:
            executable = Path(directory) / 'pullup'
            sources = [ROOT / relative for relative in MODEL_INPUTS[:-1]]
            sources.append(ROOT / 'sim/usb2/tb_usb3300_host_model_pullup.sv')
            compilation = subprocess.run(['iverilog', '-g2012', '-s', 'tb_usb3300_host_model_pullup',
                                          '-o', str(executable), *(str(source) for source in sources)],
                                         text=True, capture_output=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
            execution = subprocess.run(['vvp', str(executable)], text=True, capture_output=True, timeout=10)
            self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
            self.assertIn('PASS usb3300_host_model_pullup: 10', execution.stdout)
            print(execution.stdout.strip(), flush=True)

    def test_production_push_frame_packetization(self):
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-push-frame-') as directory:
            executable = Path(directory) / 'push_frame'
            vendor = ROOT / 'vendor/usb_host_fs_8fc3/firmware'
            command = ['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                       '-I' + str(ROOT / 'drivers/usb2'), '-I' + str(vendor), '-I' + str(vendor / 'usb'),
                       str(ROOT / 'sim/usb2/test_workstation_usb2_firmware.c'), '-o', str(executable)]
            compilation = subprocess.run(command, text=True, capture_output=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
            execution = subprocess.run([str(executable)], text=True, capture_output=True, timeout=10)
            self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
            self.assertIn('PASS workstation_usb2_firmware:', execution.stdout)
            print(execution.stdout.strip(), flush=True)

    def test_transaction_adapter_bounds_toggles_and_nyet(self):
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-backend-') as directory:
            executable = Path(directory) / 'backend'
            command = ['gcc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-pedantic', '-fsanitize=address,undefined',
                       '-I' + str(ROOT / 'drivers/usb2'), '-I' + str(ROOT / 'vendor/usb_host_fs_8fc3/firmware/usb'),
                       str(ROOT / 'drivers/usb2/workstation_usb2_backend.c'),
                       str(ROOT / 'sim/usb2/test_workstation_usb2_backend.c'), '-o', str(executable)]
            compilation = subprocess.run(command, text=True, capture_output=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
            execution = subprocess.run([str(executable)], text=True, capture_output=True, timeout=10)
            self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
            self.assertIn('PASS workstation_usb2_backend:', execution.stdout)
            print(execution.stdout.strip(), flush=True)

    def test_production_main_with_actual_25k_midi_and_pl(self):
        self.assertIsNotNone(shutil.which('verilator'), 'Verilator is required for production CPU execution')
        device, peer_sources = midi_sources()
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-application-') as directory:
            base = Path(directory)
            if os.environ.get('GW138K_USB2_APPLICATION_EVIDENCE'):
                base = Path(os.environ['GW138K_USB2_APPLICATION_EVIDENCE']).resolve()
                base.mkdir(parents=True, exist_ok=False)
            for high_speed in (1, 0):
                with self.subTest(high_speed=high_speed):
                    self.run_production_application(base, high_speed, device, peer_sources)

    def run_production_application(self, base, high_speed, device, peer_sources):
        stage, metadata = prepare(ROOT, base / f'hs_{high_speed}', firmware_profile='workstation',
                                  allow_high_speed=bool(high_speed))
        originals = [*(ROOT / relative for relative in MODEL_INPUTS), *peer_sources,
                     device / 'rtl/usb_board/vendor/usbf_defs.v', Path(__file__)]
        identities = {source: sha(source) for source in originals}
        copies = {}
        for source in originals:
            target = stage / 'simulation' / source.relative_to(ROOT.parents[3])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            self.assertEqual(sha(target), identities[source], str(source))
            copies[source] = target
        evidence = dict(schema=1, validation_stage='production_application_simulation',
                        high_speed=bool(high_speed), firmware=metadata['firmware'],
                        component_manifest_sha256=sha(stage / 'component_inputs.json'),
                        simulation_input_sha256={str(source.relative_to(ROOT.parents[3])): digest
                                                 for source, digest in identities.items()},
                        verilator_version=subprocess.check_output(['verilator', '--version'], text=True).strip(),
                        service_boundary='delayed_mock_not_workstation_owner', hardware_tested=False,
                        deployment_allowed=False, release_ready=False)
        command = ['verilator', '--binary', '--timing', '--timescale-override', '1ns/1ps', '-Wno-fatal', '-j', '4',
                   '--top-module', 'tb_workstation_usb2_application_25k', '--Mdir', str(stage / 'obj'), '-o', 'simulation',
                   f'-GHIGH_SPEED={high_speed}', '-I' + str(copies[device / 'rtl/usb_board/vendor/usbf_defs.v'].parent),
                   *(str(stage / relative) for relative in SOC_SOURCE_PATHS),
                   *(str(copies[ROOT / relative]) for relative in MODEL_INPUTS),
                   *(str(copies[source]) for source in peer_sources)]
        compilation = subprocess.run(command, text=True, capture_output=True, timeout=180)
        (stage / 'compilation.log').write_text(compilation.stdout + compilation.stderr)
        evidence['compilation'] = dict(command=command, returncode=compilation.returncode,
                                       log_sha256=sha(stage / 'compilation.log'))
        (stage / 'application_evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
        self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
        execution = subprocess.run([str(stage / 'obj/simulation')], cwd=stage,
                                   text=True, capture_output=True, timeout=600)
        (stage / 'execution.log').write_text(execution.stdout + execution.stderr)
        evidence['execution'] = dict(returncode=execution.returncode, log_sha256=sha(stage / 'execution.log'))
        evidence['source_unchanged'] = all(sha(source) == digest for source, digest in identities.items())
        (stage / 'application_evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
        self.assertTrue(evidence['source_unchanged'], 'simulation sources changed during execution')
        self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
        self.assertIn(f'PASS workstation_usb2_application_25k: HS={high_speed}', execution.stdout)
        print(execution.stdout.strip(), flush=True)
        print('Application firmware:', json.dumps({key: metadata['firmware'][key] for key in (
            'isa', 'rom_sha256', 'firmware_bytes', 'static_ram_end', 'high_speed_allowed')}, sort_keys=True), flush=True)


if __name__ == '__main__':
    unittest.main()
