#!/usr/bin/env python3
"""Actual production workstation C through native USB2 into 25K MIDI/PL RTL."""

from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_usb2_soc import prepare, SOC_SOURCE_PATHS


def midi_sources():
    device = ROOT.parents[2] / '25k/example/MIDI_KEYBOARD'
    return device, [device / relative for relative in (
        'rtl/usb_board/midi_usb_device.v', 'rtl/usb_board/midi_usb_hs_phy.v',
        'rtl/usb_board/generated/usb_composite_desc_rom.v', 'rtl/usb_board/vendor/usbf_sie_tx.v',
        'rtl/usb_board/vendor/usbf_sie_rx.v', 'rtl/usb_board/vendor/usbf_crc16.v',
        'rtl/control/panel_display_endpoint.v',
    )]


class NativeApplication(unittest.TestCase):
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
        for high_speed in (1, 0):
            with self.subTest(high_speed=high_speed), tempfile.TemporaryDirectory(prefix='workstation-usb2-application-') as directory:
                stage, metadata = prepare(ROOT, Path(directory) / 'stage', firmware_profile='workstation',
                                          allow_high_speed=bool(high_speed))
                command = ['verilator', '--binary', '--timing', '--timescale-override', '1ns/1ps', '-Wno-fatal', '-j', '4',
                           '--top-module', 'tb_workstation_usb2_application_25k', '--Mdir', str(stage / 'obj'), '-o', 'simulation',
                           f'-GHIGH_SPEED={high_speed}', '-I' + str(device / 'rtl/usb_board/vendor'),
                           *(str(stage / relative) for relative in SOC_SOURCE_PATHS),
                           *(str(ROOT / 'sim/usb2' / name) for name in ('usb3300_register_model.sv', 'usb3300_packet_model.sv',
                               'usb3300_host_model.sv', 'tb_workstation_usb2_application_25k.sv')),
                           *(str(source) for source in peer_sources)]
                compilation = subprocess.run(command, text=True, capture_output=True, timeout=180)
                self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
                execution = subprocess.run([str(stage / 'obj/simulation')], cwd=stage,
                                           text=True, capture_output=True, timeout=600)
                self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
                self.assertIn(f'PASS workstation_usb2_application_25k: HS={high_speed}', execution.stdout)
                print(execution.stdout.strip(), flush=True)
                print('Application firmware:', json.dumps(metadata['firmware'], sort_keys=True), flush=True)


if __name__ == '__main__':
    unittest.main()
