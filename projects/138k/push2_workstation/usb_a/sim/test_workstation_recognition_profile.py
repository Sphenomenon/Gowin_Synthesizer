#!/usr/bin/env python3
"""Named policy identity, exact constraint retirement and composition isolation."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_profile as profiles
from tools import workstation_recognition_policy as policy

REFERENCE='df2a822f5694c99bdba5d03b66b642a16f687673'
TOP='rtl/workstation/gw138k_push_workstation_top.v'


class RecognitionProfile(unittest.TestCase):
    def test_named_policy_cannot_alias_enabled_identity(self):
        enabled=profiles.load(ROOT,profiles.NAME);disabled=profiles.load(ROOT,profiles.NO_CNN_NAME)
        self.assertEqual(enabled['revision'],5);self.assertEqual(disabled['revision'],1)
        self.assertNotEqual(profiles.specification(profiles.NAME)['provider'],profiles.specification(profiles.NO_CNN_NAME)['provider'])
        self.assertTrue(profiles.recognition_metadata(enabled)['music_analysis_enabled'])
        self.assertFalse(profiles.recognition_metadata(disabled)['music_analysis_enabled'])
        self.assertFalse(profiles.recognition_metadata(disabled)['cnn_score_follow_enabled'])
        self.assertEqual(enabled['configuration'],profiles.RUNTIME_CONFIGURATION)
        self.assertEqual(disabled['configuration'],dict(profiles.RUNTIME_CONFIGURATION,recognition_policy='disabled_cnn_and_follow_v1'))
        matrix={f['name']:f for f in disabled['features']}
        self.assertEqual(matrix['recognition_guidance']['source_state'],'disabled_by_explicit_profile')
        self.assertTrue(all(f['hardware_acceptance']=='unverified_for_this_profile' for f in matrix.values()))
        for relative in ('rtl/memory/workstation_recording_ddr_arbiter_pipeline.sv',
                         'rtl/memory/workstation_recording_ddr_client_queues.sv',
                         'rtl/memory/workstation_recording_ddr_native_bridge.sv'):
            self.assertIn('projects/138k/push2_workstation/usb_a/'+relative,disabled['source_sha256'])

    def test_off_configuration_identity_and_mixed_policy_tampering_rejected(self):
        config=ROOT/profiles.NO_CNN_CONFIG;original=Path.read_text;base=json.loads(config.read_text())
        mutations=[dict(base,name=profiles.NAME),dict(base,revision=5)]
        for key,value in (('recognition_policy','enabled_cnn_and_follow_v1'),('cnn_score_follow_enabled',True)):
            changed=copy.deepcopy(base);changed['configuration'][key]=value;mutations.append(changed)
        for changed in mutations:
            with self.subTest(changed=changed['configuration']),patch.object(Path,'read_text',lambda path,*a,**k:
                    json.dumps(changed) if path==config else original(path,*a,**k)),self.assertRaisesRegex(ValueError,'identity changed|configuration mismatch'):
                profiles.load(ROOT,profiles.NO_CNN_NAME)

    def test_constraint_retirement_is_exact_and_default_is_byte_preserving(self):
        source='create_clock -period 20.000 [get_ports {clk_50m}]\n'+''.join(line+'\n' for line in policy.RETIRED_LINES)+\
            'set_max_delay 10.000 -from [get_regs {u_service_push_cdc/held_data*}] -to [get_regs {u_service_push_cdc/destination_data*}]\n'
        same,evidence=policy.adapt_constraints(source,True)
        self.assertEqual(same,source);self.assertFalse(evidence['retired']);policy.verify_adaptation(same,evidence,True)
        selected,evidence=policy.adapt_constraints(source,False)
        self.assertEqual(len(evidence['retired']),19);self.assertIn('u_service_push_cdc',selected)
        self.assertIn('create_clock',selected);policy.verify_adaptation(selected,evidence,False)
        altered=copy.deepcopy(evidence);altered['retired'][0]['line']+=' '
        with self.assertRaises(ValueError):policy.verify_adaptation(selected,altered,False)

    def test_constraint_drift_duplicate_unknown_and_mixed_queries_fail_closed(self):
        original=''.join(line+'\n' for line in policy.RETIRED_LINES)
        mutations=[original.replace('20.000','21.000',1),original+policy.RETIRED_LINES[0]+'\n',
            original+'set_false_path -to [get_pins {u_music/new_unreviewed_meta*/D}]\n',
            original.replace(policy.RETIRED_LINES[0],policy.RETIRED_LINES[0].replace('}', ' u_service_push_cdc/req_meta*/D}',1))]
        for text in mutations:
            with self.subTest(text=text),self.assertRaisesRegex(ValueError,'anchor|unknown or mixed'):
                policy.adapt_constraints(text,False)

    def test_provider_removes_producer_and_dedicated_cdc_without_changing_other_entry_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            temp=Path(directory)
            def preprocess(source,name):
                destination=temp/(name+'.v')
                subprocess.run(['iverilog','-g2012','-E','-I',str(ROOT),'-o',str(destination),str(source)],check=True,capture_output=True)
                return destination.read_text()
            off=preprocess(ROOT/policy.PROVIDER,'off')
            on=preprocess(ROOT/profiles.RUNTIME_PROVIDER,'on')
            for name in ('u_music (','u_score_push_cdc(','u_song_command_cdc('):
                self.assertNotIn(name,off);self.assertIn(name,on)
            for name in ('u_model_flash_guard','u_managed','u_tf_audio','u_media_preparation','u_bluetooth','u_service_push_cdc'):
                self.assertIn(name,off)
            self.assertIn("music_model_status=4'd0",off)
            self.assertIn("music_ddr_mask=32'hffffffff",off)
            self.assertIn('!RECOGNITION_ENABLED || music_model_status',off)
            self.assertIn("model_flash_cs_n=1'b1",off)
            wrapper=temp/'leak.sv';wrapper.write_text('`include "'+policy.PROVIDER+'"\n`ifdef WORKSTATION_NO_CNN\nLEAKED_POLICY_MACRO\n`endif\n')
            self.assertNotIn('LEAKED_POLICY_MACRO',preprocess(wrapper,'leak'))
            original=subprocess.check_output(['git','show',REFERENCE+':projects/138k/push2_workstation/usb_a/'+TOP],cwd=ROOT.parents[3])
            previous=temp/'previous.v';previous.write_bytes(original)
            def tokens(text):return re.sub(r'\s+','',re.sub(r'//[^\n]*|/\*.*?\*/','',text,flags=re.S))
            self.assertEqual(tokens(preprocess(previous,'legacy_before')),tokens(preprocess(ROOT/TOP,'legacy_after')))
            a=temp/'old_custom.sv';a.write_text('`define WORKSTATION_CUSTOM_138K\n`include "'+str(previous)+'"\n`undef WORKSTATION_CUSTOM_138K\n')
            self.assertEqual(tokens(preprocess(a,'custom_before')),tokens(preprocess(ROOT/'rtl/workstation/workstation_custom_138k_top.sv','custom_after')))

    @unittest.skipUnless(os.environ.get('GW138K_NO_CNN_PREPARED'),'Set GW138K_NO_CNN_PREPARED to verify actual dual prepare')
    def test_actual_prepared_profile_provider_identity_and_constraint_closure(self):
        output=Path(os.environ['GW138K_NO_CNN_PREPARED']);artifact=profiles.verify(ROOT,output)
        self.assertEqual(artifact['profile'],profiles.NO_CNN_NAME)
        metadata=json.loads((output/'integration_inputs.json').read_text())
        self.assertEqual(metadata['identity'],'custom138k-native-dual-rate-no-cnn-revision1')
        self.assertTrue(artifact['candidate_identity'].startswith(profiles.NO_CNN_NAME+'-'))
        self.assertEqual(artifact['profile_source'],profiles.NO_CNN_CONFIG)
        self.assertIn(policy.PROVIDER,artifact['enabled_inputs'])
        self.assertNotIn(profiles.RUNTIME_PROVIDER,artifact['enabled_inputs'])
        self.assertIn(profiles.RUNTIME_PROVIDER,artifact['staged_input_sha256'])
        self.assertEqual(artifact['scan_window']['compilation_provider'],policy.PROVIDER)
        self.assertEqual(artifact['runtime_audio']['top_provider'],policy.PROVIDER)
        self.assertFalse(artifact['recognition']['music_analysis_enabled'])
        self.assertEqual(len(artifact['recognition']['constraints']['retired']),19)
        for path in ('rtl/memory/workstation_recording_ddr_arbiter_pipeline.sv',
                     'rtl/memory/workstation_recording_ddr_client_queues.sv',
                     'rtl/memory/workstation_recording_ddr_native_bridge.sv'):
            self.assertNotIn(path,artifact['enabled_inputs'])
            self.assertIn(path,artifact['source_snapshot_sha256'])
        self.assertFalse(artifact['deployment_allowed']);self.assertFalse(artifact['hardware_tested'])

    @unittest.skipUnless(os.environ.get('GW138K_NO_CNN_PREPARED'),'Set GW138K_NO_CNN_PREPARED to verify prepared policy tampering')
    def test_prepared_policy_alias_provider_and_capability_tampering_rejected(self):
        output=Path(os.environ['GW138K_NO_CNN_PREPARED'])
        metadata=json.loads((output/'integration_inputs.json').read_text())
        profile=profiles.load(ROOT,profiles.NO_CNN_NAME)
        mutations=[]
        changed=copy.deepcopy(metadata);changed['identity']=profiles.specification(profiles.NAME)['integration_identity']
        mutations.append((changed,'integration identity changed'))
        changed=copy.deepcopy(metadata);changed['enabled_inputs']=[profiles.RUNTIME_PROVIDER if path==policy.PROVIDER else path for path in changed['enabled_inputs']]
        mutations.append((changed,'selected compilation provider changed'))
        changed=copy.deepcopy(metadata);changed['enabled_inputs'].append(profiles.RUNTIME_PROVIDER)
        mutations.append((changed,'selected compilation provider changed'))
        changed=copy.deepcopy(metadata);changed['recognition']['cnn_score_follow_enabled']=True
        mutations.append((changed,'recognition capability selection changed'))
        changed=copy.deepcopy(metadata);changed['runtime_audio']['top_provider']=profiles.RUNTIME_PROVIDER
        mutations.append((changed,'recognition compilation provider changed'))
        for changed,message in mutations:
            with self.subTest(message=message),self.assertRaisesRegex(ValueError,message):
                profiles._artifact(ROOT,output,changed,profile)
        changed=copy.deepcopy(metadata);changed['workstation_profile']['artifact']='alias.json'
        original=Path.read_text;integration=output/'integration_inputs.json'
        with patch.object(Path,'read_text',lambda path,*a,**k:json.dumps(changed) if path==integration else original(path,*a,**k)),\
                self.assertRaisesRegex(ValueError,'artifact changed'):
            profiles.verify(ROOT,output)
        checked=subprocess.run([sys.executable,'-m','tools.workstation_profile','verify',str(output),
            '--profile',profiles.NAME],cwd=ROOT,text=True,capture_output=True)
        self.assertNotEqual(checked.returncode,0)
        self.assertIn('candidate does not match the expected workstation profile',checked.stderr)


if __name__=='__main__':unittest.main()
