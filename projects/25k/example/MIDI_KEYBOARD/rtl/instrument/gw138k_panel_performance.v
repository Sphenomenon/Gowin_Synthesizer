`timescale 1ns/1ps
`default_nettype none
// Confirmed 138K panel controls. USB/PL sessions do not generate synth defaults
// here: the 138K owns initialization. Queued targets never acquire a new link.
module gw138k_panel_performance #(
 parameter integer CONTROL_DEPTH=64,
 parameter integer BEND_DEAD_ZONE=3
)(
 input wire clk,reset,
 input wire [15:0] key_bitmap,input wire keypad_ready,
 input wire slider_valid,slider_touch,input wire [7:0] slider_position,
 input wire enc1_step,enc1_press,enc2_step,enc2_press,
 input wire signed [1:0] enc1_direction,enc2_direction,
 input wire config_write,input wire [7:0] config_opcode,input wire [31:0] config_value,
 input wire [1:0] online,input wire [12:0] timestamp_ms,
 output wire event_valid,input wire event_ready,
 output reg [23:0] event_message,output reg [1:0] event_length,
 output reg [12:0] event_timestamp,output wire [1:0] event_targets,
 output reg [3:0] midi_channel,output reg signed [7:0] transpose,
 output wire [6:0] velocity,output wire [1:0] slider_mode,
 output reg [6:0] program_number,output wire [7:0] brightness,
 output wire [2:0] focus,output reg [15:0] active_keys,
 output reg [7:0] strip_value,output wire panic_busy,output reg [31:0] emitted_events
);
 function integer width_for;
  input integer depth;integer remaining;
  begin remaining=depth-1;width_for=0;
   while(remaining>0)begin width_for=width_for+1;remaining=remaining>>1;end
   if(width_for<1)width_for=1;
  end
 endfunction
 localparam K_CONTROL=0,K_ON=1,K_OFF=2;
 localparam ADDRESS_BITS=width_for(CONTROL_DEPTH);
 localparam COUNT_BITS=width_for(CONTROL_DEPTH+1);
 localparam WRITE_PORTS=6;
