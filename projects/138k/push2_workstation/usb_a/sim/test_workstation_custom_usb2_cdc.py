"""Native bridge CDC selector policy and actual Gowin timing-exception consumption."""

from pathlib import Path
from unittest.mock import patch
import copy
import hashlib
import html
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
from tools.workstation_custom_usb2_cdc import BRIDGE, cdc_bundle
from tools import workstation_custom_board as integration


def timing_rows(text, analysis):
    match = re.search(r'<a name="' + analysis + r'_Slack_Table">.*?<table[^>]*>(.*?)</table>', text, re.S)
    if not match:
        raise ValueError('probe timing table missing: ' + analysis)
    return [[html.unescape(re.sub('<[^>]+>', '', cell)).strip() for cell in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)]
            for row in re.findall(r'<tr>(.*?)</tr>', match[1], re.S) if '<td' in row]


def narrow_probe_coverage(setup, hold):
    payload = [row for row in setup if re.fullmatch(r'crossing/descriptor_cpu_q_\d+_s\d+/Q', row[2])
               and re.fullmatch(r'crossing/descriptor_ulpi_q_\d+_s\d+/D', row[3])]
    second = {stem: [row for row in setup if re.fullmatch('crossing/' + stem + r'_0_s\d+/Q', row[2])
                     and re.fullmatch('crossing/' + stem + r'_1_s\d+/D', row[3])]
              for stem in ('request_sync_q', 'result_sync_q')}
    second_hold = {stem: [row for row in hold if re.fullmatch('crossing/' + stem + r'_0_s\d+/Q', row[2])
                          and re.fullmatch('crossing/' + stem + r'_1_s\d+/D', row[3])]
                   for stem in ('request_sync_q', 'result_sync_q')}
    first_incoming = [row for row in (*setup, *hold)
                      if re.fullmatch(r'crossing/(request|result)_sync_q_0_s\d+/D', row[3])]
    payload_hold = [row for row in hold if 'descriptor_cpu_q' in row[2] and 'descriptor_ulpi_q' in row[3]]
    return dict(payload_setup_timed=len(payload) == 4 and all(row[6] == '16.000' for row in payload),
                second_stage_setup_timed=all(rows and all(row[6] == '2.000' for row in rows) for rows in second.values()),
                second_stage_hold_timed=all(rows and all(row[6] == '0.000' for row in rows) for rows in second_hold.values()),
                asynchronous_first_stage_only=not first_incoming,
                payload_hold_only_excluded=not payload_hold)


