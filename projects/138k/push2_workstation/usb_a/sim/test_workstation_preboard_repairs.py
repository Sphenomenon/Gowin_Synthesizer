#!/usr/bin/env python3
"""Target the actual preboard failures: local release admission and gain/glide math."""
from pathlib import Path
import hashlib
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_local_stream_release as release
from tools import workstation_effect_gain_path as effects
from tools import workstation_w_context_compare as context
from tools.workstation_baselines import load_baseline

class PreboardRepairs(unittest.TestCase):
    def test_local_release_exact_parent_and_selection(self):
        parent=load_baseline(ROOT,'resource_rework_route0').read_bytes(release.ORIGINAL)
        self.assertEqual(hashlib.sha256(parent).hexdigest(),release.PARENT_SHA256)
        with tempfile.TemporaryDirectory() as directory:
            stage=Path(directory)
            for relative,payload in [(release.ORIGINAL,parent),
                (release.SOURCE,(ROOT/release.SOURCE).read_bytes()),
                (release.CONTROLLED,(ROOT/release.CONTROLLED).read_bytes())]:
                p=stage/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(payload)
            files=ET.Element('FileList');ET.SubElement(files,'File',path=release.ORIGINAL,enable='1')
            config={release.KEY:release.POLICY,'demo_role':'W'}
            receipt=release.select(stage,files,config)
            enabled=[r.get('path')for r in files if r.get('enable')=='1']
            self.assertEqual(release.verify(stage,config,receipt,enabled),receipt)
            with self.assertRaises(ValueError):release.verify(stage,config,receipt,enabled+[release.ORIGINAL])
            with self.assertRaises(ValueError):release.configured(dict(config,demo_role='M'))
            with self.assertRaises(ValueError):release.verify(stage,{},receipt,enabled)
            p=stage/release.SOURCE
            original=p.read_bytes()
            for mutant in [original.replace(b'syn_preserve=1',b'syn_preserve=0'),
                           original.replace(b'drop_count+1\'b1',b'drop_count+2\'d2'),
                           original.replace(b'source_release[2]',b'source_release[1]')]:
                self.assertNotEqual(original,mutant);p.write_bytes(mutant)
                with self.assertRaises(ValueError):release.evidence(stage)
            p.write_bytes(original)

    def test_glide_actual_parameter_owner_last_edge(self):
        with tempfile.TemporaryDirectory() as directory:
            stage=Path(directory);rom=stage/'sim/data/audio_chain/pitch_bend_q20.mem'
            rom.parent.mkdir(parents=True)
            rom.write_bytes(load_baseline(ROOT,'resource_rework_route0').read_bytes('sim/data/audio_chain/pitch_bend_q20.mem'))
            sources=['rtl/control/workstation_parameters.sv','rtl/audio/scope_vec/scope_tf_control.sv',
                     'rtl/audio/workstation_rate_pitch_expression.sv','sim/audio/tb_pitch_committed_glide.sv']
            binary=stage/'glide.vvp'
            build=subprocess.run(['iverilog','-g2012','-s','tb_pitch_committed_glide','-o',str(binary),
                *[str(ROOT/p)for p in sources]],cwd=stage,capture_output=True,text=True,timeout=30)
            self.assertEqual(build.returncode,0,build.stdout+build.stderr)
            run=subprocess.run(['vvp',str(binary)],cwd=stage,capture_output=True,text=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertNotRegex(run.stdout+run.stderr,r'(?i)error|warning|unable|cannot')
            self.assertIn('commits=384 samples=2688 all128_CC5',run.stdout)

    def test_gain_domain_and_exact_source_inverse(self):
        source=(ROOT/effects.SOURCE).read_bytes();parent=effects.normalize(source)
        from tools.workstation_effects_reserved_config import normalize as unselect_dispatch
        self.assertEqual(hashlib.sha256(unselect_dispatch(source)).hexdigest(),effects.SELECTED_SHA256)
        self.assertEqual(hashlib.sha256(parent).hexdigest(),effects.PARENT_SHA256)
        function=re.search(r'  function automatic \[15:0\] runtime_slew.*?  endfunction',source.decode(),re.S)[0]
        # Exercise the production function for every current gain and all
        # three actual increments, at endpoints and each clamp boundary.
        tb='module gain_domain;\n'+function+'''
        integer v,d,t,k,expected,checks=0;
        initial begin
          for(v=0;v<65536;v=v+1)for(k=0;k<3;k=k+1)begin
            d=k==0?128:k==1?139:140;
            for(integer j=0;j<9;j=j+1)begin
              case(j)
                0:t=0;1:t=65535;2:t=v;3:t=v-d-1;4:t=v-d;
                5:t=v-d+1;6:t=v+d-1;7:t=v+d;8:t=v+d+1;
              endcase
              if(t>=0 && t<65536)begin
                expected=t>v ? (v+d<t?v+d:t):(v-d>t?v-d:t);
                if(runtime_slew(16'(v),16'(t),16'(d))!==16'(expected))
                  $fatal(1,"gain mismatch value=%0d target=%0d delta=%0d",v,t,d);
                checks=checks+1;
              end
            end
          end
          $display("PASS gain domain checks=%0d",checks);$finish;
        end
        endmodule
        '''
        with tempfile.TemporaryDirectory() as directory:
            stage=Path(directory);p=stage/'gain.sv';p.write_text(tb);binary=stage/'gain.vvp'
            subprocess.run(['iverilog','-g2012','-s','gain_domain','-o',str(binary),str(p)],check=True,capture_output=True,text=True,timeout=30)
            run=subprocess.run(['vvp',str(binary)],capture_output=True,text=True,timeout=60)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn('PASS gain domain',run.stdout)

    def test_context_full_key_exact_inverse(self):
        source=(ROOT/context.SOURCE).read_bytes()
        self.assertEqual(hashlib.sha256(context.normalize(source)).hexdigest(),context.PARENT_SHA256)
        for bad in [source.replace(b'context_byte<16',b'context_byte<15'),
                    source.replace(b'observed_context[context_byte*8+:8]',b'observed_context[context_byte*8+:7]')]:
            with self.assertRaises(ValueError):context.normalize(bad)

if __name__=='__main__':unittest.main()
