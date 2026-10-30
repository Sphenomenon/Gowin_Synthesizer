#!/usr/bin/env python3
"""Reject evidence drift before and during the maintained physical PLL gate."""
import copy
import json
import os
import re
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from workstation_physical_pll_audit import (physical_snapshot, sha, verify_unchanged,
    pll_inventory, shared_clock_plls, source_context, audit_workspace, audit_output_path)
from workstation_runtime_clock_audit import PLL_PATHS, verify_synthesis_identity
from workstation_profile import R00_NO_LOCAL_PANEL_NAME, specification, identity_digest


class InputBindingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.input = self.root / 'physical.sdc'
        self.input.write_text('original constraint\n')
        self.route = self.root / 'routed.sdf'
        self.route.write_text('original routed delay\n')
        self.manifest = self.root / 'physical_inputs.json'
        self.manifest.write_text(json.dumps({'identity': 'test-physical',
                                            'input_sha256': {'physical.sdc': sha(self.input)}}))

    def snapshot(self):
        return physical_snapshot(self.root, (self.route,))

    def test_unchanged_inputs_pass(self):
        inputs, snapshot = self.snapshot()
        self.assertEqual(inputs['identity'], 'test-physical')
        verify_unchanged(snapshot)

    def test_reject_initial_input_drift(self):
        self.input.write_text('changed before audit\n')
        with self.assertRaisesRegex(ValueError, 'Physical input drift'):
            self.snapshot()

    def test_reject_manifest_mutation_even_if_still_valid_json(self):
        inputs, snapshot = self.snapshot()
        self.manifest.write_text(self.manifest.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'physical_inputs.json'):
            verify_unchanged(snapshot)

    def test_reject_physical_input_mutation(self):
        inputs, snapshot = self.snapshot()
        self.input.write_text('changed during audit\n')
        with self.assertRaisesRegex(ValueError, 'physical.sdc'):
            verify_unchanged(snapshot)

    def test_reject_routed_evidence_mutation(self):
        inputs, snapshot = self.snapshot()
        self.route.write_text('changed during audit\n')
        with self.assertRaisesRegex(ValueError, 'routed.sdf'):
            verify_unchanged(snapshot)

    def test_reject_manifest_path_escape(self):
        self.manifest.write_text(json.dumps({'input_sha256': {'../outside': 'unused'}}))
        with self.assertRaisesRegex(ValueError, 'Physical input drift'):
            self.snapshot()



