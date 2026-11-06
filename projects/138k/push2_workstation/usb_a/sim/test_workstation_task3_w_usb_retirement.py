#!/usr/bin/env python3
"""Explicit W input termination, source selection and exact SDC retirement."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
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
from tools import workstation_profile as profiles
from tools import workstation_task3_w_usb_retirement as usb
from tools.workstation_task3_paired_audit import audit_constraint_inventory,TOP


class WorkerUSBRetirement(unittest.TestCase):
    def config(self):
        return deepcopy(profiles.specification(profiles.TASK3_W_NO_USB_NAME)['configuration'])

    def test_explicit_policy_preserves_real_W_configuration_and_provider(self):
        selected=profiles.specification(profiles.TASK3_W_NO_USB_NAME)
        parent=profiles.specification('custom138k-workstation-task3-w-paired-checkpoint-v21')
        self.assertEqual(selected['provider'],parent['provider'])
        self.assertEqual(selected['configuration'],dict(parent['configuration'],usb_adapter_policy=usb.POLICY))
        self.assertTrue(usb.configured(selected['configuration']))
        self.assertFalse(usb.configured(parent['configuration']))
        for field,value in (('demo_role','M'),('phone_batch_policy','old'),
                ('interboard_business_default_enabled',True),('interboard_transport_policy','other')):
            with self.subTest(field=field),self.assertRaises(ValueError):
                usb.configured(dict(self.config(),**{field:value}))

    def test_selected_descriptor_has_complete_checked_source_closure(self):
        selected=profiles.load(ROOT,profiles.TASK3_W_NO_USB_NAME)
        prefix=ROOT.relative_to(ROOT.parents[3]).as_posix()+'/'
        for source in (*usb.DEPENDENCIES,'tools/workstation_custom_board.py',
                'tools/workstation_classic_runtime.py','rtl/ddr_address_map.vh'):
            self.assertEqual(selected['source_sha256'][prefix+source],profiles.sha(ROOT/source))
        parent=ROOT.parents[3]/selected['checkpoint_parent']['configuration']
        self.assertEqual(profiles.sha(parent),selected['checkpoint_parent']['configuration_sha256'])
        self.assertFalse(selected['checkpoint_parent']['historical_descriptor_modified'])

    def test_single_implementation_selection_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            stage=Path(directory)
            for source in (usb.ORIGINAL,usb.SOURCE):
                target=stage/source;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/source,target)
            files=ET.Element('FileList')
            ET.SubElement(files,'File',path=usb.ORIGINAL,enable='1')
            result=usb.select_sources(stage,files,self.config())
            enabled=[r.get('path') for r in files if r.get('enable')=='1']
            evidence=dict(selection=result)
            self.assertEqual(usb.verify_selection(stage,self.config(),evidence,enabled),result)
            for altered in (enabled+[usb.ORIGINAL],enabled+enabled,[],[usb.ORIGINAL]):
                with self.subTest(enabled=altered),self.assertRaises(ValueError):
                    usb.verify_selection(stage,self.config(),evidence,altered)
            with self.assertRaises(ValueError):
                usb.select_sources(stage,files,self.config())
            with self.assertRaises(ValueError):
                usb.verify_selection(stage,{},evidence,enabled)
            (stage/usb.SOURCE).write_text('// tampered\n')
            with self.assertRaises(ValueError):
                usb.verify_selection(stage,self.config(),evidence,enabled)

    def test_mixed_selector_peers_clocks_and_budgets_survive_exact_inverse(self):
        original=('create_clock -name audio_76m8 -period 13.021 [get_ports {audio_clk}]\n'
            'set_false_path -to [get_pins {u_native_usb/reset*/CLEAR peer/reset*/CLEAR}]\n'
            'set_max_delay 2.000 -from [get_pins {u_native_usb/a/Q}] -to [get_pins {u_native_usb/b/D}]\n'
            'set_max_delay 2.000 -from [get_pins {peer/a/Q}] -to [get_pins {peer/b/D}]\n')
        selected,receipt=usb.adapt_constraints(original)
        self.assertEqual(selected,original.splitlines(keepends=True)[0]+
            'set_false_path -to [get_pins {peer/reset*/CLEAR}]\n'+original.splitlines(keepends=True)[3])
        self.assertEqual(usb.restore_constraints(selected,receipt),original)
        for value in (selected+'\n',selected.replace('2.000','20.000'),selected.replace('peer','other')):
            with self.subTest(sdc=value),self.assertRaises(ValueError):
                usb.restore_constraints(value,receipt)
        altered=deepcopy(receipt);altered['original_lines']+=1
        with self.assertRaises(ValueError):usb.restore_constraints(selected,altered)
        for text in ('set_false_path -to [get_pins u_native_usb/a/D]\n',
                     'set_multicycle_path 2 -to [get_pins {u_native_usb/a/D}]\n'):
            with self.assertRaises(ValueError):usb.adapt_constraints(text)
        for suffix in ('','\n'):
            text='set_false_path -to [get_pins {u_native_usb/a/D}]'+suffix
            value,evidence=usb.adapt_constraints(text)
            self.assertEqual(usb.restore_constraints(value,evidence),text)

    def test_absence_and_later_retirement_cannot_hide_actual_live_cells(self):
        def net(*names):
            return SimpleNamespace(cells={name:dict(kind='DFFCE',ports={'D':'d','Q':'q'})
                for name in names},frames={},directions={TOP:{}})
        sdc,receipt=usb.adapt_constraints('set_false_path -to [get_pins {u_native_usb/a/D}]\n')
        self.assertTrue(usb.audit_absence(net('peer/a'),constraints=receipt)['mapped_retirement_verified'])
        for name in ('u_native_usb/a','u_native_usb/host/cpu/a','u_native_usb/input_owner/a',
                'u_runtime/u_usb_cdc/held_data_0'):
            with self.subTest(name=name),self.assertRaises(ValueError):usb.audit_absence(net(name))
        meta=dict(demo_constraint_retirement=dict(changes=[dict(
            original='set_false_path -to [get_pins {old/a/D}]',removed_selectors=[],
            rebound_selectors=[dict(query='get_pins',original='old/a/D',selected='u_native_usb/a/D')])]),
            task3_w_usb_retirement=dict(constraints=receipt))
        self.assertTrue(audit_constraint_inventory(sdc,meta,net('peer/a'))['every_retired_selector_absent'])
        with self.assertRaises(ValueError):audit_constraint_inventory(sdc,meta,net('u_native_usb/a'))

    def test_real_RTL_rejects_activity_and_releases_ULPI_data(self):
        original=(ROOT/usb.ORIGINAL).read_text().split(');',1)[0]+');'
        selected=(ROOT/usb.SOURCE).read_text()
        self.assertEqual(original[original.index('module '):],
                         selected[selected.index('module '):].split(');',1)[0]+');')
        ports=[]
        for direction,width,names in re.findall(r'^\s*(input|output) wire\s*(\[[^\]]+\])?\s*([^\n]+)',original,re.M):
            ports.extend((direction,width,name.strip()) for name in names.rstrip(',').split(','))
        inputs=[name for direction,width,name in ports if direction=='input']
        outputs=[name for direction,width,name in ports if direction=='output']
        declarations='\n'.join(('reg ' if direction=='input' else 'wire ')+width+' '+name+';'
                               for direction,width,name in ports)
        connections=','.join('.'+name+'('+name+')' for direction,width,name in ports)
        checks='\n'.join('if ('+name+" !== "+("1'b1" if name=='uart_tx_o' else "'0")+
                         ') $fatal(1,"unexpected '+name+'");' for name in outputs)
        # The same top-level OE equation must release the actual external bus
        # during reset, arbitrary control traffic and unknown/disconnected inputs.
        bench=('module tb;\n'+declarations+'\nreg peer_oe;reg [7:0] peer_data;tri [7:0] pad;\n'
            "assign pad=ulpi_data_oe_o?ulpi_data_o:8'bz;\n"
            "assign pad=peer_oe?peer_data:8'bz;\n"
            'workstation_usb2_input dut('+connections+');\n'
            'task check;begin\n'+checks+'\n'
            "if (pad !== (peer_oe?peer_data:8'bz)) $fatal(1,\"ULPI contention\");\n"
            'end endtask\ninteger i;initial begin peer_oe=0;peer_data=0;\n'+
            '\n'.join(name+"='x;" for name in inputs)+'\n#2;check;\n'
            'for(i=0;i<256;i=i+1) begin\n'+
            '\n'.join(name+'={$random,$random,$random,$random};' for name in inputs)+
            '\npeer_oe=i[0];peer_data=$random;#2;check;end\n'
            '$display("PASS 257 termination states with external pad drive");$finish;end endmodule\n')
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);(work/'tb.sv').write_text(bench)
            result=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(work/'sim'),
                str(ROOT/usb.SOURCE),str(work/'tb.sv')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run(['vvp',str(work/'sim')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS 257',result.stdout)


@unittest.skipUnless(os.environ.get('GW138K_TASK3_W_NO_USB'),'explicit prepared W candidate required')
class ActualPreparedWorker(unittest.TestCase):
    def test_complete_prepared_sources_firmware_and_exact_inverse(self):
        from tools.workstation_task3_paired_audit import verify_prepared
        candidate=Path(os.environ['GW138K_TASK3_W_NO_USB'])
        metadata=json.loads((candidate/'integration_inputs.json').read_text())
        artifact=profiles.verify(ROOT,candidate)
        self.assertEqual(artifact['profile'],profiles.TASK3_W_NO_USB_NAME)
        role,profile,stage,constraints=verify_prepared(candidate,metadata)
        self.assertEqual(role,'W');self.assertFalse(metadata['native_usb'])
        self.assertEqual(profile['configuration']['usb2_cpu_ram_bytes'],49152)
        self.assertEqual(profile['configuration']['ae350_boot_rom_bytes'],131072)
        self.assertNotIn(usb.ORIGINAL,metadata['enabled_inputs'])
        self.assertEqual(metadata['enabled_inputs'].count(usb.SOURCE),1)
        self.assertFalse(metadata['hardware_tested'])
        self.assertFalse(metadata['deployment_allowed'])


@unittest.skipUnless(os.environ.get('GW138K_TASK3_W_NO_USB_MAPPED'),'explicit synthesized W candidate required')
class ActualMappedWorker(unittest.TestCase):
    def test_actual_DMA_boundary_and_protected_endpoint_mutations(self):
        from tools.workstation_demo_boundary_cdc import netlist,proposed_constraints
        from tools.workstation_task3_w_paired_cdc_audit import audit_boundary
        candidate=Path(os.environ['GW138K_TASK3_W_NO_USB_MAPPED'])
        stage=candidate/'workstation/Prj1'
        n=netlist((stage/'impl/gwsynthesis/custom_138k_integration.vg').read_text(),mapping='synthesis')
        sdc=(stage/'constraints/custom_138k.sdc').read_text()
        result=audit_boundary(n,sdc,usb_retired=True)
        self.assertEqual(result['installed_sdc']['fault_first_data_source_count'],3)
        self.assertTrue(result['installed_sdc']['functional_recovery_removal_exceptions_absent'])
        # Every added timing waiver or relaxed synchronizer bound must fail,
        # even after the USB-only part has been proved absent.
        meta=result['fault_first_stage_closure']['ff_endpoints']
        sync_pin=next(iter(meta))
        for mutation in (sdc.replace(proposed_constraints().splitlines()[1],''),
                sdc+'set_false_path -to [get_pins {'+sync_pin+'}]\n',
                sdc+'set_max_delay 20.000 -to [get_pins {'+sync_pin+'}]\n',
                sdc+'set_false_path -to [get_clocks {audio_76m8}]\n'):
            with self.subTest(sdc=mutation[-150:]),self.assertRaises(ValueError):
                audit_boundary(n,mutation,usb_retired=True)


if __name__=='__main__':
    unittest.main()
