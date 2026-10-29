`timescale 1ns/1ps
module tb_usb_board_debug;
 reg clk50=0,clk60=0,run_phy=0,streaming=0;
 always #10 clk50=!clk50;
 always #8.333 if(run_phy)clk60=!clk60;
 reg[15:0]sample_sequence=1;
 wire[31:0]source_status={sample_sequence,~sample_sequence};
 reg[31:0]local_snapshot=32'h12345678;
 reg[2:0]local_flags=3'b111;
 wire[31:0]status;
 midi_usb2_debug #(.WINDOW_CYCLES(100),.SNAPSHOT_CYCLES(10),.COUNTER_BITS(8)) dut(
  .clk_50mhz(clk50),.clk_ulpi60(clk60),.source_status(source_status),
  .local_snapshot(local_snapshot),.local_flags(local_flags),.status_50mhz(status));
 always @(posedge clk60)if(streaming)sample_sequence<=sample_sequence+1'b1;
 integer checks=0,commit_count=0;
 reg[63:0]previous_snapshot=0;
 always @(negedge clk50)begin
  if(dut.snapshot_50!=previous_snapshot)begin
   checks=checks+1;
   commit_count=commit_count+1;
   if(status[7:6]!=0)$fatal(1,"snapshot changed during a page rotation");
   if(dut.snapshot_50[63:48]!=~dut.snapshot_50[47:32])
    $fatal(1,"incoherent source mailbox");
   if(dut.snapshot_50[31:0]!=local_snapshot)$fatal(1,"wrong local snapshot");
  end
  if(status[7:6]==3 && status[31:8]!=24'h55aa33)$fatal(1,"wrong stream marker");
  previous_snapshot=dut.snapshot_50;
 end
 reg[31:0]stopped_status;
 reg[63:0]held_snapshot;
 initial begin
  repeat(350)@(negedge clk50);
  checks=checks+1;
  if(dut.window_count!=0 || status[2] || dut.snapshot_50!=0)
   $fatal(1,"stopped PHY invented a clock or source snapshot");
  stopped_status=status;
  @(negedge clk50);
  checks=checks+1;
  if(status[0]==stopped_status[0])$fatal(1,"independent heartbeat stopped");
  run_phy=1;
  repeat(400)@(negedge clk50);
  checks=checks+1;
  if(dut.window_count<118 || dut.window_count>122 || !status[2])
   $fatal(1,"incorrect native clock rate: %0d",dut.window_count);
  if(dut.snapshot_50!={source_status,local_snapshot} || status[5:3]!=local_flags)
   $fatal(1,"source/local state not published");
  streaming=1;
  repeat(500)@(negedge clk50);
  checks=checks+1;
  if(commit_count<10)$fatal(1,"mailbox stress did not update enough");
  streaming=0;
  repeat(70)@(negedge clk50);
  @(negedge clk60);run_phy=0;
  repeat(350)@(negedge clk50);
  held_snapshot=dut.snapshot_50;
  checks=checks+1;
  if(dut.window_count!=0 || status[2])$fatal(1,"lost clock remained alive");
  sample_sequence=16'hdead;
  repeat(100)@(negedge clk50);
  checks=checks+1;
  if(dut.snapshot_50!=held_snapshot)$fatal(1,"missing source clock published stale acknowledgement");
  run_phy=1;
  repeat(200)@(negedge clk50);
  checks=checks+1;
  if(dut.snapshot_50!={source_status,local_snapshot} || !status[2])
   $fatal(1,"source did not recover after clock restart");
  $display("PASS USB2 independent debug: %0d checks, %0d coherent commits, stopped/running/restarted clocks and full MIDI counts",checks,commit_count);
  $finish;
 end
 initial begin #1000000;$fatal(1,"debug timeout");end
endmodule
