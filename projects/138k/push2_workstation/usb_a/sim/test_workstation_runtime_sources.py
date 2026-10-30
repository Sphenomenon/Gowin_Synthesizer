#!/usr/bin/env python3
"""Audit real prepared runtime compile units and active include ownership.

This is Icarus preprocessing only, not synthesis or hardware acceptance.
GW138K_PROFILE_PREPARED selects an immutable, verified preparation. Optional
GW138K_RUNTIME_SOURCE_AUDIT writes the evidence outside the source tree.
"""
from pathlib import Path
import json
import os
import re
import subprocess
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_profile as profile
from tools import workstation_runtime_profile as runtime
from tools.workstation_baselines import load_baseline
from tools import workstation_custom_board_audit as board_audit
from tools import workstation_pinout as pinout
from tools.workstation_board_peripherals import prepare as prepare_peripherals
from tools.workstation_custom_flash import prepare as prepare_flash
from tools.workstation_custom_clocks import shared_cdc_bundle
from tools.workstation_timing_constraints import gray_write_alias_constraints
from test_workstation_pinout import fixture as pinout_fixture


def definitions(text):
    # Ignore comments and strings so a prose mention cannot become an owner.
    code = re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"', '', text)
    return re.findall(r'\b(module|package)\s+(?:automatic\s+)?([A-Za-z_$][\w$]*)', code)


def audit(output):
    output = Path(output).resolve()
    artifact = profile.verify(ROOT, output)
    stage = output / 'workstation/Prj1'
    baseline = load_baseline(ROOT, artifact['parent_baseline']['name'])
    ports = board_audit.check_ports(stage, json.loads((output / 'pinout/pinout.json').read_text()))

    def dependency_owner(path):
        if path in artifact['enabled_inputs']:
            return artifact['enabled_inputs'][path]
        if path in artifact['selected_source_owners']:
            owner = artifact['selected_source_owners'][path]
            return dict(origin='versioned_source', source=owner['source'],
                        source_sha256=owner['sha256'], sha256=artifact['staged_input_sha256'][path],
                        adapted=owner['sha256'] != artifact['staged_input_sha256'][path])
        if path in baseline.inputs:
            import hashlib
            original = hashlib.sha256(baseline.read_bytes(path)).hexdigest()
            return dict(origin='locked_parent_baseline', source=path, source_sha256=original,
                        sha256=artifact['staged_input_sha256'][path],
                        adapted=original != artifact['staged_input_sha256'][path])
        if path in artifact['generated_data_inputs']:
            return artifact['generated_data_inputs'][path]
        raise ValueError('runtime dependency has no provenance: ' + path)
    units = [item.get('path') for item in ET.parse(stage / 'Prj1.gprj').find('FileList')
             if item.get('enable') == '1' and item.get('type') == 'file.verilog']
    declarations, rows = {}, {}
    with tempfile.TemporaryDirectory(prefix='runtime-source-audit-') as temporary:
        temporary = Path(temporary)
        for index, unit in enumerate(units):
            preprocessed, dependencies = temporary / f'{index}.v', temporary / f'{index}.deps'
            command = ['iverilog', '-g2012', '-grelative-include', '-DSYNTHESIS', '-E', '-I', str(stage),
                       '-Mall=' + str(dependencies), '-o', str(preprocessed), unit]
            result = subprocess.run(command, cwd=stage, text=True, capture_output=True, timeout=30)
            if result.returncode:
                raise ValueError('runtime source preprocessing failed: ' + unit + '\n' + result.stderr)
            includes = sorted({Path(path).resolve().relative_to(stage).as_posix()
                               if Path(path).is_absolute() else Path(path).as_posix()
                               for path in dependencies.read_text().splitlines() if path})
            for dependency in includes:
                if dependency not in artifact['staged_input_sha256']:
                    raise ValueError('unowned runtime source dependency: ' + dependency)
            names = definitions(preprocessed.read_text())
            for kind, name in names:
                key = kind + ':' + name
                if key in declarations:
                    raise ValueError('duplicate runtime declaration: ' + key + ' in ' + declarations[key] + ' and ' + unit)
                declarations[key] = unit
            rows[unit] = dict(provenance=artifact['enabled_inputs'][unit],
                              declarations=[kind + ':' + name for kind, name in names],
                              dependencies={path: dependency_owner(path) for path in includes})
    required = ('workstation_custom_138k_top', 'hdmi_display', 'workstation_runtime_controlled',
                'workstation_runtime_audio', 'workstation_tf_runtime_service',
                'workstation_display_runtime', 'workstation_runtime_memory_guard',
                'scope_tf_transport', 'gw138k_controlled_services',
                'display_data_writer', 'display_data_reader', 'feedback_renderer')
    for module in required:
        if 'module:' + module not in declarations:
            raise ValueError('missing runtime declaration: ' + module)
    provider = 'rtl/workstation/workstation_profile_runtime.sv'
    if any(declarations['module:' + name] != provider for name in ('workstation_custom_138k_top', 'hdmi_display')):
        raise ValueError('runtime top/HDMI must share one macro-scoped compilation provider')
    if 'rtl/workstation/workstation_profile_hdmi.sv' not in rows[provider]['dependencies']:
        raise ValueError('runtime HDMI wrapper is not in the active include closure')
    for original, source in runtime.REPLACEMENTS.items():
        destination = runtime.INSTALL_PATHS.get(source, source)
        if original in rows or destination not in rows:
            raise ValueError('runtime replacement selection drift: ' + original)
    return dict(schema=1, candidate_identity=artifact['candidate_identity'],
                validation='iverilog_synthesis_macro_preprocessing_only',
                compilation_units=len(units), module_count=sum(key.startswith('module:') for key in declarations),
                package_count=sum(key.startswith('package:') for key in declarations),
                declarations=declarations, compilation=rows,
                selected_port_provenance=ports,
                synthesis_passed=False, hardware_tested=False, physical_gates_passed=False)


