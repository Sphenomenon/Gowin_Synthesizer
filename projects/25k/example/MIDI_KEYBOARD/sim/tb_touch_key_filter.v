`timescale 1ns/1ps
module tb_touch_key_filter;
 reg [15:0] before_keys=0,after_keys=0,previous_keys=0;
 reg [255:0] signals=0,references=0;
 wire [15:0] filtered_keys[0:3];
 reg [31:0] random_state=32'h2160b203;
 integer sample_number,channel;
 genvar threshold_index;
 generate for(threshold_index=0;threshold_index<4;threshold_index=threshold_index+1)begin:thresholds
  localparam integer THRESHOLD=threshold_index==0 ? 1 : threshold_index==1 ? 2 : threshold_index==2 ? 12 : 65535;
  localparam integer RELEASE=THRESHOLD>2 ? THRESHOLD-2 : 1;
  reg [15:0] expected;
  integer key_index;
  midi_touch_key_filter #(.NEGATIVE_THRESHOLD(THRESHOLD)) dut(
   .before_keys(before_keys),.after_keys(after_keys),.previous_keys(previous_keys),
   .signals(signals),.references(references),.filtered_keys(filtered_keys[threshold_index]));
  always @* begin
   for(key_index=0;key_index<16;key_index=key_index+1)
    expected[key_index]=before_keys[key_index] && after_keys[key_index] &&
      references[key_index*16+:16]>=signals[key_index*16+:16] &&
      ({1'b0,references[key_index*16+:16]}-{1'b0,signals[key_index*16+:16]})>=
        (previous_keys[key_index] ? RELEASE : THRESHOLD);
  end
  always @(sample_number)begin
   #1;if(filtered_keys[threshold_index]!==expected)$fatal(1,"Touch signed-difference equivalence failed threshold=%0d",THRESHOLD);
  end
 end endgenerate
 initial begin
  for(sample_number=0;sample_number<100000;sample_number=sample_number+1)begin
   for(channel=0;channel<16;channel=channel+1)begin
    random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
    signals[channel*16+:16]=random_state[15:0];references[channel*16+:16]=random_state[31:16];
   end
   if(sample_number<256)begin
    signals={16{16'h8000}};references={16{16'h7f80+sample_number[15:0]}};
   end
   if(sample_number==256)begin signals=0;references={16{16'hffff}};end
   if(sample_number==257)begin signals={16{16'hffff}};references=0;end
   before_keys=sample_number<258 ? 16'hffff : random_state[15:0];
   after_keys=sample_number<258 ? 16'hffff : random_state[31:16];
   previous_keys=sample_number[0] ? 16'haaaa : 16'h5555;
   #2;
  end
  $display("PASS tb_touch_key_filter 6400000 key/threshold cases, exact new/held hysteresis, unsigned extremes and negative rejection");
  $finish;
 end
endmodule
