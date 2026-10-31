#!/usr/bin/env python3
"""Exercise actual serial pins and completed-frame identity at both rates."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SerializerTest(unittest.TestCase):
    def test_source_hold(self):
        for tool in ("iverilog", "vvp"):
            self.assertIsNotNone(shutil.which(tool), f"required tool missing: {tool}")
        with tempfile.TemporaryDirectory(prefix="gw138k-i2s-hold-") as temp:
            binary = Path(temp) / "test.vvp"
            subprocess.run([
                "iverilog", "-g2012", "-s", "tb_workstation_i2s_source_hold", "-o", str(binary),
                str(ROOT / "rtl/audio/workstation_i2s_serializer.sv"),
                str(ROOT / "sim/audio/tb_workstation_i2s_source_hold.sv"),
            ], check=True)
            result = subprocess.run(["vvp", str(binary)], text=True, capture_output=True)
            print(result.stdout, end="")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS dual-rate source hold", result.stdout)

    def test_serial_frames(self):
        for tool in ("iverilog", "vvp"):
            self.assertIsNotNone(shutil.which(tool), f"required tool missing: {tool}")
        with tempfile.TemporaryDirectory(prefix="gw138k-i2s-") as temp:
            binary = Path(temp) / "test.vvp"
            subprocess.run([
                "iverilog", "-g2012", "-s", "tb_workstation_i2s_serializer", "-o", str(binary),
                str(ROOT / "rtl/audio/workstation_i2s_serializer.sv"),
                str(ROOT / "sim/audio/tb_workstation_i2s_serializer.sv"),
            ], check=True)
            result = subprocess.run(["vvp", str(binary)], text=True, capture_output=True)
            print(result.stdout, end="")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS dual-rate I2S", result.stdout)


if __name__ == "__main__":
    unittest.main()
