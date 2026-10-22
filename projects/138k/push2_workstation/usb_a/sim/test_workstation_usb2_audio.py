#!/usr/bin/env python3
"""Actual USB2 CPU, 25K peer, session, parameters, DSP and delay DMA."""

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
from test_workstation_usb2_application import MODEL_INPUTS, midi_sources


AUDIO_SIMULATION_SOURCES = (*MODEL_INPUTS[:-1], 'sim/usb2/tb_workstation_usb2_audio_25k.sv')


class NativeAudio(unittest.TestCase):
    def test_high_speed_production_audio(self):
        self.run_audio(1)

    def test_full_speed_production_audio(self):
        self.run_audio(0)

    def run_audio(self, high_speed):
        self.assertIsNotNone(shutil.which('verilator'), 'Verilator is required for native audio execution')
        device, peer_sources = midi_sources()
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-audio-execution-') as directory:
            base = Path(directory)
            if os.environ.get('GW138K_USB2_AUDIO_EVIDENCE'):
                base = Path(os.environ['GW138K_USB2_AUDIO_EVIDENCE']).resolve()
                base.mkdir(parents=True, exist_ok=True)
            stage, metadata = prepare(ROOT, base / f'hs_{high_speed}', firmware_profile='workstation',
                                      allow_high_speed=bool(high_speed), component='workstation-audio')
            originals = [*(ROOT / relative for relative in AUDIO_SIMULATION_SOURCES), *peer_sources,
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
            evidence = dict(schema=1, validation_stage='native_audio_execution', high_speed=bool(high_speed),
                            firmware=metadata['firmware'], component_manifest_sha256=sha(stage / 'component_inputs.json'),
                            simulation_input_sha256={str(source.relative_to(ROOT.parents[3])): digest
                                                     for source, digest in identities.items()},
                            verilator_version=subprocess.check_output(['verilator', '--version'], text=True).strip(),
                            audio_boundary='actual_session_parameters_dsp_frame_delivery_reference_serial_and_delay_dma',
                            memory_sink='bounded_stall_native_word_ring_model_not_ddr_controller',
                            display_sink='modeled_tile_completion_not_lcd_bus',
                            physical_dac_compatibility_verified=False,
                            hardware_tested=False, deployment_allowed=False, release_ready=False)
            evidence_file = stage / 'audio_evidence.json'
            command = ['verilator', '--binary', '--timing', '--timescale-override', '1ns/1ps', '-Wno-fatal', '-j', '4',
                       '--top-module', 'tb_workstation_usb2_audio_25k', '--Mdir', str(stage / 'obj'), '-o', 'simulation',
                       f'-GHIGH_SPEED={high_speed}', '-I' + str(stage),
                       '-I' + str(copies[device / 'rtl/usb_board/vendor/usbf_defs.v'].parent),
                       *(str(stage / relative) for relative in metadata['source_paths']),
                       *(str(copies[ROOT / relative]) for relative in AUDIO_SIMULATION_SOURCES),
                       *(str(copies[source]) for source in peer_sources)]
            for label, invocation, timeout in (('compilation', command, 300),
                                                ('execution', [str(stage / 'obj/simulation')], 1800)):
                log_file = stage / (label + '.log')
                evidence[label] = dict(command=invocation, timeout_seconds=timeout)
                evidence_file.write_text(json.dumps(evidence, indent=2) + '\n')
                print(f'Audio HS={high_speed} {label}: {stage}', flush=True)
                with log_file.open('w') as output:
                    try:
                        result = subprocess.run(invocation, cwd=stage, stdout=output, stderr=subprocess.STDOUT,
                                                text=True, timeout=timeout)
                        evidence[label]['returncode'] = result.returncode
                    except subprocess.TimeoutExpired:
                        evidence[label]['timed_out'] = True
                        raise
                    finally:
                        output.flush()
                        evidence[label]['log_sha256'] = sha(log_file)
                        evidence_file.write_text(json.dumps(evidence, indent=2) + '\n')
                self.assertEqual(result.returncode, 0, log_file.read_text()[-6000:])
            evidence['source_unchanged'] = all(sha(source) == digest for source, digest in identities.items())
            evidence['simulation_copies_unchanged'] = all(sha(copies[source]) == digest
                                                          for source, digest in identities.items())
            evidence['component_unchanged'] = all(sha(stage / relative) == digest
                                                 for relative, digest in metadata['staged_input_sha256'].items())
            evidence['preparation_inputs_unchanged'] = all(sha(ROOT / relative) == digest
                                                          for relative, digest in metadata['input_sha256'].items())
            evidence_file.write_text(json.dumps(evidence, indent=2) + '\n')
            for field in ('source_unchanged', 'simulation_copies_unchanged', 'component_unchanged',
                          'preparation_inputs_unchanged'):
                self.assertTrue(evidence[field], field)
            execution_log = (stage / 'execution.log').read_text()
            self.assertIn(f'PASS workstation_usb2_audio_25k: HS={high_speed}', execution_log)
            print(execution_log.strip(), flush=True)


if __name__ == '__main__':
    unittest.main()
