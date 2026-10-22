#!/usr/bin/env python3
"""Native full-board source selection and reversed-cable TMDS verification."""

from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ElementTree


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_custom_board as integration
from tools import workstation_pinout as pinout
from tools.workstation_baselines import load_baseline
from tools.workstation_usb2_soc import SOC_SOURCE_PATHS
from test_workstation_pinout import fixture
from test_workstation_usb2_application import MODEL_INPUTS, midi_sources


def digest(source):
    return hashlib.sha256(Path(source).read_bytes()).hexdigest()


def preprocess(source, destination):
    subprocess.run(['iverilog', '-g2012', '-E', '-I', str(ROOT), '-o', str(destination), str(source)],
                   text=True, capture_output=True, check=True, timeout=30)
    return destination.read_text()


class NativeBoard(unittest.TestCase):
    def test_native_tmds_dedicated_output_route_synthesizes(self):
        baseline = load_baseline(ROOT, 'resource_rework_route0')
        with tempfile.TemporaryDirectory(prefix='custom-tmds-synthesis-') as directory:
            stage = Path(directory)
            shutil.copyfile(ROOT / 'rtl/display_data/workstation_custom_dvi.sv', stage / 'native_dvi.sv')
            (stage / 'encoder.v').write_bytes(baseline.read_bytes('vendor/sipeed_dvi/dvi_tx_tmds_enc.v'))
            project = ElementTree.Element('Project')
            ElementTree.SubElement(project, 'Template').text = 'FPGA'
            ElementTree.SubElement(project, 'Version').text = '5'
            ElementTree.SubElement(project, 'Device', name='GW5AST-138C', pn='GW5AST-LV138PG484AC2/I1').text = 'gw5ast138c-006'
            files = ElementTree.SubElement(project, 'FileList')
            for relative in ('encoder.v', 'native_dvi.sv'):
                ElementTree.SubElement(files, 'File', path=relative, type='file.verilog', enable='1')
            ElementTree.ElementTree(project).write(stage / 'tmds.gprj', encoding='UTF-8', xml_declaration=True)
            (stage / 'synthesis.tcl').write_text('cd [file dirname [info script]]\nopen_project tmds.gprj\n'
                                               'set_option -top_module dvi_tx_top\n'
                                               'set_option -output_base_name native_tmds\nrun syn\n')
            result = subprocess.run(['gw_sh', str(stage / 'synthesis.tcl')], cwd=stage,
                                    text=True, capture_output=True, timeout=180)
            self.assertEqual(result.returncode, 0, result.stdout[-3000:] + result.stderr[-3000:])
            self.assertNotRegex(result.stdout + result.stderr, r'^ERROR\s*\(', 'native TMDS dedicated routing failed')

    def test_high_speed_native_full_profile_input(self):
        self.run_prepared_input(1)

    def test_full_speed_native_full_profile_input(self):
        self.run_prepared_input(0)

    def run_prepared_input(self, high_speed):
        variable = 'GW138K_CUSTOM_INPUT_HS_STAGE' if high_speed else 'GW138K_CUSTOM_INPUT_FS_STAGE'
        with tempfile.TemporaryDirectory(prefix='custom-board-input-') as directory:
            base = Path(directory)
            if os.environ.get(variable):
                parent = Path(os.environ[variable])
                metadata = json.loads((parent / 'integration_inputs.json').read_text())
                self.assertEqual(metadata['top_module'], 'workstation_custom_138k_top')
                self.assertEqual(metadata['high_speed_allowed'], bool(high_speed))
            else:
                profile, payloads, _ = fixture()
                netlists = {role: pinout.Netlist(payload) for role, payload in payloads.items()}
                identities = {role: dict(profile['sources'][role], sha256=pinout.digest(payload))
                              for role, payload in payloads.items()}
                with patch.object(pinout, 'load_sources', return_value=(netlists, identities)):
                    parent, metadata = integration.prepare(ROOT, base / 'netlists', base / 'parent',
                                                           allow_high_speed=bool(high_speed))
            if os.environ.get('GW138K_CUSTOM_INPUT_EVIDENCE'):
                base = Path(os.environ['GW138K_CUSTOM_INPUT_EVIDENCE'])
                base.mkdir(parents=True, exist_ok=True)
            stage = base / f'hs_{high_speed}'
            stage.mkdir(exist_ok=False)
            parent_stage = parent / 'workstation/Prj1'
            sources = (*SOC_SOURCE_PATHS, *integration.NATIVE_INPUT_SOURCES, *integration.LOCKED_INPUT_SOURCES)
            selected = {}
            for relative in (*sources, 'usb2_cpu.hex'):
                if relative in sources:
                    self.assertIn(relative, metadata['enabled_inputs'])
                source = parent_stage / relative
                self.assertEqual(digest(source), metadata['staged_input_sha256'][relative], relative)
                destination = stage / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                selected[relative] = digest(source)
            device, peer_sources = midi_sources()
            models = (*MODEL_INPUTS[:-1], 'sim/usb2/tb_workstation_usb2_input_25k.sv')
            originals = [*(ROOT / relative for relative in models), *peer_sources,
                         device / 'rtl/usb_board/vendor/usbf_defs.v', Path(__file__),
                         Path(__file__).with_name('test_workstation_usb2_application.py')]
            copies = {}
            identities = {source: digest(source) for source in originals}
            for source in originals:
                destination = stage / 'simulation' / source.relative_to(ROOT.parents[3])
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                copies[source] = destination
            evidence = dict(schema=1, high_speed=bool(high_speed), parent_stage=str(parent),
                            parent_manifest_sha256=digest(parent / 'integration_inputs.json'),
                            selected_parent_input_sha256=selected,
                            simulation_input_sha256={str(source.relative_to(ROOT.parents[3])): value
                                                     for source, value in identities.items()},
                            scope='actual_full_profile_frontend_with_resource_fifo_not_full_board_simulation',
                            audio_sink='backpressured_event_checker_not_dsp', hardware_tested=False,
                            deployment_allowed=False, release_ready=False)
            command = ['verilator', '--binary', '--timing', '--timescale-override', '1ns/1ps', '-Wno-fatal', '-j', '4',
                       '--top-module', 'tb_workstation_usb2_input_25k', '--Mdir', str(stage / 'obj'), '-o', 'simulation',
                       f'-GHIGH_SPEED={high_speed}', '-I' + str(copies[device / 'rtl/usb_board/vendor/usbf_defs.v'].parent),
                       *(str(stage / relative) for relative in sources),
                       *(str(copies[ROOT / relative]) for relative in models), *(str(copies[source]) for source in peer_sources)]
            for label, invocation, timeout in (('compilation', command, 180),
                                                ('execution', [str(stage / 'obj/simulation')], 900)):
                log = stage / (label + '.log')
                with log.open('w') as output:
                    result = subprocess.run(invocation, cwd=stage, stdout=output, stderr=subprocess.STDOUT,
                                            text=True, timeout=timeout)
                evidence[label] = dict(command=invocation, returncode=result.returncode, log_sha256=digest(log))
                (stage / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
                self.assertEqual(result.returncode, 0, log.read_text()[-6000:])
            self.assertIn(f'PASS workstation_usb2_input_25k: HS={high_speed}', (stage / 'execution.log').read_text())
            evidence['selected_inputs_unchanged'] = all(digest(stage / relative) == value for relative, value in selected.items())
            evidence['simulation_inputs_unchanged'] = all(digest(source) == value and digest(copies[source]) == value
                                                          for source, value in identities.items())
            self.assertTrue(evidence['selected_inputs_unchanged'])
            self.assertTrue(evidence['simulation_inputs_unchanged'])
            (stage / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')

    def test_default_top_retains_every_committed_legacy_token(self):
        with tempfile.TemporaryDirectory() as directory:
            text = preprocess(ROOT / 'rtl/workstation/gw138k_push_workstation_top.v', Path(directory) / 'default.v')
            tokens = re.sub(r'\s+', '', re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S))
            self.assertEqual(hashlib.sha256(tokens.encode()).hexdigest(),
                             'ec71aeb68d53a11eb7975b4e643be673f30301565f10f671f8b822e6d2674f69')

    def test_native_full_prepare_ports_closure_and_disabled_release_paths(self):
        profile, payloads, _ = fixture()
        netlists = {role: pinout.Netlist(payload) for role, payload in payloads.items()}
        identities = {role: dict(profile['sources'][role], sha256=pinout.digest(payload))
                      for role, payload in payloads.items()}
        with tempfile.TemporaryDirectory(prefix='custom-board-closure-') as directory:
            output = Path(directory) / 'native'
            with patch.object(pinout, 'load_sources', return_value=(netlists, identities)):
                _, metadata = integration.prepare(ROOT, Path(directory) / 'netlists', output)
            stage = output / 'workstation/Prj1'
            self.assertTrue(metadata['native_usb'])
            self.assertTrue(metadata['electrical_blocked'])
            self.assertFalse(metadata['legacy_usb_host_elaborated'])
            for flag in ('place_route_allowed', 'io_electrical_complete', 'timing_constraints_complete',
                         'hardware_tested', 'deployment_allowed', 'release_ready'):
                self.assertFalse(metadata[flag], flag)
            self.assertEqual(metadata['firmware']['rom_sha256'],
                             '31c4d7d58141ef0ec2b33f826a9c22251b7d4f23771cbaa189427b0f1277d457')
            self.assertEqual(metadata['audio_pin_behavior'], 'high_impedance_pending_actual_dac_identity')
            for relative, expected in metadata['staged_input_sha256'].items():
                self.assertEqual(digest(stage / relative), expected, relative)
            for relative, expected in metadata['source_snapshot_sha256'].items():
                self.assertEqual(digest(ROOT / relative), expected, relative)
            for relative in (*integration.REPLACED_INPUTS, *integration.EXCLUDED_INPUTS):
                self.assertNotIn(relative, metadata['enabled_inputs'])
            for relative in integration.NATIVE_SOURCES:
                self.assertEqual(metadata['enabled_inputs'].count(relative), 1, relative)
            self.assertIn('vendor/sipeed_dvi/dvi_tx_tmds_enc.v', metadata['enabled_inputs'])
            self.assertEqual(metadata['tmds_polarity_inverted'], [True] * 4)
            self.assertEqual((stage / 'scripts/custom_board_synthesis.tcl').read_text().count('run syn'), 1)
            self.assertNotIn('run pnr', (stage / 'scripts/custom_board_synthesis.tcl').read_text())
            self.assertTrue((stage / 'scripts/build.tcl').read_text().startswith('error '))
            text = preprocess(ROOT / 'rtl/workstation/workstation_custom_138k_top.sv', Path(directory) / 'native.v')
            self.assertNotIn('iosys2 u_usb_host', text)
            self.assertNotIn('push2_usb_a_control u_push', text)
            for instance in ('workstation_usb2_input u_native_usb', 'gw138k_usb_controlled_audio u_managed',
                             'ddr3_platform u_memory', 'hdmi_display u_video', 'basic_pitch_workstation_link u_music',
                             'delay_ddr_dma #', 'workstation_output_router u_output_router'):
                self.assertEqual(text.count(instance), 1, instance)
            header = re.search(r'module\s+workstation_custom_138k_top\s*#\(.*?\)\s*\((.*?)\);', text, re.S)[1]
            parts = re.split(r'\b(input|output|inout)\b', header)
            ports = set()
            for declaration in parts[2::2]:
                declaration = declaration.strip().removeprefix('wire').strip()
                width = re.match(r'\[(\d+):(\d+)\]', declaration)
                indices = range(int(width[2]), int(width[1]) + 1) if width else None
                names = declaration[width.end():] if width else declaration
                for name in re.findall(r'[A-Za-z_][A-Za-z_0-9]*', names):
                    ports.update(name + f'[{index}]' for index in indices) if indices is not None else ports.add(name)
            plan = json.loads((output / 'pinout/pinout.json').read_text())
            implicit_negative = {'tmds_clk_n', 'ddr_ck_n', *(f'tmds_data_n[{index}]' for index in range(3)),
                                 *(f'ddr_dqs_n[{index}]' for index in range(4))}
            self.assertEqual(ports - implicit_negative, set(plan['ports']))
            with self.assertRaises(FileExistsError):
                integration.prepare(ROOT, Path(directory) / 'netlists', output)

    def test_custom_cli_cannot_enter_accepted_build_or_release_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            for extra in (['--current-workstation'], ['--resource-rework'], ['--prepare-usb2-soc'],
                          ['--prepare-pinout', 'custom-138k'], ['--synthesis-only'], ['--user-code', 'C1102201']):
                output = Path(directory) / 'native'
                result = subprocess.run([sys.executable, str(ROOT / 'build.py'), '--prepare-custom-board',
                                         '--custom-board-output', str(output), '--netlist-dir', directory, *extra],
                                        text=True, capture_output=True, timeout=30)
                self.assertNotEqual(result.returncode, 0, extra)
                self.assertIn('cannot be mixed', result.stderr)
                self.assertFalse(output.exists())

    def test_missing_native_source_does_not_materialize_a_candidate(self):
        original = Path.is_file
        missing = ROOT / 'rtl/display_data/workstation_custom_dvi.sv'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'native'
            with patch.object(Path, 'is_file', lambda source: False if source == missing else original(source)):
                with self.assertRaisesRegex(FileNotFoundError, 'missing native-board source'):
                    integration.prepare(ROOT, Path(directory) / 'netlists', output)
            self.assertFalse(output.exists())

    def test_reversed_tmds_cable_with_official_primitives_and_independent_rgb_reference(self):
        baseline = load_baseline(ROOT, 'resource_rework_route0')
        with tempfile.TemporaryDirectory(prefix='custom-board-tmds-') as directory:
            stage = Path(os.environ.get('GW138K_CUSTOM_TMDS_EVIDENCE', directory))
            if os.environ.get('GW138K_CUSTOM_TMDS_EVIDENCE'):
                stage.mkdir(parents=True, exist_ok=False)
            locator = stage / 'gowin_paths.py'
            locator.write_bytes(baseline.read_bytes('scripts/gowin_paths.py'))
            spec = importlib.util.spec_from_file_location('custom_board_gowin_paths', locator)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            primitive = module.gowin_simlib() / 'prim_sim.v'
            text = primitive.read_text()
            blocks = []
            for name in ('GSR', 'CLKDIV', 'OSER10', 'ELVDS_OBUF'):
                blocks.append(re.search(r'^module\s+' + name + r'\s*\(.*?^endmodule\b[^\n]*', text, re.M | re.S)[0])
            models = stage / 'official_models.v'
            models.write_text('`timescale 1ns/1fs\n' + '\n\n'.join(blocks) + '\n')
            for relative in ('vendor/sipeed_dvi/video_pll_1080p_gw5a.v', 'vendor/sipeed_dvi/dvi_tx_tmds_enc.v'):
                (stage / Path(relative).name).write_bytes(baseline.read_bytes(relative))
            original = baseline.read_bytes('sim/primitives/tb_tmds_clock.sv').decode()
            native = stage / 'native_dvi.sv'
            shutil.copyfile(ROOT / 'rtl/display_data/workstation_custom_dvi.sv', native)
            evidence = dict(primitive_sha256=digest(primitive), baseline=baseline.evidence(),
                            source_sha256=digest(ROOT / 'rtl/display_data/workstation_custom_dvi.sv'),
                            original_bench_sha256=hashlib.sha256(original.encode()).hexdigest(),
                            physical_hardware_tested=False, polarity_location='parallel_word_before_OSER10',
                            serializer_reset_connector_clock_level=1, cases=[])
            for cable_swapped in (True, False):
                bench = stage / f'bench_{int(cable_swapped)}.sv'
                changed = original
                if cable_swapped:
                    declaration = '    wire [1:0] clock_pair, blue_pair, green_pair, red_pair;'
                    insertion = declaration + '\n    wire [1:0] fpga_clock,fpga_blue,fpga_green,fpga_red;\n' + '\n'.join(
                        f'    assign {observed}={{ {physical}[0],{physical}[1] }};'
                        for observed, physical in zip(('clock_pair','blue_pair','green_pair','red_pair'),
                                                      ('fpga_clock','fpga_blue','fpga_green','fpga_red')))
                    self.assertEqual(changed.count(declaration), 1)
                    changed = changed.replace(declaration, insertion)
                    anchor = 'clock_pair,blue_pair,green_pair,red_pair);'
                    self.assertEqual(changed.count(anchor), 1)
                    changed = changed.replace(anchor, 'fpga_clock,fpga_blue,fpga_green,fpga_red);')
                    reset_idle = 'clock_pair[1]!==0) $fatal'
                    self.assertEqual(changed.count(reset_idle), 1)
                    changed = changed.replace(reset_idle, 'clock_pair[1]!==1) $fatal')
                bench.write_text(changed)
                executable = stage / f'tmds_{int(cable_swapped)}'
                command = ['iverilog', '-g2012', '-s', 'tb_tmds_clock', '-o', str(executable), str(models),
                           str(stage / 'video_pll_1080p_gw5a.v'), str(stage / 'dvi_tx_tmds_enc.v'),
                           str(native), str(bench)]
                compilation = subprocess.run(command, text=True, capture_output=True, timeout=60)
                self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
                result = subprocess.run(['vvp', str(executable)], text=True, capture_output=True, timeout=60)
                log = stage / f'execution_{int(cable_swapped)}.log'
                log.write_text(result.stdout + result.stderr)
                evidence['cases'].append(dict(cable_swapped=cable_swapped, returncode=result.returncode,
                                              bench_sha256=digest(bench), log_sha256=digest(log)))
                if cable_swapped:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('PASS official Gowin TMDS clock: all 9 startup/phase cases', result.stdout)
                else:
                    self.assertNotEqual(result.returncode, 0, 'negative cable control unexpectedly passed')
                    self.assertIn('TMDS word mismatch', result.stdout)
            self.assertEqual(digest(native), evidence['source_sha256'])
            self.assertEqual(digest(ROOT / 'rtl/display_data/workstation_custom_dvi.sv'), evidence['source_sha256'])
            (stage / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
