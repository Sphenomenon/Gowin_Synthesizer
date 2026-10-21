`timescale 1ns/1ps
// The existing PC cable remains a 115200-baud MIDI input until it receives the
// private non-commercial SysEx F0 7D "P30UPLOAD" F7.  Only then does this block
// own the pins and switch to a raw 3-Mbaud, CRC-protected PCM upload session.
module music_upload_uart #(
    parameter integer CLOCK_HZ=50000000,
    parameter integer LEGACY_BAUD=115200,
    parameter integer UPLOAD_BAUD=3000000,
    parameter integer EXIT_DELAY_CYCLES=250000
)(
    input  logic clk_i,
    input  logic rst_ni,
    input  logic serial_rx_i,
    input  logic runtime_tx_i,
    output logic serial_tx_o,
    output logic legacy_rx_o,
    output logic upload_mode_o,
    output logic beat_valid_o,
    input  logic beat_ready_i,
    output logic [20:0] beat_index_o,
    output logic [255:0] beat_data_o,
    output logic [31:0] beat_keep_o,
    output logic header_valid_o,
    output logic complete_o,
    output logic [31:0] payload_bytes_o,
    output logic [31:0] frame_count_o,
    output logic [31:0] payload_crc32_o,
    output logic [31:0] committed_bytes_o,
    output logic [31:0] error_count_o
);
    localparam integer LEGACY_BIT_CYCLES=(CLOCK_HZ+LEGACY_BAUD/2)/LEGACY_BAUD;
    localparam integer UPLOAD_BIT_CYCLES=(CLOCK_HZ+UPLOAD_BAUD/2)/UPLOAD_BAUD;

    logic slow_valid,slow_error,fast_valid,fast_error;
    logic [7:0] slow_data,fast_data;
    logic begin_session;
    music_uart_rx #(.BIT_CYCLES(LEGACY_BIT_CYCLES)) u_slow_rx(
        .clk_i,.rst_ni,.enable_i(!upload_mode_o),.serial_i(serial_rx_i),
        .valid_o(slow_valid),.data_o(slow_data),.framing_error_o(slow_error));
    music_uart_rx #(.BIT_CYCLES(UPLOAD_BIT_CYCLES)) u_fast_rx(
        .clk_i,.rst_ni,.enable_i(upload_mode_o),.serial_i(serial_rx_i),
        .valid_o(fast_valid),.data_o(fast_data),.framing_error_o(fast_error));

    // Exact activation sequence.  A mismatch can itself be a new F0 so the
    // matcher immediately re-arms without leaking state between messages.
    logic [3:0] activation_index;
    function automatic [7:0] activation_byte(input logic [3:0] index);
        case(index)
            0:activation_byte=8'hf0; 1:activation_byte=8'h7d;
            2:activation_byte="P";   3:activation_byte="3";
            4:activation_byte="0";   5:activation_byte="U";
            6:activation_byte="P";   7:activation_byte="L";
            8:activation_byte="O";   9:activation_byte="A";
            10:activation_byte="D";  default:activation_byte=8'hf7;
        endcase
    endfunction

    logic parser_response_valid,parser_response_ready;
    logic [7:0] parser_response_code;
    logic [31:0] parser_response_value;
    music_upload_parser u_parser(
        .clk_i,.rst_ni,.begin_session_i(begin_session),
        .byte_valid_i(fast_valid),.byte_i(fast_data),
        .beat_valid_o,.beat_ready_i,.beat_index_o,.beat_data_o,.beat_keep_o,
        .response_valid_o(parser_response_valid),.response_ready_i(parser_response_ready),
        .response_code_o(parser_response_code),.response_value_o(parser_response_value),
        .header_valid_o,.complete_o,.payload_bytes_o,.frame_count_o,.payload_crc32_o,
        .committed_bytes_o,.error_count_o);

    // Responses are: 'R','3','0', code, value[31:0] little endian, CRC16-CCITT
    // little endian.  response_ready is delayed until the final stop bit.
    logic [79:0] response_frame;
    logic [3:0] response_index;
    logic response_active,tx_valid,tx_ready,tx_done;
    logic [7:0] tx_data;
    logic [31:0] exit_count;
    logic exit_after_response;
    logic fast_tx;

    function automatic [15:0] crc16_byte(input [15:0] prior,input [7:0] data);
        reg [15:0] value;integer bit_number;
        begin
            value=prior^{data,8'd0};
            for(bit_number=0;bit_number<8;bit_number=bit_number+1)
                value=value[15] ? (value<<1)^16'h1021 : value<<1;
            crc16_byte=value;
        end
    endfunction
    function automatic [15:0] response_crc(input [7:0] code,input [31:0] value);
        reg [15:0] crc;
        begin
            crc=16'hffff;
            crc=crc16_byte(crc,"R");crc=crc16_byte(crc,"3");crc=crc16_byte(crc,"0");
            crc=crc16_byte(crc,code);
            crc=crc16_byte(crc,value[7:0]);crc=crc16_byte(crc,value[15:8]);
            crc=crc16_byte(crc,value[23:16]);crc=crc16_byte(crc,value[31:24]);
            response_crc=crc;
        end
    endfunction

    music_uart_tx #(.BIT_CYCLES(UPLOAD_BIT_CYCLES)) u_fast_tx(
        .clk_i,.rst_ni,.valid_i(tx_valid),.data_i(tx_data),.ready_o(tx_ready),
        .serial_o(fast_tx),.byte_done_o(tx_done));

    assign legacy_rx_o=upload_mode_o ? 1'b1 : serial_rx_i;
    assign serial_tx_o=upload_mode_o ? fast_tx : runtime_tx_i;
    // byte_done is registered for one cycle after ready rises.  Suppress the
    // ready handshake in that cycle so response_index can advance first.
    assign tx_valid=response_active && tx_ready && !tx_done;
    assign tx_data=response_frame[response_index*8+:8];
    assign parser_response_ready=response_active && tx_done && response_index==9;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni)begin
            upload_mode_o<=0;activation_index<=0;begin_session<=0;
            response_frame<=0;response_index<=0;response_active<=0;
            exit_count<=0;exit_after_response<=0;
        end else begin
            begin_session<=0;
            if(!upload_mode_o && slow_valid)begin
                if(slow_data==activation_byte(activation_index))begin
                    if(activation_index==11)begin
                        upload_mode_o<=1;begin_session<=1;activation_index<=0;
                    end else activation_index<=activation_index+1'b1;
                end else activation_index<=slow_data==8'hf0 ? 4'd1 : 4'd0;
            end
            if(upload_mode_o && parser_response_valid && !response_active && exit_count==0)begin
                response_frame[7:0]<="R";response_frame[15:8]<="3";response_frame[23:16]<="0";
                response_frame[31:24]<=parser_response_code;
                response_frame[63:32]<=parser_response_value;
                response_frame[79:64]<=response_crc(parser_response_code,parser_response_value);
                response_index<=0;response_active<=1;
                exit_after_response<=parser_response_code==8'h12;
            end
            if(response_active && tx_done)begin
                if(response_index==9)begin
                    response_active<=0;response_index<=0;
                    if(exit_after_response)begin exit_count<=EXIT_DELAY_CYCLES;exit_after_response<=0;end
                end else response_index<=response_index+1'b1;
            end
            if(exit_count!=0)begin
                exit_count<=exit_count-1'b1;
                if(exit_count==1)upload_mode_o<=0;
            end
        end
    end
    // Framing errors intentionally affect only the current receiver byte. CRCs
    // and absolute offsets turn any lost upload byte into a retryable packet.
    wire unused_errors=slow_error^fast_error;
endmodule

module music_uart_rx #(parameter integer BIT_CYCLES=10)(
    input logic clk_i,rst_ni,enable_i,serial_i,
    output logic valid_o,output logic [7:0] data_o,output logic framing_error_o
);
    localparam integer TIMER_BITS=BIT_CYCLES<=1 ? 1 : $clog2(BIT_CYCLES);
    logic rx_meta,rx_sync;logic [1:0] state;logic [TIMER_BITS-1:0] timer;
    logic [2:0] bit_index;logic [7:0] shift;
    always_ff @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin rx_meta<=1;rx_sync<=1;end
        else begin rx_meta<=serial_i;rx_sync<=rx_meta;end
    end
    always_ff @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin state<=0;timer<=0;bit_index<=0;shift<=0;valid_o<=0;data_o<=0;framing_error_o<=0;end
        else begin
            valid_o<=0;framing_error_o<=0;
            if(!enable_i)begin state<=0;timer<=0;end
            else case(state)
                0:if(!rx_sync)begin timer<=BIT_CYCLES/2-1;state<=1;end
                1:if(timer!=0)timer<=timer-1'b1;else if(rx_sync)state<=0;
                  else begin timer<=BIT_CYCLES-1;bit_index<=0;state<=2;end
                2:if(timer!=0)timer<=timer-1'b1;else begin
                    shift[bit_index]<=rx_sync;timer<=BIT_CYCLES-1;
                    if(bit_index==7)state<=3;else bit_index<=bit_index+1'b1;
                end
                3:if(timer!=0)timer<=timer-1'b1;else begin
                    data_o<=shift;valid_o<=rx_sync;framing_error_o<=!rx_sync;state<=0;
                end
                default:state<=0;
            endcase
        end
    end
endmodule

module music_uart_tx #(parameter integer BIT_CYCLES=10)(
    input logic clk_i,rst_ni,valid_i,input logic [7:0] data_i,
    output logic ready_o,serial_o,byte_done_o
);
    localparam integer TIMER_BITS=BIT_CYCLES<=1 ? 1 : $clog2(BIT_CYCLES);
    logic busy;logic [9:0] shift;logic [3:0] bit_index;logic [TIMER_BITS-1:0] timer;
    assign ready_o=!busy;
    always_ff @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin busy<=0;shift<=10'h3ff;bit_index<=0;timer<=0;serial_o<=1;byte_done_o<=0;end
        else begin
            byte_done_o<=0;
            if(!busy)begin
                serial_o<=1;
                if(valid_i)begin
                    shift<={1'b1,data_i,1'b0};serial_o<=0;bit_index<=0;timer<=BIT_CYCLES-1;busy<=1;
                end
            end else if(timer!=0)timer<=timer-1'b1;
            else if(bit_index==9)begin busy<=0;serial_o<=1;byte_done_o<=1;end
            else begin
                shift<={1'b1,shift[9:1]};serial_o<=shift[1];
                bit_index<=bit_index+1'b1;timer<=BIT_CYCLES-1;
            end
        end
    end
endmodule
