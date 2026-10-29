#!/usr/bin/env python3
"""Production CPU/ULPI/input owner against a simulation-only Push endpoint peer."""

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
from tools.workstation_usb2_soc import prepare
from tools.stage_usb_firmware import sha


SIMULATION_SOURCES = tuple('sim/usb2/' + name for name in (
    'usb3300_register_model.sv', 'usb3300_packet_model.sv', 'usb3300_host_model.sv',
    'usb_push_device_model.sv', 'tb_workstation_usb2_input_push.sv',
))
PEER_SOURCES = tuple('rtl/usb_board/' + name for name in (
    'midi_usb_hs_phy.v', 'vendor/usbf_sie_tx.v', 'vendor/usbf_sie_rx.v', 'vendor/usbf_crc16.v',
))


class NativePushInput(unittest.TestCase):
    def test_high_speed_production_cpu_hotplug(self):
        self.run_push(1)

    def test_full_speed_fallback_production_cpu_hotplug(self):
        self.run_push(0)

    def test_high_speed_production_cpu_complete_frame_after_hotplug(self):
        self.run_push(1, complete_frame=True)

    def run_push(self, high_speed, complete_frame=False):
        self.assertIsNotNone(shutil.which('verilator'), 'Verilator is required for native Push execution')
        device = ROOT.parents[2] / '25k/example/MIDI_KEYBOARD'
        originals = [*(ROOT / relative for relative in SIMULATION_SOURCES),
                     *(device / relative for relative in PEER_SOURCES),
                     device / 'rtl/usb_board/vendor/usbf_defs.v', Path(__file__)]
        identities = {source: sha(source) for source in originals}
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-push-') as directory:
            base = Path(os.environ.get('GW138K_USB2_PUSH_EVIDENCE', directory)).resolve()
            base.mkdir(parents=True, exist_ok=True)
            suffix = f'hs_{high_speed}' + ('_complete_frame' if complete_frame else '')
            stage, metadata = prepare(ROOT, base / suffix, firmware_profile='workstation',
                                      allow_high_speed=bool(high_speed), component='workstation-input')
            copies = {}
            for source in originals:
                target = stage / 'simulation' / source.relative_to(ROOT.parents[3])
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                self.assertEqual(sha(target), identities[source])
                copies[source] = target
            command = ['verilator', '--binary', '--timing', '--timescale-override', '1ns/1ps', '-Wno-fatal',
                       '-j', '4', '--top-module', 'tb_workstation_usb2_input_push', '--Mdir', str(stage / 'obj'),
                       '-o', 'simulation', f'-GHIGH_SPEED={high_speed}',
                       f'-GCOMPLETE_FINAL_FRAME={int(complete_frame)}',
                       '-I' + str(copies[device / 'rtl/usb_board/vendor/usbf_defs.v'].parent),
                       *(str(stage / relative) for relative in metadata['source_paths']),
                       *(str(copies[ROOT / relative]) for relative in SIMULATION_SOURCES),
                       *(str(copies[device / relative]) for relative in PEER_SOURCES)]
            evidence = dict(schema=1, validation_stage='native_input_push_peer_simulation',
                            high_speed=bool(high_speed), firmware=metadata['firmware'],
                            component_manifest_sha256=sha(stage / 'component_inputs.json'),
                            simulation_input_sha256={str(source.relative_to(ROOT.parents[3])): digest
                                                     for source, digest in identities.items()},
                            peer='synthetic_Push_control_EP0_display_EP1_MIDI_EP2_not_physical_device',
                            descriptor_source='synthetic_minimal_not_captured_Push_descriptors',
                            display_scope=('complete_wire_frame_after_reconnect_not_image_reference' if complete_frame
                                           else 'partial_frame_and_reconnect_header_not_complete_image'),
                            service_boundary='actual_push2_usb_a_control_and_event_fifo_cdc',
                            audio_sink='backpressured_stream_checker_not_dsp',
                            verilator_version=subprocess.check_output(['verilator', '--version'], text=True).strip(),
                            hardware_tested=False, full_frame_validated=False,
                            deployment_allowed=False, release_ready=False)
            evidence_path = stage / 'push_evidence.json'
            compilation = subprocess.run(command, text=True, capture_output=True, timeout=180)
            (stage / 'compilation.log').write_text(compilation.stdout + compilation.stderr)
            evidence['compilation'] = dict(command=command, returncode=compilation.returncode,
                                           log_sha256=sha(stage / 'compilation.log'))
            evidence_path.write_text(json.dumps(evidence, indent=2) + '\n')
            self.assertEqual(compilation.returncode, 0, compilation.stdout[-4000:] + compilation.stderr[-4000:])
            execution = subprocess.run([str(stage / 'obj/simulation')], cwd=stage,
                                       text=True, capture_output=True, timeout=1800 if complete_frame else 600)
            (stage / 'execution.log').write_text(execution.stdout + execution.stderr)
            evidence['execution'] = dict(returncode=execution.returncode, log_sha256=sha(stage / 'execution.log'))
            evidence['full_frame_validated'] = (complete_frame and execution.returncode == 0 and
                                                'complete_frames=1' in execution.stdout)
            evidence['source_unchanged'] = all(sha(source) == digest for source, digest in identities.items())
            evidence['simulation_copy_unchanged'] = all(sha(copies[source]) == digest
                                                       for source, digest in identities.items())
            evidence['component_unchanged'] = all(sha(stage / relative) == digest
                                                 for relative, digest in metadata['staged_input_sha256'].items())
            evidence['preparation_inputs_unchanged'] = all(sha(ROOT / relative) == digest
                                                          for relative, digest in metadata['input_sha256'].items())
            evidence_path.write_text(json.dumps(evidence, indent=2) + '\n')
            for field in ('source_unchanged', 'simulation_copy_unchanged', 'component_unchanged',
                          'preparation_inputs_unchanged'):
                self.assertTrue(evidence[field], field)
            self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
            self.assertIn(f'PASS workstation_usb2_input_push: HS={high_speed}', execution.stdout)
            if complete_frame:
                self.assertTrue(evidence['full_frame_validated'], 'complete wire frame not observed')
            print(execution.stdout.strip(), flush=True)


if __name__ == '__main__':
    unittest.main()
