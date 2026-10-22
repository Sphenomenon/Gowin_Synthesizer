#!/usr/bin/env python3
"""Native clock inventory, Tcl declarations and unsafe plan drift rejection."""

from pathlib import Path
from unittest.mock import patch
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_custom_clocks import clock_bundle


class NativeClocks(unittest.TestCase):
    def test_gowin_sta_consumes_explicit_sixty_percent_pixel_edges(self):
        bundle = clock_bundle(ROOT)
        pixel = next(line for line in bundle['sdc'].splitlines() if '-name video_pixel148 ' in line)
        transform = re.search(r'-edges \{[0-9 ]+\}', pixel)[0]
        with tempfile.TemporaryDirectory(prefix='native-clock-edge-sta-') as directory:
            base = Path(directory)
            if os.environ.get('GW138K_CUSTOM_CLOCK_STA_EVIDENCE'):
                base = Path(os.environ['GW138K_CUSTOM_CLOCK_STA_EVIDENCE'])
                base.mkdir(parents=True, exist_ok=False)
            evidence = dict(scope='scaled_50MHz_clock_edge_syntax_probe_not_workstation_implementation',
                            clock_plan_sha256=bundle['source_sha256'], hardware_tested=False,
                            deployment_allowed=False, release_ready=False, cases=[])
            for label, edges, expected_fall in (('native_edges', transform, '60.000'),
                                                 ('wrong_fifty_percent', '-edges {1 6 11}', '50.000')):
                stage = base / label
                stage.mkdir()
                (stage / 'probe.v').write_text('module clock_probe(input wire clk_50m, output reg probe_q=0);\n'
                    'wire pixel_clock;\n'
                    'CLKDIV #(.DIV_MODE("5")) divider (.CLKOUT(pixel_clock),.HCLKIN(clk_50m),.RESETN(1\'b1),.CALIB(1\'b0));\n'
                    'always @(posedge pixel_clock) probe_q<=~probe_q;\nendmodule\n')
                (stage / 'probe.cst').write_text('IO_LOC "clk_50m" V22;\nIO_PORT "clk_50m" IO_TYPE=LVCMOS33;\n'
                                                'IO_LOC "probe_q" U15;\nIO_PORT "probe_q" IO_TYPE=LVCMOS33;\n')
                (stage / 'probe.sdc').write_text('create_clock -name reference_50 -period 20.000 -waveform {0 10} [get_ports {clk_50m}]\n'
                    f'create_generated_clock -name divided_10 -source [get_ports {{clk_50m}}] -master_clock reference_50 {edges} [get_pins {{divider/CLKOUT}}]\n')
                project = ElementTree.Element('Project')
                ElementTree.SubElement(project, 'Template').text = 'FPGA'
                ElementTree.SubElement(project, 'Version').text = '5'
                ElementTree.SubElement(project, 'Device', name='GW5AST-138C', pn='GW5AST-LV138PG484AC2/I1').text = 'gw5ast138c-006'
                files = ElementTree.SubElement(project, 'FileList')
                for relative, kind in (('probe.v', 'file.verilog'), ('probe.cst', 'file.cst'), ('probe.sdc', 'file.sdc')):
                    ElementTree.SubElement(files, 'File', path=relative, type=kind, enable='1')
                ElementTree.ElementTree(project).write(stage / 'probe.gprj', encoding='UTF-8', xml_declaration=True)
                (stage / 'probe.tcl').write_text('cd [file dirname [info script]]\nopen_project probe.gprj\n'
                                                'set_option -top_module clock_probe\nset_option -output_base_name clock_probe\nrun all\n')
                result = subprocess.run(['gw_sh', str(stage / 'probe.tcl')], cwd=stage,
                                        text=True, capture_output=True, timeout=180)
                log = stage / 'tool.log'
                log.write_text(result.stdout + result.stderr)
                self.assertEqual(result.returncode, 0, log.read_text()[-4000:])
                self.assertNotRegex(log.read_text(), r'(?m)^ERROR\b')
                report = stage / 'impl/pnr/clock_probe_tr_content.html'
                clock_table = re.search(r'Clock Summary:</a></h2>\s*<table.*?</table>', report.read_text(), re.S)[0]
                rows = [[cell.strip() for cell in re.findall(r'<td[^>]*>([^<]*)', row)]
                        for row in re.findall(r'<tr>.*?</tr>', clock_table, re.S)]
                clocks = {cells[1]: cells for cells in rows if len(cells) == 10}
                self.assertEqual(clocks['reference_50'][2:7], ['Base', '20.000', '50.000', '0.000', '10.000'])
                self.assertEqual(clocks['divided_10'][2:7], ['Generated', '100.000', '10.000', '0.000', expected_fall])
                self.assertEqual(clocks['divided_10'][7:], ['clk_50m', 'reference_50', 'divider/CLKOUT'])
                evidence['cases'].append(dict(case=label, edges=edges, tool_returncode=result.returncode,
                    matches_native_waveform=expected_fall == '60.000', clock_summary=clocks,
                    sha256={str(source.relative_to(stage)): hashlib.sha256(source.read_bytes()).hexdigest()
                            for source in (stage / 'probe.v', stage / 'probe.sdc', stage / 'probe.cst',
                                           stage / 'probe.gprj', stage / 'probe.tcl', log, report)}))
            (base / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')

    def test_all_primary_and_generated_clocks_have_explicit_tcl_declarations(self):
        bundle = clock_bundle(ROOT)
        self.assertEqual(len(bundle['plan']['primary']), 2)
        self.assertEqual(len(bundle['plan']['generated']), 9)
        self.assertNotIn('set_false_path', bundle['sdc'])
        self.assertNotIn('set_clock_groups', bundle['sdc'])
        prefix = '''
set clocks {}
proc get_ports {names} {return [list PORTS $names]}
proc get_pins {names} {return [list PINS $names]}
proc create_clock {args} {global clocks; lappend clocks [list primary $args]}
proc create_generated_clock {args} {global clocks; lappend clocks [list generated $args]}
'''
        result = subprocess.run(['tclsh'], input=prefix + bundle['sdc'] + '\nputs [llength $clocks]\n',
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), '11')
        pixel = next(line for line in bundle['sdc'].splitlines() if '-name video_pixel148 ' in line)
        self.assertIn('-edges {1 7 11}', pixel)
        self.assertNotIn('-divide_by', pixel)

    def test_frequency_and_pixel_waveform_cannot_be_relaxed(self):
        original = clock_bundle(ROOT)['plan']
        changed = copy.deepcopy(original)
        changed['primary'][1]['frequency_hz'] = 50000000
        mutations = [(changed, 'frequency or target inventory')]
        changed = copy.deepcopy(original)
        pixel = next(entry for entry in changed['generated'] if entry['name'] == 'video_pixel148')
        pixel['edges'] = [1, 6, 11]
        mutations.append((changed, '60/40 waveform changed'))
        changed = copy.deepcopy(original)
        pixel = next(entry for entry in changed['generated'] if entry['name'] == 'video_pixel148')
        del pixel['edges']
        mutations.append((changed, 'lost explicit 60/40'))
        for changed, message in mutations:
            with self.subTest(message=message), patch('tools.workstation_custom_clocks.json.loads', return_value=changed):
                with self.assertRaisesRegex(ValueError, message):
                    clock_bundle(ROOT)

    def test_source_order_and_opaque_target_are_fail_closed(self):
        original = clock_bundle(ROOT)['plan']
        changed = copy.deepcopy(original)
        changed['generated'][0]['source'] = 'audio_76m8'
        mutations = [(changed, 'source missing or not ordered')]
        changed = copy.deepcopy(original)
        changed['generated'][0]['opaque_ip_prefix'] = 'u_audio_clock'
        mutations.append((changed, 'unexpected opaque clock target'))
        for changed, message in mutations:
            with self.subTest(message=message), patch('tools.workstation_custom_clocks.json.loads', return_value=changed):
                with self.assertRaisesRegex(ValueError, message):
                    clock_bundle(ROOT)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                clock_bundle(Path(directory))


if __name__ == '__main__':
    unittest.main()
