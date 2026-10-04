from pathlib import Path
import importlib.util,json,struct,tempfile,unittest,wave,zlib,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('sample_import',ROOT/'rtl/sampler/import_samples.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)
        self.wav=self.path/'hit.wav';self.declaration=dict(granularity='single_hit',reviewed_single_sound=True,
            contains_rhythm=False,contains_melody=False,contains_arrangement=False)
        self.make()
    def make(self,rate=44100,width=2,channels=2,frames=100):
        with wave.open(str(self.wav),'wb') as w:
            w.setnchannels(channels);w.setsampwidth(width);w.setframerate(rate)
            w.writeframes(b'\x10'*(channels*width*frames))
    def test_formats_and_normalization(self):
        for width in (1,2,3,4):
            for rate in (8000,44100,48000,96000,192000):
                for channels in (1,2):
                    self.make(rate,width,channels)
                    pcm,item=m.prepare(self.wav,self.declaration,0,17,True)
                    self.assertEqual(item['frames'],(100*48000+rate-1)//rate)
                    self.assertEqual(item['crc32'],f'{zlib.crc32(pcm):08x}')
                    self.assertGreaterEqual(item['gain_q16'],65536)
    def test_declarations(self):
        for key in ('contains_rhythm','contains_melody','contains_arrangement','reviewed_single_sound','granularity'):
            d=self.declaration.copy();del d[key]
            with self.assertRaises(m.Rejected):m.prepare(self.wav,d,0,1)
        for key in ('contains_rhythm','contains_melody','contains_arrangement'):
            d=self.declaration|{key:True}
            with self.assertRaises(m.Rejected):m.prepare(self.wav,d,0,1)
        for gran in ('breakbeat','phrase','song','loop'):
            with self.assertRaises(m.Rejected):m.prepare(self.wav,self.declaration|dict(granularity=gran),0,1)
    def test_duration_and_format(self):
        self.make(rate=48000,frames=96001)
        with self.assertRaises(m.Rejected):m.prepare(self.wav,self.declaration,0,1)
        self.make(channels=3)
        with self.assertRaises(m.Rejected):m.prepare(self.wav,self.declaration,0,1)
        self.wav.write_bytes(b'not a wav')
        with self.assertRaises(m.Rejected):m.prepare(self.wav,self.declaration,0,1)
    def test_manifest(self):
        entry=self.declaration|dict(file='hit.wav',slot=0,owner=9,normalize=True)
        config=self.path/'spec.json';config.write_text(json.dumps(dict(samples=[entry])))
        subprocess.run([sys.executable,str(ROOT/'rtl/sampler/import_samples.py'),str(config),str(self.path/'out')],check=True,stdout=subprocess.DEVNULL)
        manifest=json.loads((self.path/'out/manifest.json').read_text());item=manifest['samples'][0]
        self.assertEqual(item['address_bytes'],0x09800000);self.assertEqual(item['capacity_bytes'],1048576)
        for key in ('duration_seconds','granularity','crc32','owner','format','gain_q16'):
            self.assertIn(key,item)
        with wave.open(str(self.path/'out/S00.WAV')) as w:self.assertEqual((w.getframerate(),w.getnchannels(),w.getsampwidth()),(48000,1,2))
    def test_pool_full(self):
        with self.assertRaises(m.Rejected):m.allocate([dict(slot=0,frames=0x06800000//2+1)],ROOT/'rtl/ddr_address_map.vh')
        with self.assertRaises(m.Rejected):m.allocate([dict(slot=0,frames=1),dict(slot=0,frames=1)],ROOT/'rtl/ddr_address_map.vh')
if __name__=='__main__':unittest.main()
