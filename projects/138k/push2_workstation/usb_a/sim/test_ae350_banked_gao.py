#!/usr/bin/env python3
"""Strict four-page GAO decoding and actual UART/bank RTL, without EDA."""
from pathlib import Path
import copy,csv,io,json,os,subprocess,sys,tempfile,unittest,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'sim')]
from tools.decode_ae350_banked_gao import decode,page_value,BITS,MAGIC,METADATA
from tools.decode_ae350_local_probe import frames
from tools.workstation_ae350_local_probe import gao,gao_record,native_sources

class BankedGaoTest(unittest.TestCase):
    def manifest(self):
        return dict(identity='offline-banked-only',user_code='0xc21031d1',firmware=dict(
            capacity=dict(symbols=dict(__ilm_start=0xa0000000,__ilm_end=0xa0001000,
                __bss_end=0xa0200200,__stack_bottom=0xa020c000,__stack_top=0xa0210000)),
            payload=dict(crc32=1,first=2,last=3)))

    def value(self,page=0,sequence=0,words=None,io=0x1234567b,health=0xffff078f,user=0xc21031d1,magic=MAGIC,published=True):
        if words is None:words=[15 if i==61 else 0x10000000+i for i in range(64)]
        data=[*words[page*16:(page+1)*16],sequence,user,magic,METADATA|int(published)*4|page,io,health]
        return sum(n<<(32*i) for i,n in enumerate(data))

    def sweep(self,**kw):return [self.value(page=p,**kw) for p in range(4) for _ in range(4)]

    def csv(self,values):
        out=io.StringIO();w=csv.writer(out);w.writerow(['Groups:']);w.writerow(['Data:'])
        w.writerow(['time unit: us','status_50mhz',*[f'status_50mhz[{i}]' for i in reversed(range(BITS))],''])
        for i,v in enumerate(values):
            w.writerow([str(i),'X',*['X']*BITS,''] if v is None else [str(i),f'{v:X}',*f'{v:0{BITS}b}',''])
        return out.getvalue()

    def test_exact_layout_all_words_and_repeated_sweeps(self):
        result=decode(self.csv([None,*self.sweep(),*self.sweep()]),self.manifest())
        self.assertEqual(result['capture_bits'],704);self.assertEqual(len(result['observations']),2)
        latest=result['latest'];self.assertEqual(latest['words'],[15 if i==61 else 0x10000000+i for i in range(64)])
        self.assertEqual(latest['sequence'],0);self.assertTrue(latest['complete_snapshot'])
        self.assertTrue(latest['digital_io']['frozen_at_new_sequence_sweep_boundary'])
        self.assertFalse(latest['digital_io']['external_uart_reception_verified'])
        self.assertNotIn('live_platform_health',latest['digital_io'])
        self.assertIn('no UART CRC',latest['transport']);self.assertFalse(result['hardware_acceptance'])

    def test_first_middle_last_truncation_and_unstable_pages_fail_closed(self):
        sweep=self.sweep()
        cases=[sweep[4:],sweep[:4]+sweep[8:],sweep[:12],sweep[:13],
            [self.value(page=p) for p in range(4)],
            [*sweep[:4],None,*sweep[4:]],
            [*sweep,*self.sweep(sequence=1)[:12]],
            [*sweep,*self.sweep(sequence=1),*self.sweep()]]
        for values in cases:
            with self.subTest(values=len(values)),self.assertRaises(ValueError):decode(self.csv(values),self.manifest())
        for bit in (0,32*20,32*21):
            bad=self.sweep();bad[1]^=1<<bit
            with self.assertRaises(ValueError):decode(self.csv(bad),self.manifest())
        # Matching page data cannot excuse differing frozen IO/health between pages.
        for field in ('io','health'):
            bad=self.sweep();bad[4]=self.value(page=1,**{field:3})
            with self.assertRaises(ValueError):decode(self.csv(bad),self.manifest())

    def test_reset_contexts_and_timeout_remain_explicit(self):
        changed=[15 if i==61 else 0x20000000+i for i in range(64)]
        for separator in (0,self.value(published=False,io=1)):
            r=decode(self.csv([*self.sweep(),separator,*self.sweep(words=changed)]),self.manifest())
            self.assertEqual(r['latest']['words'],changed)
            with self.assertRaises(ValueError):decode(self.csv([*self.sweep()[:8],separator,*self.sweep()[8:]]),self.manifest())
            with self.assertRaises(ValueError):decode(self.csv([*self.sweep(),separator]),self.manifest())
        changed[61]=31
        r=decode(self.csv(self.sweep(words=changed)),self.manifest())
        self.assertFalse(r['latest']['checks']['fresh_snapshot'])
        self.assertFalse(r['latest']['counter_observation_passed'])

    def test_rejects_identity_schema_geometry_header_bits_and_legacy_width(self):
        for kw in (dict(user=1),dict(magic=0),dict(io=1)):
            with self.assertRaises(ValueError):decode(self.csv(self.sweep(**kw)),self.manifest())
        with self.assertRaises(ValueError):page_value(self.value()^(1<<(32*19+3)),self.manifest())
        rows=list(csv.reader(io.StringIO(self.csv(self.sweep()))));cases=[]
        bad=copy.deepcopy(rows);bad[2][2],bad[2][3]=bad[2][3],bad[2][2];cases.append(bad)
        bad=copy.deepcopy(rows);bad[-1].pop(100);cases.append(bad)
        bad=copy.deepcopy(rows);bad[-1][100]='1' if bad[-1][100]=='0' else '0';cases.append(bad)
        for width in (544,2208):
            bad=copy.deepcopy(rows);bad[2]=['time unit: us','status_50mhz',*[f'status_50mhz[{i}]' for i in reversed(range(width))]];cases.append(bad)
        for bad in cases:
            out=io.StringIO();csv.writer(out).writerows(bad)
            with self.assertRaises(ValueError):decode(out.getvalue(),self.manifest())

    def test_explicit_mode_preserves_default_gao(self):
        self.assertEqual(gao('00006403'),gao('00006403','full64'))
        for mode,width in (('full64',2208),('banked4',704)):
            core=ET.fromstring(gao('00006403',mode)).find('AoCore')
            self.assertEqual([n.text for n in core.findall('SignalList/Bus/Signal')],
                [f'status_50mhz[{i}]' for i in reversed(range(width))])
            self.assertEqual(gao_record(mode)['capture_bits'],width)
        self.assertEqual(len(native_sources('banked4')),len(native_sources('full64'))+1)
        for function in (native_sources,gao_record):
            with self.assertRaises(ValueError):function('implicit')

    def test_actual_banked_top_ports_and_all_four_pages(self):
        from tools.workstation_baselines import load_baseline
        baseline=load_baseline(ROOT,'resource_rework_route0')
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);(work/'firmware').mkdir()
            (work/'firmware/boot.mem').write_text('00000000\n'*16384)
            (work/'probe_identity.vh').write_text("`define AE350_PROBE_USER_CODE 32'hC21031D1\n`define AE350_PROBE_BANKED_GAO\n")
            (work/'riscv_ae350_config.v').write_bytes(baseline.read_bytes('riscv_ae350_config.v'))
            header=baseline.read_bytes('src/ae350/riscv_ae350_top.v').decode().split(');',1)[0]
            (work/'cpu_stub.v').write_text(header+');\nendmodule\n')
            (work/'pll_stub.v').write_text('''module gw138k_cpu_pll_cell(input clkin,init_clk,reset,enable0,
output lock,clkout0,clkout1);assign lock=!reset;assign clkout0=clkin;assign clkout1=clkin;endmodule''')
            full=sum(i<<(i*32) for i in range(64))|(0x01020304<<2048)
            (work/'tb.sv').write_text('''module tb;reg clk=0;always #10 clk=~clk;
wire pdn,mclk,bick,lrck,data,smute;
workstation_ae350_local_memory_probe_top dut(.clk_50m(clk),.debug_uart_tx(),
.ak_pdn(pdn),.ak_mclk(mclk),.ak_bick(bick),.ak_lrck(lrck),.ak_sdata(data),.ak_smute(smute));
integer i,j;reg [3:0] pages=0;
initial begin #51;force dut.power_on=16'hffff;
force dut.u_uart.full_snapshot_50mhz=2080'hFULL;
force dut.u_uart.snapshot_published_50mhz=1'b1;
wait(dut.status_50mhz[610]);
for(j=0;j<32;j=j+1)begin @(negedge clk);
 if({smute,pdn,mclk,bick,lrck,data}!==6'b100000)$fatal(1,"DAC safety levels changed");
 if($bits(dut.status_50mhz)!=704)$fatal(1,"banked GAO width");
 if(dut.status_50mhz[607:576]!==32'ha1386402||dut.status_50mhz[575:544]!==32'hc21031d1||
    dut.status_50mhz[543:512]!==32'h01020304||dut.status_50mhz[639:611]!==29'h00880200)
     $fatal(1,"banked GAO metadata");
 pages[dut.status_50mhz[609:608]]=1;
 for(i=0;i<16;i=i+1)if(dut.status_50mhz[i*32+:32]!==dut.status_50mhz[609:608]*16+i)$fatal(1,"banked top word order");
end
if(pages!==15)$fatal(1,"missing top page");
$display("PASS actual banked top, 704 bits, four pages, DAC safety");$finish;end
initial begin #100000;$fatal(1,"top timeout");end endmodule'''.replace('FULL',f'{full:x}'))
            rtl=['rtl/probe/workstation_ae350_local_memory_probe_top.sv','rtl/probe/workstation_ae350_probe_uart.sv',
                'rtl/probe/workstation_ae350_probe_gao_banks.sv','rtl/clock/workstation_ae350_rtc.sv',
                'rtl/memory/workstation_ae350_boot_memory.sv']
            result=subprocess.run(['iverilog','-g2012','-I.','-s','tb','-o','sim','tb.sv','cpu_stub.v','pll_stub.v',
                *[str(ROOT/p) for p in rtl]],cwd=work,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run(['vvp','sim'],cwd=work,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def run_rtl(self,tb,rtl_names,mutant=False):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);(work/'tb.sv').write_text(tb)
            rtl=[ROOT/name for name in rtl_names]
            if mutant:
                old=rtl[0].read_text();before='always @(posedge pclk or negedge reset_n) begin\n        if(!reset_n)'
                self.assertEqual(old.count(before),1)
                m=work/'mutant.sv';m.write_text(old.replace(before,'always @(posedge pclk or negedge preset_n) begin\n        if(!preset_n)'));rtl[0]=m
            compile=subprocess.run(['iverilog','-g2012','-s','tb','-o','sim','tb.sv',*map(str,rtl)],cwd=work,capture_output=True,text=True)
            self.assertEqual(compile.returncode,0,compile.stderr)
            return subprocess.run(['vvp','sim'],cwd=work,capture_output=True,text=True,timeout=30)

    def test_banks_freeze_slow_sequence_live_io_and_exact_boundary_update(self):
        tb='''module tb;
reg clk=0,rst=0,pub=0;always #10 clk=~clk;
reg [2079:0] full=0;reg [31:0] io=3,health=0;wire [703:0] sample;
workstation_ae350_probe_gao_banks #(.USER_CODE(32'hc21031d1)) dut(
.clk_50m(clk),.reset_n(rst),.full_snapshot_50mhz(full),.snapshot_published_50mhz(pub),
.digital_io_50mhz(io),.health_50mhz(health),.sample_50mhz(sample));
integer i,j;reg [703:0] seen[0:3];reg [31:0] old_io,old_health;
always @(negedge clk)begin io<=io+4;health<=health+1;end
initial begin #41;rst=1;pub=1;for(i=0;i<64;i=i+1)full[i*32+:32]=32'h10000000+i;
wait(dut.frozen_valid);#1;old_io=sample[671:640];old_health=sample[703:672];
// Sequence is unchanged across many sweeps while live words/IO/health change.
for(j=0;j<96;j=j+1)begin @(posedge clk);#1;
 if(sample[671:640]!==old_io||sample[703:672]!==old_health)$fatal(1,"same-sequence live metadata leaked");
 for(i=0;i<16;i=i+1)if(sample[i*32+:32]!==32'h10000000+sample[609:608]*16+i)$fatal(1,"frozen page data");
 full[31:0]=j;end
// Present a new published bank immediately before the page3-to0 clock.
wait(dut.page==3&&dut.dwell==3);@(negedge clk);
full[2079:2048]=1;for(i=0;i<64;i=i+1)full[i*32+:32]=32'h20000000+i;
@(posedge clk);#1;if(sample[609:608]!==0||sample[543:512]!==1)$fatal(1,"boundary update delayed/torn");
for(j=0;j<32;j=j+1)begin @(posedge clk);#1;
 for(i=0;i<16;i=i+1)if(sample[i*32+:32]!==32'h20000000+sample[609:608]*16+i)$fatal(1,"boundary pages torn");end
@(negedge clk);rst=0;#1;if(dut.frozen_valid!==0||dut.frozen_snapshot!==0)$fatal(1,"common reset did not clear bank");
$display("PASS slow sequence, frozen IO/health, exact boundary and common reset");$finish;end
endmodule'''
        result=self.run_rtl(tb,['rtl/probe/workstation_ae350_probe_gao_banks.sv'])
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_actual_async_uart_bank_decoding_preset_timeout_reset_and_ack_mutant(self):
        for mode in ('normal','reset_pending','timeout_recover','common_reset','forged-ack-mutant'):
            with self.subTest(mode=mode):
                tb='''module tb;
reg clk=0,pclk=0,rst=0,prst=0;always #10 clk=~clk;always #7 pclk=~pclk;
reg [2047:0] source=0;wire tx,published;wire [2079:0] full;wire [703:0] bank;reg [703:0] sample=0;
reg [29:0] edges=0;reg last_tx=1;reg [31:0] health=0;
workstation_ae350_probe_uart #(.USER_CODE(32'hC21031D1),.BAUD_DIVISOR(4),.PERIOD_CYCLES(50),.SNAPSHOT_TIMEOUT(100)) dut(
.clk_50m(clk),.reset_n(rst),.pclk(pclk),.preset_n(prst),.source_words(source),.platform_flags({prst,3'b111}),
.tx(tx),.status_50mhz(),.full_snapshot_50mhz(full),.snapshot_published_50mhz(published));
workstation_ae350_probe_gao_banks #(.USER_CODE(32'hC21031D1)) banks(
.clk_50m(clk),.reset_n(rst),.full_snapshot_50mhz(full),.snapshot_published_50mhz(published),
.digital_io_50mhz({edges,published,tx}),.health_50mhz(health),.sample_50mhz(bank));
always @(posedge clk or negedge rst)if(!rst)begin sample<=0;edges<=0;last_tx<=1;health<=0;end
else begin sample<=bank;last_tx<=tx;if(last_tx!=tx)edges<=edges+1;health<=health+1;end
integer i,j,b,epoch=0,received=0,capture_left=0;reg active=0;reg [31:0] previous_sequence=0;reg [7:0] value;
always @(posedge pclk)if(prst)begin epoch=epoch+1;for(i=0;i<64;i=i+1)source[i*32+:32]<=32'ha1000000|(epoch<<8)|i;end
always @(negedge clk)begin
 if(!sample[610])begin if(active||sample==0)$display("GAO %h",sample);active=0;capture_left=0;end
 else begin
  if(!active||sample[543:512]!=previous_sequence)begin active=1;previous_sequence=sample[543:512];capture_left=40;end
  if(capture_left>0)begin $display("GAO %h",sample);capture_left=capture_left-1;end
 end
end
initial begin #100;rst=1;prst=1; CONTROL end
initial begin
for(j=0;j<840;j=j+1)begin @(negedge tx);#120;value=0;
for(b=0;b<8;b=b+1)begin value[b]=tx;#80;end
if(tx!==1)$fatal(1,"UART stop");$display("BYTE %02x",value);received=received+1;end
$finish;end
initial begin #3000000;$fatal(1,"simulation timeout");end
endmodule'''
                control=''
                if mode in ('reset_pending','forged-ack-mutant'):
                    control='''wait(dut.request==1);wait(dut.ack==1);wait(dut.state==0);
wait(dut.request==0);prst=0;
repeat(12)begin @(posedge pclk);#1;if(dut.ack!==1)$fatal(1,"local reset forged ack");end
prst=1;'''
                elif mode=='timeout_recover':control='prst=0;wait(dut.state==3);wait(dut.state==0);prst=1;'
                elif mode=='common_reset':control='wait(received==280);wait(dut.state==0);#1;rst=0;prst=0;#101;rst=1;prst=1;'
                result=self.run_rtl(tb.replace('CONTROL',control),['rtl/probe/workstation_ae350_probe_uart.sv','rtl/probe/workstation_ae350_probe_gao_banks.sv'],mode=='forged-ack-mutant')
                evidence=os.environ.get('GW138K_BANKED_GAO_EVIDENCE')
                if evidence:
                    target=Path(evidence);target.mkdir(parents=True,exist_ok=True)
                    with (target/(mode+'.rtl.log')).open('x') as stream:stream.write(result.stdout+result.stderr)
                if mode=='forged-ack-mutant':
                    self.assertNotEqual(result.returncode,0);self.assertIn('local reset forged ack',result.stdout);continue
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                raw=bytes(int(line.split()[1],16) for line in result.stdout.splitlines() if line.startswith('BYTE '))
                packets,bad=frames(raw);self.assertEqual(bad,0);self.assertEqual(len(packets),3)
                values=[int(line.split()[1],16) for line in result.stdout.splitlines() if line.startswith('GAO ')]
                decoded=decode(self.csv(values),self.manifest())
                if evidence:
                    for suffix,data in (('.uart.bin',raw),('.gao.csv',self.csv(values).encode()),
                            ('.decoded.json',(json.dumps(decoded,indent=2)+'\n').encode())):
                        with (target/(mode+suffix)).open('xb') as stream:stream.write(data)
                observations=decoded['observations']
                by_snapshot=[]
                for observation in observations:
                    key=(observation['sequence'],tuple(observation['words']))
                    if not by_snapshot or key!=by_snapshot[-1]:by_snapshot.append(key)
                self.assertEqual(by_snapshot,[(p['sequence'],tuple(p['words'])) for p in packets])
                self.assertEqual([p['sequence'] for p in packets],[0,0,1] if mode=='common_reset' else [0,1,2])
                if mode=='timeout_recover':
                    self.assertTrue(packets[0]['words'][61]&16)
                    self.assertFalse(observations[0]['checks']['fresh_snapshot'])
                if mode=='common_reset':self.assertGreater(decoded['reset_rows'],0)

if __name__=='__main__':unittest.main()