class DeclarationParser(unittest.TestCase):
    def test_comments_and_strings_do_not_invent_owners(self):
        self.assertEqual(definitions('// module fake\n/* package fake; */\nmodule actual;\n'
                                     'initial $display("module false"); endmodule'), [('module', 'actual')])

    def test_guard_gray_propagation_is_bounded_by_actual_source_period(self):
        selected = runtime.constraints(ROOT, dict(sdc=''))
        guard = selected['memory_guard_gray']
        self.assertEqual(guard['source_clock'], 'ddr_ui100')
        self.assertEqual(guard['source_clock_hz'], 100000000)
        self.assertEqual(guard['max_delay_ns'], 10)
        self.assertFalse(guard['setup_false_path'])
        self.assertFalse(guard['endpoint_and_routed_bound_verified'])
        paths = [line for line in selected['sdc'].splitlines() if 'memory_gray' in line]
        self.assertEqual(len(paths), 2)
        self.assertTrue(any(line.startswith('set_max_delay 10.000 ') for line in paths))
        self.assertTrue(any(line.startswith('set_false_path -hold ') for line in paths))
        self.assertFalse(any(line.startswith('set_false_path -to ') for line in paths))


class SharedConstraintSelection(unittest.TestCase):
    def test_mixed_queries_preserve_surviving_endpoints_on_each_side(self):
        line = ('set_max_delay 10 -from [get_regs {u_managed/old* u_cpu/held*}] '
                '-to [get_pins {u_tf_audio/old*/D u_runtime/u_cpu_cdc/req_meta*/D}]\n')
        selected = runtime.shared_constraints(line)
        self.assertEqual(selected['sdc'], 'set_max_delay 10 -from [get_regs {u_cpu/held*}] '
                         '-to [get_pins {u_runtime/u_cpu_cdc/req_meta*/D}]\n')
        self.assertEqual(len(selected['adapted']), 1)
        self.assertEqual(selected['omitted'], [])
        self.assertEqual(selected['adapted'][0]['removed_selectors'],
                         ['u_managed/old*', 'u_tf_audio/old*/D'])

    def test_empty_query_side_omits_whole_command(self):
        for side in ('-from', '-to'):
            line = ('set_max_delay 10 ' + side + ' [get_regs {u_managed/old*}] '
                    + ('-to' if side == '-from' else '-from') + ' [get_regs {u_cpu/held*}]\n')
            selected = runtime.shared_constraints(line)
            with self.subTest(side=side):
                self.assertEqual(selected['sdc'], '')
                self.assertEqual(selected['adapted'], [])
                self.assertEqual(len(selected['omitted']), 1)
                self.assertEqual(selected['omitted'][0]['empty_query_sides'], ['get_regs'])

    def test_unknown_retired_query_format_fails_closed(self):
        for line in ('set_false_path -to [get_pins u_managed/old*/D]',
                     'set_false_path -to [unknown_query {u_managed/old*/D}]',
                     'set_false_path -from [get_regs {u_managed/old*}] '
                     '-to [get_pins u_tf_audio/old*/D]'):
            with self.subTest(line=line), self.assertRaisesRegex(ValueError, 'unsupported runtime shared CDC'):
                runtime.shared_constraints(line)

    def test_locked_parent_recovers_three_mixed_commands(self):
        baseline = load_baseline(ROOT, 'resource_rework_route0')
        with tempfile.TemporaryDirectory(prefix='runtime-shared-sdc-') as directory:
            stage = Path(directory)
            (stage / 'constraints').mkdir()
            (stage / 'constraints/tang_mega_138k.sdc').write_bytes(
                baseline.read_bytes('constraints/tang_mega_138k.sdc')
                + gray_write_alias_constraints().encode())
            parent = shared_cdc_bundle(stage)
        selected = runtime.shared_constraints(parent['sdc'])
        self.assertEqual(len(parent['sdc'].splitlines()), 157)
        self.assertEqual(len(selected['sdc'].splitlines()), 106)
        self.assertEqual(len(selected['omitted']), 51)
        self.assertEqual([item['selected'] for item in selected['adapted']], [
            'set_false_path -to [get_pins {u_runtime/u_cpu_cdc/source_release*/CLEAR '
            'u_runtime/u_cpu_cdc/destination_release*/CLEAR}]',
            'set_false_path -to [get_pins {u_runtime/u_cpu_cdc/req_meta*/D '
            'u_runtime/u_cpu_cdc/ack_meta*/D}]',
            'set_false_path -to [get_pins {u_native_usb/input_owner/analysis_done_meta*/D}]',
        ])
        untouched = [line for line in parent['sdc'].splitlines()
                     if not any(prefix in line for prefix in runtime.REPLACED_CDC_PREFIXES)]
        self.assertEqual([line for line in selected['sdc'].splitlines()
                          if line not in {item['selected'] for item in selected['adapted']}], untouched)