class TupleTests(unittest.TestCase):
    prefixes = ('u_audio_clock/g_hardware.u_pll', 'u_usb_pll', 'u_cpu_pll', 'u_lcd/u_pll')

    def fixture(self, panel=True):
        class Routed:
            def bits(self, expression): return expression
            def route(self, source, target): return 2
            def arc(self, *unused): return 1
        r = Routed()
        r.cells = {name: ('PLL', {}) for name in PLL_PATHS
                   if panel or name != 'u_lcd/u_pll/PLL_inst'}
        r.clock_net = 'direct50'
        r.input_delay = 1
        r.constants = {'GND': 0, 'VCC': 1}
        r.drivers = {}
        for prefix in self.prefixes[:4 if panel else 3]:
            ports = {}
            for bus, width, first in (('ICPSEL', 6, 3), ('LPFRES', 3, 0), ('RESET', 1, 9)):
                ports[bus] = []
                for bit in reversed(range(width)):
                    net = prefix + '/' + bus + str(bit)
                    driver = prefix + '/pll_control_' + str(first + bit) + '_s17'
                    ports[bus].append(net)
                    r.drivers[net] = (driver, 'Q')
                    r.cells[driver] = ('DFF', {'CLK': r.clock_net, 'Q': net})
            r.cells[prefix + '/PLL_inst'] = ('PLL', ports)
        return r

    def check(self, routed, panel=True):
        return shared_clock_plls('', '', lambda *unused: routed, local_panel_enabled=panel)

    def test_default_retains_four_tuples_and_all_seven_plls(self):
        errors, result = self.check(self.fixture())
        self.assertEqual(errors, [])
        self.assertEqual(set(result), set(self.prefixes))
        self.assertTrue(all(len(item['paths']) == 10 and item['bound_ns'] == 10 for item in result.values()))

    def test_no_panel_keeps_three_complete_tuples_and_six_plls(self):
        errors, result = self.check(self.fixture(False), False)
        self.assertEqual(errors, [])
        self.assertEqual(set(result), set(self.prefixes[:3]))
        self.assertTrue(all(len(item['paths']) == 10 for item in result.values()))

    def test_default_rejects_absent_lcd_and_no_panel_rejects_extra_lcd(self):
        self.assertIn('Selected PLL inventory changed', self.check(self.fixture(False))[0][0])
        self.assertIn('Selected PLL inventory changed', self.check(self.fixture(), False)[0][0])

    def test_every_required_pll_cannot_be_missing_or_replaced(self):
        for panel in (True, False):
            base = self.fixture(panel)
            for name in pll_inventory(base.cells, local_panel_enabled=panel):
                with self.subTest(panel=panel, missing=name):
                    r = copy.deepcopy(base)
                    del r.cells[name]
                    self.assertIn('Selected PLL inventory changed', self.check(r, panel)[0][0])
            base.cells['unreviewed/PLL_inst'] = ('PLL', {})
            self.assertIn('Selected PLL inventory changed', self.check(base, panel)[0][0])

    def test_every_control_bit_preserves_owner_clock_and_budget(self):
        for panel in (True, False):
            base = self.fixture(panel)
            for prefix in self.prefixes[:4 if panel else 3]:
                ports = base.cells[prefix + '/PLL_inst'][1]
                for bus in ('ICPSEL', 'LPFRES', 'RESET'):
                    for bit, net in enumerate(ports[bus]):
                        driver = base.drivers[net][0]
                        for mutation in ('owner', 'clock', 'constant', 'delay'):
                            with self.subTest(panel=panel, prefix=prefix, bus=bus, bit=bit, mutation=mutation):
                                r = copy.deepcopy(base)
                                if mutation == 'owner': r.drivers[net] = ('other/pll_control_9_s17', 'Q')
                                elif mutation == 'clock': r.cells[driver][1]['CLK'] = 'different_clock'
                                elif mutation == 'constant': r.constants[net] = 1
                                else: r.route = lambda source, target: 9
                                self.assertTrue(self.check(r, panel)[0])

    def test_every_tuple_bus_width_and_output_pin_are_strict(self):
        for panel in (True, False):
            base = self.fixture(panel)
            for prefix in self.prefixes[:4 if panel else 3]:
                for bus in ('ICPSEL', 'LPFRES', 'RESET'):
                    r = copy.deepcopy(base)
                    r.cells[prefix + '/PLL_inst'][1][bus].append('extra')
                    self.assertTrue(self.check(r, panel)[0])
            net = base.cells[self.prefixes[0] + '/PLL_inst'][1]['RESET'][0]
            base.drivers[net] = (base.drivers[net][0], 'QN')
            self.assertTrue(self.check(base, panel)[0])

    def test_selection_is_boolean_and_parser_failure_is_a_gate_failure(self):
        with self.assertRaisesRegex(ValueError, 'explicit boolean'):
            pll_inventory(self.fixture().cells, local_panel_enabled='off')
        errors, unused = shared_clock_plls('', '', lambda *unused: (_ for _ in ()).throw(ValueError('bad SDF')))
        self.assertEqual(errors, ['bad SDF'])


class SourceSelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.physical = self.root / 'physical'
        self.physical.mkdir()
        self.stage = self.root / 'source/workstation/Prj1'
        self.stage.mkdir(parents=True)

    def fixture(self, *, profile_change=None, panel_change=None):
        stage = self.stage
        (stage / 'source.sv').write_text('source input\n')
        vg = stage / 'impl/gwsynthesis/custom_138k_integration.vg'
        vg.parent.mkdir(parents=True, exist_ok=True)
        vg.write_text('fixture VG\n')
        closure = {'source.sv': sha(stage / 'source.sv')}
        parent = dict(staged_input_sha256=closure, local_panel=dict(enabled=False, sources=[], sdc='',
            touch_input_selected=False, output_behavior='all_21_lcd_output_bits_static_low_backlight_off'))
        if panel_change: panel_change(parent)
        spec = specification(R00_NO_LOCAL_PANEL_NAME)
        profile = dict(profile=R00_NO_LOCAL_PANEL_NAME, revision=spec['revision'], configuration=copy.deepcopy(spec['configuration']),
            profile_source=spec['config'], profile_sha256='a' * 64, source_snapshot_sha256={}, firmware={}, ae350_firmware={},
            staged_input_sha256=closure, integration_metadata_sha256=identity_digest(parent))
        if profile_change: profile_change(profile)
        candidate_hash = identity_digest({key: profile[key] for key in ('profile_sha256', 'staged_input_sha256', 'source_snapshot_sha256', 'firmware', 'ae350_firmware')})
        profile.update(candidate_input_sha256=candidate_hash, candidate_identity=profile['profile'] + '-' + candidate_hash[:16])
        source = stage.parents[1]
        (source / 'workstation_profile.json').write_text(json.dumps(profile))
        (source / 'integration_inputs.json').write_text(json.dumps(parent))
        process_path = source / 'process.json'
        process_path.write_text(json.dumps(dict(completed=True, exit_code=0, inputs_unchanged=True, stage='synthesis_only',
            cwd=str(stage), candidate_identity=profile['candidate_identity'], input_sha256=closure,
            output_sha256={'impl/gwsynthesis/custom_138k_integration.vg': sha(vg)})))
        sealed = verify_synthesis_identity(stage, process_path)
        files = {'parent/workstation_profile.json': (source / 'workstation_profile.json').read_bytes(),
                 'parent/integration_inputs.json': (source / 'integration_inputs.json').read_bytes(),
                 'parent_synthesis_process.json': process_path.read_bytes(), 'custom_138k_integration.vg': vg.read_bytes()}
        for name, data in files.items():
            path = self.physical / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        inputs = dict(identity='fixture-physical', source=dict(synthesis=sealed, candidate_identity=sealed['candidate_identity'],
            staged_input_sha256=closure), input_sha256={name: sha(self.physical / name) for name in files})
        (self.physical / 'physical_inputs.json').write_text(json.dumps(inputs))
        return inputs

    def context(self, inputs):
        unused, snapshot = physical_snapshot(self.physical)
        result = source_context(self.physical, inputs, snapshot)
        verify_unchanged(snapshot)
        return result

    def test_explicit_sealed_no_panel_profile_selects_six(self):
        inputs = self.fixture()
        stage, parent, panel, selection = self.context(inputs)
        self.assertEqual(stage, self.stage)
        self.assertIs(panel, False)
        self.assertIs(selection['acceptance_inherited'], False)
        self.assertEqual(selection['candidate_identity'], inputs['source']['candidate_identity'])

    def test_source_context_standalone_import_keeps_the_same_binding(self):
        self.fixture()
        tools = Path(__file__).resolve().parents[1] / 'tools'
        program = ("import json,sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
                   "from workstation_physical_pll_audit import physical_snapshot,source_context; "
                   "p=Path(sys.argv[2]); m,s=physical_snapshot(p); "
                   "assert source_context(p,m,s)[2] is False")
        result = subprocess.run([sys.executable, '-c', program, str(tools), str(self.physical)],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_metadata_free_legacy_retains_lcd(self):
        parent = self.physical / 'parent_integration_inputs.json'
        parent.write_text('{}')
        result = source_context(self.physical, dict(parent_candidate=str(self.stage.parents[1])), {})
        self.assertIs(result[2], True)
        self.assertEqual(result[3]['policy'], 'legacy_default_LCD_required')

    def test_reject_no_panel_scope_mutations(self):
        for name, profile_change, panel_change, expected in (
                ('revision', lambda p: p.update(revision=3), None, 'Explicit no-local-panel'),
                ('source', lambda p: p.update(profile_source='other.json'), None, 'Explicit no-local-panel'),
                ('configuration', lambda p: p['configuration'].update(local_panel_policy='enabled'), None, 'Explicit no-local-panel'),
                ('metadata', None, lambda p: p['local_panel'].update(enabled=True), 'Explicit no-local-panel'),
                ('implicit', lambda p: p.update(profile='unknown-no-panel'), None, 'requires its explicit profile')):
            with self.subTest(name=name):
                inputs = self.fixture(profile_change=profile_change, panel_change=panel_change)
                with self.assertRaisesRegex(ValueError, expected): self.context(inputs)

    def test_reject_candidate_source_process_vg_and_copy_identity_substitution(self):
        inputs = self.fixture()
        for field, value in [('candidate_identity', 'different-candidate'), ('process_sha256', '0' * 64),
                             ('vg_sha256', '0' * 64), ('prepared_profile_sha256', '0' * 64)]:
            broken = copy.deepcopy(inputs)
            broken['source']['synthesis'][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'synthesis identity differs'):
                self.context(broken)
        broken = copy.deepcopy(inputs)
        broken['input_sha256']['custom_138k_integration.vg'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'metadata linkage differs'): self.context(broken)
        (self.physical / 'parent/workstation_profile.json').write_text('{}')
        inputs['input_sha256']['parent/workstation_profile.json'] = sha(self.physical / 'parent/workstation_profile.json')
        (self.physical / 'physical_inputs.json').write_text(json.dumps(inputs))
        with self.assertRaisesRegex(ValueError, 'copied metadata differs'): self.context(inputs)

    def test_nested_paths_allowed_but_symlink_and_absolute_escapes_fail(self):
        self.fixture()
        physical_snapshot(self.physical)
        outside = self.root / 'outside'
        outside.write_text('outside')
        (self.physical / 'link').symlink_to(outside)
        for name in ('link', str(outside), '../outside'):
            (self.physical / 'physical_inputs.json').write_text(json.dumps(dict(input_sha256={name: sha(outside)})))
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Physical input drift'):
                physical_snapshot(self.physical)

    def test_external_workspace_required_and_source_physical_overlap_rejected(self):
        self.fixture()
        with self.assertRaisesRegex(ValueError, 'requires a new external'):
            audit_workspace(self.physical, self.stage, False, None)
        for path in (self.physical, self.physical / 'new', self.stage, self.stage / 'new', self.root):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'new and separate'):
                audit_workspace(self.physical, self.stage, False, path)
        expected = self.root / 'external-output'
        self.assertEqual(audit_workspace(self.physical, self.stage, False, expected), expected)
        self.assertFalse(expected.exists())

    def test_external_json_cannot_overwrite_physical_or_source_inputs(self):
        self.fixture()
        for path in (self.physical / 'review.json', self.stage / 'review.json',
                     self.stage.parents[1] / 'workstation_profile.json'):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'outside physical/source'):
                audit_output_path(self.physical, self.stage, path)
        expected = self.root / 'external-review.json'
        self.assertEqual(audit_output_path(self.physical, self.stage, expected), expected)
        self.assertFalse(expected.exists())
        expected.write_text('sealed previous evidence\n')
        with self.assertRaisesRegex(ValueError, 'must be new'):
            audit_output_path(self.physical, self.stage, expected)
        self.assertEqual(expected.read_text(), 'sealed previous evidence\n')


