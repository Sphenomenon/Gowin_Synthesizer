`timescale 1ns/1ps
// Bottom-left 4x4=instrument pads; top row columns0..3=groups A..D;
// top-right4x4=pattern-per-pad. Capture press mapping until release/pressure.
module sampler_push(
  input logic clk,rst_n,panic,input logic in_valid,output logic in_ready,
  input logic [17:0] in_event,
  output logic out_valid,input logic out_ready,output logic [17:0] out_event,
  output logic pattern_valid,output logic [3:0] pattern,
  output logic [1:0] group_select
);
  logic [6:0] held_key[64];logic [63:0] held;
  integer pad,row,col,slot;logic [3:0] kind;logic [6:0] note,value;
  assign in_ready=!out_valid || out_ready;
  always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin out_valid<=0;out_event<=0;pattern_valid<=0;pattern<=0;group_select<=0;held<=0;
      for(int i=0;i<64;i++) held_key[i]<=0;end
    else begin
      pattern_valid<=0;if(out_valid && out_ready) out_valid<=0;
      if(in_valid && in_ready) begin
        kind=in_event[17:14];note=in_event[13:7];value=in_event[6:0];
        if(note>=36 && note<=99 && (kind==0 || kind==1 || kind==5)) begin
          pad=int'(note)-36;row=pad/8;col=pad%8;
          if(held[pad] && (kind==0 || kind==5 || (kind==1 && value==0))) begin
            out_valid<=1;out_event<={kind,held_key[pad],value};if(kind!=5) held[pad]<=0;
          end else if(row==7 && col<4 && kind==1 && value!=0) group_select<=2'(col);
          else if(row>=4 && col>=4 && kind==1 && value!=0) begin pattern_valid<=1;pattern<=4'((row-4)*4+col-4);end
          else if(row<4 && col<4 && kind==1 && value!=0) begin
            slot=int'(group_select)*16+row*4+col;
            held_key[pad]<=7'(36+slot);held[pad]<=1;out_valid<=1;out_event<={4'd1,7'(36+slot),value};
          end
        end else begin out_valid<=1;out_event<=in_event;end
      end
      if(panic) begin held<=0;out_valid<=0;pattern_valid<=0;end
    end
  end
endmodule
