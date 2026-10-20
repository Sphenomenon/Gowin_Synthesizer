`timescale 1ns/1ps
module tb_scope_event_ab;
`ifdef SCOPE_NETLIST
  GSR GSR(.GSRI(1'b1));
`endif
  reg clk=0; always #5 clk=~clk;
  reg rst=0,panic=0,ce=0,ev=0,on=0;
  reg [6:0] note=0,vel=100;
  reg [2:0] shape=0,mshape=1,profile=0;
  reg [21:0] pitch=1048576;
  wire r0,r1,v0,v1,e0,e1,b0,b1;
  wire signed [31:0] x0,x1,y0,y1;
  wire [7:0] a0,a1;
  wire [3:0] c0,c1;
  wire [31:0] rej0,rej1;
  wire cfg0,cfg1,freq0,freq1,clip0,clip1;
  scope_vec_engine dut(.clk_i(clk),.rst_ni(rst),.panic_i(panic),.sample_ce_i(ce),
    .sample_ready_o(r0),.sample_valid_o(v0),.left_o(x0),.right_o(y0),
    .event_valid_i(ev),.event_note_on_i(on),.event_ready_o(e0),.event_note_i(note),.event_velocity_i(vel),
    .event_shape_i(shape),.event_morph_shape_i(mshape),.event_profile_i(profile),.event_pitch_q20_i(pitch),
    .pitch_q20_i(22'd1048576),.morph_q15_i(16'd12345),.scale_q15_i(16'd16384),.rotation_i(7'd41),
    .cal_x_q14_i(16'sd16384),.cal_y_q14_i(16'sd16384),.offset_x_i(32'sd17),.offset_y_i(-32'sd13),
    .active_mask_o(a0),.active_count_o(c0),.rejected_events_o(rej0),.config_error_o(cfg0),
    .frequency_error_o(freq0),.clip_o(clip0),.busy_o(b0));
  scope_vec_engine_reference old(.clk_i(clk),.rst_ni(rst),.panic_i(panic),.sample_ce_i(ce),
    .sample_ready_o(r1),.sample_valid_o(v1),.left_o(x1),.right_o(y1),
    .event_valid_i(ev),.event_note_on_i(on),.event_ready_o(e1),.event_note_i(note),.event_velocity_i(vel),
    .event_shape_i(shape),.event_morph_shape_i(mshape),.event_profile_i(profile),.event_pitch_q20_i(pitch),
    .pitch_q20_i(22'd1048576),.morph_q15_i(16'd12345),.scale_q15_i(16'd16384),.rotation_i(7'd41),
    .cal_x_q14_i(16'sd16384),.cal_y_q14_i(16'sd16384),.offset_x_i(32'sd17),.offset_y_i(-32'sd13),
    .active_mask_o(a1),.active_count_o(c1),.rejected_events_o(rej1),.config_error_o(cfg1),
    .frequency_error_o(freq1),.clip_o(clip1),.busy_o(b1));
  integer samples=0,events=0,cycles=0;
`ifndef SCOPE_NETLIST
  for(genvar k=0;k<8;k=k+1) begin: compare_voices
    always @(negedge clk) if(rst) begin
      if({dut.phase[k],dut.base_step[k],dut.own_pitch[k],dut.note[k],dut.shape[k],dut.morph_shape[k],
          dut.env_state[k],dut.envelope[k],dut.attack[k],dut.decay[k],dut.sustain[k],dut.release_step[k],dut.velocity[k]}
         !=={old.phase[k],old.base_step[k],old.own_pitch[k],old.note[k],old.shape[k],old.morph_shape[k],
          old.env_state[k],old.envelope[k],old.attack[k],old.decay[k],old.sustain[k],old.release_step[k],old.velocity[k]})
        $fatal(1,"voice mismatch cycle=%0d voice=%0d",cycles,k);
    end
  end
`endif
  always @(negedge clk) if(rst) begin
    cycles++;
    if({r0,v0,x0,y0,e0,b0,a0,c0,rej0,cfg0,freq0,clip0}!=={r1,v1,x1,y1,e1,b1,a1,c1,rej1,cfg1,freq1,clip1})
      $fatal(1,"output mismatch cycle=%0d",cycles);
  end
  // Observe accepted inputs before sequential updates; stimulus changes only
  // on the falling edge. This is deterministic in both Verilator and Icarus.
  always @(posedge clk) if(rst) begin
    if(v0) samples++;
    if(ev&&e0) events++;
  end
  task event_send(input bit is_on,input integer n,input integer velocity,input integer prof);
    @(negedge clk);ev=0;ce=0;
    while(!e0) @(negedge clk);
    on=is_on;note=7'(n);vel=7'(velocity);profile=3'(prof);ev=1;
    @(negedge clk);ev=0;
  endtask
  task sample;
    @(negedge clk);while(!r0) @(negedge clk);ce=1;
    @(negedge clk);ce=0;
    while(!v0) @(negedge clk);
  endtask
  task clear;
    @(negedge clk);panic=1;ev=0;ce=0;
    @(negedge clk);panic=0;
  endtask
  initial begin
    repeat(4) @(negedge clk);rst=1;
    // Every note, velocity boundary and profile: validity must match the ROM.
    for(integer n=0;n<128;n++) begin
      clear();event_send(1,n,n%2 ? 127 : 1,n%5);sample();
      event_send(0,n,0,0);sample();
    end
    for(integer t=0;t<80;t++) begin
      clear();
      // Duplicate notes/full pool exercise the original lowest-index priority.
      for(integer k=0;k<12;k++) event_send(1,48+k%4,100,k%5);
      sample();
      for(integer k=0;k<8;k++) begin event_send(0,48+k%4,0,0);sample();end
      for(integer k=0;k<10;k++) begin
        event_send(1,40+(t+k)%44,k%3 ? 100:0,k%8);sample();
      end
    end
    repeat(2) @(negedge clk);
    if(samples!=1776 || events!=2656) $fatal(1,"incorrect coverage %0d %0d",samples,events);
`ifdef SCOPE_NETLIST
    $display("PASS scope_event_ab: %0d cycles, %0d events, %0d stereo frames, synthesized outputs exact",cycles,events,samples);
`else
    $display("PASS scope_event_ab: %0d cycles, %0d events, %0d stereo frames, all voice states exact",cycles,events,samples);
`endif
    $finish;
  end
  initial begin #200000000;$fatal(1,"timeout");end
endmodule
