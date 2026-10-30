#!/usr/bin/env python3
"""Native/legacy source selection, profile isolation and missing/drift rejection."""
from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_runtime_counter as counter
from tools.workstation_baselines import load_baseline
from tools import workstation_profile as profiles
from tools import workstation_runtime_profile as runtime
from tools import workstation_custom_board as board


class CounterSources(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='runtime-counter-source-')
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name) / 'candidate'
        self.stage = self.output / 'workstation/Prj1'
        self.stage.mkdir(parents=True)
        legacy = self.stage / counter.LEGACY
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(load_baseline(ROOT, 'resource_rework_route0').read_bytes(counter.LEGACY))
        native = self.stage / counter.NATIVE
        native.parent.mkdir(parents=True)
        native.write_bytes((ROOT / counter.NATIVE).read_bytes())
        self.files = ET.Element('FileList')
        ET.SubElement(self.files, 'File', path=counter.LEGACY, enable='0')
        ET.SubElement(self.files, 'File', path=counter.NATIVE, enable='1')
        self.metadata = dict(runtime_audio=dict(counter_cdc=counter.metadata(ROOT)),
            replaced_compilation_inputs={counter.LEGACY: dict(sha256=counter.LEGACY_SHA256,
                replacement=counter.NATIVE, selected_destination=counter.NATIVE)},
            copied_source_destinations={counter.NATIVE:counter.NATIVE},
            copied_sources_sha256={counter.NATIVE:counter.sha(native)}, enabled_inputs=[counter.NATIVE],
            staged_input_sha256={counter.NATIVE:counter.sha(native),counter.LEGACY:counter.LEGACY_SHA256})
        self.profile = dict(enabled_inputs={counter.NATIVE:dict(sha256=counter.sha(native))},
                            staged_input_sha256=self.metadata['staged_input_sha256'])
        self.write()

    def write(self):
        root = ET.Element('Project')
        root.append(self.files)
        ET.ElementTree(root).write(self.stage / 'Prj1.gprj')
        (self.output / 'integration_inputs.json').write_text(json.dumps(self.metadata))
        (self.output / 'workstation_profile.json').write_text(json.dumps(self.profile))

    def test_native_owner_is_explicit_and_prepared_legacy_bytes_are_retained(self):
        selected = counter.selection_evidence(self.stage)
        self.assertEqual(selected['selection'], 'compiled_native_balanced')
        self.assertEqual(counter.selected_source(self.stage), (self.stage / counter.NATIVE).resolve())
        self.assertEqual(counter.sha(self.stage / counter.LEGACY), counter.LEGACY_SHA256)

    def test_old_serial_candidates_remain_explicit_and_native_metadata_cannot_claim_them(self):
        self.files[0].set('enable','1')
        self.files[1].set('enable','0')
        self.write()
        with self.assertRaisesRegex(ValueError,'native policy cannot select legacy'):
            counter.selection_evidence(self.stage)
        self.metadata['runtime_audio'].pop('counter_cdc')
        self.write()
        self.assertEqual(counter.selection_evidence(self.stage)['selection'],'compiled_locked_serial')

    def test_missing_native_never_falls_back_to_staged_disabled_parent(self):
        (self.stage / counter.NATIVE).unlink()
        with self.assertRaisesRegex(ValueError,'enabled implementation is missing'):
            counter.selected_source(self.stage)

    def test_duplicate_or_no_selected_source_is_rejected(self):
        for a,b in [('1','1'),('0','0')]:
            self.files[0].set('enable',a)
            self.files[1].set('enable',b)
            self.write()
            with self.assertRaisesRegex(ValueError,'exactly one'):
                counter.selection_evidence(self.stage)
        ET.SubElement(self.files,'File',path=counter.NATIVE,enable='1')
        self.write()
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            counter.selection_evidence(self.stage)

    def test_native_hash_owner_and_compilation_metadata_mutations_are_rejected(self):
        original = copy.deepcopy(self.metadata)
        mutations = []
        for key in ('runtime_audio','replaced_compilation_inputs','copied_source_destinations','copied_sources_sha256','enabled_inputs','staged_input_sha256'):
            item = copy.deepcopy(original)
            item[key] = [] if key == 'enabled_inputs' else {}
            mutations.append(item)
        for item in mutations:
            self.metadata = item
            self.write()
            with self.subTest(mutation=item), self.assertRaises(ValueError):
                counter.selection_evidence(self.stage)
        self.metadata = original
        self.write()
        (self.stage / counter.NATIVE).write_text('// drift\n')
        with self.assertRaisesRegex(ValueError,'policy/identity changed'):
            counter.selection_evidence(self.stage)

    def test_profile_source_hash_and_parent_bytes_are_independent_checks(self):
        self.profile['enabled_inputs'][counter.NATIVE]['sha256']='0'*64
        self.write()
        with self.assertRaisesRegex(ValueError,'prepared profile compiled source identity'):
            counter.selection_evidence(self.stage)
        (self.stage / counter.LEGACY).write_text('// drift\n')
        with self.assertRaisesRegex(ValueError,'locked parent bytes changed'):
            counter.selection_evidence(self.stage)

    def test_all_four_explicit_runtime_profiles_lock_new_owner_without_business_revision(self):
        self.assertIn(counter.NATIVE,runtime.SOURCES)
        self.assertEqual(runtime.REPLACEMENTS[counter.LEGACY],counter.NATIVE)
        self.assertNotIn(counter.NATIVE,board.NATIVE_SOURCES)
        self.assertNotIn(counter.LEGACY,board.REPLACED_INPUTS)
        prefix='projects/138k/push2_workstation/usb_a/'
        for name in profiles.PROFILE_REGISTRY:
            with self.subTest(profile=name):
                profile=profiles.load(ROOT,name)
                self.assertEqual(profile['configuration'],profiles.specification(name)['configuration'])
                for path in (counter.NATIVE,'tools/workstation_runtime_counter.py'):
                    self.assertEqual(profile['source_sha256'][prefix+path],counter.sha(ROOT/path))


if __name__=='__main__':
    unittest.main()
