`timescale 1ns/1ps
`default_nettype none
module midi_ble_usb_bridge(
 input wire clk,reset,usb_online,ble_online,
 input wire local_valid,output wire local_ready,input wire [23:0] local_message,input wire [1:0] local_length,
 input wire phone_valid,output wire phone_ready,input wire [23:0] phone_message,input wire [1:0] phone_length,
 output wire out_valid,input wire out_ready,output wire [23:0] out_message,output wire [1:0] out_length
);
 localparam [2:0] CLEAR=0,IDLE=1,NOTE_READ=2,NOTE_WRITE=3,PEDAL=4,CLEAN_READ=5,SCAN=6;
 reg [2:0] state;
 reg [7:0] held_notes[0:255] /* synthesis syn_ramstyle="block_ram" */;
 reg [7:0] held_word,clear_address,clear_last,note_address,clean_address;
 reg [2:0] note_bit,clean_bit;
 reg note_value,discard_rx,cleanup_pending,previous_ble;
 reg [15:0] sustain;
 reg [3:0] clean_channel;
 reg pending_valid;
 reg [23:0] pending_message;
 reg [1:0] pending_length;
 reg prefer_phone,locked,locked_phone;
 wire [7:0] read_address=(state==NOTE_READ || state==NOTE_WRITE) ? note_address : clean_address;
 wire cleanup_valid=(state==PEDAL && sustain[clean_channel]) || (state==SCAN && held_word[clean_bit]);
 wire bridge_valid=pending_valid || cleanup_valid;
 wire select_phone=locked ? locked_phone : bridge_valid && (!local_valid || prefer_phone);
 wire [23:0] bridge_message=pending_valid ? pending_message : state==PEDAL ?
  {4'hb,clean_channel,8'd64,8'd0} : {4'h8,clean_address[7:4],1'b0,clean_address[3:0],clean_bit,8'd0};
 assign out_valid=!reset && usb_online && (select_phone ? bridge_valid : local_valid);
 assign out_message=select_phone ? bridge_message : local_message;
 assign out_length=select_phone ? (pending_valid ? pending_length : 2'd3) : local_length;
 assign local_ready=!reset && usb_online && !select_phone && out_ready;
 assign phone_ready=!reset && (!usb_online || (state==CLEAR && discard_rx) ||
  (usb_online && ble_online && state==IDLE && !pending_valid && !cleanup_pending));
 wire bridge_accept=out_valid && out_ready && select_phone;
 wire scan_done=state==SCAN && clean_bit==7 && (!held_word[7] || bridge_accept);
 always @(posedge clk)begin
  held_word<=held_notes[read_address];
  if(state==CLEAR)held_notes[clear_address]<=0;
  else if(state==NOTE_WRITE)held_notes[note_address]<=note_value ?
   held_word | (8'b1<<note_bit) : held_word & ~(8'b1<<note_bit);
  else if(scan_done)held_notes[clean_address]<=0;
 end
 always @(posedge clk)begin
  if(reset || !usb_online)begin
   state<=CLEAR;clear_address<=0;clear_last<=255;discard_rx<=1;
   sustain<=0;cleanup_pending<=0;previous_ble<=ble_online;
   pending_valid<=0;pending_message<=0;pending_length<=0;
   note_address<=0;note_bit<=0;note_value<=0;clean_address<=0;clean_bit<=0;clean_channel<=0;
   prefer_phone<=1;locked<=0;locked_phone<=0;
  end else begin
   previous_ble<=ble_online;
   if(previous_ble && !ble_online)cleanup_pending<=1;
   if(out_valid && !out_ready)begin locked<=1;locked_phone<=select_phone;end
   else if(out_ready)begin
    locked<=0;
    if(out_valid)prefer_phone<=!select_phone;
   end
   if(phone_valid && phone_ready && state==IDLE)begin
    pending_valid<=1;pending_message<=phone_message;pending_length<=phone_length;
   end
   case(state)
    CLEAR:begin
     if(clear_address==clear_last)begin state<=IDLE;discard_rx<=0;end
     else clear_address<=clear_address+1'b1;
    end
    IDLE:begin
     if(pending_valid && bridge_accept)begin
      pending_valid<=0;
      if(pending_message[23:20]==8 || pending_message[23:20]==9)begin
       note_address<={pending_message[19:16],pending_message[14:11]};
       note_bit<=pending_message[10:8];
       note_value<=pending_message[23:20]==9 && pending_message[6:0]!=0;
       state<=NOTE_READ;
      end else if(pending_message[23:20]==11)begin
       case(pending_message[15:8])
        64:sustain[pending_message[19:16]]<=pending_message[6];
        121:sustain[pending_message[19:16]]<=0;
        120,123:begin
         clear_address<={pending_message[19:16],4'd0};clear_last<={pending_message[19:16],4'hf};
         discard_rx<=0;state<=CLEAR;
        end
        default:begin end
       endcase
      end else if(pending_message[23:16]==8'hff)begin
       clear_address<=0;clear_last<=255;discard_rx<=0;sustain<=0;state<=CLEAR;
      end
     end else if(cleanup_pending && !pending_valid)begin state<=PEDAL;clean_channel<=0;end
    end
    NOTE_READ:state<=NOTE_WRITE;
    NOTE_WRITE:state<=IDLE;
    PEDAL:if(!sustain[clean_channel] || bridge_accept)begin
     sustain[clean_channel]<=0;
     if(clean_channel==15)begin state<=CLEAN_READ;clean_address<=0;end
     else clean_channel<=clean_channel+1'b1;
    end
    CLEAN_READ:begin state<=SCAN;clean_bit<=0;end
    SCAN:if(!held_word[clean_bit] || bridge_accept)begin
     if(clean_bit==7)begin
      if(clean_address==255)begin state<=IDLE;cleanup_pending<=0;end
      else begin clean_address<=clean_address+1'b1;state<=CLEAN_READ;end
     end else clean_bit<=clean_bit+1'b1;
    end
    default:begin state<=CLEAR;clear_address<=0;clear_last<=255;discard_rx<=1;end
   endcase
  end
 end
endmodule
`default_nettype wire