`ifndef SYNTHESIS
 initial begin
  if(CONTROL_DEPTH<8 || (CONTROL_DEPTH & (CONTROL_DEPTH-1))!=0)
   $fatal(1,"CONTROL_DEPTH must be a power of two >= 8");
 end
`endif
 reg valid_slot;reg [1:0] targets,slot_kind;reg [3:0] slot_key;
 reg [6:0] held_note[0:15];reg [3:0] held_channel[0:15];reg [1:0] held_targets[0:15];
 reg [1:0] press_targets[0:15];
 reg [15:0] previous_keys;reg [1:0] previous_online;
 reg signed [7:0] applied_transpose;reg [3:0] applied_channel;
 reg [6:0] volume;reg [2:0] program_index;
 reg [13:0] bend_value;
 reg [13:0] bend_curve[0:255];
 integer curve_index;
 initial for(curve_index=0;curve_index<256;curve_index=curve_index+1)
  bend_curve[curve_index]=bend_at(curve_index[7:0]);
 reg bend_pending;
 reg [23:0] bend_pending_message;
 reg [1:0] bend_pending_targets;
 reg [12:0] bend_pending_timestamp;
 reg [ADDRESS_BITS-1:0] q_read,q_write,rd_next,wr_next;
 reg [COUNT_BITS-1:0] q_count,count_next;
 reg [WRITE_PORTS-1:0] store_valid;
 reg [WRITE_PORTS*ADDRESS_BITS-1:0] store_address;
 reg [WRITE_PORTS*32-1:0] store_payload;
 reg [WRITE_PORTS*2-1:0] store_targets;
 wire pop_control;
 wire [ADDRESS_BITS-1:0] next_read=reset ? {ADDRESS_BITS{1'b0}} :
  (pop_control ? q_read+1'b1 : q_read);
 wire [8*32-1:0] bank_heads;
 wire [8*2-1:0] bank_targets;
 reg head_stale;
 reg head_pending,next_head_written;
 integer pending_port;
 always @* begin
  head_pending=0;next_head_written=0;
  for(pending_port=0;pending_port<WRITE_PORTS;pending_port=pending_port+1)
   if(store_valid[pending_port])begin
    if(store_address[pending_port*ADDRESS_BITS+:ADDRESS_BITS]==q_read)head_pending=1;
    if(store_address[pending_port*ADDRESS_BITS+:ADDRESS_BITS]==next_read)next_head_written=1;
   end
 end
 always @(posedge clk)begin
  if(reset)head_stale<=0;else head_stale<=next_head_written;
 end
 genvar bank;
 generate for(bank=0;bank<8;bank=bank+1)begin:control_bank
  (* syn_ramstyle="block_ram" *) reg [31:0] payload[0:CONTROL_DEPTH/8-1];
  reg [31:0] read_payload;
  reg [1:0] target_masks[0:CONTROL_DEPTH/8-1];
  reg write_enable;
  reg [ADDRESS_BITS-1:0] write_row;
  reg [31:0] write_payload;
  reg [1:0] write_targets;
  integer port_index,mask_row;
  always @* begin
   write_enable=0;write_row=0;write_payload=0;write_targets=0;
   for(port_index=0;port_index<WRITE_PORTS;port_index=port_index+1)
    if(store_valid[port_index] && store_address[port_index*ADDRESS_BITS+:3]==bank)begin
     write_enable=1;
     write_row=write_row | (store_address[port_index*ADDRESS_BITS+:ADDRESS_BITS]>>3);
     write_payload=write_payload | store_payload[port_index*32+:32];
     write_targets=write_targets | store_targets[port_index*2+:2];
    end
  end
  always @(posedge clk)begin
   if(write_enable)payload[write_row]<=write_payload;
   read_payload<=payload[next_read>>3];
  end
  always @(posedge clk)begin
   for(mask_row=0;mask_row<CONTROL_DEPTH/8;mask_row=mask_row+1)
    if(reset)target_masks[mask_row]<=0;
    else if(write_enable && write_row==mask_row)target_masks[mask_row]<=write_targets & online;
    else target_masks[mask_row]<=target_masks[mask_row] & online;
  end
  assign bank_heads[bank*32+:32]=read_payload;
  assign bank_targets[bank*2+:2]=target_masks[q_read>>3];
 end endgenerate
 reg [31:0] control_head;
 reg [1:0] control_head_targets;
 integer head_bank;
 always @* begin
  control_head=0;control_head_targets=0;
  for(head_bank=0;head_bank<8;head_bank=head_bank+1)
   if(q_read[2:0]==head_bank)begin
    control_head=control_head | bank_heads[head_bank*32+:32];
    control_head_targets=control_head_targets | bank_targets[head_bank*2+:2];
   end
 end
 // Kept visible for offline fault assertions; not a new protocol field.
 reg [31:0] control_overflows;
 integer i,k,mapped;reg found;reg [3:0] selected;reg [15:0] desired;
 wire retuning=transpose!=applied_transpose || midi_channel!=applied_channel;
 assign pop_control=!valid_slot && !found && !(retuning && active_keys==0) &&
  q_count!=0 && !head_pending && !head_stale;
 wire session_change=online!=previous_online;
 wire [1:0] input_targets=online & previous_online;
 wire [13:0] requested_bend=slider_touch ? bend_curve[slider_position] : 14'd8192;
 assign velocity=7'd100;assign slider_mode=2'd2;assign brightness=8'd96;assign focus=0;
 assign panic_busy=retuning;
 assign event_targets=targets & online;
 assign event_valid=valid_slot && |event_targets;
 function [6:0] program_at;
  input [2:0] index;
  begin case(index)0:program_at=73;1:program_at=40;2:program_at=56;3:program_at=12;default:program_at=0;endcase end
 endfunction
 function [13:0] bend_at;
  input [7:0] position;
  integer v;
  begin
   if(position<128-BEND_DEAD_ZONE)v=(8192*position)/(128-BEND_DEAD_ZONE);
   else if(position>128+BEND_DEAD_ZONE)v=8192+(8191*(position-128-BEND_DEAD_ZONE))/(127-BEND_DEAD_ZONE);
   else v=8192;
   bend_at=v;
  end
 endfunction
 task enqueue_to;
  input [2:0] write_port;
  input [23:0] message;input [1:0] length;
  input [1:0] mask;input [12:0] stamp;
  reg [14:0] code;
  begin
`ifndef SYNTHESIS
   if(!message[23] || message[15] || message[7] || !length[1])
    $fatal(1,"Control queue requires MIDI status, seven-bit data and length 2 or 3");
   if(message[23:20]!=4'he && message[23:20]!=4'hb && message[23:20]!=4'hc)
    $fatal(1,"Unsupported queued MIDI status");
   if(message[23:20]==4'hb && message[15:8]!=7 && message[15:8]!=88 && message[15:8]!=89)
    $fatal(1,"Unsupported queued CC number");
   if(length!=(message[23:20]==4'hc ? 2 : 3) || (message[23:20]==4'hc && message[7:0]!=0))
    $fatal(1,"Queued MIDI length or Program Change padding mismatch");
`endif
   if(message[23:20]==4'he)code={1'b0,message[14:8],message[6:0]};
   else if(message[23:20]==4'hb)code={2'b10,message[13:8],message[6:0]};
   else code={2'b11,message[14:8],6'd0};
   if(count_next<CONTROL_DEPTH)begin
    store_valid[write_port]<=1;
    store_address[write_port*ADDRESS_BITS+:ADDRESS_BITS]<=wr_next;
    store_payload[write_port*32+:32]<={stamp,message[19:16],code};
    store_targets[write_port*2+:2]<=mask;
    wr_next=wr_next+1'b1;count_next=count_next+1'b1;
   end else control_overflows<=control_overflows+1'b1;
  end
 endtask
 task enqueue;
  input [2:0] write_port;
  input [23:0] message;input [1:0] length;
  begin enqueue_to(write_port,message,length,input_targets,timestamp_ms);end
 endtask
 always @* begin
  desired=0;
  for(i=0;i<16;i=i+1)
   desired[i]=keypad_ready && key_bitmap[i] && |(press_targets[i] & online);
  if(retuning)desired=0;
  found=0;selected=0;
  for(i=15;i>=0;i=i-1)if(active_keys[i] && !desired[i])begin found=1;selected=i;end
  if(!found && !retuning && online!=0)
   for(i=15;i>=0;i=i-1)if(desired[i] && !active_keys[i])begin found=1;selected=i;end
  mapped=48+selected+$signed(applied_transpose);
 end
 always @(posedge clk)begin
  if(reset)begin
   midi_channel<=0;transpose<=0;applied_channel<=0;applied_transpose<=0;
   volume<=127;program_index<=0;program_number<=73;strip_value<=128;bend_value<=8192;
   valid_slot<=0;targets<=0;slot_kind<=0;slot_key<=0;
   event_message<=0;event_length<=0;event_timestamp<=0;emitted_events<=0;
   active_keys<=0;previous_keys<=0;previous_online<=0;
   bend_pending<=0;bend_pending_message<=0;bend_pending_targets<=0;bend_pending_timestamp<=0;
   q_read<=0;q_write<=0;q_count<=0;control_overflows<=0;
   store_valid<=0;
   for(k=0;k<16;k=k+1)begin held_note[k]<=0;held_channel[k]<=0;held_targets[k]<=0;press_targets[k]<=0;end
  end else begin
   previous_online<=online;targets<=targets & online;
   store_valid<=0;
   previous_keys<=keypad_ready ? key_bitmap : 16'd0;
   if(slider_valid)strip_value<=slider_touch ? slider_position : 8'd128;
   rd_next=q_read;wr_next=q_write;count_next=q_count;
   // Invalidate only ended targets, including queued beats. Joining BLE must
   // not discard USB controls or inherit notes/controls from the USB session.
   for(k=0;k<16;k=k+1)begin
    held_targets[k]<=held_targets[k] & online;
    if(!keypad_ready || !key_bitmap[k])press_targets[k]<=0;
    else if(!previous_keys[k])press_targets[k]<=input_targets;
    else press_targets[k]<=press_targets[k] & online;
    if(active_keys[k] && (held_targets[k] & online)==0)active_keys[k]<=0;
   end
   if(valid_slot && (event_ready || event_targets==0))begin
    valid_slot<=0;
    if(event_targets!=0)begin
     emitted_events<=emitted_events+1'b1;
     if(slot_kind==K_ON)begin
      active_keys[slot_key]<=1;held_note[slot_key]<=event_message[14:8];
      held_channel[slot_key]<=event_message[19:16];held_targets[slot_key]<=event_targets;
     end else if(slot_kind==K_OFF)begin active_keys[slot_key]<=0;held_targets[slot_key]<=0;end
    end
   end
   // One stable output slot, releases before new notes, all old offs before
   // any transposed ons. No control can rewrite a stalled event payload.
   if(!valid_slot)begin
    if(found)begin
     slot_key<=selected;event_length<=3;event_timestamp<=timestamp_ms;
     if(active_keys[selected])begin
      event_message<={{4'h8,held_channel[selected]},1'b0,held_note[selected],8'd0};
      targets<=held_targets[selected] & online;slot_kind<=K_OFF;valid_slot<=1;
     end else if(mapped>=0 && mapped<=127)begin
      event_message<={{4'h9,applied_channel},1'b0,mapped[6:0],8'd100};
      targets<=press_targets[selected] & online;slot_kind<=K_ON;valid_slot<=1;
     end
    end else if(retuning && active_keys==0)begin
     applied_channel<=midi_channel;applied_transpose<=transpose;
    end else if(pop_control)begin
     if(!control_head[14])
      event_message<={4'he,control_head[18:15],1'b0,control_head[13:7],1'b0,control_head[6:0]};
     else if(!control_head[13])
      event_message<={4'hb,control_head[18:15],1'b0,control_head[11],control_head[12:7],1'b0,control_head[6:0]};
     else event_message<={4'hc,control_head[18:15],1'b0,control_head[12:6],8'd0};
     event_length<=control_head[14:13]==2'b11 ? 2'd2 : 2'd3;
     event_timestamp<=control_head[31:19];targets<=control_head_targets & online;
     slot_kind<=K_CONTROL;valid_slot<=1;
     rd_next=rd_next+1'b1;count_next=count_next-1'b1;
    end
   end
   bend_pending_targets<=bend_pending_targets & online;
   if(bend_pending)begin
    if((bend_pending_targets & online)==0)bend_pending<=0;
    else if(count_next<CONTROL_DEPTH)begin
     enqueue_to(0,bend_pending_message,3,bend_pending_targets & online,bend_pending_timestamp);
     bend_pending<=0;
    end
   end
   if(config_write)begin
    if(config_opcode==8'h10)midi_channel<=config_value[3:0];
    if(config_opcode==8'h11)transpose<=config_value[7:0];
   end
   if(input_targets!=0)begin
    if(enc1_step && enc1_direction>0 && volume<127)begin
     volume<=volume+1'b1;enqueue(1,{4'hb,midi_channel,8'd7,1'b0,volume+7'd1},3);
    end else if(enc1_step && enc1_direction<0 && volume>0)begin
     volume<=volume-1'b1;enqueue(1,{4'hb,midi_channel,8'd7,1'b0,volume-7'd1},3);
    end
    if(enc1_press)enqueue(2,{4'hb,midi_channel,8'd89,8'd1},3);
    if(enc2_step && enc2_direction!=0)begin
     if(enc2_direction>0)begin
      program_index<=program_index==4 ? 0 : program_index+1'b1;
      program_number<=program_at(program_index==4 ? 0 : program_index+3'd1);
      enqueue(3,{4'hc,midi_channel,1'b0,program_at(program_index==4 ? 0 : program_index+3'd1),8'd0},2);
     end else begin
      program_index<=program_index==0 ? 4 : program_index-1'b1;
      program_number<=program_at(program_index==0 ? 4 : program_index-3'd1);
      enqueue(3,{4'hc,midi_channel,1'b0,program_at(program_index==0 ? 4 : program_index-3'd1),8'd0},2);
     end
    end
    if(enc2_press)enqueue(4,{4'hb,midi_channel,8'd88,8'd127},3);
    if(slider_valid)begin
     if(requested_bend!=bend_value)begin
      bend_value<=requested_bend;
      if(count_next<CONTROL_DEPTH)
       enqueue(5,{4'he,midi_channel,1'b0,requested_bend[6:0],1'b0,requested_bend[13:7]},3);
      else begin
       bend_pending<=1;bend_pending_targets<=input_targets;bend_pending_timestamp<=timestamp_ms;
       bend_pending_message<={4'he,midi_channel,1'b0,requested_bend[6:0],1'b0,requested_bend[13:7]};
      end
     end
    end
   end
   if(session_change)begin
    if(slot_kind==K_CONTROL && (targets & online)==0)valid_slot<=0;
    if(online[0] && !previous_online[0])begin
     volume<=127;program_index<=0;program_number<=73;bend_value<=8192;
    end
   end
   q_read<=rd_next;q_write<=wr_next;q_count<=count_next;
  end
 end
endmodule
`default_nettype wire
