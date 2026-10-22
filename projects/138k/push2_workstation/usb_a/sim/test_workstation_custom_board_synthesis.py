#!/usr/bin/env python3
"""Actual native full-profile synthesis and independent fail-closed audits."""

from pathlib import Path
from unittest.mock import patch
import copy
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
from tools import workstation_custom_board as integration
from tools import workstation_custom_board_audit as verification
from tools import workstation_pinout as pinout
from test_workstation_pinout import fixture


class NativeSynthesis(unittest.TestCase):
    def test_actual_synthesis_and_rejected_corruptions(self):
        with tempfile.TemporaryDirectory(prefix='native-full-synthesis-audit-') as directory:
            output = Path(directory) / 'candidate'
            if os.environ.get('GW138K_CUSTOM_SYNTHESIS_INPUT'):
                shutil.copytree(Path(os.environ['GW138K_CUSTOM_SYNTHESIS_INPUT']), output)
            else:
                profile, payloads, _ = fixture()
                netlists = {role: pinout.Netlist(payload) for role, payload in payloads.items()}
                identities = {role: dict(profile['sources'][role], sha256=pinout.digest(payload))
                              for role, payload in payloads.items()}
                with patch.object(pinout, 'load_sources', return_value=(netlists, identities)):
                    integration.prepare(ROOT, Path(directory) / 'netlists', output)
                script = output / 'workstation/Prj1/scripts/custom_board_synthesis.tcl'
                with (output / 'synthesis.log').open('w') as log:
                    result = subprocess.run(['gw_sh', str(script)], stdout=log, stderr=subprocess.STDOUT,
                                            text=True, timeout=1200)
                self.assertEqual(result.returncode, 0, (output / 'synthesis.log').read_text()[-4000:])
            result = verification.audit(output)
            self.assertEqual(result['resources'], dict(Register=46750, Lut=58868, Alu=13217, Bsram=201,
                                                       Ssram=1455, MULTALU27X18=45, MULT12X12=40, MULT27X36=45,
                                                       self_bsram=0, subtree_bsram=201))
            self.assertEqual(result['verified_rom_words'], 16384)
            self.assertEqual(result['port_coverage']['logical_location_entries'], 101)
            self.assertEqual(result['port_coverage']['physical_port_bits'], 110)
            self.assertFalse(result['release_ready'])
            self.assertFalse(result['deployment_allowed'])
            clocks = result['explicit_clock_audit']
            self.assertEqual(len(clocks['clocks']), 11)
            self.assertEqual(sum(clock.get('verified', False) for clock in clocks['clocks'].values()), 8)
            self.assertEqual(clocks['deferred_opaque_ip_targets'],
                             ['u_memory/u_ddr3/gw3_top/u_ddr_phy_top/fclkdiv/CLKOUT'])
            self.assertFalse(clocks['source_netlist_verified'])
            self.assertFalse(clocks['routed_timing_verified'])
            manifest = output / 'integration_inputs.json'
            original = json.loads(manifest.read_text())
            mutations = []
            for flag in verification.DISALLOWED:
                changed = copy.deepcopy(original)
                changed[flag] = True
                mutations.append((changed, 'not board acceptance'))
            for field, value, message in (
                    ('bitstream_sha256', '0' * 64, 'preparation policy'),
                    ('tmds_polarity_inverted', [False] * 4, 'preparation policy'),
                    ('electrical_blocked', False, 'electrical blocking'),
                    ('source_policy', 'accepted_full83', 'preparation policy')):
                changed = copy.deepcopy(original)
                changed[field] = value
                mutations.append((changed, message))
            changed = copy.deepcopy(original)
            changed['source_snapshot_sha256']['firmware.c'] = '0' * 64
            mutations.append((changed, 'source snapshot changed'))
            changed = copy.deepcopy(original)
            del changed['source_snapshot_sha256']['tools/workstation_custom_board.py']
            mutations.append((changed, 'lost required provenance'))
            changed = copy.deepcopy(original)
            del changed['staged_input_sha256']['constraints/custom_138k.sdc']
            mutations.append((changed, 'compiler closure lost'))
            changed = copy.deepcopy(original)
            changed['enabled_inputs'].append(changed['enabled_inputs'][0])
            mutations.append((changed, 'GPRJ input selection'))
            changed = copy.deepcopy(original)
            changed['firmware']['high_speed_allowed'] = not original['high_speed_allowed']
            mutations.append((changed, 'business firmware profile'))
            for changed, message in mutations:
                with self.subTest(message=message):
                    manifest.write_text(json.dumps(changed))
                    with self.assertRaisesRegex(ValueError, message):
                        verification.audit(output)
            manifest.write_text(json.dumps(original))
            stage = output / 'workstation/Prj1'
            source = stage / 'rtl/display_data/workstation_custom_dvi.sv'
            original_bytes = source.read_bytes()
            source.write_bytes(original_bytes + b'\n')
            with self.assertRaisesRegex(ValueError, 'staged input changed'):
                verification.audit(output)
            source.write_bytes(original_bytes)
            log = output / 'synthesis.log'
            original_log = log.read_text()
            for changed in (original_log + '\nERROR (CK0013) : injected\n',
                            original_log.replace('GowinSynthesis finish', 'incomplete')):
                log.write_text(changed)
                with self.assertRaisesRegex(ValueError, 'did not finish without errors'):
                    verification.audit(output)
            log.write_text(original_log)
            report = stage / 'impl/gwsynthesis/custom_138k_integration_syn_rsc.xml'
            original_report = report.read_text()
            for changed, message in (
                    (original_report.replace('name="workstation_custom_138k_top"', 'name="wrong_top"', 1), 'top mismatch'),
                    (original_report.replace('T_Bsram="201(0)"', 'T_Bsram="200(0)"', 1), 'inconsistent hierarchy'),
                    (original_report.replace('name="u_delay_ddr_dma"', 'name="missing_delay"', 1), 'missing elaborated features')):
                self.assertNotEqual(changed, original_report)
                report.write_text(changed)
                with self.assertRaisesRegex(ValueError, message):
                    verification.audit(output)
            report.write_text(original_report)
            netlist = stage / 'impl/gwsynthesis/custom_138k_integration.vg'
            original_netlist = netlist.read_text()
            changed, count = re.subn(r"(defparam memory_0_memory_0_0_0_s\.INIT_RAM_00=256'h)([0-9A-Fa-f])",
                                    lambda match: match[1] + ('0' if match[2] != '0' else '1'), original_netlist)
            self.assertEqual(count, 1)
            netlist.write_text(changed)
            with self.assertRaisesRegex(ValueError, 'synthesized ROM mismatch'):
                verification.audit(output)
            netlist.write_text(original_netlist)
            for before, after, message in (
                    ('defparam PLL_inst.FCLKIN="49.5";', 'defparam PLL_inst.FCLKIN="50";', 'declared input frequency changed'),
                    ('defparam PLL_inst.MDIV_SEL=15;', 'defparam PLL_inst.MDIV_SEL=16;', 'frequency does not match SDC'),
                    ('defparam u_pixel_div.DIV_MODE="5";', 'defparam u_pixel_div.DIV_MODE="6";', 'divider waveform changed')):
                self.assertEqual(original_netlist.count(before), 1)
                netlist.write_text(original_netlist.replace(before, after))
                with self.assertRaisesRegex(ValueError, message):
                    verification.audit(output)
            netlist.write_text(original_netlist)
            changed = re.sub(r'(defparam PLL_inst\.CLKOUT0_PE_COARSE=)0;', r'\g<1>1;', original_netlist, count=1)
            self.assertNotEqual(changed, original_netlist)
            netlist.write_text(changed)
            with self.assertRaisesRegex(ValueError, 'phase, feedback or output enable changed'):
                verification.audit(output)
            netlist.write_text(original_netlist)
            plan = json.loads((output / 'pinout/pinout.json').read_text())
            del plan['ports']['usb2_ulpi_stp']
            with self.assertRaisesRegex(ValueError, 'port coverage mismatch'):
                verification.check_ports(stage, plan)
            self.assertEqual(verification.audit(output)['netlist_sha256'], result['netlist_sha256'])


if __name__ == '__main__':
    unittest.main()
