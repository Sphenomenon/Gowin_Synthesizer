#!/usr/bin/env python3
"""Actual W provider preprocessing, native RAM elaboration and placement drift probes.

An explicit immutable parent stage supplies the unrelated vendor/firmware closure.
Only a temporary verification fixture is created; production preparation remains
the existing locked native-board path.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tools'))
from tools import workstation_profile as profiles
from tools import workstation_task3_w_media_profile as media
from tools.workstation_cnn_cdc import transform as synchronize_diagnostics

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class CnnMemorySelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence=dict(configurations=[],rejected_mutations=[])

    def setUp(self):
        type(self).test_result=self._outcome.result

    @classmethod
    def tearDownClass(cls):
        target=os.environ.get('GW138K_TASK3_CNN_MEMORY_EVIDENCE')
        if target:
            complete=(cls.test_result.wasSuccessful() and
                      len(cls.evidence['configurations'])==3 and
                      cls.evidence.get('configuration_policy_checked') is True and
                      'local_signal_elaboration' in cls.evidence)
            Path(target).write_text(json.dumps(dict(cls.evidence,
                passed=complete,hardware_tested=False,
                synthesis_verified=False,physical_timing_verified=False),indent=2)+'\n')

    def test_01_explicit_registry_and_defaults(self):
        for name,signal,coeff in ((profiles.TASK3_W_MEDIA_NAME,1,1),
                (profiles.TASK3_W_SIGNAL_NAME,0,1),(profiles.TASK3_W_CQT_NAME,0,0)):
            spec=profiles.specification(name)
            selected=media.cnn_memory_configuration(spec['configuration'])
            self.assertEqual(selected,media.cnn_memory_provider(spec['provider']))
            self.assertEqual((selected['USE_DDR_SIGNAL'],selected['USE_DDR_CQT_COEFF']),
                             (signal,coeff))
            self.assertEqual((selected['USE_DDR_FRONT_COEFF'],selected['USE_ALL_DDR']),(1,0))
        for value in ('unregistered',None,False,0,{'USE_DDR_SIGNAL':0}):
            configuration=dict(profiles.specification(profiles.TASK3_W_SIGNAL_NAME)['configuration'],
                               cnn_memory_policy=value)
            with self.subTest(value=value),self.assertRaises(ValueError):
                media.cnn_memory_configuration(configuration)
            self.evidence['rejected_mutations'].append(dict(case='unknown policy',value=value))
        with self.assertRaises(ValueError):media.cnn_memory_provider('unregistered.sv')
        self.evidence['configuration_policy_checked']=True

    def parent_stage(self):
        selected=os.environ.get('GW138K_TASK3_CNN_MEMORY_PARENT_STAGE')
        if not selected:self.skipTest('explicit immutable parent stage required; no cache fallback')
        parent=Path(selected).resolve()
        self.assertTrue((parent/'Prj1.gprj').is_file())
        return parent

    def fixture(self,parent,stage,provider):
        shutil.copytree(parent,stage,ignore=shutil.ignore_patterns('impl'))
        selected=('rtl/music/basic_pitch_workstation_link.sv',
            'rtl/music/workstation_cnn_task_service.sv',
            'rtl/workstation/workstation_task3_w_media.sv',media.BOARD,
            'rtl/workstation/gw138k_push_workstation_top.v',media.PROVIDER,provider)
        for relative in dict.fromkeys(selected):
            target=stage/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/relative,target)
        # Reproduce only the unchanged existing resource-parent dimension and
        # diagnostic transform, with the same unique anchor as its builder.
        link=stage/'rtl/music/basic_pitch_workstation_link.sv'
        old='.WIN_LEN(43844),.FRAME_LIMIT(172),.OCTAVE_LIMIT(9),'
        new=".WIN_LEN(44100),.FRAME_LIMIT(8),.OCTAVE_LIMIT(9),\n        .CQT_HOP_NUMERATOR(22050),.CQT_HOP_DENOMINATOR(4),\n        .FEATURE_TILE_COLS(16),.COARSE_GUIDANCE(1'b1),"
        text=link.read_text();self.assertEqual(text.count(old),1)
        link.write_text(synchronize_diagnostics(text.replace(old,new,1)))
        tree=ET.parse(stage/'Prj1.gprj')
        rows=[r for r in tree.find('FileList') if r.get('enable')=='1' and
              r.get('path')==media.PROVIDER]
        self.assertEqual(len(rows),1);rows[0].set('path',provider)
        tree.write(stage/'Prj1.gprj')
        files=[r.get('path') for r in tree.find('FileList') if r.get('enable')=='1' and
               Path(r.get('path')).suffix in ('.sv','.v')]
        result=subprocess.run(['iverilog','-g2012','-grelative-include','-E','-I.','-o','-',*files],
            cwd=stage,capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stderr)
        return result.stdout

    def test_02_actual_provider_closure_and_destructive_mutations(self):
        parent=self.parent_stage()
        for name in (profiles.TASK3_W_MEDIA_NAME,profiles.TASK3_W_SIGNAL_NAME,profiles.TASK3_W_CQT_NAME):
            spec=profiles.specification(name)
            with self.subTest(profile=name),tempfile.TemporaryDirectory(prefix='task3-cnn-memory-') as temp:
                stage=Path(temp)/'stage';text=self.fixture(parent,stage,spec['provider'])
                proof=media.selected_source_evidence(stage,text)
                wanted=media.cnn_memory_configuration(spec['configuration'])
                actual=proof['selected_CNN_memory'];self.assertTrue(proof['native_CNN_memory_parameters'])
                self.assertEqual(actual,wanted)
                native=media.source_negative_controls(stage,text)
                self.assertEqual(len(native),6)
                mutations=[
                    ('link-default','basic_pitch_workstation_link',"parameter bit USE_DDR_SIGNAL = 1'b1", "parameter bit USE_DDR_SIGNAL = 1'b0"),
                    ('task-default','workstation_cnn_task_service',"parameter bit CNN_USE_DDR_SIGNAL=1'b1", "parameter bit CNN_USE_DDR_SIGNAL=1'b0"),
                    ('media-default','workstation_task3_w_media',"parameter bit CNN_USE_DDR_SIGNAL=1'b1", "parameter bit CNN_USE_DDR_SIGNAL=1'b0"),
                    ('link-chain','basic_pitch_workstation_link','.USE_DDR_SIGNAL(USE_DDR_SIGNAL)',".USE_DDR_SIGNAL(1'b0)"),
                    ('task-chain','workstation_cnn_task_service','.USE_DDR_SIGNAL(CNN_USE_DDR_SIGNAL)',".USE_DDR_SIGNAL(1'b0)"),
                    ('media-chain','workstation_task3_w_media','.CNN_USE_DDR_SIGNAL(CNN_USE_DDR_SIGNAL)',".CNN_USE_DDR_SIGNAL(1'b0)"),
                    ('board-chain','workstation_custom_138k_top','.CNN_USE_DDR_SIGNAL(TASK3_CNN_USE_DDR_SIGNAL)',".CNN_USE_DDR_SIGNAL(1'b0)"),
                    ('front-must-stay-DDR','basic_pitch_workstation_link',".USE_DDR_FRONT_COEFF(1'b1)",".USE_DDR_FRONT_COEFF(1'b0)"),
                    ('external-state','basic_pitch_workstation_link',".USE_EXTERNAL_STATE(1'b1)",".USE_EXTERNAL_STATE(1'b0)"),
                    ('all-DDR','basic_pitch_workstation_link',".USE_ALL_DDR(1'b0)",".USE_ALL_DDR(1'b1)"),
                ]
                for label,module,before,after in mutations:
                    body=re.findall(r'\bmodule\s+'+module+r'\b.*?\bendmodule\b',text,re.S)
                    self.assertEqual(len(body),1);self.assertEqual(body[0].count(before),1)
                    changed=text.replace(body[0],body[0].replace(before,after,1),1)
                    with self.subTest(mutation=label),self.assertRaises(ValueError):
                        media.selected_source_evidence(stage,changed)
                    self.evidence['rejected_mutations'].append(dict(profile=name,case=label))
                for key in ('USE_DDR_SIGNAL','USE_DDR_CQT_COEFF'):
                    before='localparam TASK3_CNN_'+key+"=1'b"+str(wanted[key])+';'
                    after='localparam TASK3_CNN_'+key+"=1'b"+str(1-wanted[key])+';'
                    self.assertEqual(text.count(before),1)
                    with self.assertRaises(ValueError):media.selected_source_evidence(stage,text.replace(before,after,1))
                    self.evidence['rejected_mutations'].append(dict(profile=name,case='provider-localparam '+key))
                tree=ET.parse(stage/'Prj1.gprj');rows=tree.find('FileList')
                ET.SubElement(rows,'File',path=next(p for p in media.CNN_MEMORY_PROVIDERS if p!=spec['provider']),enable='1')
                tree.write(stage/'Prj1.gprj')
                with self.assertRaises(ValueError):media.selected_source_evidence(stage,text)
                self.evidence['rejected_mutations'].append(dict(profile=name,case='duplicate-provider'))
                self.evidence['configurations'].append(dict(profile=name,selection=wanted,
                    actual_preprocessed_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    preserved_native_negative_controls=native))

    def test_03_actual_local_signal_RAM_elaboration(self):
        # Actual selected CQT RTL, not a stubbed parameter-chain model. No
        # simulation or synthesis is performed; inspect the real elaboration.
        with tempfile.TemporaryDirectory(prefix='task3-cnn-ram-elaboration-') as temp:
            out=Path(temp)/'cqt.vvp'
            command=['iverilog','-g2012','-s','basic_pitch_cqt_engine',
                '-Pbasic_pitch_cqt_engine.WIN_LEN=44100',
                '-Pbasic_pitch_cqt_engine.USE_DDR_SIGNAL=0',
                '-Pbasic_pitch_cqt_engine.USE_DDR_COEFF=0','-I'+str(ROOT/'rtl/music'),'-o',str(out),
                str(ROOT/'rtl/music/basic_pitch_cqt_engine.sv')]
            result=subprocess.run(command,capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            compiled=out.read_text()
            self.assertEqual(len(re.findall(r'\.scope module, "u_sig_ram" "basic_pitch_signal_ram"',compiled)),1)
            arrays=re.findall(r'\.array/s "mem", 44099 0, 15 0;',compiled)
            self.assertEqual(len(arrays),1)
            self.assertIn('"g_local_signal"',compiled)
            self.assertNotIn('"g_ddr_signal"',compiled)
            self.evidence['local_signal_elaboration']=dict(command=command,
                actual_source_sha256=sha(ROOT/'rtl/music/basic_pitch_cqt_engine.sv'),
                elaboration_sha256=sha(out),single_RAM_module=True,
                actual_memory_shape=dict(depth=44100,width=16))

if __name__=='__main__':unittest.main()