class ActualCandidates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selection = os.environ.get('GW138K_PLL_AUDIT_PHYSICALS')
        if not selection:
            raise unittest.SkipTest('select existing physical manifests with GW138K_PLL_AUDIT_PHYSICALS; never invokes EDA')
        cls.paths = [Path(path).resolve() for path in selection.split(os.pathsep)]

    def test_actual_profile_source_and_exact_synthesized_pll_inventory(self):
        from workstation_synthesis_netlist import SynthesisNetlist
        for physical in self.paths:
            with self.subTest(physical=physical):
                inputs, snapshot = physical_snapshot(physical)
                stage, parent, panel, selection = source_context(physical, inputs, snapshot)
                if 'source' not in inputs:
                    # Legacy routed VO has the same exact primitive hierarchy.
                    text = (physical / 'impl/pnr/custom_138k_integration.vo').read_text()
                    cells = {m[2].lstrip('\\'): (m[1], {}) for m in re.finditer(
                        r'^(\w+)\s+(\\\S+|\w+)\s+\((.*?)^\);', text, re.M | re.S)}
                else:
                    text = (stage / 'impl/gwsynthesis/custom_138k_integration.vg').read_text()
                    netlist = SynthesisNetlist(text, 'workstation_custom_138k_top')
                    cells = {name: (item['kind'], {}) for name, item in netlist.cells.items()}
                    self.assertIs(selection['acceptance_inherited'], False)
                expected = 7 if panel else 6
                self.assertEqual(len(pll_inventory(cells, local_panel_enabled=panel)), expected)
                with self.assertRaisesRegex(ValueError, 'Selected PLL inventory changed'):
                    pll_inventory(cells, local_panel_enabled=not panel)
                verify_unchanged(snapshot)

    def test_distinct_no_panel_candidates_cannot_substitute_source_identity(self):
        records = [(path, physical_snapshot(path)[0]) for path in self.paths]
        records = [(path, value) for path, value in records if 'source' in value]
        if len(records) < 2: self.skipTest('two sealed source candidates required')
        for physical, inputs in records:
            for other, replacement in records:
                if physical == other: continue
                broken = copy.deepcopy(inputs)
                broken['source'] = replacement['source']
                with self.subTest(physical=physical, replacement=other), self.assertRaisesRegex(ValueError, 'copied metadata differs'):
                    source_context(physical, broken, {})


if __name__ == '__main__':
    unittest.main()
