`timescale 1ns/1ps
module tb_scope_tf_transport;
 reg clk=0,rst_n=0,valid=0,song=0,ready=1,lost=0;
 reg [31:0] control=0;
 reg [3:0] song_track=0;
 reg [4:0] count=4;
 wire mode,run,restart,cancel,error;
 wire [3:0] track;
 integer starts=0,cancels=0;
 always #10 clk=~clk;
 scope_tf_transport dut(.clk_i(clk),.rst_ni(rst_n),.control_valid_i(valid),.control_i(control),
  .song_valid_i(song),.song_track_i(song_track),.playlist_ready_i(ready),.card_lost_i(lost),.track_count_i(count),
  .mode_o(mode),.run_o(run),.track_o(track),.restart_o(restart),.cancel_analysis_o(cancel),.error_o(error));
 always @(posedge clk) begin if(restart) starts<=starts+1;if(cancel)cancels<=cancels+1;end
 task publish(input integer epoch,index,action,input bit m,r);
  @(negedge clk);control={16'(epoch),2'b00,r,m,4'(index),2'(action),6'd0};valid=1;
  @(negedge clk);valid=0;@(negedge clk);
 endtask
 task select_song(input integer index);
  song_track=4'(index);song=1;@(negedge clk);song=0;@(negedge clk);
 endtask
 initial begin
  repeat(4) @(negedge clk);rst_n=1;
  publish(1,0,0,1,1);if(!mode || !run || track!=0 || starts!=1 || cancels!=1)$fatal(1,"enter without model");
  publish(1,0,0,1,1);if(starts!=1)$fatal(1,"periodic held state retriggered restart");
  publish(1,0,0,1,0);if(run || track!=0 || starts!=1)$fatal(1,"pause position");
  publish(1,0,0,1,1);if(!run || starts!=1)$fatal(1,"resume position");
  select_song(2);if(track!=2 || starts!=2)$fatal(1,"TF song-menu launch");
  publish(2,0,3,1,1);if(track!=2 || starts!=3)$fatal(1,"restart reverted to stale absolute index");
  publish(3,0,1,1,1);if(track!=3 || starts!=4)$fatal(1,"next did not use selected menu track");
  publish(4,0,1,1,1);if(track!=3 || starts!=4 || !error || run)$fatal(1,"actual playlist upper bound");
  publish(5,0,2,1,1);if(track!=2 || error || !run || starts!=5)$fatal(1,"recover previous");
  publish(6,0,0,1,1);if(track!=0 || starts!=6)$fatal(1,"absolute select");
  publish(7,0,2,1,1);if(track!=0 || !error || starts!=6)$fatal(1,"previous underflow");
  publish(8,1,0,1,1);if(error || track!=1 || starts!=7)$fatal(1,"valid select clears error");
  ready=0;lost=1;@(negedge clk);lost=0;@(negedge clk);if(run)$fatal(1,"card loss stale audio");
  publish(8,1,0,1,1);if(run || starts!=7)$fatal(1,"missing card restarted");
  ready=1;repeat(3) @(negedge clk);if(!run || track!=1 || starts!=8)$fatal(1,"same-track hotplug recovery");
  publish(8,1,0,0,0);if(mode || run || cancels!=2)$fatal(1,"exit must clear NN partial capture");
  select_song(3);if(track!=1 || starts!=8)$fatal(1,"non-TF menu intercepted");
  ready=0;publish(9,2,0,1,1);if(run || track!=2)$fatal(1,"enter awaiting scan");
  ready=1;count=1;repeat(3) @(negedge clk);if(run || !error || starts!=8)$fatal(1,"recovered playlist missing selected track");
  count=4;publish(10,1,0,1,1);if(track!=1 || error || !run || starts!=9)$fatal(1,"rearm after changed directory");
  publish(12,0,1,1,1);if(track!=1 || !error || run || starts!=9)$fatal(1,"coalesced relative commands must fail explicitly");
  publish(13,0,3,1,1);if(track!=1 || error || !run || starts!=10)$fatal(1,"restart recovers coalesced command error");
  $display("M scope_transport_assertions 21");$display("M scope_transport_restarts %0d",starts);
  $display("PASS scope_tf_transport");$finish;
 end
 initial begin #100000;$fatal(1,"timeout");end
endmodule
