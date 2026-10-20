`timescale 1ns/1ps
// Downloaded score stores LED cues only, never pre-recorded sound. The sample
// counter is the timebase: cue data={absolute_frame[31:0], key_mask[31:0]}.
module score_led_player (
    input logic clk_i,rst_ni,sample_ce_i,
    input logic write_i,input logic[7:0] write_address_i,input logic[63:0] write_data_i,
    input logic start_i,stop_i,input logic[8:0] length_i,
    output logic running_o,done_o,
    output logic[31:0] leds_o,frame_o
);
  wire [63:0] cue;
  logic[7:0] read_address;
  logic[8:0] length;
  logic[1:0] state;
  for(genvar bank=0;bank<2;bank=bank+1) begin : g_cue_sdp
    workstation_sdp #(.ADDR_WIDTH(8)) ram(
      .write_clk_i(clk_i),.write_enable_i(write_i && !running_o),.write_addr_i(write_address_i),
      .write_data_i(write_data_i[bank*32+:32]),.read_clk_i(clk_i),
      .read_enable_i(1'b1),.read_addr_i(read_address),.read_data_o(cue[bank*32+:32]));
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      running_o<=0;done_o<=0;leds_o<=0;frame_o<=0;length<=0;state<=0;read_address<=0;
    end else begin
      done_o<=0;
      if(start_i && !running_o && length_i>0 && length_i<=256) begin
        running_o<=1;frame_o<=0;read_address<=0;length<=length_i;state<=1;leds_o<=0;
      end else if(stop_i) begin running_o<=0;leds_o<=0;state<=0;end
      else if(running_o) begin
        if(sample_ce_i) frame_o<=frame_o+1;
        if(state==1) state<=2;
        else if(state==2) state<=3;
        else if(state==3 && cue[63:32]<=frame_o) begin
          leds_o<=cue[31:0];
          if({1'b0,read_address}+1>=length) begin running_o<=0;done_o<=1;state<=0;end
          else begin read_address<=read_address+1'b1;state<=1;end
        end
      end
    end
  end
endmodule
