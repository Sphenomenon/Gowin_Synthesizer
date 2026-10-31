#!/usr/bin/env python3
"""Explicit bsram8 canonical snapshot, actual synchronous RAM/UART/GAO tests."""
from pathlib import Path
import json,os,subprocess,tempfile,unittest,sys,csv,io
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'sim')]
import test_ae350_banked_gao as banked
from tools.decode_ae350_bsram8_gao import decode,page_value
from tools.decode_ae350_local_probe import frames
from tools.workstation_ae350_local_probe import gao_record,native_sources
TB=r'''`timescale 1ns/1ps
module tb;
`ifdef WORKSTATION_SDP_VENDOR_SIM
GSR GSR(.GSRI(1'b1));
`endif
reg clk=0,pclk=0,rst=0,prst=0;always #10 clk=~clk;always #7 pclk=~pclk;
reg [2047:0] source=0;wire tx,published,update;wire [447:0] next_sample;reg[447:0] sample=0;
reg[29:0] edges=0;reg last_tx=1;reg[31:0] health=0;
workstation_ae350_probe_snapshot_ram #(.USER_CODE(32'hc21031d4),.PAGE_WORDS(8),.BAUD_DIVISOR(@BAUD@),.PERIOD_CYCLES(50),.SNAPSHOT_TIMEOUT(100)) dut(
.clk_50m(clk),.reset_n(rst),.pclk(pclk),.preset_n(prst),.source_words(source),.platform_flags({prst,3'b111}),
.digital_io_50mhz({edges,published,tx}),.health_50mhz(health),.tx(tx),.snapshot_published_50mhz(published),.sample_update_o(update),.sample_50mhz(next_sample));
always @(posedge clk or negedge rst)if(!rst)begin sample<=0;edges<=0;last_tx<=1;health<=0;end
else begin if(update)sample<=next_sample;last_tx<=tx;if(last_tx!=tx)edges<=edges+1;health<=health+1;end
integer i,j,b,epoch=0,received=0,capture_left=0,stable_cycles=0,changes=0;reg active=0;
reg[31:0] previous_sequence=0;reg[7:0] value;reg[447:0] old_sample=0;
integer copy_writes=0;
always @(posedge clk)if(!rst)copy_writes=0;else begin
 if(dut.write_enable)begin
  if(dut.frozen_valid&&dut.copy_bank==dut.frozen_bank)$fatal(1,"copy overwrote active frozen bank");
  copy_writes=copy_writes+1;
 end
 if(dut.state==4)begin
  if(!dut.pending_flags[4]&&copy_writes!=16)$fatal(1,"fresh publication before complete16-group copy");
  copy_writes=0;
 end
end
always @(posedge pclk)if(prst)begin epoch=epoch+1;for(i=0;i<64;i=i+1)source[i*32+:32]<=32'ha1000000|(epoch<<8)|i;end
always @(negedge clk)begin
 if(!sample[355])begin if(active||sample==0)$display("GAO %h",sample);active=0;capture_left=0;stable_cycles=0;end
 else begin
  if(old_sample!=sample)begin
   if(stable_cycles!=0&&stable_cycles!=4)$fatal(1,"page dwell changed %d",stable_cycles);
   if(old_sample[355]&&old_sample[287:256]==sample[287:256]&&sample[354:352]!==old_sample[354:352]+3'd1)$fatal(1,"page order");
   old_sample=sample;stable_cycles=1;changes=changes+1;
  end else stable_cycles=stable_cycles+1;
  if(!active||sample[287:256]!=previous_sequence)begin active=1;previous_sequence=sample[287:256];capture_left=72;end
  if(capture_left>0)begin $display("GAO %h",sample);capture_left=capture_left-1;end
 end
end
initial begin #100;rst=1;prst=1; CONTROL end
initial begin
 for(j=0;j<840;j=j+1)begin @(negedge tx);#(30*@BAUD@);value=0;
  for(b=0;b<8;b=b+1)begin value[b]=tx;#(20*@BAUD@);end
  if(tx!==1)$fatal(1,"UART stop");$display("BYTE %02x",value);received=received+1;
 end
 if(changes<24)$fatal(1,"insufficient page coverage");$display("PASS canonical synchronous RAM snapshot/UART/GAO");$finish;
end
initial begin #4000000;$fatal(1,"timeout");end
endmodule'''
def narrow_csv(values):
 out=io.StringIO();writer=csv.writer(out);writer.writerow(['time unit: us','status_50mhz',*[f'status_50mhz[{i}]' for i in reversed(range(448))]])
 for i,v in enumerate(values):writer.writerow([str(i),f'{v:X}',*f'{v:0448b}'])
 return out.getvalue()
