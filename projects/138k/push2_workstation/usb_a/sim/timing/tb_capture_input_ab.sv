`timescale 1ns/1ps
module tb_capture_input_ab;
 reg sc=0,rc=0,rn=0,valid=0;always #5 sc=~sc;always #7 rc=~rc;
 reg [31:0] sample=0,reference=0,voices=0,status=0;
 reg vd=0;reg [31:0] sd=0,td=0,ad=0,hd=0;
 always @(posedge sc or negedge rn)
  if(!rn)begin vd<=0;sd<=0;td<=0;ad<=0;hd<=0;end
  else begin vd<=valid;sd<=sample;td<=reference;ad<=voices;hd<=status;end
 reg release_block=0;reg [4:0] addr=0;
 always @(negedge rc)begin addr<=addr+1'b1;release_block<=addr[2:0]==3;end
 for(genvar smooth=0;smooth<2;smooth=smooth+1)begin:g
  wire ar,br;wire [31:0] ap,av,ast,aq,ask,arev,adout,bp,bv,bst,bq,bsk,brev,bdout;
  feedback_capture #(.INPUT_REGISTERED(1),.SMOOTH_TRIGGER(smooth),.TRIGGER_TIMEOUT_SAMPLES(7),.CAPTURE_SAMPLES(32)) dut(
    .source_clk(sc),.source_reset_n(rn),.sample_data(sample),.sample_valid(valid),.trigger_reference(reference),.active_voices(voices),.status_data(status),
    .render_clk(rc),.render_reset_n(rn),.snapshot_ready(ar),.snapshot_release(release_block),.snapshot_peak(ap),.snapshot_voices(av),.snapshot_status(ast),
    .snapshot_sequence(aq),.snapshot_skipped(ask),.snapshot_revision(arev),.wave_read_enable(1'b1),.wave_read_addr(addr),.wave_read_data(adout));
  feedback_capture_reference #(.SMOOTH_TRIGGER(smooth),.TRIGGER_TIMEOUT_SAMPLES(7),.CAPTURE_SAMPLES(32)) original(
    .source_clk(sc),.source_reset_n(rn),.sample_data(sd),.sample_valid(vd),.trigger_reference(td),.active_voices(ad),.status_data(hd),
    .render_clk(rc),.render_reset_n(rn),.snapshot_ready(br),.snapshot_release(release_block),.snapshot_peak(bp),.snapshot_voices(bv),.snapshot_status(bst),
    .snapshot_sequence(bq),.snapshot_skipped(bsk),.snapshot_revision(brev),.wave_read_enable(1'b1),.wave_read_addr(addr),.wave_read_data(bdout));
  integer checks=0,blocks=0;
  always @(posedge sc)begin
   #1;if(rn)begin
    if({dut.capture_peak,dut.capture_voices,dut.capture_status,dut.write_index,dut.write_bank,dut.block_complete,dut.trigger_wait,dut.trigger_armed,dut.capturing,dut.capture_revision} !==
       {original.capture_peak,original.capture_voices,original.capture_status,original.write_index,original.write_bank,original.block_complete,original.trigger_wait,original.trigger_armed,original.capturing,original.capture_revision})$fatal(1,"capture state mismatch smooth%0d",smooth);
    for(integer i=0;i<64;i=i+1)if(dut.samples[i] !== original.samples[i])$fatal(1,"capture RAM mismatch smooth%0d addr%0d",smooth,i);
    checks=checks+1;
   end
  end
  always @(posedge rc)begin
   #1;if(rn)begin
    if({ar,ap,av,ast,aq,ask,arev,adout} !== {br,bp,bv,bst,bq,bsk,brev,bdout})$fatal(1,"capture publication mismatch smooth%0d",smooth);
    if(ar && release_block)blocks=blocks+1;
   end
  end
 end
 reg [31:0] random_state=32'ha53ce701;
 initial begin
  repeat(4)@(negedge sc);rn=1;
  for(integer cycle=0;cycle<30000;cycle=cycle+1)begin
   @(negedge sc);random_state=random_state*32'd1664525+32'd1013904223;
   valid=(cycle%17)<12;sample=random_state;
   if(cycle%53==0)sample=32'h80000000;
   if(cycle%59==0)sample=32'h7fffffff;
   if(cycle%61==0)sample=0;
   reference={24'(cycle/173),6'd0,cycle%11==0,cycle%7==0};
   voices=cycle%61==0?0:random_state^32'h73ab5713;status=random_state^cycle;
   if(cycle==10000 || cycle==20000)rn=0;
   if(cycle==10004 || cycle==20004)rn=1;
  end
  valid=0;repeat(30)@(negedge sc);
  if(g[0].checks<29000 || g[1].checks<29000 || g[0].blocks<10 || g[1].blocks<10)$fatal(1,"insufficient capture coverage");
  $display("PASS capture_input_ab: cycles=%0d/%0d snapshots=%0d/%0d, exact banks/peaks/metadata, raw and six-pole triggers, one-cycle input pipeline, resets",g[0].checks,g[1].checks,g[0].blocks,g[1].blocks);$finish;
 end
 initial begin #1000000;$fatal(1,"timeout");end
endmodule
