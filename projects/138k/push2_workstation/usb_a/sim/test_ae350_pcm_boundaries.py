#!/usr/bin/env python3
"""Actual bundled-session CDC and final serial-cache revocation boundaries."""
from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class Boundaries(unittest.TestCase):
    def run_tb(self,source,modules):
        with tempfile.TemporaryDirectory(prefix='gw138k-pcm-boundary-') as d:
            w=Path(d);(w/'tb.sv').write_text(source)
            c=subprocess.run(['iverilog','-g2012','-s','tb','-o','sim','tb.sv',*[str(ROOT/p) for p in modules]],cwd=w,capture_output=True,text=True)
            self.assertEqual(c.returncode,0,c.stderr)
            r=subprocess.run(['vvp','sim'],cwd=w,capture_output=True,text=True,timeout=20)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);print(r.stdout,end='');return r.stdout
    def test_session_bundle_capture_and_asynchronous_revoke(self):
        self.run_tb(r'''`timescale 1ns/1ps
module tb;
reg clk=0,rst=0,ready=0;always #6.5 clk=!clk;
reg[31:0] se=32'h11111111,sg=32'haaaaaaaa;wire live;wire[31:0] e,g;
workstation_ae350_pcm_session dut(.reset_ni(rst),.clk_i(clk),.source_ready_i(ready),.source_epoch_i(se),.source_generation_i(sg),.live_o(live),.epoch_o(e),.generation_o(g));
task release_check;begin
 for(integer n=0;n<3;n=n+1)begin @(posedge clk);#0.1;if(live)$fatal(1,"bundle released before synchronizer/settle");end
 @(posedge clk);#0.1;if(!live||e!==se||g!==sg)$fatal(1,"bundle tuple missing or spliced");
end endtask
initial begin
 #17;rst=1;#2;ready=1;release_check();
 // Source must hold tuple immutable while ready; ready revokes between clocks.
 @(negedge clk);#1;ready=0;#0.1;if(live)$fatal(1,"revoke waited for destination edge");
 se=32'h22222222;#1;sg=32'hbbbbbbbb;#19;ready=1;release_check();
 // A sub-destination-cycle pulse still closes the gate asynchronously.
 @(negedge clk);#1;ready=0;#0.1;if(live)$fatal(1,"short revoke missed");
 se=32'h33333333;sg=32'hcccccccc;#1;ready=1;release_check();
 #1;rst=0;#0.1;if(live)$fatal(1,"reset did not close");#19;rst=1;release_check();
 $display("PASS held epoch/generation CDC, settle, short asynchronous revocation and reset");$finish;
end
initial begin #10000;$fatal(1,"timeout");end
endmodule''',['rtl/audio/workstation_ae350_pcm_session.sv'])
    def test_source_hold_discards_cache_and_late_response_at_both_rates(self):
        self.run_tb(r'''`timescale 1ns/1ps
module tb;
reg clk=0,rst=0,rate=0,hold=0,auto_response=1;always #5 clk=!clk;
reg valid=0;wire ready,request,bck,lrck,sd,fv,fe;wire[31:0] req_seq,pcm,seq,rejected;
reg[31:0] sample_seq=0,sample_pcm=0;reg[15:0] marker=16'h1111;
workstation_i2s_serializer #(.PDN_HOLD_FRAMES(1),.STARTUP_MUTE_FRAMES(3),.SAMPLE_ERROR_ENABLE(1),.SOURCE_HOLD_ENABLE(1)) dut(
.clk_i(clk),.rst_ni(rst),.rate_44k1_i(rate),.epoch_i(32'd7),.quiesce_i(1'b0),.resume_i(1'b1),.source_hold_i(hold),
.request_o(request),.request_sequence_o(req_seq),.sample_valid_i(valid),.sample_ready_o(ready),.sample_44k1_i(rate),.sample_error_i(1'b0),
.sample_epoch_i(32'd7),.sample_sequence_i(sample_seq),.sample_pcm_i(sample_pcm),.bck_o(bck),.lrck_o(lrck),.data_o(sd),
.frame_valid_o(fv),.frame_error_o(fe),.frame_pcm_o(pcm),.frame_sequence_o(seq),.rejected_sample_count_o(rejected));
integer position=0,frames=0,zero_frames=0,good_new=0;reg[31:0] decoded=0,last_decoded=0,last_seq=0;reg have_seq=0,check_new=0;
always @(negedge rst)begin position=0;decoded=0;last_decoded=0;have_seq=0;end
always @(posedge bck)if(rst)begin #0.1;
 if(lrck!==(position>=32))$fatal(1,"LRCK changed in frame");
 if(position>=1&&position<=16)decoded[32-position]=sd;
 else if(position>=33&&position<=48)decoded[48-position]=sd;
 else if(sd!==0)$fatal(1,"nonzero I2S padding");
 if(position==63)begin position=0;last_decoded=decoded;decoded=0;end else position=position+1;
end
always @(negedge clk)begin
 valid=0;
 if(rst&&request&&auto_response)begin
  if(hold||dut.source_guard!=0)$fatal(1,"request leaked while held");
  sample_seq=req_seq;sample_pcm={marker,marker^16'hffff};valid=1;
 end
 if(fv)begin
  if(pcm!==last_decoded)$fatal(1,"tap differs from full physical frame");
  if(have_seq&&seq!==last_seq+1)$fatal(1,"held schedule skipped sequence");
  have_seq=1;last_seq=seq;frames=frames+1;
  if(check_new)begin
   if(fe)begin if(pcm!==0)$fatal(1,"held error replayed PCM");zero_frames=zero_frames+1;end
   else begin if(pcm!==32'h3333cccc)$fatal(1,"old cache or late response revived");good_new=good_new+1;end
  end
 end
end
reg[31:0] current,saved_seq,old_rejected,late_seq;integer target;
initial begin
 for(integer mode=0;mode<2;mode=mode+1)begin
  rst=0;hold=0;check_new=0;auto_response=1;marker=16'h1111;rate=(mode==1);#23;rst=1;
  target=frames+5;wait(frames>=target);wait(dut.have_next&&dut.bit_position==8);
  @(negedge clk);#0.2;current=dut.current_pcm;saved_seq=dut.current_sequence;late_seq=dut.wanted_sequence;
  hold=1;auto_response=0;old_rejected=rejected;
  // The complete current frame may finish. The cached following frame cannot.
  wait(fv);#0.1;if(pcm!==current||seq!==saved_seq)$fatal(1,"source hold truncated current frame");
  @(negedge clk);#0.2;sample_seq=late_seq;sample_pcm=32'h2222dddd;valid=1;
  @(posedge clk);#0.1;@(negedge clk);#0.2;valid=0;
  if(rejected<=old_rejected)$fatal(1,"late response not discarded");
  check_new=1;target=frames+4;wait(frames>=target);wait(dut.bit_position==11);
  @(negedge clk);#0.2;hold=0;marker=16'h3333;auto_response=1;zero_frames=0;good_new=0;
  target=frames+8;wait(frames>=target);#1;
  if(zero_frames<3||good_new<3)$fatal(1,"guard/resume coverage zeros=%d good=%d",zero_frames,good_new);
  check_new=0;
 end
 $display("PASS both-rate I2S current-frame completion, cached/late discard, zero schedule and guarded resume");$finish;
end
initial begin #500000;$fatal(1,"timeout");end
endmodule''',['rtl/audio/workstation_i2s_serializer.sv'])
if __name__=='__main__':unittest.main()