class NarrowSnapshotRamTest(unittest.TestCase):
 def manifest(self):
  m=banked.BankedGaoTest().manifest();m['identity']='offline-bsram8-only';m['user_code']='0xc21031d4';m['gao']=gao_record('bsram8');return m
 def run_tb(self,control='',mode='normal',baud=4,vendor=False,mutant=None):
  with tempfile.TemporaryDirectory(prefix='ae350-snapshot-ram-') as d:
   w=Path(d);(w/'tb.sv').write_text(TB.replace('CONTROL',control).replace('@BAUD@',str(baud)))
   src=ROOT/'rtl/probe/workstation_ae350_probe_snapshot_ram.sv'
   if mutant:
    text=src.read_text();before,after=mutant;assert text.count(before)==1;text=text.replace(before,after);src=w/'mutant.sv';src.write_text(text)
   args=['iverilog','-g2012','-s','tb','-o','sim','tb.sv',str(src),str(ROOT/'rtl/memory/workstation_sdp.sv')]
   if vendor:
    args.insert(1,'-DWORKSTATION_SDP_VENDOR_SIM');args.append('/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/simlib/gw5a/prim_sim.v')
   c=subprocess.run(args,cwd=w,capture_output=True,text=True);self.assertEqual(c.returncode,0,c.stderr)
   r=subprocess.run(['vvp','sim'],cwd=w,capture_output=True,text=True,timeout=60)
   target=os.environ.get('GW138K_SNAPSHOT_RAM_EVIDENCE')
   if target:
    p=Path(target);p.mkdir(parents=True,exist_ok=True);(p/(mode+'.rtl.log')).write_text(r.stdout+r.stderr)
   if mutant and r.returncode!=0:return r,None,None
   if mutant:
    try:
     raw=bytes(int(x.split()[1],16) for x in r.stdout.splitlines() if x.startswith('BYTE '))
     packets,bad=frames(raw);self.assertEqual(bad,0)
     values=[int(x.split()[1],16) for x in r.stdout.splitlines() if x.startswith('GAO ')]
     d=decode(narrow_csv(values),self.manifest())
     for x in d['observations']:
      self.assertIn((x['sequence'],x['words']),[(y['sequence'],y['words']) for y in packets])
    except (AssertionError,ValueError):
     r.oracle_rejected=True;return r,None,None
    return r,None,None
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   raw=bytes(int(s.split()[1],16) for s in r.stdout.splitlines() if s.startswith('BYTE '));packets,bad=frames(raw)
   self.assertEqual(bad,0);self.assertEqual(len(packets),3)
   values=[int(s.split()[1],16) for s in r.stdout.splitlines() if s.startswith('GAO ')]
   csv=narrow_csv(values);decoded=decode(csv,self.manifest())
   found=[]
   for x in decoded['observations']:
    key=x['sequence'],tuple(x['words'])
    if not found or key!=found[-1]:found.append(key)
   self.assertEqual(found,[(x['sequence'],tuple(x['words'])) for x in packets])
   for x in packets:
    payload=[v for i,v in enumerate(x['words']) if i!=61]
    if not x['words'][61]&16:
     self.assertTrue(all((v>>8)==(payload[0]>>8) for v in payload),'pclk snapshot torn across RAM copy')
     self.assertTrue(all((v&255)==i for i,v in enumerate(x['words']) if i!=61),'word/lane ordering')
   if target:
    (p/(mode+'.uart.bin')).write_bytes(raw);(p/(mode+'.gao.csv')).write_text(csv);(p/(mode+'.decoded.json')).write_text(json.dumps(decoded,indent=2)+'\n')
   return r,packets,decoded
 def test_end_to_end_normal_and_fastest_uart(self):
  for baud in (1,4):
   with self.subTest(baud=baud):self.run_tb(mode='normal-baud'+str(baud),baud=baud)
 def test_native_gw5a_synchronous_sdp_primitive(self):self.run_tb(mode='vendor-sdp',vendor=True)
 def test_local_reset_pending_keeps_ack_and_held_capture(self):
  control='''wait(dut.request==1);wait(dut.ack==1);wait(dut.state==0);wait(dut.request==0);prst=0;
repeat(12)begin @(posedge pclk);#1;if(dut.ack!==1)$fatal(1,"local reset forged ack");end prst=1;'''
  self.run_tb(control,mode='local-reset')
 def test_initial_timeout_and_real_recovery(self):
  _,packets,decoded=self.run_tb('prst=0;wait(dut.state==4);wait(dut.state==0);prst=1;',mode='initial-timeout')
  self.assertTrue(packets[0]['words'][61]&16);self.assertFalse(decoded['observations'][0]['checks']['fresh_snapshot']);self.assertFalse(packets[1]['words'][61]&16)
 def test_timeout_retains_prior_bank_and_marks_stale(self):
  _,p,_=self.run_tb('wait(received==280);prst=0;wait(received==560);prst=1;',mode='retain-timeout')
  self.assertTrue(p[1]['words'][61]&16)
  self.assertEqual([v for i,v in enumerate(p[0]['words']) if i!=61],[v for i,v in enumerate(p[1]['words']) if i!=61])
 def test_common_reset_never_exposes_uninitialized_ram(self):
  _,p,d=self.run_tb('wait(received==280);wait(dut.state==0);#1;rst=0;prst=0;#101;rst=1;prst=1;',mode='common-reset')
  self.assertEqual([x['sequence'] for x in p],[0,0,1]);self.assertGreater(d['reset_rows'],0)
 def test_actual_top_keeps448_registered_bits_all_words_and_dac_safety(self):
  from tools.workstation_baselines import load_baseline
  baseline=load_baseline(ROOT,'resource_rework_route0')
  with tempfile.TemporaryDirectory() as directory:
   w=Path(directory);(w/'firmware').mkdir();(w/'firmware/boot.mem').write_text('00000000\n'*16384)
   (w/'probe_identity.vh').write_text("`define AE350_PROBE_USER_CODE 32'hC21031D4\n`define AE350_PROBE_BSRAM_GAO\n`define AE350_PROBE_BSRAM8_GAO\n")
   (w/'riscv_ae350_config.v').write_bytes(baseline.read_bytes('riscv_ae350_config.v'))
   header=baseline.read_bytes('src/ae350/riscv_ae350_top.v').decode().split(');',1)[0]
   (w/'cpu_stub.v').write_text(header+');\nendmodule\n')
   (w/'pll_stub.v').write_text('module gw138k_cpu_pll_cell(input clkin,init_clk,reset,enable0,output lock,clkout0,clkout1);assign lock=!reset;assign clkout0=clkin;assign clkout1=clkin;endmodule')
   data=sum(i<<(i*32) for i in range(64))
   tb='''module tb;reg clk=0;always #10 clk=~clk;wire pdn,mclk,bick,lrck,data,smute;
workstation_ae350_local_memory_probe_top dut(.clk_50m(clk),.debug_uart_tx(),.ak_pdn(pdn),.ak_mclk(mclk),.ak_bick(bick),.ak_lrck(lrck),.ak_sdata(data),.ak_smute(smute));
defparam dut.u_uart.PERIOD_CYCLES=30;defparam dut.u_uart.BAUD_DIVISOR=4;
integer i,j;reg[7:0] pages=0;
initial begin #51;force dut.power_on=16'hffff;force dut.pclk=clk;force dut.preset_n=1;
force dut.u_uart.source_words=2048'hDATA;
wait(dut.status_50mhz[355]);for(j=0;j<72;j=j+1)begin @(negedge clk);
if({smute,pdn,mclk,bick,lrck,data}!==6'b100000)$fatal(1,"DAC safety");
if($bits(dut.status_50mhz)!=448||dut.status_50mhz[351:320]!==32'ha1386404||dut.status_50mhz[319:288]!==32'hc21031d4)$fatal(1,"explicit bsram8 identity");
pages[dut.status_50mhz[354:352]]=1;
for(i=0;i<8;i=i+1)if(dut.status_50mhz[354:352]*8+i!=61 && dut.status_50mhz[i*32+:32]!==dut.status_50mhz[354:352]*8+i)$fatal(1,"top word order");
end if(pages!==255)$fatal(1,"missing pages");$display("PASS actual bsram8 top,448bits/all64words/DAC safety");$finish;end
initial begin #100000;$fatal(1,"top timeout");end endmodule'''.replace('DATA',f'{data:x}')
   (w/'tb.sv').write_text(tb)
   rtl=['rtl/probe/workstation_ae350_local_memory_probe_top.sv','rtl/probe/workstation_ae350_probe_snapshot_ram.sv','rtl/memory/workstation_sdp.sv','rtl/clock/workstation_ae350_rtc.sv','rtl/memory/workstation_ae350_boot_memory.sv']
   c=subprocess.run(['iverilog','-g2012','-I.','-s','tb','-o','sim','tb.sv','cpu_stub.v','pll_stub.v',*[str(ROOT/x) for x in rtl]],cwd=w,capture_output=True,text=True);self.assertEqual(c.returncode,0,c.stderr)
   r=subprocess.run(['vvp','sim'],cwd=w,capture_output=True,text=True,timeout=10);self.assertEqual(r.returncode,0,r.stdout+r.stderr)

 def test_negative_controls_reject_forged_ack_bad_read_schedule_and_bank_reuse(self):
  control='''wait(dut.request==1);wait(dut.ack==1);wait(dut.state==0);wait(dut.request==0);prst=0;
repeat(12)begin @(posedge pclk);#1;if(dut.ack!==1)$fatal(1,"local reset forged ack");end prst=1;'''
  mutants=[('forged-ack',control,('always @(posedge pclk or negedge reset_n)begin\n        if(!reset_n)',
      'always @(posedge pclk or negedge preset_n)begin\n        if(!preset_n)')),
    ('read-schedule','',('wire narrow_group=phase!=3;','wire narrow_group=phase==3;')),
    ('overwrite-active','',('copy_bank<=!published_bank;copy_zero<=0;','copy_bank<=published_bank;copy_zero<=0;'))]
  for name,c,mutation in mutants:
   with self.subTest(mutant=name):
    try:
     r,_,_=self.run_tb(c,mode='negative-'+name,mutant=mutation)
     if name=='forged-ack':self.assertNotEqual(r.returncode,0);self.assertIn('local reset forged ack',r.stdout)
     else:
      # The native consumer oracle must reject the wrong pipeline or live-bank
      # overwrite; a UART CRC alone cannot prove snapshot immutability.
      self.assertTrue(r.returncode!=0 or getattr(r,'oracle_rejected',False),r.stdout)
    except AssertionError:raise

 def test_old_mode_schema_cannot_be_relabelled(self):
  self.assertEqual(gao_record('bsram8')['schema'],'A1386404');self.assertEqual(gao_record('bsram8')['page_cycles'],4)
  self.assertNotIn('rtl/probe/workstation_ae350_probe_uart.sv',native_sources('bsram8'))
  self.assertIn('rtl/memory/workstation_sdp.sv',native_sources('bsram8'))
  with self.assertRaises(ValueError):page_value(banked.BankedGaoTest().value(),self.manifest())
if __name__=='__main__':unittest.main()
