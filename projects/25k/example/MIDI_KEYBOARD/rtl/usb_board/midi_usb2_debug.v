`timescale 1ns/1ps
`default_nettype none
module midi_usb2_debug #(
 parameter integer WINDOW_CYCLES=50000,
 parameter integer SNAPSHOT_CYCLES=50000,
 parameter integer COUNTER_BITS=16
)(
 input wire clk_50mhz,clk_ulpi60,
 input wire[31:0]source_status,local_snapshot,
 input wire[2:0]local_flags,
 output wire[31:0]status_50mhz
);
 reg[COUNTER_BITS-1:0]ulpi_counter=0;
 reg[7:0]ulpi_gray=0;
 wire[COUNTER_BITS-1:0]ulpi_next=ulpi_counter+1'b1;
 wire[7:0]divided_next=ulpi_next[COUNTER_BITS-1:COUNTER_BITS-8];
 always @(posedge clk_ulpi60)begin
  ulpi_counter<=ulpi_next;
  ulpi_gray<=(divided_next>>1)^divided_next;
 end
 (* ASYNC_REG="TRUE" *)reg[7:0]gray_meta=0,gray_sync=0;
 function[7:0]gray_to_binary;
  input[7:0]gray;
  integer bit_index;
  begin
   gray_to_binary[7]=gray[7];
   for(bit_index=6;bit_index>=0;bit_index=bit_index-1)
    gray_to_binary[bit_index]=gray_to_binary[bit_index+1]^gray[bit_index];
  end
 endfunction
 wire[7:0]binary_count=gray_to_binary(gray_sync);
 reg[15:0]window_timer=0,snapshot_timer=0;
 reg[7:0]window_count=0,previous_count=0;
 reg request_toggle=0,acknowledge=0;
 (* ASYNC_REG="TRUE" *)reg request_meta=0,request_sync=0;
 reg[31:0]snapshot_hold=0;
 always @(posedge clk_ulpi60)begin
  request_meta<=request_toggle;
  request_sync<=request_meta;
  if(request_sync!=acknowledge)begin
   snapshot_hold<=source_status;
   acknowledge<=request_sync;
  end
 end
 (* ASYNC_REG="TRUE" *)reg ack_meta=0,ack_sync=0;
 reg ack_settled=0,waiting=0,cohort=0;
 reg[63:0]snapshot_50=0;
 reg[2:0]flags_50=0;
 reg[4:0]phase=0;
 reg heartbeat=0;
 always @(posedge clk_50mhz)begin
  gray_meta<=ulpi_gray;
  gray_sync<=gray_meta;
  ack_meta<=acknowledge;
  ack_sync<=ack_meta;
  ack_settled<=ack_sync;
  phase<=phase+1'b1;
  heartbeat<=!heartbeat;
  if(window_timer==WINDOW_CYCLES-1)begin
   window_timer<=0;
   window_count<=binary_count-previous_count;
   previous_count<=binary_count;
  end else window_timer<=window_timer+1'b1;
  if(snapshot_timer==SNAPSHOT_CYCLES-1)begin
   snapshot_timer<=0;
   if(!waiting)begin
    request_toggle<=!request_toggle;
    waiting<=1;
   end
  end else snapshot_timer<=snapshot_timer+1'b1;
  if(waiting&&ack_settled==request_toggle&&phase==31)begin
   snapshot_50<={snapshot_hold,local_snapshot};
   flags_50<=local_flags;
   cohort<=!cohort;
   waiting<=0;
  end
 end
 wire[23:0]payload=phase[4:3]==0?snapshot_50[55:32]:
  phase[4:3]==1?{snapshot_50[63:56],snapshot_50[31:16]}:
  phase[4:3]==2?{snapshot_50[15:0],window_count}:24'h55aa33;
 assign status_50mhz={payload,phase[4:3],flags_50,(window_count!=0),cohort,heartbeat};
endmodule
`default_nettype wire
