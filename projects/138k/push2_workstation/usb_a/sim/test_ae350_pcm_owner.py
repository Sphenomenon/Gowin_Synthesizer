#!/usr/bin/env python3
from pathlib import Path
import os,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
BASE=r'''module tb;
reg clk=0,rst=0,cpu=0;always #5 clk=~clk;
reg cv=0,cw=0;reg [11:0] ca=0;reg [31:0] cd=0;reg [3:0] cs=15;
wire cr,err;wire [31:0] rd;
reg live=1,ctx_ready=1,rate44=0,tf=0,sw=0,take=0;reg [31:0] ce=11,tg=22,pe=7;
wire signed [31:0] left,right;wire clear,hold,selected,failed,hard_fault;wire [21:0] cancel;
reg history_ready=1,history_done=0;integer history_count=0;
workstation_ae350_pcm_owner #(.PREFILL_FRAMES(@PREFILL@),.HISTORY_TIMEOUT_CYCLES(1000)) dut(
.clk_i(clk),.reset_ni(rst),.cpu_ready_i(cpu),.command_valid_i(cv),.command_write_i(cw),
.command_address_i(ca),.command_data_i(cd),.command_strobes_i(cs),.command_ready_o(cr),.response_data_o(rd),.response_error_o(err),
.session_live_i(live),.controller_epoch_i(ce),.transport_generation_i(tg),.context_ready_i(ctx_ready),.rate_44100_i(rate44),
.physical_epoch_i(pe),.tf_busy_i(tf),.switch_busy_i(sw),.sample_take_i(take),
.legacy_left_i(32'sh12340000),.legacy_right_i(32'shfedc0000),.pcm_left_o(left),.pcm_right_o(right),
.history_clear_o(clear),.history_ready_i(history_ready),.history_done_i(history_done),.serial_hold_o(hold),
.cancel_epoch_o(cancel),.selected_o(selected),.failed_o(failed),.hard_fault_o(hard_fault));
always @(posedge clk)begin history_done<=0;
 if(clear&&history_ready)history_count<=4;
 else if(history_count>0)begin history_count<=history_count-1;if(history_count==1)history_done<=1;end
end
integer errors=0,i,j;reg [31:0] id,oldcancel;
task write(input[11:0] a,input[31:0] d,input e);begin
 @(negedge clk);cv=1;cw=1;ca=a;cd=d;#1;
 if(err!==e)$fatal(1,"command error addr=%h data=%h got=%b expected=%b failure=%d",a,d,err,e,dut.failure);
 @(negedge clk);cv=0;cw=0;end endtask
task key(input[31:0] stream);begin
 write('h020,ce,0);write('h024,tg,0);write('h028,stream,0);write('h02c,rate44?44100:48000,0);write('h030,pe,0);end endtask
task block(input integer slot,seq,n,base);reg[15:0] l,r;begin
 for(integer x=0;x<n;x=x+1)begin l=base+x;r= -base-x;write('h800+slot*512+x*4,{r,l},0);end
 write('h034,slot,0);write('h038,n,0);write('h03c,seq,0);write('h040,2,0);end endtask
task arm(input[31:0] stream);begin key(stream);write('h040,1,0);end endtask
task select_bt;begin write('h040,3,0);wait(!hold);#1;end endtask
task tick;begin @(negedge clk);take=1;@(negedge clk);take=0;repeat(2)@(negedge clk);end endtask
EXTRA
initial begin #21;rst=1;cpu=1;repeat(4)@(negedge clk);BODY end
initial begin #MAXTIME;$fatal(1,"timeout");end
endmodule'''
class PcmOwnerTest(unittest.TestCase):
    def run_tb(self,body,prefill=256,timeout=30,max_time=10000000000,extra=""):

        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory);(work/'tb.sv').write_text(BASE.replace('EXTRA',extra).replace('BODY',body).replace('@PREFILL@',str(prefill)).replace('MAXTIME',str(max_time)))
            r=subprocess.run(['iverilog','-g2012','-s','tb','-o','sim','tb.sv',str(ROOT/'rtl/audio/workstation_ae350_pcm_owner.sv')],cwd=work,capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run(['vvp','sim'],cwd=work,capture_output=True,text=True,timeout=timeout)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            return r.stdout

    def test_blocks_stereo_atomic_source_apply_and_no_old_sample_on_underrun(self):
        log=self.run_tb(r'''
arm(1);block(0,0,128,-32000);block(1,1,128,-31872);
if(dut.queued!=256||dut.owned!=3)$fatal(1,"commit occupancy");
write('h800,32'h1,1); // Owned slot is immutable.
select_bt();
for(i=0;i<255;i=i+1)begin
 if(left!==((-32000+i)<<16)||right!==((32000-i)<<16))$fatal(1,"stereo ordering/interpolation i=%d L=%h R=%h",i,left,right);
 tick();
 if(i==126 && !dut.owned[0])$fatal(1,"slot freed before last consumed sample");
 if(i==127 && dut.owned[0])$fatal(1,"slot not returned after last consumed sample");
end
if(dut.applied_id==0)$fatal(1,"source application missing");
if(left!==0||right!==0)$fatal(1,"underrun exposed stale pair");tick();
if(!failed||dut.failure!=4||dut.armed||dut.queued!=0)$fatal(1,"underrun must terminate stream");
wait(!hold);tick();if(selected||left!==32'h12340000)$fatal(1,"legacy not restored");
write('h040,1,1); // CPU cannot reopen same retired stream epoch.
$display("PASS stereo atomic blocks, immutable slot, apply and terminal underrun");$finish;''')
        self.assertIn('PASS',log)

    def test_session_cpu_rate_tf_cancel_and_stale_owner_fences(self):
        for reason,trigger in [(1,'cpu=0;'),(2,'live=0;'),(7,'pe=pe+1;'),(8,'tf=1;')]:
            with self.subTest(reason=reason):
                self.run_tb(r'''arm(1);block(0,0,128,100);block(1,1,128,228);select_bt();tick();
oldcancel=cancel;@(negedge clk);TRIGGER
repeat(3)@(negedge clk);
if(!failed||dut.failure!=REASON||dut.armed||dut.queued!=0||cancel==oldcancel)$fatal(1,"revocation failed");
if(left!==0||right!==0)$fatal(1,"old PCM survived fence");
wait(!hold);tick();if(selected)$fatal(1,"old BT automatically restored");
cpu=1;live=1;tf=0;key(1);write('h040,1,1);
arm(2);block(0,0,128,500);block(1,1,128,628);select_bt();tick();
key(1);write('h040,5,1);if(!selected||!dut.armed)$fatal(1,"old owner canceled new stream");
key(2);write('h040,5,0);wait(!hold);tick();write('h040,5,0); // matching cancel idempotent
$display("PASS reset/session/rate/TF fence and stale owner");$finish;'''.replace('TRIGGER',trigger).replace('REASON',str(reason)))

    def test_bad_partial_descriptor_and_sequence_wrap_fail_closed(self):
        self.run_tb(r'''arm(1);write('h034,0,0);write('h038,128,0);write('h03c,0,0);
write('h800,32'h11223344,0);write('h040,2,1);
if(!failed||dut.queued!=0||dut.owned!=0)$fatal(1,"partial block published");
arm(2);block(0,0,128,0);write('h034,1,0);write('h038,128,0);write('h03c,2,0);write('h040,2,1);
if(!failed||dut.failure!=6)$fatal(1,"sequence gap not terminal");
arm(3);force dut.expected_sequence=32'hffffffff;write('h040,2,1);release dut.expected_sequence;
if(!failed||dut.failure!=6)$fatal(1,"sequence wrap allowed");
$display("PASS partial descriptors, sequence gap/wrap");$finish;''')

    def test_pending_select_cancel_and_history_timeout(self):
        self.run_tb(r'''arm(1);block(0,0,128,0);block(1,1,128,128);
history_ready=0;write('h040,3,0);write('h040,5,0);
history_ready=1;wait(!hold);tick();
if(selected||dut.armed||dut.pending_id!=0)$fatal(1,"canceled pending select restored BT");
arm(2);block(0,0,128,0);block(1,1,128,128);
history_ready=0;write('h040,3,0);repeat(1010)@(negedge clk);
if(!hard_fault||!hold||!failed||dut.failure!=10)$fatal(1,"history timeout not quarantined");
$display("PASS pending cancel and history timeout");$finish;''')

    def test_fractional_src_zero_one_two_consumption_across_tiny_blocks(self):
        self.run_tb(r'''arm(1);block(0,0,1,100);block(1,1,1,200);block(2,2,1,300);block(3,3,1,400);
select_bt();force dut.phase=24'h800000;force dut.step_q24=32'd16777216;#1;
if(left!==(150<<16)||right!==(-150<<16))$fatal(1,"fractional stereo interpolation");
release dut.phase;release dut.step_q24;
force dut.phase=0;force dut.step_q24=32'd16743662;tick();
if(dut.input_frames!=0)$fatal(1,"zero input consume unavailable");release dut.phase;release dut.step_q24;
force dut.phase=24'hffffff;force dut.step_q24=32'd16810770;tick();
if(dut.input_frames!=2||dut.owned!=12||dut.head_slot!=2)$fatal(1,"two input cross-block consume");
release dut.phase;release dut.step_q24;repeat(2)@(negedge clk);force dut.phase=0;#1;
if(left!==300<<16)$fatal(1,"cross-block atomic read wrong");
$display("PASS interpolation, 0/1/2 source steps and tiny-block ownership");$finish;''',prefill=4)


    def test_full_queue_backpressure_and_simultaneous_publish_consume(self):
        self.run_tb(r'''arm(1);
block(0,0,128,0);block(1,1,128,128);block(2,2,128,256);block(3,3,128,384);
id=dut.command_id;write('h800,32'hbad,1);write('h034,0,0);write('h03c,4,0);write('h040,2,1);
if(dut.queued!=512||dut.owned!=15||failed||dut.command_id!=id||dut.overflows!=2)$fatal(1,"full queue overwrote owner");
write('h040,5,0);arm(2);block(0,0,2,100);block(1,1,2,200);select_bt();
write('hc00,32'hfed4012c,0);write('hc04,32'hfed3012d,0);
write('h034,2,0);write('h038,2,0);write('h03c,2,0);
@(negedge clk);take=1;cv=1;cw=1;ca='h040;cd=2;#1;if(err)$fatal(1,"concurrent commit refused");
@(negedge clk);take=0;cv=0;cw=0;
if(dut.queued!=5||dut.owned!=7||dut.input_frames!=1||dut.expected_sequence!=3)$fatal(1,"concurrent occupancy lost");
repeat(2)@(negedge clk);tick();if(dut.owned!=6||dut.queued!=4)$fatal(1,"last consumed sample did not return slot");
$display("PASS full queue immutability/backpressure and simultaneous commit/consume");$finish;''',prefill=4)

    def test_identity_capacity_and_cpu_reset_partial_history(self):
        self.run_tb(r'''@(negedge clk);dut.cancel_epoch_o=22'h3fffff;key(1);write('h040,1,1);
if(dut.armed)$fatal(1,"exhausted cancel identity allowed ARM");@(negedge clk);dut.cancel_epoch_o=0;dut.command_id=32'hfffffffe;arm(1);
if(dut.command_id!=32'hffffffff)$fatal(1,"last command id incorrect");
write('h040,5,1);if(!dut.armed||dut.command_id!=32'hffffffff)$fatal(1,"command identity wrapped");
$display("PASS command/cancellation identity never wraps");$finish;''')
        self.run_tb(r'''arm(1);write('h800,32'h12345678,0);cpu=0;repeat(3)@(negedge clk);cpu=1;
if(!failed||dut.written[0]!=0||dut.owned!=0)$fatal(1,"reset retained partial slot");key(1);write('h040,1,1);
arm(2);block(0,0,128,100);block(1,1,128,228);history_ready=0;write('h040,3,0);
cpu=0;repeat(3)@(negedge clk);cpu=1;history_ready=1;wait(!hold);tick();
if(selected||dut.armed||!failed)$fatal(1,"CPU reset during history revived BT");
$display("PASS CPU reset cancels partial write and pending source history");$finish;''')

    def test_actual_long_frequency_offsets_jitter_and_stereo_reference(self):
        count=int(os.environ.get('GW138K_PCM_DRIFT_FRAMES','576000'))
        for rate,ppm in ((48000,-2000),(48000,2000),(44100,-2000),(44100,2000)):
            with self.subTest(rate=rate,ppm=ppm):
                extra=r"""
reg run_stream=0;integer source_acc=0,source_frames=0;
integer out_count=0,ref_input=0,seq=3,zeros=0,ones=0,twos=0;
reg[23:0] ref_phase=0;reg[25:0] ref_sum;
integer l0,l1,r0,r1,want_l,want_r,used;
reg signed[63:0] numerator_l,numerator_r;
always @(posedge clk)if(run_stream)begin
 source_acc=source_acc+1000000+PPM;
 if(source_acc>=12000000)begin source_acc=source_acc-12000000;source_frames=source_frames+1;end
end
function integer ramp(input integer frame);ramp=frame%20000-10000;endfunction
""".replace('PPM',str(ppm))
                body=r"""
rate44=RATE44;arm(1);
block(0,0,128,-10000);block(1,1,128,-9872);block(2,2,128,-9744);
select_bt();run_stream=1;
fork
 begin
  while(out_count<FRAMES)begin
   repeat(11)@(negedge clk);
   if(failed||hold||!selected||!dut.cache_current)$fatal(1,"continuous stream lost n=%d failure=%d queued=%d",out_count,dut.failure,dut.queued);
   l0=ramp(ref_input);l1=ramp(ref_input+1);r0= -l0;r1= -l1;
   numerator_l=$signed(l0)*$signed(64'sd16777216-{40'd0,ref_phase})+$signed(l1)*$signed({40'd0,ref_phase});
   numerator_r=$signed(r0)*$signed(64'sd16777216-{40'd0,ref_phase})+$signed(r1)*$signed({40'd0,ref_phase});
   want_l=numerator_l>>>24;want_r=numerator_r>>>24;
   if($signed(left)!==(want_l<<16)||$signed(right)!==(want_r<<16))
    $fatal(1,"independent stereo SRC reference n=%d input=%d phase=%h got=%h/%h expected=%h/%h",out_count,ref_input,ref_phase,left,right,want_l<<16,want_r<<16);
   ref_sum={2'b0,ref_phase}+dut.step_q24;used=ref_sum>>24;
   if(used==0)zeros=zeros+1;else if(used==1)ones=ones+1;else if(used==2)twos=twos+1;else $fatal(1,"unbounded source step");
   ref_input=ref_input+used;ref_phase=ref_sum[23:0];
   take=1;@(negedge clk);take=0;out_count=out_count+1;
   if(dut.input_frames!=ref_input||dut.queued>512)$fatal(1,"input count/capacity violated");
  end
  run_stream=0;
  if(dut.step_q24<16743662||dut.step_q24>16810770)$fatal(1,"SRC ratio outside bound");
  if(PPM<0&&zeros==0)$fatal(1,"negative offset never used zero-step");
  if(PPM>0&&twos==0)$fatal(1,"positive offset never used two-step");
  $display("PASS drift rate=RATE ppm=PPM frames=%d queue=%d min=%d max=%d step=%d consumed=%d 0/1/2=%d/%d/%d",out_count,dut.queued,dut.minimum_queue,dut.maximum_queue,dut.step_q24,ref_input,zeros,ones,twos);
  $finish;
 end
 begin
  forever begin
   wait(source_frames>=(seq-2)*128);
   // Bounded decoder/service jitter, independent of the occupancy controller.
   repeat((seq%7)*50)@(negedge clk);
   wait(!dut.owned[seq%4]);
   for(j=0;j<128;j=j+1)begin
    l0=ramp(seq*128+j);r0= -l0;write('h800+(seq%4)*512+j*4,{16'(r0),16'(l0)},0);
   end
   write('h034,seq%4,0);write('h038,128,0);write('h03c,seq,0);write('h040,2,0);seq=seq+1;
  end
 end
join
""".replace('RATE44',str(int(rate==44100))).replace('FRAMES',str(count)).replace('PPM',str(ppm)).replace('RATE',str(rate))
                log=self.run_tb(body,extra=extra,timeout=120,max_time=count*200)
                print(log.strip(),flush=True)

if __name__=='__main__':unittest.main()
