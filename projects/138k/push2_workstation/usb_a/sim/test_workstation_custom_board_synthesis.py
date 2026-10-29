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
import xml.etree.ElementTree as ElementTree


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_custom_board as integration
from tools import workstation_custom_board_audit as verification
from tools import workstation_pinout as pinout
from test_workstation_pinout import fixture
from tools.workstation_custom_usb2_cdc import audit_usb2_cdc, cdc_bundle
from tools.workstation_custom_input_cdc import audit_input_fifo, input_cdc_bundle
from tools.workstation_custom_clocks import audit_clocks, audit_shared_cdc
from tools.workstation_baselines import load_baseline
from tools.workstation_resource_timing import event_fifo
from tools.workstation_custom_timing import audit_resets
from test_workstation_ddr_bist import synthesized_failure_cone


class NativeSynthesis(unittest.TestCase):
    def test_actual_synthesis_and_rejected_corruptions(self):
        with tempfile.TemporaryDirectory(prefix='native-full-synthesis-audit-') as directory:
            output = Path(directory) / 'candidate'
            stage = output / 'workstation/Prj1'
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
            self.assertEqual(result['identity'], integration.IDENTITY)
            self.assertEqual(result['resources'], dict(Register=54219, Lut=73127, Alu=15544, Bsram=272,
                                                       Ssram=419, MULTALU27X18=46, MULT12X12=41, MULT27X36=45,
                                                       self_bsram=0, subtree_bsram=272))
            self.assertEqual(set(result['delay_fifo_storage_audit']), {'u_write_fifo', 'u_read_fifo'})
            for storage in result['delay_fifo_storage_audit'].values():
                self.assertEqual((storage['bsram_blocks'], storage['distributed_ram_blocks'],
                                  storage['entries'], storage['width']), (4, 0, 512, 65))
            self.assertEqual(result['verified_rom_words'], 16384)
            selected_fifo = event_fifo(load_baseline(ROOT, 'resource_rework_route0').read_bytes(
                'src/usb_host/gw138k_usb_event_fifo.v').decode()).encode()
            self.assertEqual((stage / 'src/usb_host/gw138k_usb_event_fifo.v').read_bytes(), selected_fifo)
            input_crossings = result['input_fifo_cdc_audit']
            self.assertEqual(input_crossings['pointer_bits'], 14)
            self.assertEqual(len(input_crossings['resolved_pin_selectors']), 9)
            self.assertTrue(input_crossings['source_netlist_endpoints_verified'])
            self.assertFalse(input_crossings['physical_timing_verified'])
            self.assertFalse(input_crossings['native_constraints_complete'])
            self.assertEqual(result['port_coverage']['logical_location_entries'], 133)
            self.assertEqual(result['port_coverage']['physical_port_bits'], 142)
            self.assertFalse(result['release_ready'])
            self.assertFalse(result['deployment_allowed'])
            self.assertFalse(result['electrical_blocked'])
            self.assertEqual(result['electrical_check']['status'], 'no_voltage_domain_conflict_detected')
            self.assertFalse(result['electrical_check']['actual_board_measured'])
            self.assertFalse(result['electrical_check']['full_electrical_acceptance'])
            clocks = result['explicit_clock_audit']
            self.assertEqual(len(clocks['clocks']), 13)
            self.assertEqual(sum(clock.get('verified', False) for clock in clocks['clocks'].values()), 9)
            self.assertEqual(clocks['clocks']['dac_ref12m288']['frequency_hz'], 12288000)
            self.assertNotIn('dac_49m152', clocks['clocks'])
            self.assertEqual(clocks['clocks']['lcd_pixel31m5']['frequency_hz'], 31500000)
            self.assertTrue(clocks['clocks']['lcd_pixel31m5']['verified'])
            self.assertFalse(result['master_volume_audit']['double_master_attenuation'])
            self.assertFalse(result['master_volume_audit']['physical_audio_verified'])
            self.assertEqual(clocks['deferred_opaque_ip_targets'],
                             ['u_memory/u_ddr3/gw3_top/u_ddr_phy_top/fclkdiv/CLKOUT'])
            self.assertFalse(clocks['source_netlist_verified'])
            self.assertFalse(clocks['routed_timing_verified'])
            ui_clock = clocks['clocks']['ddr_ui100']
            self.assertIsNotNone(ui_clock['net'])
            self.assertTrue(ui_clock['source_boundary_verified'])
            self.assertFalse(ui_clock['verified'])
            self.assertEqual(ui_clock['frequency_hz'], 100000000)
            self.assertEqual(set(ui_clock['clock_observer_registers']), {0, 1, 2})
            resets = result['bridge_reset_audit']
            self.assertTrue(resets['transaction_reset_topology_verified'])
            self.assertFalse(resets['physical_reset_timing_verified'])
            self.assertFalse(resets['cdc_constraints_complete'])
            crossings = result['usb2_bridge_cdc_audit']
            self.assertTrue(crossings['source_netlist_endpoints_verified'])
            self.assertEqual(sum(len(entry['first_stage']) for entry in crossings['controls'].values()), 10)
            self.assertEqual(sum(len(entry['implemented_bits']) for entry in crossings['mailboxes'].values()), 116)
            self.assertFalse(crossings['physical_timing_verified'])
            self.assertFalse(crossings['native_constraints_complete'])
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
                    ('electrical_blocked', True, 'electrical blocking'),
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
            pinout_path = output / 'pinout/pinout.json'
            original_pinout = pinout_path.read_bytes()
            for field, value in (('status', 'accepted'), ('status', 'blocked'),
                                 ('actual_board_measured', True), ('full_electrical_acceptance', True)):
                changed_plan = json.loads(original_pinout)
                changed_plan['electrical_check'][field] = value
                pinout_path.write_text(json.dumps(changed_plan))
                changed = copy.deepcopy(original)
                changed['pinout_sha256'] = verification.sha(pinout_path)
                manifest.write_text(json.dumps(changed))
                with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, 'electrical blocking'):
                    verification.audit(output)
            pinout_path.write_bytes(original_pinout)
            manifest.write_text(json.dumps(original))
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
                    (original_report.replace('T_Bsram="'+str(result['resources']['Bsram'])+'(0)"',
                        'T_Bsram="'+str(result['resources']['Bsram']-1)+'(0)"', 1), 'inconsistent hierarchy'),
                    (original_report.replace('name="u_delay_ddr_dma"', 'name="missing_delay"', 1), 'missing elaborated features')):
                self.assertNotEqual(changed, original_report)
                report.write_text(changed)
                with self.assertRaisesRegex(ValueError, message):
                    verification.audit(output)
            report.write_text(original_report)
            netlist = stage / 'impl/gwsynthesis/custom_138k_integration.vg'
            original_netlist = netlist.read_text()
            bist_cone = synthesized_failure_cone(original_netlist)
            self.assertFalse(bist_cone['address_sources'])
            self.assertTrue(bist_cone['expected_sources'])
            self.assertLessEqual(bist_cone['maximum_alu_depth'], 8)
            self.assertEqual(len(result['native_usb_reset_audit']['resets']), 16)
            self.assertEqual(len(result['native_usb_reset_audit']['levels']), 8)
            with self.assertRaisesRegex(ValueError, 'two-stage release/level topology changed: .*feedback/source_release'):
                audit_resets(original_netlist, clocks)
            with self.assertRaisesRegex(ValueError, 'unreviewed native feedback source clock'):
                audit_resets(original_netlist, clocks, feedback_source_clock='usb_48m')
            self.assertEqual(audit_resets(original_netlist, clocks, feedback_source_clock='audio_76m8'),
                             result['native_usb_reset_audit'])
            controller = re.search(r'^module\s+workstation_usb2_host_controller\s*\(.*?^endmodule\b',
                                   original_netlist, re.M | re.S)
            self.assertIsNotNone(controller)
            for port, replacement in [('D', 'GND'), ('CLK', 'GND'), ('CLEAR', 'GND')]:
                changed, count = re.subn(r'(DFF\w+\s+fatal_sync_q_1_s\d+\s*\(.*?\.' + port + r'\()[^)]*',
                                        lambda match: match[1] + replacement, controller[0], count=1, flags=re.S)
                self.assertEqual(count, 1)
                with self.assertRaisesRegex(ValueError, 'two-stage release/level topology changed'):
                    audit_resets(original_netlist[:controller.start()] + changed +
                                 original_netlist[controller.end():], clocks, feedback_source_clock='audio_76m8')
            first_stage = re.search(r'DFF\w+\s+fatal_sync_q_0_s\d+\s*\(.*?\.Q\(([^)]*)',
                                    controller[0], re.S)
            self.assertIsNotNone(first_stage)
            changed, count = re.subn(r'(DFF\w+\s+fatal_latched_q_s\d+\s*\(.*?\.D\()[^)]*',
                                    lambda match: match[1] + first_stage[1], controller[0], count=1, flags=re.S)
            self.assertEqual(count, 1)
            with self.assertRaisesRegex(ValueError, 'first synchronizer stage has functional fanout'):
                audit_resets(original_netlist[:controller.start()] + changed +
                             original_netlist[controller.end():], clocks, feedback_source_clock='audio_76m8')
            unused_totals, resource_rows = verification.hierarchy(ElementTree.fromstring(original_report))
            memory = re.search(r'(?m)^  SDPX9B \\g_large_head\.even_memory[^\s]+\s+\(.*?^\);', original_netlist, re.S)
            self.assertIsNotNone(memory)
            changed, count = re.subn(r'(\.CLKB\()[^)]*', r'\g<1>GND', memory[0])
            self.assertEqual(count, 1)
            with self.assertRaisesRegex(ValueError, 'dual-clock memory contract changed'):
                verification.audit_delay_fifo_storage(original_netlist[:memory.start()] + changed +
                                                     original_netlist[memory.end():], resource_rows)
            changed_rows = copy.deepcopy(resource_rows)
            changed_rows['u_managed/u_audio/u_workstation/effects/delay_stage/u_write_fifo']['Ssram'] = 1
            with self.assertRaisesRegex(ValueError, 'four BSRAM and no distributed RAM'):
                verification.audit_delay_fifo_storage(original_netlist, changed_rows)
            output_audio = re.search(r'workstation_fpc_audio\s+u_fpc_audio\s*\(.*?\);', original_netlist, re.S)
            self.assertIsNotNone(output_audio)
            changed, count = re.subn(r'(\.performance_words\()([^[]+)\[63:56\]', lambda match: match[1] + match[2] + '[56:63]',
                                    output_audio[0], count=1)
            self.assertEqual(count, 1)
            with self.assertRaisesRegex(ValueError, 'master volume must reach final output once'):
                verification.audit_master_volume(original_netlist[:output_audio.start()] + changed +
                                                 original_netlist[output_audio.end():])
            effect_audio = re.search(r'stereo_effects\s+effects\s*\(.*?\);', original_netlist, re.S)
            self.assertIsNotNone(effect_audio)
            changed, count = re.subn(r'(\.expression_gain\()([^[]+)\[15:8\]',
                                    lambda match: match[1] + match[2] + '[8:15]', effect_audio[0], count=1)
            self.assertEqual(count, 1)
            with self.assertRaisesRegex(ValueError, 'master volume must reach final output once'):
                verification.audit_master_volume(original_netlist[:effect_audio.start()] + changed +
                                                 original_netlist[effect_audio.end():])
            if result['identity'].endswith(('-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
                self.assertEqual(set(result['native_receiver_audit']),
                                 {'bluetooth_uart', 'fpc_pll_reset', 'fpc_reference_monitor'})
                uart = re.search(r'^module\s+bt_uart_fast\s*\(.*?^endmodule\b', original_netlist, re.M | re.S)
                self.assertIsNotNone(uart)
                receiver = re.search(r'DFFPE\s+rx_sync_1_s\d+\s*\(.*?\.D\(([^)]*)', uart[0], re.S)
                self.assertIsNotNone(receiver)
                for stem, replacement, reason in (
                        ('rx_sync_1', 'GND', 'direct two-stage connection'),
                        ('tx_busy', receiver[1], 'first stage has functional fanout')):
                    changed, count = re.subn(r'(DFF\w+\s+' + stem + r'_s\d+\s*\(.*?\.D\()[^)]*',
                                             lambda match: match[1] + replacement, uart[0], count=1, flags=re.S)
                    self.assertEqual(count, 1)
                    with self.assertRaisesRegex(ValueError, reason):
                        verification.audit_native_receivers(original_netlist[:uart.start()] + changed +
                                                            original_netlist[uart.end():], clocks)
            if result['identity'].endswith(('-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
                self.assertEqual(result['shared_cdc_audit']['constraints'], 157)
                self.assertEqual(len(result['shared_cdc_audit']['resolved_selectors']), 145)
                self.assertEqual(len(result['shared_cdc_audit']['deferred_opaque_ddr_selectors']), 13)
                with self.assertRaisesRegex(ValueError, 'shared CDC selector is empty'):
                    audit_shared_cdc(stage, original_netlist.replace('held_request_', 'missing_request_'))
                bundle = integration.shared_cdc_bundle(stage)
                bundle['sdc'] = bundle['sdc'].replace('u_video/u_renderer/u_capture/req_meta_s0/D',
                    'u_video/u_renderer/u_capture/req_meta_s0/D missing_synchronizer/D', 1)
                with patch('tools.workstation_custom_clocks.shared_cdc_bundle', return_value=bundle):
                    with self.assertRaisesRegex(ValueError, 'selector is empty: missing_synchronizer/D'):
                        audit_shared_cdc(stage, original_netlist)
            recorder = re.search(r'^module\s+ble_recording\s*\(.*?^endmodule\b',
                                 original_netlist, re.M | re.S)
            self.assertIsNotNone(recorder)
            capture_cells = re.findall(r'SDPB\s+(\\live_capture\.pcm_memory\S+)\s+\((.*?)\);',
                                       recorder[0], re.S)
            self.assertEqual(len(capture_cells), 32)
            for name, ports in capture_cells:
                self.assertIn('.ADA(recorded_frames_Z[13:0])', ports)
                self.assertIn('.ADB(sample_address[13:0])', ports)
                self.assertIn('.CLKA(clk_50m_d)', ports)
                self.assertIn('.CLKB(clk_50m_d)', ports)
                self.assertIn('defparam ' + name + ' .BIT_WIDTH_0=1;', recorder[0])
                self.assertIn('defparam ' + name + ' .BIT_WIDTH_1=1;', recorder[0])
            extra_sdc = cdc_bundle(ROOT)['sdc'] + input_cdc_bundle(ROOT)['sdc'] + integration.FPC_AUDIO_SDC + integration.BLUETOOTH_SDC
            if result['identity'].endswith(('-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
                extra_sdc += integration.LCD_SDC
            if result['identity'].endswith(('-a12', '-a13', '-a14', '-a15', '-a16', '-a17', '-a18', '-a19', '-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
                extra_sdc += integration.shared_cdc_bundle(stage)['sdc']
            if result['identity'].endswith(('-a20', '-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
                extra_sdc += integration.timing_constraints()
            if result['identity'].endswith(('-a21', '-a22', '-a23', '-a24', '-a25', '-a26')):
                extra_sdc += integration.MODEL_FLASH_SDC
            self.assertEqual(audit_clocks(ROOT, stage, original_netlist, extra_sdc=extra_sdc), clocks)
            changed, count = re.subn(r'(DFFCE\s+ui_reset_sync_\d+_s\d+\s*\(.*?\.CLK\()[^)]*',
                                    lambda match: match[1] + 'clk_50m_d', original_netlist, count=1, flags=re.S)
            self.assertEqual(count, 1)
            with self.assertRaisesRegex(ValueError, 'not the distinct wrapper output'):
                audit_clocks(ROOT, stage, changed, extra_sdc=extra_sdc)
            wrapper = re.search(r'^module\s+DDR3_Memory_Interface_Top\s*\(.*?^endmodule\b',
                                original_netlist, re.M | re.S)
            self.assertIsNotNone(wrapper)
            output_port = re.escape(ui_clock['wrapper_output_port'])
            changed, count = re.subn(r'(?m)^output\s+' + output_port + r'\s*;',
                                    'input ' + ui_clock['wrapper_output_port'] + ';', wrapper[0], count=1)
            self.assertEqual(count, 1)
            with self.assertRaisesRegex(ValueError, 'does not resolve through the opaque wrapper output'):
                audit_clocks(ROOT, stage, original_netlist[:wrapper.start()] + changed + original_netlist[wrapper.end():],
                             extra_sdc=extra_sdc)
            changed, count = re.subn(r"(defparam memory_0_memory_0_0_0_s\.INIT_RAM_00=256'h)([0-9A-Fa-f])",
                                    lambda match: match[1] + ('0' if match[2] != '0' else '1'), original_netlist)
            self.assertEqual(count, 1)
            netlist.write_text(changed)
            with self.assertRaisesRegex(ValueError, 'synthesized ROM mismatch'):
                verification.audit(output)
            netlist.write_text(original_netlist)
            bridge = re.search(r'^module\s+workstation_usb2_cpu_bridge\s*\(.*?^endmodule\b',
                               original_netlist, re.M | re.S)
            for domain, name in (('cpu', 'transmit_count_q_0'), ('ulpi', 'state_q_0')):
                clear = resets['release_chains'][domain]['session']['asynchronous_clear']
                changed, count = re.subn(r'(DFFCE\s+' + name + r'_s\d+\s*\(.*?\.CLEAR\()[^)]*',
                                        lambda match: match[1] + clear, bridge[0], count=1, flags=re.S)
                self.assertEqual(count, 1)
                netlist.write_text(original_netlist[:bridge.start()] + changed + original_netlist[bridge.end():])
                with self.assertRaisesRegex(ValueError, 'bypasses local reset release'):
                    verification.audit(output)
            netlist.write_text(original_netlist)
            for stem, port, replacement, message in (
                    ('request_sync_q_1', 'D', 'GND', 'two-stage connection changed'),
                    ('request_sync_q_0', 'CE', 'GND', 'not unconditionally clocked'),
                    ('request_sync_q_0', 'CLK', 'usb_clk', 'clock domain changed'),
                    ('descriptor_ulpi_q_29', 'D', 'GND', 'held payload dependency missing'),
                    ('result_cpu_q_21', 'D', 'GND', 'held payload dependency missing'),
                    ('snapshot_cpu_q_79', 'D', 'GND', 'held payload dependency missing')):
                changed, count = re.subn(r'(DFFCE\s+' + stem + r'_s\d+\s*\(.*?\.' + port + r'\()[^)]*',
                                        lambda match: match[1] + replacement, bridge[0], count=1, flags=re.S)
                self.assertEqual(count, 1)
                with self.assertRaisesRegex(ValueError, message):
                    audit_usb2_cdc(ROOT, original_netlist[:bridge.start()] + changed + original_netlist[bridge.end():], clocks)
            changed = re.sub(r'(?<=\s)descriptor_cpu_q_29_s0(?=\s|\.)', 'descriptor_cpu_q_30_s0', bridge[0])
            self.assertNotEqual(changed, bridge[0])
            with self.assertRaisesRegex(ValueError, 'register bit inventory changed'):
                audit_usb2_cdc(ROOT, original_netlist[:bridge.start()] + changed + original_netlist[bridge.end():], clocks)
            for module_name, stem, port, replacement, message in (
                    ('consume_cdc', 'stage1_0', 'D', 'GND', 'two-stage connection changed'),
                    ('consume_cdc', 'stage0_0', 'CE', 'GND', 'not unconditionally clocked'),
                    ('consume_cdc', 'stage0_0', 'CLK', 'audio_clk', 'clock domain changed'),
                    ('produce_cdc', 'stage0_6', 'D', 'GND', 'registered Gray pointer source changed')):
                module = re.search(r'^module\s+\\gw138k_usb_event_fifo\.fifo\.unbuffered\.' + module_name +
                                   r'\s*\(.*?^endmodule\b', original_netlist, re.M | re.S)
                self.assertIsNotNone(module)
                changed, count = re.subn(r'(DFFCE\s+' + stem + r'_s\d+\s*\(.*?\.' + port + r'\()[^)]*',
                                        lambda match: match[1] + replacement, module[0], count=1, flags=re.S)
                self.assertEqual(count, 1)
                with self.assertRaisesRegex(ValueError, message):
                    audit_input_fifo(ROOT, original_netlist[:module.start()] + changed + original_netlist[module.end():], clocks)
            module = re.search(r'^module\s+\\gw138k_usb_event_fifo\.fifo\.unbuffered\s*\(.*?^endmodule\b',
                               original_netlist, re.M | re.S)
            self.assertIsNotNone(module)
            changed, count = re.subn(r'(SDPX9B\s+\S+\s*\(.*?\.CLKB\()[^)]*',
                                    lambda match: match[1] + 'usb_clk', module[0], count=1, flags=re.S)
            self.assertEqual(count, 1)
            with self.assertRaisesRegex(ValueError, 'dual-clock packet memory changed'):
                audit_input_fifo(ROOT, original_netlist[:module.start()] + changed + original_netlist[module.end():], clocks)
            for before, after, expected_count, message in (
                    ('defparam PLL_inst.FCLKIN="49.5";', 'defparam PLL_inst.FCLKIN="50";', 1, 'declared input frequency changed'),
                    ('defparam PLL_inst.MDIV_SEL=15;', 'defparam PLL_inst.MDIV_SEL=16;', 2, 'frequency does not match SDC'),
                    ('defparam u_pixel_div.DIV_MODE="5";', 'defparam u_pixel_div.DIV_MODE="6";', 1, 'divider waveform changed')):
                self.assertEqual(original_netlist.count(before), expected_count)
                netlist.write_text(original_netlist.replace(before, after, 1))
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
