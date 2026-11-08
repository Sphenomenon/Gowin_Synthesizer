"""Checked W-only selection, source drift and historical inverse controls."""
from pathlib import Path
import json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools import workstation_ble_terminal_cofactor as repair
from tools import workstation_ble_completion_publication as publication

class Selection(unittest.TestCase):
    def test_selection_and_inverse_chain(self):
        source=(ROOT/repair.SOURCE).read_text();parent=repair.restore(source)
        manifest=json.loads((ROOT/repair.MANIFEST).read_text())
        self.assertEqual(repair.digest(parent),manifest['parent_sha256'])
        config={repair.KEY:repair.POLICY,publication.KEY:publication.POLICY,'demo_role':'W',
                'preboard_cdc_policy':'task3_W_proven_release_and_CNN_drain_CDC_v1'}
        with tempfile.TemporaryDirectory()as directory:
            stage=Path(directory);p=stage/repair.SOURCE;p.parent.mkdir(parents=True);p.write_text(source)
            self.assertIsNone(repair.select(stage,{}))
            publication.select(stage,config);receipt=repair.select(stage,config)
            self.assertEqual(receipt['added_state_bits'],0)
            self.assertEqual(publication.unselect(repair.unselect(p.read_text())),source)
            self.assertEqual(repair.restore(p.read_text()),parent)
            self.assertEqual(publication.restore(p.read_text()),publication.restore(parent))
            self.assertEqual(publication.digest(publication.restore(parent)),
                             json.loads((ROOT/publication.MANIFEST).read_text())['parent_sha256'])
            with self.assertRaises(ValueError):repair.select(stage,config)
        for bad in ({repair.KEY:'unknown'},dict(config,demo_role='M'),
                    {repair.KEY:repair.POLICY,'demo_role':'W'}):
            with self.assertRaises(ValueError):repair.configured(bad)
        for changed in (source.replace('completion_code_with_fault=completion_code;',
                                       'completion_code_with_fault=0;',1),
                        source.replace(repair.DEFAULT,repair.DEFAULT+'; '+repair.SELECTED,1)):
            with self.assertRaises(ValueError):repair.restore(changed)

if __name__=='__main__':unittest.main(verbosity=2)
