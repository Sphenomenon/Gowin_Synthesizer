"""Hermetic guard against accidentally returning to same-process builds."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class BuildDispatch(unittest.TestCase):
    def test_every_build_variant_uses_safe_builder(self):
        wrapper = Path(__file__).with_name('gowin.sh')
        with tempfile.TemporaryDirectory(prefix='gw-dispatch-') as directory:
            root = Path(directory)
            binaries = root/'bin'
            binaries.mkdir()
            ide = root/'ide'
            (ide/'bin').mkdir(parents=True)
            for path, marker in ((binaries/'python3', 'SAFE_BUILDER'),
                                 (ide/'bin/gw_sh', 'DIRECT_QUERY')):
                path.write_text('#!/bin/sh\nprintf "%s\\n" "'+marker+'"\n')
                path.chmod(0o755)
            env = dict(os.environ, PATH=str(binaries)+':'+os.environ['PATH'],
                       GW25K_IDE_DIR=str(ide))
            cases = [('build.tcl', 'SAFE_BUILDER'),
                     ('a/build_gao.tcl', 'SAFE_BUILDER'),
                     ('prj/usb2_device/build_serial_gao.tcl', 'SAFE_BUILDER'),
                     ('build_probe.tcl', 'SAFE_BUILDER'),
                     ('scan.tcl', 'DIRECT_QUERY')]
            for name, expected in cases:
                with self.subTest(name=name):
                    process = subprocess.run(['/bin/sh', str(wrapper), name],
                        capture_output=True, text=True, env=env, check=True)
                    self.assertEqual(process.stdout.strip(), expected)


if __name__ == '__main__':
    unittest.main()
