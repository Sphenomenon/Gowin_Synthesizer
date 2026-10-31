#!/usr/bin/env python3
"""Actual business firmware diagnostic calls and native atomic C350 publication."""
from pathlib import Path
import binascii,hashlib,itertools,json,os,re,struct,subprocess,sys,tempfile,types,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'sim')]
from tools.ae350_local_memory import symbol_values
with patch.dict(sys.modules,{'serial':types.ModuleType('serial')}):
    from tools import capture_scope_smoke as smoke
    from tools.capture_scope_smoke import business_diagnostic,BUSINESS_PAGES
from ae350_split_rv32 import SplitCpu
from ae350_rv32_startup import ModelError

class BusinessCpu(SplitCpu):
    """Real instructions with a narrow coherent MMIO stub, not an RTL CPU model."""
    def __init__(self,evidence):
        self.metadata=json.loads((evidence/'build_metadata.json').read_text())
        symbols=symbol_values((evidence/'firmware.nm').read_text())
        image=b''.join(int(w,16).to_bytes(4,'little')for w in(evidence/'boot.mem').read_text().splitlines())
        assert len(image)==65536
        super().__init__(image.ljust(131072,b'\0'),symbols);self.image=bytearray(image)
        self.mmio={0xf8050000:0x424d4201,0xf8050004:0x00401001,
            0xf805000c:1,0xf8050010:0x12345678,0xf8050014:0xabcdef01,0xf8050018:1,
            0xf8050100:0x52434403,0xf8050104:0x00301002,0xf8050154:1,0xf8050140:244}
        self.trace=[];self.publications=[]
    def read(self,address,width=4,*,fetch=False):
        if 0xf8050000<=address<=0xf80501fc and not fetch:
            if width!=4 or address&3:raise ModelError('invalid modeled business MMIO')
            self.trace.append(('R',address,self.mmio.get(address,0)));return self.mmio.get(address,0)
        return super().read(address,width,fetch=fetch)
    def write(self,address,value,width=4):
        if 0xf8050000<=address<=0xf80501fc:
            if width!=4 or address&3:raise ModelError('invalid modeled business MMIO')
            self.trace.append(('W',address,value));self.mmio[address]=value
            if address==0xf80500dc:self.mmio[0xf8050008]=256|{1:0,2:2,3:3}[value]
            return
        super().write(address,value,width)
        if address==0xf800001c:self.publications.append((value,self.diagnostics[24]))
    def pump(self):return self.call('a138_ble_business_firmware_pump')
    def pages(self):
        rows={}
        for _ in range(16):
            self.mmio[0xf8050148]=self.mmio.get(0xf8050148,0)+1500;self.pump()
            meta,value=self.publications[-1];rows[(meta>>8)&255]=(meta,value)
        return rows

