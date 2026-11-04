#!/usr/bin/env python3
"""Verify locked baseline reconstruction, provenance, and fail-closed behavior."""
from pathlib import Path
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from baseline_fixture import digest, rewrite_descriptor, write_baseline
from workstation_baselines import load_baseline, relative_name
from workstation_composition import SOURCES as COMPOSITION_SOURCES


class BaselineSources(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repository/projects/138k/push2_workstation/usb_a'
        self.files = {
            'Prj1.gprj': '<Project><FileList><File path="src/core.sv"/></FileList></Project>',
            'src/core.sv': b'module core;\r\nendmodule\r\n',
            'rtl/music/weights.mem': '0001\n0002\n',
        }
        self.fixture = write_baseline(self.root, 'test', self.files,
                                      excluded={'docs/evidence/history.log': 'historical capture\n'},
                                      metadata={'build_metadata.json': b'{"hardware_tested": false}\n'})

    def test_exact_bytes_and_metadata_are_reconstructed(self):
        baseline = load_baseline(self.root, 'test')
        output = self.root / 'new_output'
        baseline.materialize(output / 'Prj1')
        baseline.copy_metadata(output)
        for name, value in self.files.items():
            expected = value.encode() if isinstance(value, str) else value
            self.assertEqual((output / 'Prj1' / name).read_bytes(), expected)
        self.assertFalse((output / 'Prj1/docs').exists())
        self.assertEqual(json.loads((output / 'build_metadata.json').read_text()), {'hardware_tested': False})
        self.assertEqual(baseline.verify(), 1)
        self.assertEqual(baseline.evidence()['excluded_files'], 1)

    def test_no_historical_results_are_needed(self):
        self.assertFalse((self.root / 'results').exists())
        baseline = load_baseline(self.root, 'test')
        self.assertEqual(baseline.music, {'rtl/music/weights.mem': self.fixture.inputs['rtl/music/weights.mem']})

    def test_source_corruption_or_missing_source_fails_before_creating_output(self):
        baseline = load_baseline(self.root, 'test')
        source = self.fixture.project / 'src/core.sv'
        for action in ('corrupt', 'missing'):
            with self.subTest(action=action):
                if action == 'corrupt':
                    source.write_bytes(b'wrong source')
                else:
                    source.unlink()
                output = self.root / action
                with self.assertRaisesRegex(ValueError, 'input tree drifted: src/core.sv'):
                    baseline.materialize(output)
                self.assertFalse(output.exists())
                source.write_bytes(self.files['src/core.sv'])

    def test_existing_output_is_not_overwritten_or_deleted(self):
        baseline = load_baseline(self.root, 'test')
        output = self.root / 'existing'
        output.mkdir()
        (output / 'keep').write_text('user work')
        with self.assertRaises(FileExistsError):
            baseline.materialize(output)
        self.assertEqual((output / 'keep').read_text(), 'user work')

    def test_descriptor_drift_is_rejected(self):
        self.fixture.manifest.write_text(self.fixture.manifest.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'baseline manifest is missing or changed'):
            load_baseline(self.root, 'test')

    def test_origin_manifest_drift_is_rejected(self):
        self.fixture.original.write_text(self.fixture.original.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'origin manifest is missing or changed'):
            load_baseline(self.root, 'test')

    def test_changed_original_digest_cannot_be_rebound(self):
        rewrite_descriptor(self.root, 'test',
                           lambda value: value['files']['src/core.sv'].update(sha256='0' * 64))
        with self.assertRaisesRegex(ValueError, 'differs from origin input: src/core.sv'):
            load_baseline(self.root, 'test')

    def test_unlisted_inputs_cannot_be_added(self):
        rewrite_descriptor(self.root, 'test',
                           lambda value: value['files'].update({'extra.sv': value['files']['src/core.sv']}))
        with self.assertRaisesRegex(ValueError, 'does not partition the origin inputs'):
            load_baseline(self.root, 'test')

    def test_production_inputs_cannot_be_excluded(self):
        def exclude_core(value):
            value['files'].pop('src/core.sv')
            value['excluded']['src/core.sv'] = 'historical_documentation_or_capture'
        rewrite_descriptor(self.root, 'test', exclude_core)
        with self.assertRaisesRegex(ValueError, 'cannot exclude a production baseline input'):
            load_baseline(self.root, 'test')

    def test_retired_document_outside_docs_does_not_supply_production_input(self):
        write_baseline(self.root, 'retired', self.files,
                       excluded={'rtl/audio/README.md': 'historical notes'})
        baseline = load_baseline(self.root, 'retired')
        self.assertEqual(set(baseline.inputs), set(self.files))
        baseline.materialize(self.root / 'retired-output')
        self.assertFalse((self.root / 'retired-output/rtl/audio/README.md').exists())

    def test_document_extension_cannot_hide_a_project_input(self):
        write_baseline(self.root, 'referenced_doc',
                       {'Prj1.gprj': '<Project><File path="src/core.md"/></Project>'},
                       excluded={'src/core.md': 'module core; endmodule'})
        with self.assertRaisesRegex(ValueError, 'project files missing from locked baseline'):
            load_baseline(self.root, 'referenced_doc')

    def test_gprj_reference_must_be_in_source_closure(self):
        write_baseline(self.root, 'incomplete',
                       {'Prj1.gprj': '<Project><File path="src/missing.sv"/></Project>'})
        with self.assertRaisesRegex(ValueError, 'project files missing from locked baseline'):
            load_baseline(self.root, 'incomplete')

    def test_missing_metadata_is_rejected(self):
        (self.root / 'fixture_sources/test/build_metadata.json').unlink()
        with self.assertRaisesRegex(ValueError, 'input tree drifted: build_metadata.json'):
            load_baseline(self.root, 'test')

    def test_unsafe_paths_are_rejected(self):
        for name in ('', '.', '../outside', 'src/../outside', '/absolute', 'src//core.sv',
                     'src/./core.sv', 'C:/outside', 'src\\core.sv'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                relative_name(name)

    def test_source_path_traversal_is_rejected(self):
        rewrite_descriptor(self.root, 'test',
                           lambda value: value['files']['src/core.sv'].update(source='../outside'))
        with self.assertRaisesRegex(ValueError, 'unsafe baseline path'):
            load_baseline(self.root, 'test')

    def test_source_symlink_cannot_escape_repository(self):
        source = self.fixture.project / 'src/core.sv'
        external = Path(self.temp.name) / 'outside.sv'
        external.write_bytes(source.read_bytes())
        source.unlink()
        source.symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'source escapes repository'):
            load_baseline(self.root, 'test')

    def test_encoded_input_preserves_original_eof(self):
        source = self.fixture.project / 'Prj1.gprj'
        original = source.read_bytes()
        payload = base64.b64encode(original) + b'\n'
        source.write_bytes(payload)
        rewrite_descriptor(self.root, 'test',
                           lambda value: value['files']['Prj1.gprj'].update(
                               encoding='base64', source_sha256=digest(payload)))
        baseline = load_baseline(self.root, 'test')
        self.assertEqual(baseline.read_bytes('Prj1.gprj'), original)
        self.assertFalse(baseline.read_bytes('Prj1.gprj').endswith(b'\n'))

    def test_decoded_payload_cannot_change_even_with_updated_storage_hash(self):
        source = self.fixture.project / 'src/core.sv'
        payload = base64.b64encode(b'changed core') + b'\n'
        source.write_bytes(payload)
        rewrite_descriptor(self.root, 'test',
                           lambda value: value['files']['src/core.sv'].update(
                               encoding='base64', source_sha256=digest(payload)))
        with self.assertRaisesRegex(ValueError, 'decoded input tree drifted: src/core.sv'):
            load_baseline(self.root, 'test')

    def test_unknown_baseline_cannot_fall_back_to_local_results(self):
        with self.assertRaisesRegex(ValueError, 'unknown locked baseline'):
            load_baseline(self.root, 'latest_build')

    def test_git_lf_and_working_tree_crlf_reconstruct_identical_original_bytes(self):
        source = self.fixture.project / 'src/core.sv'
        original = source.read_bytes()
        normalized = original.replace(b'\r\n', b'\n')
        rewrite_descriptor(self.root, 'test',
                           lambda value: value['files']['src/core.sv'].update(
                               encoding='crlf', source_sha256=digest(normalized)))
        for stored in (normalized, original):
            source.write_bytes(stored)
            self.assertEqual(load_baseline(self.root, 'test').read_bytes('src/core.sv'), original)
        source.write_bytes(normalized + b'changed source\n')
        with self.assertRaisesRegex(ValueError, 'input tree drifted: src/core.sv'):
            load_baseline(self.root, 'test')

    def test_mixed_line_endings_are_restored_by_explicit_line_map(self):
        original = b'line one\r\nline two\nline three\r\nlast line without newline'
        fixture = write_baseline(self.root, 'mixed', {'core.sv': original})
        normalized = original.replace(b'\r\n', b'\n')
        (fixture.project / 'core.sv').write_bytes(normalized)
        rewrite_descriptor(self.root, 'mixed',
                           lambda value: value['files']['core.sv'].update(
                               encoding='crlf', source_sha256=digest(normalized), crlf_lines=[1, 3]))
        self.assertEqual(load_baseline(self.root, 'mixed').read_bytes('core.sv'), original)

    def test_invalid_line_maps_are_rejected(self):
        source = self.fixture.project / 'src/core.sv'
        normalized = source.read_bytes().replace(b'\r\n', b'\n')
        for endings in ([0], [3], [1, 1], ['1'], [[1]]):
            rewrite_descriptor(self.root, 'test',
                               lambda value: value['files']['src/core.sv'].update(
                                   encoding='crlf', source_sha256=digest(normalized), crlf_lines=endings))
            with self.subTest(endings=endings), self.assertRaisesRegex(ValueError, 'invalid baseline CRLF line map'):
                load_baseline(self.root, 'test')

    def test_raw_inputs_do_not_silently_normalize_newlines(self):
        source = self.fixture.project / 'src/core.sv'
        source.write_bytes(source.read_bytes().replace(b'\r\n', b'\n'))
        with self.assertRaisesRegex(ValueError, 'input tree drifted: src/core.sv'):
            load_baseline(self.root, 'test')


class ProductionBaselines(unittest.TestCase):
    def test_all_registered_sources_and_project_references_are_bound(self):
        for name, source_files in (('accepted_full83', 411), ('timing85', 414),
                                   ('resource_rework_route0', 434)):
            with self.subTest(name=name):
                baseline = load_baseline(ROOT, name)
                self.assertEqual(len(baseline.inputs), source_files)
                self.assertGreater(baseline.verify(), 0)
                self.assertNotIn('firmware/boot.elf', baseline.inputs)
                self.assertNotIn('firmware/boot.bin', baseline.inputs)
                self.assertFalse(any(path.startswith('docs/') for path in baseline.inputs))


    def test_retirement_preserves_original_production_hashes(self):
        for name in ('accepted_full83', 'timing85', 'resource_rework_route0'):
            with self.subTest(name=name):
                original = json.loads((ROOT / 'baselines' / (name + '.json')).read_text())
                baseline = load_baseline(ROOT, name)
                removed = set(original['files']) - baseline.inputs.keys()
                self.assertTrue(removed)
                self.assertTrue(all(Path(path).suffix in ('.md', '.log') for path in removed))
                self.assertEqual(baseline.inputs, {
                    path: entry['sha256'] for path, entry in original['files'].items()
                    if path not in removed})
                self.assertEqual(baseline.descriptor['origin'], original['origin'])
                self.assertEqual(baseline.descriptor['metadata'], original['metadata'])


@unittest.skipUnless(os.environ.get('GW138K_VERIFY_CLEAN_PREPARE') == '1',
                     'set GW138K_VERIFY_CLEAN_PREPARE=1 to run clean-checkout preparation')
class CleanCheckoutPreparation(unittest.TestCase):
    def test_profiles_reconstruct_without_private_history(self):
        repository = ROOT.parents[3]
        profiles = {
            'accepted_full83': ['--current-workstation'],
            'timing85': ['--current-workstation', '--cnn-timing85'],
            'resource_timing': ['--resource-rework', '--resource-timing'],
        }
        report = dict(passed=False, hardware_tested=False, synthesis_run=False,
                      private_historical_staging_present=False, profiles={}, simulations={})

        def run(command, cwd):
            result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout

        def prepare(root, flags):
            # macOS temporary directories may be reached through /var or /tmp
            # symlinks; builders print their canonical ROOT-derived path.
            root = root.resolve()
            text = run([sys.executable, str(root / 'build.py'), *flags, '--prepare-only'], root)
            output = Path(next(line for line in text.splitlines() if line.startswith(str(root / 'results/'))))
            inputs = json.loads((output / 'workstation_inputs.json').read_text())
            for name, expected in inputs.items():
                self.assertEqual(digest((output / 'Prj1' / name).read_bytes()), expected)
            return output, inputs

        with tempfile.TemporaryDirectory(prefix='fpga-source-closure-') as temporary:
            checkout = Path(temporary) / 'checkout'
            run(['git', 'clone', '--quiet', '--local', '--no-hardlinks', str(repository), str(checkout)], repository)
            changed = run(['git', 'diff', 'HEAD', '--name-only', '-z'], repository).split('\0')
            added = [ROOT / 'tools/workstation_baselines.py', ROOT / 'sim/baseline_fixture.py',
                     ROOT / 'sim/test_workstation_baselines.py', ROOT / 'tools/workstation_composition.py']
            added.extend(ROOT / name for name in COMPOSITION_SOURCES)
            added.extend(path for path in (ROOT / 'baselines').rglob('*') if path.is_file())
            names = {name for name in changed if name}
            names.update(path.relative_to(repository).as_posix() for path in added)
            for name in names:
                source, destination = repository / name, checkout / name
                if source.is_file():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                elif destination.is_file():
                    destination.unlink()
            clean_root = checkout / ROOT.relative_to(repository)
            self.assertFalse((clean_root / 'results').exists())
            for name, flags in profiles.items():
                expected = prepare(ROOT, flags)[1]
                clean_output, actual = prepare(clean_root, flags)
                self.assertEqual(actual, expected, name)
                metadata = json.loads((clean_output / 'build_metadata.json').read_text())
                report['profiles'][name] = dict(passed=True, source_files=len(actual), changed=[],
                                                inputs_sha256=digest(json.dumps(actual, sort_keys=True).encode()),
                                                source_baselines=metadata['source_baselines'])
                if name == 'timing85':
                    log = run([sys.executable, str(clean_root / 'sim/timing/test_cnn_trace_cdc.py'),
                               str(clean_output)], checkout)
                    report['simulations']['trace_cdc'] = dict(passed=True, log=log.strip())
                if name == 'resource_timing':
                    log = run([sys.executable, str(clean_root / 'sim/resource_timing/run_lifecycle.py'),
                               str(clean_output)], checkout)
                    report['simulations']['lifecycle'] = dict(passed=True, log=log.strip())
            descriptor = json.loads((clean_root / 'baselines/accepted_full83.json').read_text())
            entry = next(value for value in descriptor['files'].values()
                         if '/baselines/objects/' in value['source'])
            source = checkout / entry['source']
            source.write_bytes(source.read_bytes() + b'corrupt')
            existing = set((clean_root / 'results').iterdir())
            result = subprocess.run([sys.executable, str(clean_root / 'build.py'),
                                     '--current-workstation', '--prepare-only'],
                                    cwd=checkout, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('input tree drifted', result.stderr)
            self.assertEqual(set((clean_root / 'results').iterdir()), existing)
            report['corrupt_source_rejected'] = dict(passed=True, exit_code=result.returncode)
            for name in ('song_guide_full83_20261006_203125_607466',
                         'song_guide_full85_clk50_20261007_084539_884006_route1',
                         'resource_rework_final_route0_20261020_041042'):
                self.assertFalse((clean_root / 'results' / name).exists())
        report['passed'] = True
        if os.environ.get('GW138K_CLOSURE_REPORT'):
            destination = Path(os.environ['GW138K_CLOSURE_REPORT'])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    unittest.main()
