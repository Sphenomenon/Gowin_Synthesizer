"""Selected native event FIFO: Gray flight policy, ordering and restart fencing."""

from pathlib import Path
from unittest.mock import patch
import copy
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
from tools import workstation_custom_board as integration
from tools.workstation_baselines import load_baseline
from tools.workstation_custom_input_cdc import FIFO, PLAN_SOURCE, input_cdc_bundle
from tools.workstation_resource_timing import event_fifo
from test_workstation_custom_usb2_cdc import timing_rows


def selected_fifo():
    baseline = load_baseline(ROOT, 'resource_rework_route0')
    return event_fifo(baseline.read_bytes('src/usb_host/gw138k_usb_event_fifo.v').decode())


def gray_probe_coverage(setup, hold):
    prefix = 'crossing/fifo/unbuffered/'
    first = [row for row in setup if row[3].startswith(prefix) and re.search(r'/(consume|produce)_cdc/stage0_\d+_s\d+/D$', row[3])]
    def interstage(row):
        source = re.fullmatch(re.escape(prefix) + r'(consume|produce)_cdc/stage0_(\d+)_s\d+/Q', row[2])
        return source and re.fullmatch(re.escape(prefix + source[1] + '_cdc/stage1_' + source[2]) + r'_s\d+/D', row[3])
    second = [row for row in setup if interstage(row)]
    second_hold = [row for row in hold if interstage(row)]
    first_hold = [row for row in hold if row[3].startswith(prefix) and re.search(r'/(consume|produce)_cdc/stage0_\d+_s\d+/D$', row[3])]
    expected = {prefix + f'{direction}_cdc/stage0_{bit}_s0/D' for direction in ('consume', 'produce') for bit in range(7)}
    actual = {re.sub(r'_s\d+/D$', '_s0/D', row[3]) for row in first}
    return dict(all_gray_bits_setup_timed=actual == expected and len(first) == 14 and all(row[6] == '10.000' for row in first),
                second_stage_setup_timed=len(second) == 14 and all(row[6] == '2.000' for row in second),
                second_stage_hold_timed=len(second_hold) == 14 and all(row[6] == '0.000' for row in second_hold),
                gray_hold_only_excluded=not first_hold,
                binary_alias_msb_only=all('produce_w_bin_' not in row[2] or re.search(r'produce_w_bin_6_s\d+/Q$', row[2]) for row in first))


