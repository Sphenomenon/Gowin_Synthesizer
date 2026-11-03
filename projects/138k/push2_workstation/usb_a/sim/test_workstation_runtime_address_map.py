"""Compile the shared DDR guard with the actual runtime map installation."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_recording_policy import (
    MAP_DESTINATION, address_map_inputs, install_address_map, verify_address_map,
)


class RuntimeAddressMap(unittest.TestCase):
    def test_old_map_fails_new_guard_and_authoritative_install_passes(self):
        original, selected = address_map_inputs(ROOT)
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            target = stage / MAP_DESTINATION
            target.parent.mkdir(parents=True)
            target.write_bytes(original)
            guard = ROOT / 'rtl/ddr_address_map_guard.v'
            command = ['iverilog', '-g2012', '-s', 'ddr_address_map_guard',
                       '-o', str(stage / 'guard'), str(guard)]
            old = subprocess.run(command, cwd=stage, capture_output=True, text=True)
            self.assertNotEqual(old.returncode, 0)
            self.assertIn('PRJ1_DDR_BLE_PCM', old.stderr)
            evidence = install_address_map(ROOT, stage)
            verify_address_map(ROOT, stage, evidence)
            current = subprocess.run(command, cwd=stage, capture_output=True, text=True)
            self.assertEqual(current.returncode, 0, current.stdout + current.stderr)
            self.assertEqual(target.read_bytes(), selected)
            target.write_bytes(selected + b'\n')
            with self.assertRaisesRegex(ValueError, 'provenance changed'):
                verify_address_map(ROOT, stage, evidence)


if __name__ == '__main__':
    unittest.main()
