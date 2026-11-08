"""Pack/fetch selection preserves historical bytes and rejects faulty source."""
from pathlib import Path
import json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools import workstation_ble_pack_cofactor as repair
from tools import workstation_ble_terminal_tuple as tuple_repair
from tools import workstation_ble_terminal_cofactor as terminal
from tools import workstation_ble_completion_publication as publication

class PackSelection(unittest.TestCase):
    def test_selection_and_exact_historical_inverses(self):
        source=(ROOT/repair.SOURCE).read_text();parent=repair.restore(source)
        self.assertEqual(repair.digest(parent),json.loads((ROOT/repair.MANIFEST).read_text())['parent_sha256'])
        for older in (tuple_repair,terminal,publication):
            self.assertEqual(older.restore(source),older.restore(parent))
        config={repair.KEY:repair.POLICY,tuple_repair.KEY:tuple_repair.POLICY,
                terminal.KEY:terminal.POLICY,publication.KEY:publication.POLICY,
                'demo_role':'W','preboard_cdc_policy':'task3_W_proven_release_and_CNN_drain_CDC_v1'}
        with tempfile.TemporaryDirectory()as directory:
            stage=Path(directory);p=stage/repair.SOURCE;p.parent.mkdir(parents=True);p.write_text(source)
            self.assertIsNone(repair.select(stage,{}))
            publication.select(stage,config);terminal.select(stage,config);tuple_repair.select(stage,config)
            receipt=repair.select(stage,config)
            self.assertEqual(receipt['added_state_bits'],0)
            self.assertTrue(receipt['immediate_native_fault_preserved'])
            self.assertEqual(repair.restore(p.read_text()),parent)
            restored=publication.unselect(terminal.unselect(tuple_repair.unselect(repair.unselect(p.read_text()))))
            self.assertEqual(restored,source)
            with self.assertRaises(ValueError):repair.select(stage,config)
        for bad in ({repair.KEY:'unknown'},dict(config,demo_role='M'),dict(config,raw_terminal_tuple_policy=None)):
            with self.assertRaises(ValueError):repair.configured(bad)
        for a,b in [('default:legacy_pack_writes=1;','default:legacy_pack_writes=0;'),
                    ('fetch_address_without_fault=fetch_address+29\'d8;','fetch_address_without_fault=fetch_address;'),
                    ('pack_frames<=pack_without_fault;','pack_frames<=0;')]:
            self.assertIn(a,source)
            with self.assertRaises(ValueError):repair.restore(source.replace(a,b,1))

if __name__=='__main__':unittest.main(verbosity=2)
