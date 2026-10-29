#!/usr/bin/env python3
"""Runtime vector: native48 equivalence and independently fitted PCM frequency."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_baselines import load_baseline


class RuntimeVector(unittest.TestCase):
    def test_equivalence_rate_switch_pcm_and_envelope(self):
        native=ROOT/'rtl/audio/workstation_runtime_scope_vec.sv'
        provenance=ROOT/'rtl/audio/workstation_runtime_scope_vec.provenance.json'
        info=json.loads(provenance.read_text())
        text=native.read_text()
        for edit in reversed(info['edits']):
            self.assertEqual(text.count(edit['after']),edit['occurrences'],edit['before'])
            text=text.replace(edit['after'],edit['before'])
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),info['parent_sha256'])
        self.assertEqual(text.encode(),(ROOT/info['parent_path']).read_bytes())
        sources=[ROOT/info['parent_path'],native,provenance,ROOT/'sim/audio/tb_workstation_runtime_scope_vec.sv']
        data=list((ROOT/'rtl/audio/scope_vec/data').glob('*.mem'))
        hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources+data}
        with tempfile.TemporaryDirectory(prefix='runtime-vector-') as directory:
            directory=Path(directory)
            (directory/'rtl/audio/scope_vec').mkdir(parents=True)
            (directory/'rtl/audio/scope_vec/data').symlink_to(ROOT/'rtl/audio/scope_vec/data',target_is_directory=True)
            baseline=load_baseline(ROOT,'resource_rework_route0')
            (directory/'adsr.mem').write_bytes(baseline.read_bytes('sim/matlab/output/stage13_note_voice/stage13_adsr_q24.mem'))
            binary=directory/'vector.vvp'
            r=subprocess.run(['iverilog','-g2012','-s','tb_workstation_runtime_scope_vec','-o',str(binary),
                              str(sources[0]),str(native),str(sources[3])],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            r=subprocess.run(['vvp',str(binary)],cwd=directory,capture_output=True,text=True,timeout=90)
            summary='\n'.join(line for line in (r.stdout+r.stderr).splitlines() if not line.startswith('S '))
            self.assertEqual(r.returncode,0,summary)
            self.assertIn('PASS runtime vector:',summary)
            print(summary)
            streams={tag:[] for tag in (48,44,49)}
            for line in r.stdout.splitlines():
                if line.startswith('S '):
                    _,tag,left,right=line.split();streams[int(tag)].append((int(left),int(right)))
            for tag,rate in [(48,48000),(44,44100),(49,48000)]:
                values=np.asarray(streams[tag],dtype=float)
                self.assertEqual(values.shape,(1024,2))
                self.assertGreater(np.max(np.abs(values)),0)
                angle=np.unwrap(np.arctan2(values[:,1],values[:,0]))
                hz=np.polyfit(np.arange(1024),angle,1)[0]*rate/(2*np.pi)
                self.assertAlmostEqual(hz,440,delta=0.002)
                print(f'PCM_FREQUENCY epoch_tag={tag} sample_rate={rate} measured_hz={hz:.9f}')
        self.assertEqual(hashes,{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources+data})
        for name,digest in hashes.items():print('SOURCE',name,'SHA256='+digest)


if __name__=='__main__':unittest.main()
