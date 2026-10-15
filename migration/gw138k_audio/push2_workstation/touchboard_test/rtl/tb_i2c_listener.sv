// Passive pad decoder: no connection to the master's FSM, data, or strobes.
// Each transaction includes address byte, payload, and every ACK/NACK bit.
module tb_i2c_listener #(parameter integer MAX_BYTES=65)(
    input wire clk,rst_n,scl,sda,
    output reg [MAX_BYTES*8-1:0] bytes_rise,bytes_late,
    output reg [MAX_BYTES-1:0] nack_bits,
    output reg [6:0] byte_count,
    output reg stopped,overflow,disagreement,
    output reg [31:0] start_gap
);
    reg scl_meta,scl_sync,scl_prev,sda_meta,sda_sync,sda_prev;
    reg active,high_last,clock_seen;
    reg [3:0] bit_count;
    reg [7:0] shift_rise,shift_late;
    reg [31:0] gap_ticks;
    wire rising=scl_sync && !scl_prev;
    wire falling=!scl_sync && scl_prev;
    wire start_seen=scl_sync && scl_prev && !sda_sync && sda_prev;
    wire stop_seen=scl_sync && scl_prev && sda_sync && !sda_prev;
    always @(posedge clk or negedge rst_n) begin
      if(!rst_n) begin
        scl_meta<=1; scl_sync<=1; scl_prev<=1;
        sda_meta<=1; sda_sync<=1; sda_prev<=1;
        active<=0; high_last<=1; clock_seen<=0; bit_count<=0;
        shift_rise<=0; shift_late<=0; gap_ticks<=0;
        bytes_rise<=0; bytes_late<=0; nack_bits<=0;
        byte_count<=0; stopped<=0; overflow<=0; disagreement<=0; start_gap<=0;
      end else begin
        scl_meta<=scl; scl_sync<=scl_meta; scl_prev<=scl_sync;
        sda_meta<=sda; sda_sync<=sda_meta; sda_prev<=sda_sync;
        if(scl_sync) high_last<=sda_sync;
        if(gap_ticks!=32'hffffffff) gap_ticks<=gap_ticks+1'b1;
        if(start_seen) begin
          active<=1; clock_seen<=0; bit_count<=0; shift_rise<=0; shift_late<=0;
          bytes_rise<=0; bytes_late<=0; nack_bits<=0;
          byte_count<=0; stopped<=0; overflow<=0; disagreement<=0;
          start_gap<=gap_ticks;
        end else if(stop_seen) begin
          active<=0; clock_seen<=0; stopped<=1; gap_ticks<=0;
        end else if(active) begin
          if(rising) begin
            clock_seen<=1;
            if(bit_count==8) begin
              if(byte_count<MAX_BYTES) begin
                bytes_rise[byte_count*8 +: 8]<=shift_rise;
                bytes_late[byte_count*8 +: 8]<=shift_late;
                nack_bits[byte_count]<=sda_sync;
                byte_count<=byte_count+1'b1;
              end else overflow<=1;
              if(shift_rise!=shift_late) disagreement<=1;
            end else shift_rise<={shift_rise[6:0],sda_sync};
          end
          if(falling && clock_seen) begin
            clock_seen<=0;
            if(bit_count==8) begin bit_count<=0; shift_rise<=0; shift_late<=0; end
            else begin bit_count<=bit_count+1'b1; shift_late<={shift_late[6:0],high_last}; end
          end
        end
      end
    end
endmodule