class SelectedTopPorts(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='runtime-top-port-')
        self.addCleanup(temporary.cleanup)
        self.stage = Path(temporary.name).resolve()
        selected, payloads, _ = pinout_fixture()
        baseline = load_baseline(ROOT, selected['core_baseline'])
        self.plan = pinout.resolve(selected, {role: pinout.Netlist(data) for role, data in payloads.items()},
                                   baseline.read_bytes('constraints/tang_mega_138k.cst').decode('utf-8-sig'))
        for relative in (board_audit.SHARED_TOP, 'rtl/workstation/workstation_custom_138k_top.sv',
                         'rtl/workstation/workstation_profile_runtime.sv',
                         'rtl/workstation/workstation_profile_hdmi.sv',
                         'rtl/workstation/workstation_hdmi_display.sv', 'probes/audio_clock_i2s/probe.json'):
            target = self.stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        (self.stage / 'constraints').mkdir()
        mapping = json.loads((ROOT / 'boards/custom_138k/bluetooth.json').read_text())
        for name, record in mapping['ports'].items():
            self.plan['ports'][name] = dict(balls=[record['ball']], origin='reviewed_core_connector_bluetooth')
        prepare_peripherals(ROOT, self.stage, self.plan, self.stage)
        prepare_flash(ROOT, self.stage, self.plan, self.stage)
        self.locations = pinout.render_constraints(self.plan)
        (self.stage / 'constraints/custom_138k.locations.cst').write_text(self.locations)

    def select(self, runtime_enabled):
        provider = ('rtl/workstation/workstation_profile_runtime.sv' if runtime_enabled else
                    'rtl/workstation/workstation_custom_138k_top.sv')
        project = ET.Element('Project')
        files = ET.SubElement(project, 'FileList')
        ET.SubElement(files, 'File', path=provider, type='file.verilog', enable='1')
        ET.ElementTree(project).write(self.stage / 'Prj1.gprj')
        extra = 'IO_LOC "clk_16m9344" J19;\n' if runtime_enabled else ''
        (self.stage / 'constraints/custom_138k.cst').write_text(self.locations + extra)
        return provider

    def test_actual_default_provider_keeps_conditional_runtime_port_absent(self):
        provider = self.select(False)
        result = board_audit.check_ports(self.stage, self.plan)
        self.assertEqual(result['compilation_provider'], provider)
        self.assertEqual(result['supplemental_ports'], {})
        self.assertFalse(result['runtime_physical_audits_covered'])

    def test_actual_runtime_provider_requires_reviewed_clock_port_and_location(self):
        provider = self.select(True)
        result = board_audit.check_ports(self.stage, self.plan)
        self.assertEqual(result['compilation_provider'], provider)
        self.assertEqual(result['supplemental_ports'], {'clk_16m9344': ['J19']})
        self.assertEqual(result['scope'], 'selected_source_ports_only')
        combined = self.stage / 'constraints/custom_138k.cst'
        combined.write_text(combined.read_text().replace('"clk_16m9344" J19;', '"clk_16m9344" J18;'))
        with self.assertRaisesRegex(ValueError, 'combined CST locations differ'):
            board_audit.check_ports(self.stage, self.plan)

    def test_missing_or_extra_ports_are_rejected_after_preprocessing(self):
        self.select(False)
        source = self.stage / board_audit.SHARED_TOP
        original = source.read_text()
        self.assertIn('input wire clk_50m,', original)
        source.write_text(original.replace('input wire clk_50m,', 'input wire clk_50m, input wire unexpected_port,', 1))
        with self.assertRaisesRegex(ValueError, 'port coverage mismatch'):
            board_audit.check_ports(self.stage, self.plan)
        source.write_text(original)
        self.select(True)
        source.write_text(original.replace('    input wire clk_16m9344,\n', '', 1))
        with self.assertRaisesRegex(ValueError, 'port coverage mismatch'):
            board_audit.check_ports(self.stage, self.plan)

    def test_two_selected_top_providers_are_rejected(self):
        self.select(False)
        project = self.stage / 'Prj1.gprj'
        tree = ET.parse(project)
        ET.SubElement(tree.find('FileList'), 'File', path='rtl/workstation/workstation_profile_runtime.sv',
                      type='file.verilog', enable='1')
        tree.write(project)
        with self.assertRaisesRegex(ValueError, 'exactly one selected compilation provider'):
            board_audit.check_ports(self.stage, self.plan)


@unittest.skipUnless(os.environ.get('GW138K_PROFILE_PREPARED'), 'Set GW138K_PROFILE_PREPARED')
class ActualPreparedSources(unittest.TestCase):
    def test_no_duplicate_declaration_or_unowned_dependency(self):
        result = audit(os.environ['GW138K_PROFILE_PREPARED'])
        self.assertGreater(result['compilation_units'], 200)
        self.assertGreater(result['module_count'], 200)
        if os.environ.get('GW138K_RUNTIME_SOURCE_AUDIT'):
            destination = Path(os.environ['GW138K_RUNTIME_SOURCE_AUDIT']).resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({key: result[key] for key in ('candidate_identity', 'compilation_units',
                                                       'module_count', 'package_count')}))


if __name__ == '__main__':
    unittest.main()
