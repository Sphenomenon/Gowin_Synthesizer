`timescale 1ns/1ps
module tb_effect_queue;
reg clk=0,rst=0,valid=0;
always #5 clk=~clk;
reg [6:0] a=0,b=0;
reg [10:0] sample_div=0;
wire tick=sample_div==1599;
wire sample_valid;
reg frame_start=0;
always @(posedge clk) if(!rst) sample_div<=0; else sample_div<=tick ? 0 : sample_div+1'b1;
wire ready,ev,er;
wire [17:0] event_data;
wire [2:0] mask;
wire [5:0] order;
wire [31:0] applied;
push2_controls push(.clk(clk),.rst(!rst),.connected(1'b1),.valid(valid),.ready(ready),.kind(4'd11),.cable(4'd0),.channel(4'd0),.a(a),.b(b),
 .actual_control({29'd0,mask}),.actual_options(32'd0),.event_valid(ev),.event_ready(er),.event_data(event_data));
gw138k_event_workstation dut(.clk_i(clk),.rst_ni(rst),.midi_byte_valid_i(1'b0),.midi_byte_i(8'd0),.pc_byte_valid_i(1'b0),.pc_byte_i(8'd0),
 .cpu_event_valid_i(ev),.cpu_event_i(event_data),.cpu_event_ready_o(er),.sample_ce_i(tick),.sample_valid_o(sample_valid),.pcm_left_i(32'd0),.pcm_right_i(32'd0),
 .effect_mask_o(mask),.effect_order_o(order),.applied_events_o(applied));
feedback_dashboard #(.ENABLE_ANALYSIS(1)) display(.clk(clk),.reset_n(rst),.enable(1'b1),.frame_start(frame_start),
 .pixel_x(11'd0),.pixel_y(11'd0),.effect_mask(mask),.effect_order(order),.wave_sample(32'd0),.wave_previous(32'd0),
 .waveform_held(1'b0),.peak_data(32'd0),.active_voices(32'd0),.status_data(32'd0),.spectrum_left(8'd0),.spectrum_right(8'd0),
 .image_hit(1'b0),.peak_left(16'd0),.peak_right(16'd0),.image_gain(3'd0),.analysis_sequence(32'd0),.analysis_skipped(32'd0),
 .sequence_data(32'd0),.skipped_data(32'd0),.memory_status(32'd3),.underruns(32'd0),.framecount(32'd0));
integer count=0;
task audio_frames(input integer n);
 begin repeat(n) begin @(posedge sample_valid);@(negedge clk);end end
endtask
task display_frames;
 begin repeat(52) begin @(negedge clk);frame_start=1;@(negedge clk);frame_start=0;end end
endtask
task send(input integer id, velocity);
 begin
  @(negedge clk);a=7'(20+id);b=7'(velocity);valid=1;
  do @(posedge clk);while(!ready);
  @(negedge clk);valid=0;repeat(12) @(posedge clk);
 end
endtask
task press(input integer id);
 begin send(id,127);send(id,0);count++;wait(applied==count);@(negedge clk);end
endtask
task check(input [2:0] m,input [5:0] o,input integer slots);
 begin if(mask!==m || order!==o || dut.effect_count!=slots)$fatal(1,"queue mask=%h order=%h slots=%0d wanted %h %h %0d",mask,order,dut.effect_count,m,o,slots);end
endtask
initial begin
 #12;rst=1;repeat(20) @(posedge clk);
 for(integer i=0;i<3;i++) for(integer j=0;j<3;j++) if(i!=j) for(integer clear_id=0;clear_id<3;clear_id++) begin
  automatic integer k=3-i-j;
  press(i);check(3'(1<<i),{4'b1111,2'(i)},1);
  repeat(3) begin press(i);check(3'(1<<i),{4'b1111,2'(i)},1);end
  press(j);check(3'((1<<i)|(1<<j)),{2'b11,2'(j),2'(i)},2);
  press(i);press(j);check(3'((1<<i)|(1<<j)),{2'b11,2'(j),2'(i)},2);
  press(k);check(7,{2'(k),2'(j),2'(i)},3);
  audio_frames(70);
  if(dut.effects.delay_stage.gain!=8192 || dut.effects.chorus_stage.gain!=8192 || dut.effects.reverb_stage.gain!=8192)
    $fatal(1,"effects never enabled");
  display_frames();
  if(display.effect_x0==1120 || display.effect_x1==1120 || display.effect_x2==1120) $fatal(1,"missing selected card");
  // Hold the fourth press and send repeated MIDI value 127. It must clear
  // once, stay empty, and never append that effect until released/repressed.
  send(clear_id,127);count++;wait(applied==count);@(negedge clk);check(0,6'b11_11_11,0);
  repeat(3) begin send(clear_id,127);check(0,6'b11_11_11,0);end
  send(clear_id,0);
  if(applied!=count)$fatal(1,"held clear key created extra events");
  audio_frames(70);
  if(dut.effects.delay_stage.gain || dut.effects.chorus_stage.gain || dut.effects.reverb_stage.gain)
    $fatal(1,"all-off left an audible effect gain enabled");
  display_frames();
  if(display.effect_x0!=1120 || display.effect_x1!=1120 || display.effect_x2!=1120 || display.visible_mask!=0) $fatal(1,"clear left a visible card");
 end
 press(2);check(4,6'b11_11_10,1);
 $display("PASS 6 permutations x 3 clearing keys: full -> empty, held clear stays empty, next press starts one card, duplicates unchanged, actual wet gains zero, all three cards exit; %0d presses",count);$finish;
end
initial begin #100000000;$fatal(1,"timeout");end
endmodule
