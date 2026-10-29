#!/usr/bin/env python3
"""Real input owner and CDC regression for delayed attachment PANIC feedback."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
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
from tools.workstation_custom_board_audit import audit_native_feedback


class FeedbackClockAudit(unittest.TestCase):
    def test_source_destination_and_inventory_are_fail_closed(self):
        prefix = 'u_native_usb/input_owner/feedback/'
        clocks = dict(clocks=dict(audio_76m8=dict(net='audio'), usb_48m=dict(net='cpu')))
        pins = {prefix + 'held_data_287_s0': 'audio', prefix + 'ack_meta_s0': 'audio',
                prefix + 'request_toggle_s1': 'audio', prefix + 'req_meta_s0': 'cpu',
                prefix + 'destination_data_287_s0': 'cpu', prefix + 'destination_valid_s0': 'cpu'}
        netlist = SimpleNamespace(cells={name: dict(kind='DFFCE') for name in pins},
                                  pin=lambda name, port: pins[name])
        with patch('tools.workstation_custom_board_audit.SynthesisNetlist', return_value=netlist):
            result = audit_native_feedback('', clocks)
            self.assertTrue(result['source_domain_verified'])
            self.assertFalse(result['physical_timing_verified'])
            for register, bad_clock, message in (('held_data_287_s0', 'ref50', 'original audio'),
                                                  ('req_meta_s0', 'ref50', 'input-owner CPU')):
                name = prefix + register
                original = pins[name]
                pins[name] = bad_clock
                with self.subTest(register=register), self.assertRaisesRegex(ValueError, message):
                    audit_native_feedback('', clocks)
                pins[name] = original
            for register in ('held_data_287_s0', 'destination_data_287_s0', 'destination_valid_s0'):
                name = prefix + register
                original = netlist.cells.pop(name)
                with self.subTest(register=register), self.assertRaisesRegex(ValueError, 'inventory changed'):
                    audit_native_feedback('', clocks)
                netlist.cells[name] = original
            netlist.cells[prefix + 'unreviewed_s0'] = dict(kind='DFFCE')
            with self.assertRaisesRegex(ValueError, 'inventory changed'):
                audit_native_feedback('', clocks)


class FeedbackFence(unittest.TestCase):
    def test_direct_audio_feedback_preserves_release_with_old_chain_negative_control(self):
        with tempfile.TemporaryDirectory(prefix='workstation-feedback-fence-') as directory:
            base = Path(os.environ.get('GW138K_USB2_FEEDBACK_EVIDENCE', directory)).resolve()
            stage, metadata = prepare(ROOT, base / 'fence', firmware_profile='workstation',
                                      component='workstation-input')
            original = ROOT / 'sim/usb2/tb_workstation_usb2_feedback_fence.sv'
            bench = stage / original.name
            shutil.copyfile(original, bench)
            inputs = {original: sha(original), Path(__file__): sha(Path(__file__))}
            command = ['verilator', '--binary', '--timing', '--timescale-override', '1ns/1ps', '-Wno-fatal',
                       '-j', '4', '--top-module', 'tb_workstation_usb2_feedback_fence', '--Mdir', str(stage / 'obj'),
                       '-o', 'simulation', *(str(stage / relative) for relative in metadata['source_paths']), str(bench)]
            compilation = subprocess.run(command, capture_output=True, text=True, timeout=180)
            (stage / 'compilation.log').write_text(compilation.stdout + compilation.stderr)
            self.assertEqual(compilation.returncode, 0, compilation.stdout[-2000:] + compilation.stderr[-4000:])
            execution = subprocess.run([str(stage / 'obj/simulation')], cwd=stage,
                                       capture_output=True, text=True, timeout=120)
            (stage / 'execution.log').write_text(execution.stdout + execution.stderr)
            checks = dict(source_unchanged=all(sha(source) == digest for source, digest in inputs.items()),
                          bench_unchanged=sha(bench) == inputs[original],
                          component_unchanged=all(sha(stage / relative) == digest
                                                 for relative, digest in metadata['staged_input_sha256'].items()),
                          prepare_inputs_unchanged=all(sha(ROOT / relative) == digest
                                                       for relative, digest in metadata['input_sha256'].items()))
            result = dict(scope='real_owner_and_CDC_with_modeled_audio_epoch_not_CPU_DSP_or_hardware',
                          compilation_returncode=compilation.returncode, execution_returncode=execution.returncode,
                          execution_sha256=sha(stage / 'execution.log'), component_manifest_sha256=sha(stage / 'component_inputs.json'),
                          simulation_sha256={str(source): digest for source, digest in inputs.items()},
                          checks=checks, hardware_tested=False, deployment_allowed=False, release_ready=False)
            (stage / 'feedback_evidence.json').write_text(json.dumps(result, indent=2) + '\n')
            self.assertTrue(all(checks.values()), checks)
            self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
            self.assertIn('PASS feedback fence:', execution.stdout)
            print(execution.stdout.strip(), flush=True)


if __name__ == '__main__':
    unittest.main()
