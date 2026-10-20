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
 localparam K_CONTROL=0,K_ON=1,K_OFF=2;
 reg valid_slot;reg [1:0] targets,slot_kind;reg [3:0] slot_key;
 reg [6:0] held_note[0:15];reg [3:0] held_channel[0:15];reg [1:0] held_targets[0:15];
 reg [15:0] blocked_keys;reg [1:0] previous_online;
 reg signed [7:0] applied_transpose;reg [3:0] applied_channel;
 reg [6:0] volume;reg [2:0] program_index;
 reg [13:0] bend_value;
 reg [23:0] control_message[0:CONTROL_DEPTH-1];
 reg [1:0] control_length[0:CONTROL_DEPTH-1],control_targets[0:CONTROL_DEPTH-1];
 reg [12:0] control_timestamp[0:CONTROL_DEPTH-1];
 integer q_read,q_write,q_count,rd_next,wr_next,count_next;
 // Kept visible for offline fault assertions; not a new protocol field.
 reg [31:0] control_overflows;
 integer i,k,mapped;reg found;reg [3:0] selected;reg [15:0] desired;
 wire retuning=transpose!=applied_transpose || midi_channel!=applied_channel;
 wire session_change=online!=previous_online;
 wire [13:0] requested_bend=slider_touch ? bend_at(slider_position) : 14'd8192;
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
 task enqueue;
  input [23:0] message;input [1:0] length;
  begin
   if(count_next<CONTROL_DEPTH)begin
    control_message[wr_next]<=message;control_length[wr_next]<=length;
    control_targets[wr_next]<=online;control_timestamp[wr_next]<=timestamp_ms;
    wr_next=wr_next==CONTROL_DEPTH-1 ? 0 : wr_next+1;count_next=count_next+1;
   end else control_overflows<=control_overflows+1'b1;
  end
 endtask
 always @* begin
  // A held key on a surviving link remains owned by that link. A newly
  // connected link cannot gain that note until the key is lifted/re-pressed.
  desired=keypad_ready ? key_bitmap & ~(blocked_keys & ~active_keys) : 16'd0;
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
   active_keys<=0;blocked_keys<=0;previous_online<=0;
   q_read<=0;q_write<=0;q_count<=0;control_overflows<=0;
   for(k=0;k<16;k=k+1)begin held_note[k]<=0;held_channel[k]<=0;held_targets[k]<=0;end
   for(k=0;k<CONTROL_DEPTH;k=k+1)control_targets[k]<=0;
  end else begin
   previous_online<=online;targets<=targets & online;
   blocked_keys<=blocked_keys & key_bitmap;
   rd_next=q_read;wr_next=q_write;count_next=q_count;
   // Invalidate only ended targets, including queued beats. Joining BLE must
   // not discard USB controls or inherit notes/controls from the USB session.
   for(k=0;k<CONTROL_DEPTH;k=k+1)control_targets[k]<=control_targets[k] & online;
   for(k=0;k<16;k=k+1)begin
    held_targets[k]<=held_targets[k] & online;
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
      targets<=online;slot_kind<=K_ON;valid_slot<=1;
     end
    end else if(retuning && active_keys==0)begin
     applied_channel<=midi_channel;applied_transpose<=transpose;
    end else if(q_count!=0)begin
     event_message<=control_message[q_read];event_length<=control_length[q_read];
     event_timestamp<=control_timestamp[q_read];targets<=control_targets[q_read] & online;
     slot_kind<=K_CONTROL;valid_slot<=1;
     rd_next=rd_next==CONTROL_DEPTH-1 ? 0 : rd_next+1;count_next=count_next-1;
    end
   end
   if(config_write)begin
    if(config_opcode==8'h10)midi_channel<=config_value[3:0];
    if(config_opcode==8'h11)transpose<=config_value[7:0];
   end
   if(online!=0 && !session_change)begin
    if(enc1_step && enc1_direction>0 && volume<127)begin
     volume<=volume+1'b1;enqueue({4'hb,midi_channel,8'd7,1'b0,volume+7'd1},3);
    end else if(enc1_step && enc1_direction<0 && volume>0)begin
     volume<=volume-1'b1;enqueue({4'hb,midi_channel,8'd7,1'b0,volume-7'd1},3);
    end
    if(enc1_press)enqueue({4'hb,midi_channel,8'd89,8'd1},3);
    if(enc2_step && enc2_direction!=0)begin
     if(enc2_direction>0)begin
      program_index<=program_index==4 ? 0 : program_index+1'b1;
      program_number<=program_at(program_index==4 ? 0 : program_index+3'd1);
      enqueue({4'hc,midi_channel,1'b0,program_at(program_index==4 ? 0 : program_index+3'd1),8'd0},2);
     end else begin
      program_index<=program_index==0 ? 4 : program_index-1'b1;
      program_number<=program_at(program_index==0 ? 4 : program_index-3'd1);
      enqueue({4'hc,midi_channel,1'b0,program_at(program_index==0 ? 4 : program_index-3'd1),8'd0},2);
     end
    end
    if(enc2_press)enqueue({4'hb,midi_channel,8'd88,8'd127},3);
    if(slider_valid)begin
     strip_value<=slider_touch ? slider_position : 8'd128;
     if(requested_bend!=bend_value)begin
      bend_value<=requested_bend;
      enqueue({4'he,midi_channel,1'b0,requested_bend[6:0],1'b0,requested_bend[13:7]},3);
     end
    end
   end
   if(session_change)begin
    if(slot_kind==K_CONTROL && (targets & online)==0)valid_slot<=0;
    blocked_keys<=key_bitmap;
    if(online[0] && !previous_online[0])begin
     volume<=127;program_index<=0;program_number<=73;strip_value<=128;bend_value<=8192;
    end
   end else if(online==0)blocked_keys<=key_bitmap;
   q_read<=rd_next;q_write<=wr_next;q_count<=count_next;
  end
 end
endmodule
`default_nettype wire