class NativeBridgeCdc(unittest.TestCase):
    def test_missing_cdc_plan_does_not_materialize_a_candidate(self):
        read_text = Path.read_text

        def unavailable(source, *args, **kwargs):
            if source == ROOT / 'boards/custom_138k/usb2_cdc.json':
                raise FileNotFoundError('CDC plan missing')
            return read_text(source, *args, **kwargs)

        with tempfile.TemporaryDirectory(prefix='native-cdc-missing-') as directory:
            output = Path(directory) / 'candidate'
            with patch.object(Path, 'read_text', unavailable), self.assertRaisesRegex(FileNotFoundError, 'CDC plan missing'):
                integration.prepare(ROOT, Path(directory) / 'netlists', output)
            self.assertFalse(output.exists())

    def test_narrow_sdc_inventory_and_tcl_syntax(self):
        bundle = cdc_bundle(ROOT)
        lines = bundle['sdc'].splitlines()
        self.assertEqual(len(lines), 22)
        self.assertEqual(sum(line.startswith('set_false_path -from') for line in lines), 8)
        self.assertEqual(sum(line.startswith('set_false_path -hold') for line in lines), 3)
        self.assertEqual(sum(line.startswith('set_max_delay') for line in lines), 11)
        self.assertNotRegex(bundle['sdc'], r'get_clocks|set_clock_groups|/CLEAR|/PRESET|transmit_memory|receive_memory')
        self.assertEqual(len(bundle['mailboxes']['snapshot']['bits']), 64)
        self.assertNotIn(9, bundle['mailboxes']['snapshot']['bits'])
        self.assertIn(79, bundle['mailboxes']['snapshot']['bits'])
        execution = subprocess.run(['tclsh'], input='proc get_pins {pins} {return $pins}\n'
                                   'proc set_false_path {args} {puts false_path}\n'
                                   'proc set_max_delay {args} {puts max_delay}\n' + bundle['sdc'],
                                   text=True, capture_output=True, timeout=10)
        self.assertEqual(execution.returncode, 0, execution.stderr)
        self.assertEqual(execution.stderr, '')
        self.assertEqual(execution.stdout.count('false_path'), 11)
        self.assertEqual(execution.stdout.count('max_delay'), 11)

    def test_relaxed_budgets_and_missing_inventory_are_rejected(self):
        original = cdc_bundle(ROOT)['plan']
        read_text = Path.read_text

        def plan_text(source, *args, **kwargs):
            return json.dumps(changed) if source == ROOT / 'boards/custom_138k/usb2_cdc.json' else read_text(source, *args, **kwargs)

        for key, value in (('synchronizer_max_delay_ns', 1.5), ('mailbox_max_delay_ns', 12.0)):
            changed = copy.deepcopy(original)
            changed[key] = value
            with patch.object(Path, 'read_text', plan_text):
                self.assertEqual(cdc_bundle(ROOT)['plan'][key], value)
        mutations = []
        for key, value in (('synchronizer_max_delay_ns', 2.001), ('mailbox_max_delay_ns', 16.001),
                           ('mailbox_max_delay_ns', True), ('mailbox_max_delay_ns', float('nan')),
                           ('controls', original['controls'][:-1]), ('mailboxes', ['descriptor']),
                           ('bridge', '*'), ('snapshot_constant_bits', [9, 9]), ('snapshot_constant_bits', [80]),
                           ('unreviewed_exception_mode', True)):
            changed = copy.deepcopy(original)
            changed[key] = value
            mutations.append(changed)
        for changed in mutations:
            with self.subTest(plan=changed), patch.object(Path, 'read_text', plan_text):
                with self.assertRaises(ValueError):
                    cdc_bundle(ROOT)

    def test_mailbox_hold_monitors_reject_early_writes(self):
        original = (ROOT / 'rtl/usb2/workstation_usb2_cpu_bridge.sv').read_text()
        mutations = (
            ('descriptor', 'result_sync_q <= {result_sync_q[0], result_toggle_q};',
             'result_sync_q <= {result_sync_q[0], result_toggle_q}; if (busy_q) descriptor_cpu_q <= descriptor_cpu_q ^ 30\'d1;',
             'descriptor source changed before next request'),
            ('result', 'request_sync_q <= {request_sync_q[0], request_toggle_q}; recovery_q <= 0;',
             'request_sync_q <= {request_sync_q[0], request_toggle_q}; recovery_q <= 0; '
             'if (state_q == IDLE) result_mailbox_q <= result_mailbox_q ^ 22\'d1;',
             'result source changed before next request'),
            ('snapshot', 'if (snapshot_ack_sync_q[1] == snapshot_toggle_q) begin', 'if (1\'b1) begin',
             'snapshot source changed before acknowledgement'))
        for name, before, after, message in mutations:
            with self.subTest(mailbox=name), tempfile.TemporaryDirectory(prefix='usb2-held-mailbox-negative-') as directory:
                stage = Path(directory)
                self.assertEqual(original.count(before), 1)
                (stage / 'mutant.sv').write_text(original.replace(before, after))
                compilation = subprocess.run(['iverilog', '-g2012', '-s', 'tb_workstation_usb2_cpu_bridge',
                    '-o', str(stage / 'simulation'), str(stage / 'mutant.sv'),
                    str(ROOT / 'sim/usb2/tb_workstation_usb2_cpu_bridge.sv')], text=True, capture_output=True, timeout=30)
                self.assertEqual(compilation.returncode, 0, compilation.stderr)
                execution = subprocess.run(['vvp', str(stage / 'simulation')], text=True, capture_output=True, timeout=20)
                self.assertNotEqual(execution.returncode, 0)
                self.assertIn(message, execution.stdout + execution.stderr)

    def test_actual_gowin_sta_keeps_payload_setup_and_second_stage_paths(self):
        self.assertIsNotNone(shutil.which('gw_sh'), 'Gowin is required for timing-exception consumption')
        bundle = cdc_bundle(ROOT)
        lines = bundle['sdc'].splitlines()
        selected = [line.replace(BRIDGE, 'crossing') for line in [*lines[:4], *lines[16:18]]]
        baseline = '\n'.join(selected) + '\n'
        cases = (('narrow', baseline, True),
                 ('wrong_payload_full_false_path', baseline.replace('set_false_path -hold', 'set_false_path'), False),
                 ('wrong_second_stage_false_path', baseline +
                  'set_false_path -to [get_pins {crossing/request_sync_q_1_s*/D}]\n', False))
        with tempfile.TemporaryDirectory(prefix='custom-usb2-cdc-sta-') as directory:
            base = Path(directory)
            if os.environ.get('GW138K_CUSTOM_USB2_CDC_STA_EVIDENCE'):
                base = Path(os.environ['GW138K_CUSTOM_USB2_CDC_STA_EVIDENCE'])
                base.mkdir(parents=True, exist_ok=False)
            evidence = dict(scope='isolated_dual_clock_constraint_consumption_probe_not_native_board_implementation',
                            cdc_plan_sha256=bundle['source_sha256'], cases=[], hardware_tested=False,
                            deployment_allowed=False, release_ready=False)
            for label, constraints, accepted in cases:
                stage = base / label
                stage.mkdir()
                shutil.copyfile(ROOT / 'sim/usb2/workstation_cdc_timing_probe.sv', stage / 'probe.sv')
                (stage / 'probe.sdc').write_text(
                    'create_clock -name cpu_48 -period 20.833333 [get_ports {clk_cpu}]\n'
                    'create_clock -name ulpi_60 -period 16.666667 [get_ports {clk_ulpi}]\n' + constraints)
                (stage / 'probe.cst').write_text('IO_LOC "clk_cpu" V22;\nIO_LOC "clk_ulpi" C18;\n'
                                               'IO_LOC "reset_n" C13;\nIO_LOC "observed" U15;\n'
                                               'IO_PORT "clk_cpu" IO_TYPE=LVCMOS33;\nIO_PORT "clk_ulpi" IO_TYPE=LVCMOS33;\n'
                                               'IO_PORT "reset_n" IO_TYPE=LVCMOS33;\nIO_PORT "observed" IO_TYPE=LVCMOS33;\n')
                project = ElementTree.Element('Project')
                ElementTree.SubElement(project, 'Template').text = 'FPGA'
                ElementTree.SubElement(project, 'Version').text = '5'
                device = json.loads((ROOT / 'boards/custom_138k/pinout.json').read_text())['device']
                ElementTree.SubElement(project, 'Device', name='GW5AST-138C', pn=device).text = 'gw5ast138c-006'
                files = ElementTree.SubElement(project, 'FileList')
                for relative, kind in (('probe.sv', 'file.verilog'), ('probe.sdc', 'file.sdc'), ('probe.cst', 'file.cst')):
                    ElementTree.SubElement(files, 'File', path=relative, type=kind, enable='1')
                ElementTree.ElementTree(project).write(stage / 'probe.gprj', encoding='UTF-8', xml_declaration=True)
                (stage / 'probe.tcl').write_text('cd [file dirname [info script]]\nopen_project probe.gprj\n'
                                                'set_option -top_module custom_cdc_timing_probe\n'
                                                'set_option -output_base_name cdc_probe\nset_option -verilog_std sysv2017\nrun all\n')
                result = subprocess.run(['gw_sh', str(stage / 'probe.tcl')], cwd=stage,
                                        text=True, capture_output=True, timeout=180)
                (stage / 'tool.log').write_text(result.stdout + result.stderr)
                self.assertEqual(result.returncode, 0, (stage / 'tool.log').read_text()[-4000:])
                self.assertNotRegex((stage / 'tool.log').read_text(), r'(?m)^ERROR\b')
                report = stage / 'impl/pnr/cdc_probe_tr_content.html'
                setup, hold = (timing_rows(report.read_text(), analysis) for analysis in ('Setup', 'Hold'))
                coverage = narrow_probe_coverage(setup, hold)
                self.assertEqual(all(coverage.values()), accepted, json.dumps(coverage) + '\n' + str(setup))
                evidence['cases'].append(dict(case=label, tool_returncode=result.returncode,
                    accepted_constraint_coverage=accepted, coverage=coverage, setup_paths=setup, hold_paths=hold,
                    sha256={str(source.relative_to(stage)): hashlib.sha256(source.read_bytes()).hexdigest()
                            for source in (stage / 'probe.sv', stage / 'probe.sdc', stage / 'probe.cst',
                                           stage / 'probe.gprj', stage / 'probe.tcl', stage / 'tool.log', report)}))
                (base / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
