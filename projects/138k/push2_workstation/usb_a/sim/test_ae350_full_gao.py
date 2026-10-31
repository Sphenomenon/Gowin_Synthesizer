#!/usr/bin/env python3
"""Actual async snapshot RTL and strict complete-GAO capture decoding."""
from pathlib import Path
import copy,csv,io,json,subprocess,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'sim')]
from tools.decode_ae350_probe_gao import decode,decode_value,BITS,MAGIC
from tools.decode_ae350_local_probe import frames

class FullGaoTest(unittest.TestCase):
    def manifest(self):
        return dict(identity='offline-test-only',user_code='0xc21031d1',firmware=dict(
            capacity=dict(symbols=dict(__ilm_start=0xa0000000,__ilm_end=0xa0001000,
                __bss_end=0xa0200200,__stack_bottom=0xa020c000,__stack_top=0xa0210000)),
            payload=dict(crc32=1,first=2,last=3)))

    def value(self,sequence=0,**kw):
        words=[0x10000000+i for i in range(64)];words[61]=15
        if 'words' in kw:words=kw['words']
        header=[sequence,kw.get('user',0xc21031d1),kw.get('magic',MAGIC),
            kw.get('io',0x1234567b),0xffff078f]
        return sum(n<<(32*i) for i,n in enumerate([*words,*header]))

    def csv(self,values):
        stream=io.StringIO();writer=csv.writer(stream)
        writer.writerow(['Groups:']);writer.writerow(['Data:'])
        writer.writerow(['time unit: us','status_50mhz',*[f'status_50mhz[{i}]' for i in reversed(range(BITS))],''])
        writer.writerow(['0','X',*['X']*BITS,''])
        for i,value in enumerate(values,1):writer.writerow([str(i),f'{value:X}',*f'{value:0{BITS}b}',''])
        return stream.getvalue()

    def test_all64_words_sequence_schema_and_digital_io_are_separate(self):
        result=decode(self.csv([self.value(),self.value()]),self.manifest())
        self.assertEqual(result['valid_rows'],2);self.assertEqual(result['unknown_rows'],1)
        latest=result['latest'];self.assertEqual(len(latest['words']),64)
        for i in range(64):self.assertEqual(latest['words'][i],15 if i==61 else 0x10000000+i)
        self.assertEqual(len(latest['software_owned_words']),58)
        self.assertEqual(latest['digital_io']['uart_output_drive'],1)
        self.assertEqual(latest['digital_io']['uart_output_edges_modulo_2_30'],0x1234567b>>2)
        self.assertFalse(latest['digital_io']['external_uart_reception_verified'])
        for user,io in [(1,0x1234567b),(0xc21031d1,0x12345679)]:
            x=decode_value(self.value(user=user,io=io),self.manifest())
            self.assertFalse(x['local_memory_checks_passed'])
            self.assertFalse(x['checks']['identity'] if user==1 else x['checks']['gao_snapshot_published'])

    def test_real_firmware_model_diagnostics_pass_full_gao_assessment(self):
        from tools.workstation_ae350_local_probe import firmware
        from tools.stage_ae350_firmware import decode_rom
        from ae350_probe_rv32 import ProbeCpu
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'firmware'
            fw=firmware(ROOT,out,None)
            cpu=ProbeCpu(decode_rom(out/'boot.mem',65536),fw['capacity']['symbols'])
            self.assertEqual(cpu.run_probe(),'probe_pass')
            words=[cpu.diagnostics.get(i*4,0) for i in range(64)]
            words[58]=1;words[61]=15  # Explicit offline PL/transport stimulus.
            manifest=dict(identity='actual-instruction-model-only',user_code='0xc21031d1',firmware=fw)
            result=decode(self.csv([self.value(words=words)]),manifest)
            self.assertTrue(result['latest']['local_memory_checks_passed'])
            self.assertTrue(result['latest']['counter_observation_passed'])
            self.assertFalse(result['hardware_acceptance'])
            words[61]=31
            stale=decode_value(self.value(words=words),manifest)
            self.assertTrue(stale['mcycle']['running'])
            self.assertFalse(stale['counter_observation_passed'])

    def test_rejects_truncated_legacy_reordered_bits_magic_and_mixed_sequence(self):
        text=self.csv([self.value()]);rows=list(csv.reader(io.StringIO(text)))
        cases=[]
        bad=copy.deepcopy(rows);bad[2][2],bad[2][3]=bad[2][3],bad[2][2];cases.append(bad)
        bad=copy.deepcopy(rows);bad[-1].pop(123);cases.append(bad)
        bad=copy.deepcopy(rows);bad[-1][100]='1' if bad[-1][100]=='0' else '0';cases.append(bad)
        bad=copy.deepcopy(rows);bad[2]=['time unit: us','status_50mhz',*[f'status_50mhz[{i}]' for i in reversed(range(544))]];cases.append(bad)
        for bad in cases:
            out=io.StringIO();csv.writer(out).writerows(bad)
            with self.assertRaises(ValueError):decode(out.getvalue(),self.manifest())
        with self.assertRaises(ValueError):decode(self.csv([self.value(magic=0)]),self.manifest())
        with self.assertRaisesRegex(ValueError,'without a new sequence'):
            decode(self.csv([self.value(),self.value()^(1<<(32*55))]),self.manifest())
        with self.assertRaises(ValueError):decode_value(1<<BITS,self.manifest())

    def test_timeout_and_unpublished_values_never_claim_freshness(self):
        words=[0]*64;words[61]=31
        result=decode_value(self.value(words=words),self.manifest())
        self.assertFalse(result['checks']['fresh_snapshot'])
        result=decode_value(self.value(io=1),self.manifest())
        self.assertFalse(result['checks']['gao_snapshot_published'])

    def test_actual_async_rtl_full_snapshot_matches_uart_and_local_reset_cannot_forge_ack(self):
        for mode in ('normal','reset_pending','timeout_recover','forged-ack-mutant'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                work=Path(directory)
                tb='''module tb;
reg clk=0,pclk=0,rst=0,prst=0;always #10 clk=~clk;always #7 pclk=~pclk;
reg [2047:0] source=0;wire tx,published;wire [2079:0] full;
workstation_ae350_probe_uart #(.USER_CODE(32'hC21031D1),.BAUD_DIVISOR(4),.PERIOD_CYCLES(50),.SNAPSHOT_TIMEOUT(100)) dut(
.clk_50m(clk),.reset_n(rst),.pclk(pclk),.preset_n(prst),.source_words(source),.platform_flags({prst,3'b111}),
.tx(tx),.status_50mhz(),.full_snapshot_50mhz(full),.snapshot_published_50mhz(published));
integer i,j,b,epoch=0,snapshots=0;reg [2079:0] previous=0;reg [7:0] value;
always @(posedge pclk)if(prst)begin epoch=epoch+1;for(i=0;i<64;i=i+1)source[i*32+:32]<=32'ha1000000|(epoch<<8)|i;end
always @(negedge clk)if(published&&full!==previous)begin
 $display("SNAP %h",full);snapshots=snapshots+1;previous=full;
end
initial begin #100;rst=1;prst=1; CONTROL end
initial begin
for(j=0;j<840;j=j+1)begin @(negedge tx);#120;value=0;
for(b=0;b<8;b=b+1)begin value[b]=tx;#80;end
if(tx!==1)$fatal(1,"UART stop");$display("BYTE %02x",value);end
if(snapshots!=3)$fatal(1,"full snapshot count");$finish;end
initial begin #3000000;$fatal(1,"simulation timeout");end
endmodule'''
                control=''
                if mode in ('reset_pending','forged-ack-mutant'):
                    # Wait for request zero while ack is still one: the exact
                    # reset-to-zero forged-ack case in the previous transport.
                    control='''wait(dut.request==1);wait(dut.ack==1);wait(dut.state==0);
wait(dut.request==0);prst=0;
repeat(12)begin @(posedge pclk);#1;if(dut.ack!==1)$fatal(1,"local reset forged ack");end
prst=1;'''
                elif mode=='timeout_recover':
                    control='''prst=0;wait(dut.state==3);wait(dut.state==0);prst=1;'''
                (work/'tb.sv').write_text(tb.replace('CONTROL',control))
                rtl=ROOT/'rtl/probe/workstation_ae350_probe_uart.sv'
                if mode=='forged-ack-mutant':
                    original=rtl.read_text()
                    before='always @(posedge pclk or negedge reset_n) begin\n        if(!reset_n)'
                    after='always @(posedge pclk or negedge preset_n) begin\n        if(!preset_n)'
                    self.assertEqual(original.count(before),1)
                    rtl=work/'mutant.sv';rtl.write_text(original.replace(before,after))
                subprocess.run(['iverilog','-g2012','-s','tb','-o','sim','tb.sv',str(rtl)],cwd=work,check=True,capture_output=True)
                run=subprocess.run(['vvp','sim'],cwd=work,capture_output=True,text=True,timeout=20)
                if mode=='forged-ack-mutant':
                    self.assertNotEqual(run.returncode,0)
                    self.assertIn('local reset forged ack',run.stdout)
                    continue
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                raw=bytes(int(line.split()[1],16) for line in run.stdout.splitlines() if line.startswith('BYTE '))
                packets,bad=frames(raw);self.assertEqual(bad,0);self.assertEqual(len(packets),3)
                snapshots=[int(line.split()[1],16) for line in run.stdout.splitlines() if line.startswith('SNAP ')]
                self.assertEqual(len(snapshots),3)
                for index,(packet,snapshot) in enumerate(zip(packets,snapshots)):
                    self.assertEqual(snapshot>>2048,index)
                    self.assertEqual([(snapshot>>(i*32))&0xffffffff for i in range(64)],packet['words'])
                    if mode=='timeout_recover' and index==0:
                        self.assertTrue(packet['words'][61]&16)
                    else:
                        self.assertEqual(packet['words'][61],15)
                        prefix=packet['words'][0]&0xffffff00
                        self.assertTrue(all(v==prefix|i for i,v in enumerate(packet['words']) if i!=61))

if __name__=='__main__':unittest.main()
