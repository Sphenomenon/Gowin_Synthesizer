`timescale 1ns/1ps
`default_nettype none
// First-party SD data integrity checker. No SPI command or transport owner.
// SD SPI data: init=0, polynomial=0x1021, MSB first, no final XOR.
// The native session presents payload indexes 513..2, then CRC indexes 1/0.
module workstation_tf_sd_crc16_v1 (
    input wire clk_i,rst_ni,clear_i,
    input wire byte_valid_i,
    input wire [15:0] byte_index_i,
    input wire [7:0] byte_i,
    output reg complete_o,valid_o
);
    reg [15:0] payload_crc;
    reg [7:0] crc_high;
    reg [9:0] expected_index;
    reg order_error;
    function automatic [15:0] next_crc(input [15:0] previous,input [7:0] data);
        reg [15:0] value;
        integer bitno;
        begin
            value=previous;
            for(bitno=7;bitno>=0;bitno=bitno-1)
                value={value[14:0],1'b0} ^ ((value[15]^data[bitno]) ? 16'h1021 : 16'h0000);
            next_crc=value;
        end
    endfunction
    always @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni) begin
            payload_crc<=0;crc_high<=0;expected_index<=10'd513;
            order_error<=0;complete_o<=0;valid_o<=0;
        end else if(clear_i) begin
            payload_crc<=0;crc_high<=0;expected_index<=10'd513;
            order_error<=0;complete_o<=0;valid_o<=0;
        end else if(byte_valid_i) begin
            if(complete_o || byte_index_i!={6'd0,expected_index}) begin
                order_error<=1;valid_o<=0;
            end
            if(byte_index_i>=16'd2 && byte_index_i<=16'd513)
                payload_crc<=next_crc(payload_crc,byte_i);
            else if(byte_index_i==16'd1) crc_high<=byte_i;
            else if(byte_index_i==16'd0) begin
                complete_o<=1;
                valid_o<=!complete_o && !order_error && expected_index==0 &&
                         {crc_high,byte_i}==payload_crc;
            end
            if(expected_index!=0) expected_index<=expected_index-1'b1;
        end
    end
endmodule
`default_nettype wire
