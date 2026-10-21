#!/usr/bin/env python3
"""Native production CPU to the existing workstation input owner."""

from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_usb2_soc import prepare
from tools.stage_usb_firmware import sha


class NativeInput(unittest.TestCase):
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
            self.assertFalse((stage / 'impl').exists())

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
