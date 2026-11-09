"""The explicit M cache selection must retain or retire the right owners."""
from pathlib import Path
import json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools import workstation_cache_raster as cache
from tools.workstation_profile import PROFILE_REGISTRY

class CacheRaster(unittest.TestCase):
    def setUp(self):
        self.configuration=dict(PROFILE_REGISTRY['custom138k-workstation-task3-m-preboard-v1']['configuration'])
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.stage=Path(temporary.name)
        for name in (cache.SOURCE,cache.MANIFEST):
            target=self.stage/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_bytes())
        cache.select(self.stage,self.configuration)

    def test_default_and_W_do_not_select_the_new_raster(self):
        self.assertFalse(cache.configured({}))
        self.assertIsNone(cache.evidence(ROOT,{}))
        for changes in ({'demo_role':'W'},{cache.KEY:'automatic'},{'display_metadata_minor':0}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):cache.configured(dict(self.configuration,**changes))

    def test_only_the_absent_duplicate_ACK_constraints_are_retired(self):
        live='set_max_delay 2.000 -from [get_pins {live/Q}] -to [get_pins {live/D}]\n'
        parent='\n'.join(cache.RETIRED_LINES)+'\n'+live
        selected,metadata=cache.constraints(self.stage,parent,self.configuration)
        self.assertEqual(selected,live)
        self.assertEqual(metadata['removed_constraints'],list(cache.RETIRED_LINES))
        for bad in (parent+cache.RETIRED_LINES[0]+'\n',live,
                    parent+'set_false_path -to [get_pins {u_video/u_renderer/u_capture/other/D}]\n'):
            with self.subTest(sdc=bad),self.assertRaises(ValueError):cache.constraints(self.stage,bad,self.configuration)

    def test_source_and_provider_drift_are_rejected(self):
        with tempfile.TemporaryDirectory()as temporary:
            stage=Path(temporary);manifest=json.loads((ROOT/cache.MANIFEST).read_text())
            for name in (*manifest['sources'],cache.MANIFEST):
                target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_bytes())
            cache.select(stage,self.configuration)
            expected=cache.evidence(stage,self.configuration)
            self.assertEqual(expected,cache.evidence(self.stage,self.configuration))
            for name in tuple(manifest['sources']):
                path=stage/name;old=path.read_bytes();path.write_bytes(old+b'\n')
                with self.subTest(source=name),self.assertRaises(ValueError):cache.evidence(stage,self.configuration)
                path.write_bytes(old)

if __name__=='__main__':unittest.main()