class NativeInputCdc(unittest.TestCase):
    def test_missing_plan_does_not_materialize_candidate(self):
        read_text = Path.read_text
        def unavailable(source, *args, **kwargs):
            if source == ROOT / PLAN_SOURCE:
                raise FileNotFoundError('input CDC plan missing')
            return read_text(source, *args, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'candidate'
            with patch.object(Path, 'read_text', unavailable), self.assertRaisesRegex(FileNotFoundError, 'input CDC plan missing'):
                integration.prepare(ROOT, Path(directory) / 'netlists', output)
            self.assertFalse(output.exists())

    def test_narrow_gray_constraints_and_tcl(self):
        bundle = input_cdc_bundle(ROOT)
        self.assertEqual(len(bundle['sdc'].splitlines()), 6)
        self.assertEqual(bundle['sdc'].count('set_false_path -hold'), 2)
        self.assertEqual(bundle['sdc'].count(' 10.000'), 2)
        self.assertEqual(bundle['sdc'].count(' 2.000'), 2)
        self.assertIn('produce_w_bin_6_s*/Q', bundle['sdc'])
        self.assertNotRegex(bundle['sdc'], r'get_clocks|set_clock_groups|CLEAR|PRESET|storage|produce_w_bin_\*')
        execution = subprocess.run(['tclsh'], input='proc get_pins {pins} {return $pins}\n'
            'proc set_false_path {args} {puts false_path}\nproc set_max_delay {args} {puts max_delay}\n' + bundle['sdc'],
            text=True, capture_output=True, timeout=20)
        self.assertEqual(execution.returncode, 0, execution.stderr)
        self.assertEqual(execution.stdout.splitlines().count('max_delay'), 4)

    def test_relaxed_or_incomplete_inventory_fails(self):
        original = json.loads((ROOT / PLAN_SOURCE).read_text())
        read_text = Path.read_text
        for key, value in (('gray_max_delay_ns', 10.001), ('gray_max_delay_ns', True),
                           ('gray_max_delay_ns', float('nan')), ('synchronizer_max_delay_ns', 2.001),
                           ('pointer_bits', 6), ('pointer_bits', True), ('write_binary_alias_bit', 5),
                           ('fifo', '*'), ('unreviewed_exception', True)):
            changed = copy.deepcopy(original)
            changed[key] = value
            def source_text(source, *args, **kwargs):
                return json.dumps(changed) if source == ROOT / PLAN_SOURCE else read_text(source, *args, **kwargs)
            with self.subTest(key=key, value=value), patch.object(Path, 'read_text', source_text), self.assertRaises(ValueError):
                input_cdc_bundle(ROOT)

    def run_fifo(self, source, half_period):
        with tempfile.TemporaryDirectory(prefix='native-input-fifo-') as directory:
            stage = Path(directory)
            (stage / 'fifo.sv').write_text(source)
            compilation = subprocess.run(['iverilog', '-g2012', '-s', 'tb_workstation_input_fifo',
                '-Ptb_workstation_input_fifo.CPU_HALF_PERIOD_PS=' + str(half_period), '-o', str(stage / 'simulation'),
                str(stage / 'fifo.sv'), str(ROOT / 'sim/usb2/tb_workstation_input_fifo.sv')],
                text=True, capture_output=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stderr)
            return subprocess.run(['vvp', str(stage / 'simulation')], text=True, capture_output=True, timeout=30)

    def test_selected_gray_fifo_orders_wraps_backpressures_and_flushes(self):
        for half_period in (10417, 7353, 25000):
            with self.subTest(half_period=half_period):
                result = self.run_fifo(selected_fifo(), half_period)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('PASS workstation_input_fifo:', result.stdout)
                print(result.stdout.strip())

    def test_gray_monitors_reject_binary_pointer_mutants(self):
        source = selected_fifo()
        for before, after in (
                ('else if(\\$3 )consume_r_gry<=consume_increment_gray;', 'else if(\\$3 )consume_r_gry<=consume_r_bin;'),
                ('else produce_w_gry <= \\$39 ;', 'else produce_w_gry <= produce_w_bin;')):
            self.assertEqual(source.count(before), 1)
            result = self.run_fifo(source.replace(before, after), 10417)
            self.assertNotEqual(result.returncode, 0)
            self.assertRegex(result.stdout + result.stderr, r'Gray pointer (changed more than one bit|does not encode binary pointer)')

    def test_actual_gowin_gray_setup_and_second_stage_hold_survive(self):
        self.assertIsNotNone(shutil.which('gw_sh'))
        bundle = input_cdc_bundle(ROOT)
        baseline = bundle['sdc'].replace(FIFO, 'crossing/fifo/unbuffered')
        cases = (('narrow', baseline, True),
                 ('wrong_full_false_path', baseline.replace('set_false_path -hold', 'set_false_path'), False),
                 ('wrong_second_stage_false_path', baseline +
                  'set_false_path -to [get_pins {crossing/fifo/unbuffered/consume_cdc/stage1_*_s*/D}]\n', False))
        with tempfile.TemporaryDirectory(prefix='native-input-gray-sta-') as directory:
            base = Path(directory)
            if os.environ.get('GW138K_CUSTOM_INPUT_CDC_STA_EVIDENCE'):
                base = Path(os.environ['GW138K_CUSTOM_INPUT_CDC_STA_EVIDENCE'])
                base.mkdir(parents=True, exist_ok=False)
            evidence = dict(scope='isolated_selected_event_fifo_constraint_consumption_not_native_board_implementation',
                cdc_plan_sha256=bundle['source_sha256'], cases=[], hardware_tested=False, deployment_allowed=False, release_ready=False)
            for label, constraints, accepted in cases:
                stage = base / label
                stage.mkdir()
                (stage / 'fifo.sv').write_text(selected_fifo())
                shutil.copyfile(ROOT / 'sim/usb2/workstation_input_fifo_timing_probe.sv', stage / 'probe.sv')
                (stage / 'probe.sdc').write_text('create_clock -name usb_48m -period 20.833333 [get_ports {clk_cpu}]\n'
                    'create_clock -name audio_76m8 -period 13.020833 [get_ports {clk_audio}]\n' + constraints +
                    'report_timing -setup -max_paths 500 -max_common_paths 5\n'
                    'report_timing -hold -max_paths 500 -max_common_paths 5\n')
                (stage / 'probe.cst').write_text('IO_LOC "clk_cpu" V22;\nIO_LOC "clk_audio" C18;\n'
                    'IO_LOC "reset" C13;\nIO_LOC "observed" U15;\n'
                    'IO_PORT "clk_cpu" IO_TYPE=LVCMOS33;\nIO_PORT "clk_audio" IO_TYPE=LVCMOS33;\n'
                    'IO_PORT "reset" IO_TYPE=LVCMOS33;\nIO_PORT "observed" IO_TYPE=LVCMOS33;\n')
                project = ElementTree.Element('Project')
                ElementTree.SubElement(project, 'Template').text = 'FPGA'
                ElementTree.SubElement(project, 'Version').text = '5'
                device = json.loads((ROOT / 'boards/custom_138k/pinout.json').read_text())['device']
                ElementTree.SubElement(project, 'Device', name='GW5AST-138C', pn=device).text = 'gw5ast138c-006'
                files = ElementTree.SubElement(project, 'FileList')
                for relative, kind in (('probe.sv','file.verilog'), ('fifo.sv','file.verilog'), ('probe.sdc','file.sdc'), ('probe.cst','file.cst')):
                    ElementTree.SubElement(files, 'File', path=relative, type=kind, enable='1')
                ElementTree.ElementTree(project).write(stage / 'probe.gprj', encoding='UTF-8', xml_declaration=True)
                (stage / 'probe.tcl').write_text('cd [file dirname [info script]]\nopen_project probe.gprj\n'
                    'set_option -top_module workstation_input_fifo_timing_probe\nset_option -output_base_name input_fifo_probe\n'
                    'set_option -verilog_std sysv2017\nrun all\n')
                execution = subprocess.run(['gw_sh', str(stage / 'probe.tcl')], cwd=stage, text=True, capture_output=True, timeout=180)
                (stage / 'tool.log').write_text(execution.stdout + execution.stderr)
                self.assertEqual(execution.returncode, 0, (stage / 'tool.log').read_text()[-2500:])
                self.assertNotRegex(execution.stdout + execution.stderr, r'(?m)^ERROR\b')
                report = stage / 'impl/pnr/input_fifo_probe_tr_content.html'
                setup, hold = (timing_rows(report.read_text(), analysis) for analysis in ('Setup', 'Hold'))
                coverage = gray_probe_coverage(setup, hold)
                self.assertEqual(all(coverage.values()), accepted, str(coverage))
                evidence['cases'].append(dict(case=label, tool_returncode=execution.returncode,
                    accepted_constraint_coverage=accepted, coverage=coverage, setup_paths=setup, hold_paths=hold,
                    sha256={str(source.relative_to(stage)): hashlib.sha256(source.read_bytes()).hexdigest()
                        for source in (stage / 'fifo.sv', stage / 'probe.sv', stage / 'probe.sdc', stage / 'probe.cst',
                                       stage / 'probe.gprj', stage / 'probe.tcl', stage / 'tool.log', report)}))
                (base / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
