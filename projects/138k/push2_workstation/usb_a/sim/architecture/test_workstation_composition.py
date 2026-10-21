import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import workstation_composition as composition


class NativeComposition(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.stage = Path(self.directory.name)
        project = ET.Element('Project')
        files = ET.SubElement(project, 'FileList')
        ET.SubElement(files, 'File', path='src/push2/gw138k_push_workstation_top.v',
                      type='file.verilog', enable='1')
        ET.ElementTree(project).write(self.stage / 'Prj1.gprj')

    def test_installs_exact_sources_once_and_is_idempotent(self):
        first = composition.install(self.stage)
        self.assertEqual(first, composition.install(self.stage))
        composition.verify(self.stage, first)
        for source, destination in composition.SOURCES.items():
            self.assertEqual((ROOT / source).read_bytes(), (self.stage / destination).read_bytes())

    def test_missing_source_fails_before_materialization(self):
        with patch.object(composition, 'ROOT', self.stage / 'missing'):
            with self.assertRaisesRegex(ValueError, 'missing composition sources'):
                composition.install(self.stage)
        self.assertFalse((self.stage / 'src').exists())

    def test_duplicate_compilation_input_fails(self):
        project = self.stage / 'Prj1.gprj'
        tree = ET.parse(project)
        files = tree.find('FileList')
        files.append(copy.deepcopy(files[0]))
        tree.write(project)
        with self.assertRaisesRegex(ValueError, 'duplicate compilation input'):
            composition.install(self.stage)

    def test_changed_staged_source_fails(self):
        evidence = composition.install(self.stage)
        destination = next(iter(composition.SOURCES.values()))
        (self.stage / destination).write_text('wrong source\n')
        with self.assertRaisesRegex(ValueError, 'composition source drift'):
            composition.verify(self.stage, evidence)

    def test_disabled_compilation_input_fails(self):
        evidence = composition.install(self.stage)
        project = self.stage / 'Prj1.gprj'
        tree = ET.parse(project)
        tree.find('FileList')[0].set('enable', '0')
        tree.write(project)
        with self.assertRaisesRegex(ValueError, 'input selection drift'):
            composition.verify(self.stage, evidence)

    def test_incomplete_manifest_and_wrong_destination_fail(self):
        evidence = composition.install(self.stage)
        source = next(iter(composition.SOURCES))
        del evidence['sources'][source]
        with self.assertRaisesRegex(ValueError, 'incomplete composition manifest'):
            composition.verify(self.stage, evidence)
        evidence = composition.install(self.stage)
        evidence['sources'][source]['destination'] = 'somewhere_else.v'
        with self.assertRaisesRegex(ValueError, 'input selection drift'):
            composition.verify(self.stage, evidence)


if __name__ == '__main__':
    unittest.main()
