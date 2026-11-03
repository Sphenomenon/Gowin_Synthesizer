"""Actual USB observation CDC and strict M-only source identity boundaries."""
import copy
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import workstation_usb_status as status
from tools import workstation_usb_status_provenance as provenance
from tools import workstation_profile as profiles
from tools.workstation_baselines import load_baseline


class WorkstationUsbStatus(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('GW138K_USB_STATUS_NETLIST'),'requires actual M5 mapped netlist')
    def test_actual_status_mailbox_chains_and_bypass_rejection(self):
        from tools.workstation_native_protocol_audit import protocol_netlist
        from tools.workstation_runtime_pcm_cdc import Graph
        n=protocol_netlist(Path(os.environ['GW138K_USB_STATUS_NETLIST']).read_text(),
                          mapping=os.environ.get('GW138K_USB_STATUS_MAPPING','synthesis'))
        g=Graph(n)
        # The bridge auditor checks hierarchical synthesis; routed mailbox
        # chains below are checked directly in the flat physical netlist.
        if os.environ.get('GW138K_USB_STATUS_MAPPING','synthesis') == 'synthesis':
            from tools import workstation_usb2_bridge_audit as bridge
            with patch.object(bridge,'SynthesisNetlist',return_value=n):
                reset_proof=bridge.audit_bridge_resets('already parsed', 'workstation_custom_138k_top')
                self.assertTrue(reset_proof['transaction_reset_topology_verified'])
                for domain in ('cpu','ulpi'):
                    stages=reset_proof['release_chains'][domain]['release']['stages']
                    second=stages[1];saved=n.cells[second]['ports']['D']
                    try:
                        n.cells[second]['ports']['D']=n.cells[stages[0]]['ports']['D']
                        with self.assertRaisesRegex(ValueError,'two-stage reset release changed'):
                            bridge.audit_bridge_resets('already parsed','workstation_custom_138k_top')
                    finally:n.cells[second]['ports']['D']=saved
        for scope,width in [('u_usb_display_status/link_cdc',4),
                            ('u_video/u_usb_status_panel/u_status_cdc',8)]:
            held=[p for p,c in n.cells.items() if c['kind'].startswith('DFF') and
                  re.fullmatch(re.escape(scope+'/held_data_')+r'\d+_s\d+',p)]
            destination=[p for p,c in n.cells.items() if c['kind'].startswith('DFF') and
                         re.fullmatch(re.escape(scope+'/destination_data_')+r'\d+_s\d+',p)]
            self.assertEqual(len(held),width,scope)
            self.assertEqual(len(destination),width,scope)
            source_clock={n.pin(p,'CLK') for p in held}
            destination_clock={n.pin(p,'CLK') for p in destination}
            self.assertEqual(len(source_clock),1);self.assertEqual(len(destination_clock),1)
            self.assertNotEqual(source_clock,destination_clock)
            for source,first,second,third,clock in [
                    ('request_toggle','req_meta','req_sync','req_settled',destination_clock),
                    ('acknowledge_toggle','ack_meta','ack_sync',None,source_clock)]:
                a,b,c=(g.register(scope,stem) for stem in (source,first,second))
                def verify_chain():
                    if n.pin(b,'D')!=n.pin(a,'Q') or n.pin(c,'D')!=n.pin(b,'Q'):
                        raise ValueError('USB status synchronizer bypass')
                verify_chain()
                self.assertEqual({n.pin(p,'CLK') for p in (b,c)},clock)
                self.assertEqual(set(g.closure([b])['endpoints']),{c+'/D'})
                if third:
                    d=g.register(scope,third)
                    self.assertEqual(n.pin(d,'D'),n.pin(c,'Q'))
                    self.assertEqual({n.pin(d,'CLK')},clock)
                saved=n.cells[c]['ports']['D']
                try:
                    n.cells[c]['ports']['D']=n.cells[a]['ports']['Q']
                    with self.assertRaisesRegex(ValueError,'bypass'):verify_chain()
                finally:n.cells[c]['ports']['D']=saved

    @unittest.skipUnless(shutil.which('iverilog'),'requires Icarus Verilog')
    def test_native_observer_to_panel_full_frame(self):
        baseline=load_baseline(ROOT,'resource_rework_route0')
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory);font=output/'video_font_5x7.v'
            font.write_bytes(baseline.read_bytes('src/video/video_font_5x7.v'))
            subprocess.run(['iverilog','-g2012','-DWORKSTATION_NATIVE_USB_STATUS',
                '-s','tb_usb_status_panel','-o',str(output/'sim'),
                str(ROOT/'sim/display/tb_usb_status_panel.sv'),
                *(str(ROOT/p) for p in status.SOURCES),
                str(ROOT/'rtl/control/workstation_stream_cdc.sv'),str(font)],check=True)
            result=subprocess.run(['vvp',str(output/'sim')],cwd=output,capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS USB status',result.stdout)

    @unittest.skipUnless(shutil.which('iverilog'),'requires Icarus Verilog')
    def test_disabled_panel_preserves_preprocessed_composition(self):
        info=json.loads((ROOT/provenance.MANIFEST).read_text())
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            for relative in info['records']:
                source=(ROOT/relative).read_bytes()
                parent,_=provenance.restore_parent(source,relative)
                for flags in ([],['-DWORKSTATION_CUSTOM_138K'],
                              ['-DWORKSTATION_CUSTOM_138K','-DWORKSTATION_RUNTIME_NATIVE',
                               '-DWORKSTATION_PUSH_RATE_CONTROL','-DWORKSTATION_XY_STEREO']):
                    tokens=[]
                    for label,payload in [('current',source),('parent',parent)]:
                        path=output/(label+'.sv');path.write_bytes(payload)
                        preprocessed=output/(label+'.v')
                        subprocess.run(['iverilog','-g2012','-E',*flags,'-o',str(preprocessed),str(path)],check=True)
                        text=re.sub(r'//[^\n]*|/\*.*?\*/','',preprocessed.read_text(),flags=re.S)
                        tokens.append(re.findall(r'\w+|[^\s]',text))
                    self.assertEqual(tokens[0],tokens[1],(relative,flags))

    @unittest.skipUnless(os.environ.get('GW138K_USB_STATUS_PREPARED'),'requires real M5 preparation')
    def test_real_m5_prepared_inputs_and_snapshot_binding(self):
        output=Path(os.environ['GW138K_USB_STATUS_PREPARED'])
        artifact=profiles.verify(ROOT,output)
        self.assertEqual(artifact['revision'],5)
        self.assertEqual(artifact['configuration']['usb_status_panel_policy'],status.POLICY)
        for source in status.SOURCES:self.assertIn(source,artifact['enabled_inputs'])
        stage=output/'workstation/Prj1'
        metadata=json.loads((output/'integration_inputs.json').read_text())
        selected=dict(metadata['usb_status_panel']);selected.pop('reset_alias_rebinding')
        self.assertEqual(selected,status.evidence())
        self.assertIn('.active_voices(shared_render_meta[159:128])',
                      (stage/'rtl/workstation/workstation_hdmi_display.sv').read_text())
        self.assertIn('.device_state_o(usb_display_device)',
                      (stage/'rtl/workstation/gw138k_push_workstation_top.v').read_text())
        selected=(stage/'constraints/custom_138k.sdc').read_text()
        self.assertIn(status.constraints(),selected)
        self.assertFalse(artifact['hardware_tested'])

    @unittest.skipUnless(shutil.which('iverilog'),'requires Icarus Verilog')
    def test_real_cdc_stop_fault_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            cdc=output/'gw138k_stream_cdc.sv'
            cdc.write_bytes((ROOT/'rtl/control/workstation_stream_cdc.sv').read_bytes())
            subprocess.run(['iverilog','-g2012','-s','tb_workstation_usb2_display_status',
                '-o',str(output/'sim'),str(ROOT/'sim/usb2/tb_workstation_usb2_display_status.sv'),
                str(ROOT/status.SOURCES[0]),str(cdc)],check=True)
            result=subprocess.run(['vvp',str(output/'sim')],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS actual USB status',result.stdout)

    def test_exact_lineage_and_tamper_rejection(self):
        info=json.loads((ROOT/provenance.MANIFEST).read_text())
        for relative,record in info['records'].items():
            source=(ROOT/relative).read_bytes()
            parent,evidence=provenance.restore_parent(source,relative)
            self.assertEqual(hashlib.sha256(parent).hexdigest(),record['parent_sha256'])
            self.assertEqual(evidence['current_source_sha256'],record['current_sha256'])
            self.assertTrue(evidence['exact_round_trip_verified'])
            self.assertFalse(evidence['input_source_rewritten'])
            self.assertIsNone(provenance.restore_parent(source+b'\n',relative)[1])
        changed=copy.deepcopy(info)
        relative=next(iter(changed['records']))
        changed['records'][relative]['edits'][0]['after']='missing anchor'
        data=json.dumps(changed).encode()
        with patch.object(Path,'read_bytes',return_value=data), \
                self.assertRaisesRegex(ValueError,'manifest changed'):
            provenance.restore_parent(b'',relative)
        with patch.object(Path,'read_bytes',return_value=data), \
                patch.object(provenance,'MANIFEST_SHA256',hashlib.sha256(data).hexdigest()), \
                self.assertRaisesRegex(ValueError,'reverse anchor drift'):
            provenance.restore_parent((ROOT/relative).read_text().encode(),relative)

    def test_m_only_configuration_and_legacy_candidate(self):
        m=profiles.specification(profiles.M_DEMO_NAME)
        self.assertEqual(m['revision'],5)
        self.assertTrue(m['usb_status_panel'])
        for name in profiles.PROFILE_REGISTRY:
            if name!=profiles.M_DEMO_NAME:
                spec=profiles.specification(name)
                self.assertFalse(spec.get('usb_status_panel',False))
                self.assertNotIn('usb_status_panel_policy',spec['configuration'])
        old=dict(profile=profiles.M_DEMO_NAME,revision=4,profile_source=m['config'],
                 configuration={k:v for k,v in m['configuration'].items() if k!='usb_status_panel_policy'})
        self.assertFalse(profiles.prepared_specification(old)['usb_status_panel'])
        parent='before\n'+status.OLD_RELEASE_BLOCK+'after\n'
        installed,evidence=status.install(parent)
        self.assertEqual(status.verify(installed,evidence),parent)
        self.assertNotIn('bridge/ulpi_release_q_',installed)
        with self.assertRaises(ValueError):status.verify(installed.replace('10.000','100.000'),evidence)
        with self.assertRaises(ValueError):status.verify(installed,{})
        with self.assertRaises(ValueError):status.verify(installed.replace(status.ALIAS_NOTE,''),evidence)
        with self.assertRaises(ValueError):status.install(parent.replace('2.000','20.000'))


if __name__=='__main__':unittest.main(verbosity=2)