class DiagnosticRTL(unittest.TestCase):
    def test_business_capture_mode_reads_crc_frames_without_midi_writes(self):
        class Port:
            def __init__(self,fault):self.n=0;self.fault=fault
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def reset_input_buffer(self):pass
            def readline(self):
                self.n+=1
                words=[self.n,0x55490473,0xb5000003|(self.fault<<16),self.n,0x43505531,0x50415353,self.n,0]
                crc=binascii.crc_hqx(struct.pack('<8I',*words),0xffff)
                return ('C350 '+''.join('%08X '%w for w in words)+'%04X\r\n'%crc).encode()
            def read_until(self,*args,**kwargs):return self.readline()
            def write(self,*args):raise AssertionError('business-only capture must not send MIDI')
        for fault in (0,103):
            with tempfile.TemporaryDirectory()as d:
                target=Path(d)/'capture.json';port=Port(fault);ticks=itertools.count()
                with patch.object(smoke,'serial',types.SimpleNamespace(Serial=lambda **kw:port)), \
                    patch.object(smoke.time,'monotonic',side_effect=lambda:next(ticks)*0.1), \
                    patch.object(sys,'argv',['capture_scope_smoke.py','--business-only','--seconds','3','--output',str(target)]), \
                    patch('builtins.print'):
                    if fault:
                        with self.assertRaises(SystemExit):smoke.main()
                    else:smoke.main()
                result=json.loads(target.read_text())
                self.assertEqual(result['passed'],not bool(fault))
                self.assertEqual(result['midi_control_commands'],[])
                if not fault:self.assertTrue(result['business_ready'])

    def test_only_business_provider_selects_observation_and_no_macro_leaks(self):
        with tempfile.TemporaryDirectory()as d:
            p=Path(d)
            for name,selected in [('workstation_profile_ae350_business_v1.sv',True),
                    ('workstation_profile_hci_owner_v1.sv',True),
                    ('workstation_profile_classic_runtime_v1.sv',False),
                    ('workstation_profile_classic_runtime_rom96_v1.sv',False),
                    ('workstation_profile_runtime.sv',False)]:
                wrapper=p/'provider.sv'
                wrapper.write_text('`include "rtl/workstation/'+name+'"\n`ifdef WORKSTATION_CPU_BLE_DIAGNOSTICS\nLEAKED_BUSINESS_DIAGNOSTICS\n`endif\n')
                out=p/'preprocessed.v'
                subprocess.run(['iverilog','-g2012','-E','-I'+str(ROOT),'-o',str(out),str(wrapper)],check=True,capture_output=True)
                text=out.read_text()
                self.assertNotIn('LEAKED_BUSINESS_DIAGNOSTICS',text)
                self.assertEqual('business_diagnostic_stage' in text,selected,name)

    def test_actual_apb_atomic_pair_reset_strobes_and_uart_mapping(self):
        source=(ROOT/'rtl/workstation/gw138k_push_workstation_top.v').read_text()
        block=source.split('    // Reuse the boot diagnostic page and existing C350 snapshot.',1)[1].split('\n',1)[1].split('`endif',1)[0]
        module='''module test;
reg pclk=0,preset_n=0,psel=0,penable=0,pwrite=0;reg[31:0]paddr=0,pwdata=0;reg[3:0]pstrb=15;
wire valid_word=paddr[31:12]==20'hf8000 && paddr[1:0]==0 && pstrb==4'hf;
reg[31:0]business_diagnostic_stage,business_diagnostic_meta,business_diagnostic_data;
always #5 pclk=~pclk;
'''+block+'''
task put(input[31:0]a,input[31:0]v);begin @(negedge pclk);psel=1;penable=1;pwrite=1;paddr=a;pwdata=v;@(negedge pclk);psel=0;end endtask
initial begin
 #1;preset_n=0;#11;preset_n=1;
 put(32'hf8000018,32'h11223344);
 if(business_diagnostic_meta!==0 || business_diagnostic_data!==0)$fatal(1,"stage leaked");
 put(32'hf800001c,32'hb5000303);
 if({business_diagnostic_meta,business_diagnostic_data}!==64'hb500030311223344)$fatal(1,"atomic publish");
 put(32'hf8000018,32'h55667788);
 if({business_diagnostic_meta,business_diagnostic_data}!==64'hb500030311223344)$fatal(1,"torn tuple");
 pstrb=3;put(32'hf800001c,32'hdeadbeef);
 if(business_diagnostic_meta!==32'hb5000303)$fatal(1,"partial write");
 pstrb=15;put(32'hf800001c,32'hb5000403);
 if({business_diagnostic_meta,business_diagnostic_data}!==64'hb500040355667788)$fatal(1,"second publish");
 @(negedge pclk);preset_n=0;#1;
 if({business_diagnostic_meta,business_diagnostic_data,business_diagnostic_stage}!==96'd0)$fatal(1,"reset");
 $display("PASS atomic existing diagnostic page");$finish;end endmodule
'''
        with tempfile.TemporaryDirectory()as d:
            p=Path(d);(p/'tb.sv').write_text(module)
            compiled=subprocess.run(['iverilog','-g2012','-s','test','-o',str(p/'tb'),str(p/'tb.sv')],capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            result=subprocess.run(['vvp',str(p/'tb')],check=True,capture_output=True,text=True)
            self.assertIn('PASS atomic',result.stdout)
        self.assertIn('.cpu_words({trap_cause,heartbeat,ram_result,signature,business_diagnostic_data,business_diagnostic_meta,ui_report})',source)

    def test_full_width_decoder_and_old_variant_rejection(self):
        for page,name in enumerate(BUSINESS_PAGES):
            words=[17,0x55490473,0xb5730000|(page<<8)|0xff,0xffffffff,0x43505531,0x50415353,99,0]
            result=business_diagnostic(words)
            self.assertEqual((result['field'],result['value'],result['fault'],result['phase']),(name,0xffffffff,0x73,7))
        self.assertIsNone(business_diagnostic([0,3,123,0xa0000100,0,0,0,0]))
        self.assertIsNone(business_diagnostic([0,3,0xb500ff00,0,0,0,0,0]))

@unittest.skipUnless(os.environ.get('GW138K_BUSINESS_DIAGNOSTIC_FIRMWARE'),'Set GW138K_BUSINESS_DIAGNOSTIC_FIRMWARE to actual linked business firmware')
class ActualFirmware(unittest.TestCase):
    def setUp(self):
        self.evidence=Path(os.environ['GW138K_BUSINESS_DIAGNOSTIC_FIRMWARE'])
        self.cpu=BusinessCpu(self.evidence)
        for name,digest in self.cpu.metadata['input_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest,name)
        self.assertEqual(self.cpu.run(),'services_main')
        self.cpu.call('a138_ble_business_firmware_init')

    def test_real_init_pump_claim_completion_and_all_pages(self):
        c=self.cpu
        self.assertEqual(c.publications,[(0xb5000000,0)])
        c.pump();self.assertEqual([x for x in c.trace if x[0]=='W'][-1],('W',0xf80500dc,1))
        # Coherent, already-validated GET request. Actual RV32 code performs
        # CLAIM, physical-key INSPECT, GET policy and COMPLETE. No physical
        # descriptor is needed for GET; the stub supplies no PCM or wire model.
        for off,value in {8:257,0x1c:1,0x20:1,0x24:1,0x28:0x12345678,0x2c:0xabcdef01,
                0x30:17,0x34:123,0x38:456,0x3c:(0x22<<16)|4,
                0x1d0:1,0x1d4:1,0x1d8:1,0x1dc:0x12345678,0x1e0:0xabcdef01}.items():c.mmio[0xf8050000+off]=value
        for _ in range(3):c.pump()
        commands=[x[2]for x in c.trace if x[:2]==('W',0xf80500dc)]
        self.assertEqual(commands,[1,2,3])
        self.assertFalse(any(x[:2]==('W',0xf8050108)for x in c.trace))
        c.mmio[0xf8050008]=256
        pages=c.pages();self.assertEqual(set(pages),set(range(16)))
        self.assertGreater(pages[0][1],0)
        self.assertEqual((pages[1][1],pages[2][1],pages[3][1]),(1,1,17))
        self.assertEqual(pages[4][1]&255,0x22)
        self.assertTrue(all(meta>>24==0xb5 and meta&3==3 for meta,_ in pages.values()))

    def test_real_observer_fault_is_visible_and_never_reopens(self):
        c=self.cpu;c.pump();c.trace=[];c.mmio[0xf805010c]=512;c.pump()
        meta,value=c.publications[-1]
        self.assertEqual((meta>>16)&255,103)
        self.assertEqual((meta>>8)&255,0)
        self.assertGreater(value,0)
        c.mmio[0xf805010c]=0;c.trace=[];c.pump()
        self.assertFalse(c.trace)

if __name__=='__main__':unittest.main()
