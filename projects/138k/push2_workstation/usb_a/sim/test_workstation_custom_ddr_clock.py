"""Resolve the native DDR clock plan against an isolated implementation of its exact IP."""

from pathlib import Path
import hashlib
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
from tools.workstation_baselines import load_baseline
from tools.workstation_custom_clocks import DDR_CLOCK_SOURCES, ddr_probe_sdc, audit_implemented_ddr_clock


DDR_SOURCES = DDR_CLOCK_SOURCES
PROBE_SOURCE = 'sim/timing/workstation_ddr_clock_probe.sv'


def prepare_probe(stage):
    baseline = load_baseline(ROOT, 'resource_rework_route0')
    for relative in DDR_SOURCES:
        source = stage / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(baseline.read_bytes(relative))
    shutil.copyfile(ROOT / PROBE_SOURCE, stage / 'probe.sv')
    original = baseline.read_bytes('constraints/tang_mega_138k.cst').decode()
    selected = [line for line in original.splitlines() if
        (line.startswith(('IO_LOC', 'IO_PORT')) and re.search(r'"(?:ddr_[^"]+|clk_50m)"', line)) or
        (line.startswith('INS_LOC') and 'u_memory/' in line)]
    (stage / 'probe.cst').write_text('\n'.join(selected) + '\n'
        'IO_LOC "reset_n" C13;\nIO_PORT "reset_n" IO_TYPE=LVCMOS33;\n'
        'IO_LOC "observed" U15;\nIO_PORT "observed" IO_TYPE=LVCMOS33;\n')
    (stage / 'probe.sdc').write_text(ddr_probe_sdc(ROOT))
    project = ElementTree.Element('Project')
    ElementTree.SubElement(project, 'Template').text = 'FPGA'
    ElementTree.SubElement(project, 'Version').text = '5'
    device = json.loads((ROOT / 'boards/custom_138k/pinout.json').read_text())['device']
    ElementTree.SubElement(project, 'Device', name='GW5AST-138C', pn=device).text = 'gw5ast138c-006'
    files = ElementTree.SubElement(project, 'FileList')
    for relative, kind in [*((name, 'file.verilog') for name in (*DDR_SOURCES, 'probe.sv')),
                           ('probe.cst', 'file.cst'), ('probe.sdc', 'file.sdc')]:
        ElementTree.SubElement(files, 'File', path=relative, type=kind, enable='1')
    ElementTree.ElementTree(project).write(stage / 'probe.gprj', encoding='UTF-8', xml_declaration=True)
    (stage / 'probe.tcl').write_text('cd [file dirname [info script]]\nopen_project probe.gprj\n'
        'set_option -top_module workstation_ddr_clock_probe\nset_option -output_base_name ddr_clock_probe\n'
        'set_option -verilog_std sysv2017\nset_option -use_cpu_as_gpio 1\n'
        'set_option -gen_sdf 1\nset_option -gen_verilog_sim_netlist 1\nrun all\n')
    return {str(source.relative_to(stage)): hashlib.sha256(source.read_bytes()).hexdigest()
            for source in stage.rglob('*') if source.is_file()}


class NativeDdrClock(unittest.TestCase):
    def test_actual_selected_ddr_ip_implementation(self):
        self.assertIsNotNone(shutil.which('gw_sh'))
        with tempfile.TemporaryDirectory(prefix='native-ddr-clock-') as directory:
            stage = Path(directory)
            if os.environ.get('GW138K_CUSTOM_DDR_CLOCK_EVIDENCE'):
                stage = Path(os.environ['GW138K_CUSTOM_DDR_CLOCK_EVIDENCE'])
                stage.mkdir(parents=True, exist_ok=False)
            inputs = prepare_probe(stage)
            result = subprocess.run(['gw_sh', str(stage / 'probe.tcl')], cwd=stage,
                text=True, capture_output=True, timeout=480)
            (stage / 'tool.log').write_text(result.stdout + result.stderr)
            self.assertEqual(result.returncode, 0, (stage / 'tool.log').read_text()[-5000:])
            self.assertNotRegex(result.stdout + result.stderr, r'(?m)^ERROR\b')
            self.assertTrue(all(hashlib.sha256((stage / name).read_bytes()).hexdigest() == digest for name, digest in inputs.items()))
            self.assertTrue((stage / 'impl/pnr/ddr_clock_probe.vo').is_file())
            audit = audit_implemented_ddr_clock(ROOT, stage)
            self.assertEqual(audit['divide_by'], 4)
            self.assertEqual(audit['ui_clock_hz'], 100000000)
            self.assertEqual(len(audit['consumer_registers']), 8)
            self.assertFalse(audit['native_routed_timing_verified'])
            self.assertFalse(audit['ddr_data_path_verified'])
            self.assertTrue(all(summary['negative_paths'] == 0 for summary in audit['consumer_timing_summary'].values()))
            text = (stage / 'impl/pnr/ddr_clock_probe.vo').read_text()
            for before, after, message in (
                    ('/fclkdiv .DIV_MODE="4";', '/fclkdiv .DIV_MODE="5";', 'DDR UI divider changed'),
                    ('/PLL_inst .MDIV_SEL=16;', '/PLL_inst .MDIV_SEL=17;', 'DDR memory PLL frequency changed'),
                    ('/fclkdiv ', '/missing_divider ', 'DDR UI target not resolved')):
                self.assertIn(before, text)
                with self.assertRaisesRegex(ValueError, message):
                    audit_implemented_ddr_clock(ROOT, stage, text.replace(before, after))
            changed, count = re.subn(r'(DFFCE\s+ui_counter_\d+_s\d+\s*\(.*?\.CLK\()[^)]*',
                lambda match: match[1] + 'clk_50m', text, count=1, flags=re.S)
            self.assertEqual(count, 1)
            with self.assertRaisesRegex(ValueError, 'UI consumer clock changed'):
                audit_implemented_ddr_clock(ROOT, stage, changed)
            changed, count = re.subn(r'(CLKDIV\s+\\u_memory/u_ddr3/gw3_top/u_ddr_phy_top/fclkdiv\s*\(.*?\.HCLKIN\()[^)]*',
                lambda match: match[1] + 'clk_50m', text, count=1, flags=re.S)
            self.assertEqual(count, 1)
            with self.assertRaisesRegex(ValueError, 'divider source wiring changed'):
                audit_implemented_ddr_clock(ROOT, stage, changed)
            ip_path = stage / 'vendor/gowin_ddr3/ddr3_memory_interface.v'
            original = ip_path.read_bytes()
            ip_path.write_bytes(original + b'\n')
            with self.assertRaisesRegex(ValueError, 'differs from selected locked source'):
                audit_implemented_ddr_clock(ROOT, stage)
            ip_path.write_bytes(original)
            (stage / 'clock_audit.json').write_text(json.dumps(audit, indent=2) + '\n')
            (stage / 'tool_result.json').write_text(json.dumps(dict(
                validation_stage='isolated_selected_ddr_clock_implementation_not_native_board_acceptance',
                tool_returncode=result.returncode, inputs_sha256=inputs, inputs_unchanged=True,
                hardware_tested=False, deployment_allowed=False, release_ready=False), indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
