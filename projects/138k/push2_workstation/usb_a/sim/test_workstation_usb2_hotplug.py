#!/usr/bin/env python3
"""One production CPU alternates real 25K MIDI/PL RTL and a modeled Push peer."""

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
from test_workstation_usb2_application import midi_sources
from workstation_usb2_audio_inputs import stage_audio


SIMULATION_SOURCES = tuple('sim/usb2/' + name for name in (
    'usb3300_register_model.sv', 'usb3300_packet_model.sv', 'usb3300_host_model.sv',
    'usb_push_device_model.sv', 'tb_workstation_usb2_mixed_hotplug.sv',
))


class MixedHotplug(unittest.TestCase):
    def test_one_cpu_high_speed_alternating_devices(self):
        self.run_hotplug(1)

    def test_one_cpu_full_speed_fallback_alternating_devices(self):
        self.run_hotplug(0)

    def test_high_speed_complete_frame_after_alternating_devices(self):
        self.run_hotplug(1, complete_frame=True)

    @unittest.skipUnless(os.environ.get('GW138K_USB2_AUDIO_INPUT'), 'explicit audited native audio candidate required')
    def test_high_speed_alternating_devices_with_real_serial_audio(self):
        self.run_hotplug(1, complete_frame=True, audio_core=True)

    @unittest.skipUnless(os.environ.get('GW138K_USB2_AUDIO_INPUT'), 'explicit audited native audio candidate required')
    def test_full_speed_alternating_devices_with_real_serial_audio(self):
        self.run_hotplug(0, complete_frame=True, audio_core=True)

    def run_hotplug(self, high_speed, complete_frame=False, audio_core=False):
        self.assertIsNotNone(shutil.which('verilator'), 'Verilator is required for mixed-peer execution')
        if audio_core:
            self.assertTrue(complete_frame, 'real audio hotplug must include the final complete Push frame')
            self.assertIn('GW138K_USB2_AUDIO_INPUT', os.environ, 'explicit audited native audio candidate required')
        device, peer_sources = midi_sources()
        simulation_sources = SIMULATION_SOURCES + (('sim/usb2/workstation_usb2_audio_sink.sv',) if audio_core else ())
        originals = [*(ROOT / relative for relative in simulation_sources), *peer_sources,
                     device / 'rtl/usb_board/vendor/usbf_defs.v', Path(__file__),
                     Path(__file__).with_name('test_workstation_usb2_application.py'),
                     Path(__file__).with_name('workstation_usb2_audio_inputs.py')]
        identities = {source: sha(source) for source in originals}
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-hotplug-') as directory:
            base = Path(os.environ.get('GW138K_USB2_HOTPLUG_EVIDENCE', directory)).resolve()
            base.mkdir(parents=True, exist_ok=True)
            suffix = '_audio' if audio_core else '_complete_frame' if complete_frame else ''
            stage, metadata = prepare(ROOT, base / f'hs_{high_speed}{suffix}', firmware_profile='workstation',
                                      allow_high_speed=bool(high_speed), component='workstation-input')
            audio_sources, audio_evidence, audio_originals, audio_copies = [], {}, {}, {}
            if audio_core:
                audio_sources, audio_evidence, audio_originals, audio_copies = stage_audio(
                    os.environ['GW138K_USB2_AUDIO_INPUT'], stage)
            copies = {}
            for source in originals:
                target = stage / 'simulation' / source.relative_to(ROOT.parents[3])
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                self.assertEqual(sha(target), identities[source])
                copies[source] = target
            command = ['verilator', '--binary', '--timing', '--timescale-override', '1ns/1ps', '-Wno-fatal',
                       '-j', '4', '--top-module', 'tb_workstation_usb2_mixed_hotplug', '--Mdir', str(stage / 'obj'),
                       '-o', 'simulation', f'-GHIGH_SPEED={high_speed}',
                       f'-GCOMPLETE_FINAL_FRAME={int(complete_frame)}', f'-GAUDIO_CORE={int(audio_core)}',
                       '-I' + str(stage / 'audio_inputs'),
                       '-I' + str(copies[device / 'rtl/usb_board/vendor/usbf_defs.v'].parent),
                       *(str(stage / relative) for relative in metadata['source_paths']),
                       *(str(copies[ROOT / relative]) for relative in simulation_sources),
                       *(str(copies[source]) for source in peer_sources), *(str(source) for source in audio_sources)]
            evidence = dict(schema=1, validation_stage='native_input_mixed_peer_hotplug_simulation',
                            high_speed=bool(high_speed), firmware=metadata['firmware'],
                            component_manifest_sha256=sha(stage / 'component_inputs.json'),
                            simulation_input_sha256={str(source.relative_to(ROOT.parents[3])): digest
                                                     for source, digest in identities.items()},
                            sequence=['25k', 'push', '25k', 'push'], cpu_reset_between_connections=False,
                            physical_link='one_shared_USB3300_model_not_four_independent_sessions',
                            panel_peer='actual_25K_MIDI_PL_RTL_with_modeled_tile_completion',
                            push_peer='synthetic_Push_EP0_EP1_EP2_not_physical_device',
                            audio_sink=('native_session_parameters_DSP_frame_delivery_output_router_FPC_I2S'
                                        if audio_core else 'backpressured_event_checker_not_DSP_or_serial_audio'),
                            native_audio_inputs=audio_evidence,
                            display_scope=('PL_restart_and_complete_Push_transport_frame_not_physical_image'
                                           if complete_frame else 'PL_restart_and_partial_Push_frame_not_complete_image'),
                            verilator_version=subprocess.check_output(['verilator', '--version'], text=True).strip(),
                            hardware_tested=False, full_frame_validated=False, real_audio_validated=False,
                            deployment_allowed=False, release_ready=False)
            evidence_path = stage / 'hotplug_evidence.json'
            compilation = subprocess.run(command, text=True, capture_output=True, timeout=600 if audio_core else 180)
            (stage / 'compilation.log').write_text(compilation.stdout + compilation.stderr)
            evidence['compilation'] = dict(command=command, returncode=compilation.returncode,
                                           log_sha256=sha(stage / 'compilation.log'))
            evidence_path.write_text(json.dumps(evidence, indent=2) + '\n')
            self.assertEqual(compilation.returncode, 0, compilation.stdout[-4000:] + compilation.stderr[-4000:])
            timed_out = False
            with (stage / 'execution.log').open('w') as log:
                try:
                    execution = subprocess.run([str(stage / 'obj/simulation')], cwd=stage,
                                               text=True, stdout=log, stderr=subprocess.STDOUT,
                                               timeout=7200 if audio_core else 1800 if complete_frame else 900)
                    returncode = execution.returncode
                except subprocess.TimeoutExpired:
                    timed_out = True
                    returncode = None
            execution_log = (stage / 'execution.log').read_text()
            evidence['execution'] = dict(returncode=returncode, timed_out=timed_out,
                                         log_sha256=sha(stage / 'execution.log'))
            evidence['source_unchanged'] = all(sha(source) == digest for source, digest in identities.items())
            evidence['simulation_copy_unchanged'] = all(sha(copies[source]) == digest
                                                       for source, digest in identities.items())
            evidence['component_unchanged'] = all(sha(stage / relative) == digest
                                                 for relative, digest in metadata['staged_input_sha256'].items())
            evidence['preparation_inputs_unchanged'] = all(sha(ROOT / relative) == digest
                                                          for relative, digest in metadata['input_sha256'].items())
            evidence['audio_sources_unchanged'] = all(sha(source) == digest for source, digest in audio_originals.items())
            evidence['audio_copies_unchanged'] = all(sha(source) == digest for source, digest in audio_copies.items())
            evidence['audio_preparation_inputs_unchanged'] = all(
                sha(ROOT / relative) == digest for relative, digest in audio_evidence.get('source_snapshot_sha256', {}).items())
            evidence['audio_bluetooth_inputs_unchanged'] = all(
                sha(ROOT.parents[3] / relative) == digest
                for relative, digest in audio_evidence.get('bluetooth_source_snapshot_sha256', {}).items())
            evidence['full_frame_validated'] = complete_frame and returncode == 0 and 'complete_frames=1' in execution_log
            evidence['real_audio_validated'] = audio_core and returncode == 0 and 'real_audio=1' in execution_log
            evidence_path.write_text(json.dumps(evidence, indent=2) + '\n')
            for field in ('source_unchanged', 'simulation_copy_unchanged', 'component_unchanged',
                          'preparation_inputs_unchanged', 'audio_sources_unchanged', 'audio_copies_unchanged',
                          'audio_preparation_inputs_unchanged', 'audio_bluetooth_inputs_unchanged'):
                self.assertTrue(evidence[field], field)
            self.assertFalse(timed_out, 'mixed hotplug execution timed out: ' + execution_log[-4000:])
            self.assertEqual(returncode, 0, execution_log[-6000:])
            self.assertIn(f'PASS workstation_usb2_mixed_hotplug: HS={high_speed}', execution_log)
            if complete_frame:
                self.assertTrue(evidence['full_frame_validated'])
            if audio_core:
                self.assertTrue(evidence['real_audio_validated'])
            print(execution_log.strip(), flush=True)


if __name__ == '__main__':
    unittest.main()
