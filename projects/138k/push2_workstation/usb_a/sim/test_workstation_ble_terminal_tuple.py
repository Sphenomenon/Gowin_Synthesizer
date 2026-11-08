"""Tuple selection retains both older inverses and rejects source drift."""
from pathlib import Path
import json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools import workstation_ble_terminal_tuple as repair
from tools import workstation_ble_terminal_cofactor as terminal
from tools import workstation_ble_completion_publication as publication

class TupleSelection(unittest.TestCase):
    def test_selected_bytes_and_historical_inverses(self):
        source=(ROOT/repair.SOURCE).read_text();parent=repair.restore(source)
        self.assertEqual(repair.digest(parent),json.loads((ROOT/repair.MANIFEST).read_text())['parent_sha256'])
        self.assertEqual(terminal.restore(source),terminal.restore(parent))
        self.assertEqual(publication.restore(source),publication.restore(parent))
        config={repair.KEY:repair.POLICY,terminal.KEY:terminal.POLICY,publication.KEY:publication.POLICY,
                'demo_role':'W','preboard_cdc_policy':'task3_W_proven_release_and_CNN_drain_CDC_v1'}
        with tempfile.TemporaryDirectory()as directory:
            stage=Path(directory);p=stage/repair.SOURCE;p.parent.mkdir(parents=True);p.write_text(source)
            self.assertIsNone(repair.select(stage,{}))
            publication.select(stage,config);terminal.select(stage,config);receipt=repair.select(stage,config)
            self.assertEqual(receipt['added_state_bits'],0)
            self.assertEqual(repair.restore(p.read_text()),parent)
            self.assertEqual(publication.unselect(terminal.unselect(repair.unselect(p.read_text()))),source)
            with self.assertRaises(ValueError):repair.select(stage,config)
        for bad in ({repair.KEY:'unknown'},dict(config,demo_role='M'),dict(config,raw_completion_policy=None)):
            with self.assertRaises(ValueError):repair.configured(bad)
        for a,b in [('ready_with_fault=command_req_sync;','ready_with_fault=0;'),
                    ('default:legacy_tuple_writes=1;','default:legacy_tuple_writes=0;')]:
            self.assertIn(a,source)
            with self.assertRaises(ValueError):repair.restore(source.replace(a,b,1))

if __name__=='__main__':unittest.main(verbosity=2)
