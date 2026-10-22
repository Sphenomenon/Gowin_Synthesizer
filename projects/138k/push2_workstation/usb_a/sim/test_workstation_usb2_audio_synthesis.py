#!/usr/bin/env python3
"""Synthesis and negative audits for the separate audio component budget."""

from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_usb2_soc import prepare, audit_component_synthesis
from tools.workstation_usb2_audio_audit import audit_audio_component_synthesis, REGISTER_LIMIT_EXCLUSIVE


class AudioSynthesis(unittest.TestCase):
    def test_actual_synthesis_rom_resources_and_fail_closed_audit(self):
        with tempfile.TemporaryDirectory(prefix='workstation-usb2-audio-synthesis-') as directory:
            stage = Path(directory) / 'stage'
            if os.environ.get('GW138K_USB2_AUDIO_SYNTHESIS_INPUT'):
                reference = Path(os.environ['GW138K_USB2_AUDIO_SYNTHESIS_INPUT']).resolve()
                metadata = json.loads((reference / 'component_inputs.json').read_text())
                paths = (*metadata['staged_input_sha256'], 'component_inputs.json',
                         'impl/gwsynthesis/usb2_soc_component.vg', 'impl/gwsynthesis/usb2_soc_component_syn_rsc.xml')
                for relative in paths:
                    destination = stage / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(reference / relative, destination)
            else:
                self.assertIsNotNone(shutil.which('gw_sh'), 'Gowin synthesis is required')
                stage, metadata = prepare(ROOT, stage, firmware_profile='workstation', component='workstation-audio')
                result = subprocess.run(['gw_sh', str(stage / 'synthesis.tcl')], cwd=stage,
                                        text=True, capture_output=True, timeout=600)
                self.assertEqual(result.returncode, 0, result.stdout[-4000:] + result.stderr[-4000:])
                self.assertNotIn('ERROR', result.stdout + result.stderr)
            result = audit_audio_component_synthesis(stage)
            self.assertEqual(result['memory_primitives'], dict(SDPB=75, SDPX9B=1, pROM=21,
                                                               RAM16SDP4=1190, RAM16SDP1=4))
            self.assertEqual(result['synthesis_bsram_equivalent'], 97)
            self.assertEqual(result['synthesis_ssram'], 1194)
            self.assertEqual(result['verified_rom_words'], 16384)
            self.assertLess(result['registers'], REGISTER_LIMIT_EXCLUSIVE)
            self.assertFalse(result['deployment_allowed'])
            self.assertFalse(result['place_route_verified'])
            with self.assertRaisesRegex(ValueError, 'not the explicit USB2 CPU component'):
                audit_component_synthesis(stage)
            netlist = stage / 'impl/gwsynthesis/usb2_soc_component.vg'
            original = netlist.read_text()
            pattern = r"(defparam memory_0_memory_0_0_0_s\.INIT_RAM_00=256'h)([0-9A-Fa-f])"
            changed, count = re.subn(pattern, lambda match: match[1] + ('0' if match[2] != '0' else '1'), original)
            self.assertEqual(count, 1)
            mutations = [
                (changed, 'synthesized ROM mismatch'),
                (original + '\npROM unexpected_rom (.DO());\n', 'RAM/register resource gate failed'),
                (original.replace('SDPX9B storage_storage_0_0_s', 'OTHER storage_storage_0_0_s'),
                 'RAM/register resource gate failed'),
                (original + '\nDPB unexpected_dpb (.DOA());\n', 'RAM/register resource gate failed'),
                (original + '\nSP unexpected_sp (.DO());\n', 'RAM/register resource gate failed'),
                (original + '\npROM hidden_array [0:1] (.DO());\n', 'requires scalar primitive instances'),
                (original.replace('module workstation_usb2_audio (', 'module unexpected_top (', 1),
                 'synthesized top module mismatch'),
                (original + ''.join(f'\nDFF extra_register_{index} (.Q());'
                                    for index in range(REGISTER_LIMIT_EXCLUSIVE - result['registers'])),
                 'RAM/register resource gate failed'),
            ]
            for changed, message in mutations:
                with self.subTest(message=message):
                    self.assertNotEqual(changed, original)
                    netlist.write_text(changed)
                    with self.assertRaisesRegex(ValueError, message):
                        audit_audio_component_synthesis(stage)
            netlist.write_text(original)
            resource = stage / 'impl/gwsynthesis/usb2_soc_component_syn_rsc.xml'
            original_resource = resource.read_text()
            resource.write_text(original_resource.replace('T_Bsram="97(0)"', 'T_Bsram="76(0)"'))
            with self.assertRaisesRegex(ValueError, 'resource report does not match'):
                audit_audio_component_synthesis(stage)
            resource.write_text(original_resource)
            manifest = stage / 'component_inputs.json'
            original_manifest = manifest.read_text()
            for mutation in ('source_policy', 'missing_staged_header', 'release_ready'):
                changed = json.loads(original_manifest)
                if mutation == 'missing_staged_header':
                    del changed['staged_input_sha256']['rtl/ddr_address_map.vh']
                else:
                    changed[mutation] = True
                manifest.write_text(json.dumps(changed))
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    audit_audio_component_synthesis(stage)
            manifest.write_text(original_manifest)
            header = stage / 'rtl/ddr_address_map.vh'
            header.write_text(header.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'synthesis input identity changed'):
                audit_audio_component_synthesis(stage)


if __name__ == '__main__':
    unittest.main()
