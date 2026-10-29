#!/usr/bin/env python3
"""Run the real FS host CPU and 25K endpoint over resolved USB1 D+/D- wires."""

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
from tools.stage_usb_firmware import sha, stage_usb_firmware, verify_usb2_cpu_vendor
from tools.workstation_usb1 import HOST_SOURCES, prepare, build

PEER = ROOT.parents[3] / 'projects/25k/example/MIDI_KEYBOARD'


class Usb1Tests(unittest.TestCase):
    def test_explicit_25k_profile_and_drift_rejection(self):
        with tempfile.TemporaryDirectory(prefix='usb1-prepare-') as directory:
            output, metadata = prepare(ROOT, Path(directory) / 'peer', '251028FA', board='25k')
            self.assertFalse(metadata['high_speed_allowed'])
            self.assertFalse(metadata['deployment_allowed'])
            self.assertTrue(metadata['complete_keyboard'])
            self.assertIn('`define MIDI_USB1_FS', (output / 'usb1_profile.vh').read_text())
            timing = (output / 'usb1.sdc').read_text()
            self.assertNotIn('get_ports {ulpi_', timing)
            self.assertLess(timing.index('create_generated_clock'), timing.index('set_max_delay'))
            self.assertNotIn('"clk_ulpi60"', (output / 'usb1.cst').read_text())
            with self.assertRaises(FileExistsError):
                prepare(ROOT, output, '251028FB', board='25k')
            (output / 'usb1_profile.vh').write_text('')
            with self.assertRaisesRegex(ValueError, 'staged input drifted'):
                build(output)

    def test_profiles_are_not_silently_combined(self):
        result = subprocess.run([sys.executable, str(ROOT / 'build.py'), '--usb1-identify',
                                 '--current-workstation'], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('cannot be mixed', result.stderr)

    def test_fs_only_device(self):
        self.run_fs_device(fs_only=True)

    def test_dual_speed_device_reset_tail(self):
        self.run_fs_device(fs_only=False)

    def run_fs_device(self, fs_only):
        with tempfile.TemporaryDirectory(prefix='usb1-device-') as directory:
            executable = Path(directory) / 'device.vvp'
            result = subprocess.run(['iverilog', '-g2012', '-s', 'tb_usb_board_device',
                                     '-Ptb_usb_board_device.HIGH_SPEED=0',
                                     '-Ptb_usb_board_device.FULL_SPEED_ONLY=' + str(int(fs_only)),
                                     '-Irtl/usb_board/vendor', '-o', str(executable), '-c', 'sources.f',
                                     'sim/gowin_io_models.v', 'sim/tb_usb_board_device.v'],
                                    cwd=PEER, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run(['vvp', str(executable)], cwd=PEER, text=True, capture_output=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS USB board UTMI', result.stdout)
            print(result.stdout, flush=True)

    def test_physical_pair(self):
        self.run_physical_pair()

    def test_usb2_device_fallback_pair(self):
        self.run_physical_pair(peer_usb2=True)

    @unittest.skipUnless(os.environ.get('GW_USB1_PEER_SNAPSHOT'), 'explicit released 25K snapshot not selected')
    def test_released_usb2_device_fallback_pair(self):
        snapshot = Path(os.environ['GW_USB1_PEER_SNAPSHOT']).resolve()
        self.assertTrue(os.environ.get('GW_USB1_PEER_MANIFEST'), 'released snapshot requires an explicit build manifest')
        self.assertTrue(os.environ.get('GW_USB1_PEER_MANIFEST_SHA256'), 'released manifest requires its expected SHA256')
        manifest_path = Path(os.environ['GW_USB1_PEER_MANIFEST']).resolve()
        self.assertEqual(sha(manifest_path), os.environ['GW_USB1_PEER_MANIFEST_SHA256'])
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(manifest['configuration']['top'], 'midi_keyboard_top')
        self.assertFalse(manifest['configuration'].get('usb2_probe', False))
        self.assertTrue(all(sha(snapshot / name) == digest for name, digest in manifest['sha256'].items()))
        identity = dict(user_code=manifest['user_code'], source_identity=manifest['source_identity'],
                        configuration=manifest['configuration'], build_manifest_sha256=sha(manifest_path))
        self.run_physical_pair(peer_usb2=True, peer_root=snapshot, released_identity=identity,
                               debug_profile=manifest.get('usb2_debug_profile'))

    def run_physical_pair(self, peer_usb2=False, peer_root=PEER, released_identity=None, debug_profile=None):
        self.assertIsNotNone(shutil.which('verilator'), 'Verilator is required for full CPU/physical FS execution')
        verify_usb2_cpu_vendor(ROOT)
        with tempfile.TemporaryDirectory(prefix='usb1-pair-') as directory:
            output = Path(directory)
            if os.environ.get('GW_USB1_EVIDENCE'):
                output = Path(os.environ['GW_USB1_EVIDENCE']).resolve()
                if peer_usb2:
                    output = output.with_name(output.name + ('-released-usb2' if released_identity else '-usb2'))
                output.mkdir(parents=True, exist_ok=False)
            metadata = stage_usb_firmware(ROOT, output, output, entry='usb1_identify.c')
            if debug_profile:
                header = (peer_root / debug_profile['file']).read_text()
                self.assertEqual(sha(peer_root / debug_profile['file']), debug_profile['input_sha256'])
                self.assertEqual(header.count('`endif'), 1)
                header = header.replace('`endif', ''.join('`define ' + name + '\n' for name in debug_profile['defines']) + '`endif')
                (output / debug_profile['file']).write_text(header)
                self.assertEqual(sha(output / debug_profile['file']), debug_profile['staged_sha256'])
            sources = [ROOT / name for name in HOST_SOURCES if not name.endswith(
                ('.vh', 'workstation_usb1_clock.sv', 'workstation_usb1_identify_top.sv'))]
            excluded = ('midi_usb1_link.v', 'usbf_defs.v')
            sources += [peer_root / name for name in (peer_root / 'sources.f').read_text().splitlines()
                        if '/usb_board/' in name and not name.endswith(
                            excluded)]
            sources += [peer_root / 'rtl/control/panel_display_endpoint.v', ROOT / 'sim/usb1/tb_workstation_usb1_pair.sv']
            sources += [ROOT / 'sim/usb1/usb3300_fs_device_model.sv', ROOT / 'sim/usb1/gowin_usb_pad_models.sv']
            identities = {str(source): sha(source) for source in [*sources,
                          Path(__file__), peer_root / 'sources.f',
                          ROOT / 'vendor/usb_host_fs_8fc3/src/usbh_host_defs.v',
                          peer_root / 'rtl/usb_board/vendor/usbf_defs.v',
                          *([peer_root / 'usb2_debug_profile.vh'] if (peer_root / 'usb2_debug_profile.vh').exists() else [])]}
            command = ['verilator', '--binary', '--timing', '--timescale-override', '1ns/1ps', '-Wno-fatal',
                       '-j', '4', '--top-module', 'tb_workstation_usb1_pair', '--Mdir', str(output / 'obj'),
                       '-o', 'simulation', '-I' + str(ROOT / 'vendor/usb_host_fs_8fc3/src'),
                       '-I' + str(output), '-I' + str(peer_root / 'rtl/usb_board/vendor'), '-I' + str(peer_root),
                       '-GPEER_USB2=' + str(int(peer_usb2)), '-GTRACE=' + str(int(bool(os.environ.get('GW_USB1_TRACE')))),
                       *map(str, sources)]
            compilation = subprocess.run(command, cwd=output, capture_output=True, text=True, timeout=180)
            (output / 'compilation.log').write_text(compilation.stdout + compilation.stderr)
            self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
            result = subprocess.run([str(output / 'obj/simulation')], cwd=output,
                                    capture_output=True, text=True, timeout=600)
            (output / 'execution.log').write_text(result.stdout + result.stderr)
            print('\n'.join(line for line in result.stdout.splitlines() if line.startswith(('PASS ', 'USB1 connection '))), flush=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS USB1 physical FS pair', result.stdout)
            self.assertRegex(result.stdout, r'USB1 FS identify build [0-9a-fA-F]{8}\n')
            self.assertRegex(result.stdout, r'USB1 status [0-9a-fA-F]+ identity [fF][bB]9[bB][fF][bB]9[aA] midi [0-9]+')
            if peer_usb2:
                self.assertIn('PASS USB1 host / USB2 device FS fallback', result.stdout)
            self.assertNotIn('ERROR:', result.stdout)
            self.assertTrue(all(sha(Path(source)) == digest for source, digest in identities.items()))
            self.assertTrue(all(sha(ROOT / name) == digest for name, digest in metadata['live_sha256'].items()))
            evidence = dict(passed=True, firmware=metadata, source_sha256=identities,
                            compilation_command=command,
                            compilation_log_sha256=sha(output / 'compilation.log'),
                            execution_log_sha256=sha(output / 'execution.log'),
                            physical_boundary='digital_resolved_dp_dm_not_board_measurement',
                            application='actual_25k_bridge_and_pl_endpoint_with_tile_completion_model',
                            peer_transport='usb3300_ulpi_model_fs_fallback' if peer_usb2 else 'usb1_fs_only',
                            released_peer=released_identity,
                            debug_profile=debug_profile,
                            generated_debug_header_sha256=sha(output / debug_profile['file']) if debug_profile else None,
                            peer_reset_on_detach=not peer_usb2,
                            hardware_validated=False)
            (output / 'verification.json').write_text(json.dumps(evidence, indent=2) + '\n')
            report = os.environ.get('GW_USB1_REPORT')
            if report:
                Path(report).write_text(json.dumps(evidence, indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
