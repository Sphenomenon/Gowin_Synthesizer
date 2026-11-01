`timescale 1ns/1ps
`default_nettype none
module midi_touch_key_filter #(
 parameter integer NEGATIVE_THRESHOLD=12,
 parameter integer CHANNELS=16
)(
 input wire [CHANNELS-1:0] before_keys,after_keys,previous_keys,
 input wire [CHANNELS*16-1:0] signals,references,
 output wire [CHANNELS-1:0] filtered_keys
);
 localparam integer PRESS_LEVEL=NEGATIVE_THRESHOLD;
 localparam integer RELEASE_LEVEL=NEGATIVE_THRESHOLD>2 ? NEGATIVE_THRESHOLD-2 : 1;
 genvar channel;
 generate for(channel=0;channel<CHANNELS;channel=channel+1)begin:key_filter
  wire [16:0] difference={1'b0,references[channel*16+:16]}-{1'b0,signals[channel*16+:16]};
  assign filtered_keys[channel]=before_keys[channel] && after_keys[channel] && !difference[16] &&
    difference[15:0]>=(previous_keys[channel] ? RELEASE_LEVEL : PRESS_LEVEL);
 end endgenerate
endmodule
`default_nettype wire
