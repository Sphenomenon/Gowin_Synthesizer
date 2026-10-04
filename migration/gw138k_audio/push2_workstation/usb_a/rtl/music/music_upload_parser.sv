`timescale 1ns/1ps
// Byte protocol -> aligned 256-bit DDR beats.  Every DATA packet carries its
// own CRC32 and absolute payload offset.  A rejected retry overwrites the same
// DDR range; committed_offset advances only after CRC and enqueue success.
module music_upload_parser #(
    parameter integer MAX_PACKET_BYTES=16384
) (
    input  logic clk_i,
    input  logic rst_ni,
    input  logic begin_session_i,
    input  logic byte_valid_i,
    input  logic [7:0] byte_i,
    output logic beat_valid_o,
    input  logic beat_ready_i,
    output logic [20:0] beat_index_o,
    output logic [255:0] beat_data_o,
    output logic [31:0] beat_keep_o,
    output logic response_valid_o,
    input  logic response_ready_i,
    output logic [7:0] response_code_o,
    output logic [31:0] response_value_o,
    output logic header_valid_o,
    output logic complete_o,
    output logic [31:0] payload_bytes_o,
    output logic [31:0] frame_count_o,
    output logic [31:0] payload_crc32_o,
    output logic [31:0] committed_bytes_o,
    output logic [31:0] error_count_o
);
    localparam [3:0] FIND_MAGIC=0,READ_ARGUMENTS=1,READ_DATA=2,DRAIN_DATA=3,
        SEND_RESPONSE=4,COMPLETE=5;
    localparam [1:0] COMMAND_HEADER=0,COMMAND_DATA=1,COMMAND_END=2;
    localparam [7:0] ACK_HEADER=8'h10,ACK_DATA=8'h11,ACK_END=8'h12,
        ERROR_HEADER=8'h81,ERROR_SEQUENCE=8'h82,
        ERROR_PACKET_CRC=8'h83,ERROR_OVERFLOW=8'h84,ERROR_FINAL=8'h85;
    localparam [31:0] MAGIC_HEADER=32'h3053554d; // "MUS0", little endian
    localparam [31:0] MAGIC_DATA=32'h30544144;   // "DAT0"
    localparam [31:0] MAGIC_END=32'h30444e45;    // "END0"

    logic [3:0] state;
    logic [1:0] command;
    logic [23:0] magic_shift;
    logic [159:0] argument_data,argument_with_byte;
    logic [4:0] argument_count,argument_length;
    logic [31:0] packet_offset,packet_length,packet_expected_crc;
    logic [31:0] packet_count;
    logic [31:0] packet_crc,global_crc,global_crc_before_packet;
    logic [255:0] pack_data,pack_with_byte;
    logic [31:0] pack_keep,keep_with_byte;
    logic [4:0] pack_lane;
    logic packet_enqueue_error;
    logic [7:0] pending_response;
    logic [31:0] pending_value;

    function automatic [31:0] crc32_byte(input [31:0] prior,input [7:0] data);
        reg [31:0] value;integer bit_number;
        begin
            value=prior^{24'd0,data};
            for(bit_number=0;bit_number<8;bit_number=bit_number+1)
                value=value[0] ? (value>>1)^32'hedb88320 : value>>1;
            crc32_byte=value;
        end
    endfunction

    wire [31:0] magic_with_byte={byte_i,magic_shift};
    wire [31:0] next_packet_crc=crc32_byte(packet_crc,byte_i);
    wire [31:0] next_global_crc=crc32_byte(global_crc,byte_i);
    wire packet_last=packet_count+1'b1==packet_length;
    wire beat_boundary=pack_lane==31 || packet_last;
    wire beat_slot_available=!beat_valid_o || beat_ready_i;
    wire packet_crc_ok=(next_packet_crc^32'hffffffff)==packet_expected_crc;

    always_comb begin
        argument_with_byte=argument_data;
        argument_with_byte[argument_count*8+:8]=byte_i;
        pack_with_byte=pack_data;
        pack_with_byte[pack_lane*8+:8]=byte_i;
        keep_with_byte=pack_keep;
        keep_with_byte[pack_lane]=1'b1;
    end

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni)begin
            state<=FIND_MAGIC;command<=0;magic_shift<=0;argument_data<=0;
            argument_count<=0;argument_length<=0;packet_offset<=0;packet_length<=0;
            packet_expected_crc<=0;packet_count<=0;packet_crc<=32'hffffffff;
            global_crc<=32'hffffffff;global_crc_before_packet<=32'hffffffff;
            pack_data<=0;pack_keep<=0;pack_lane<=0;packet_enqueue_error<=0;
            beat_valid_o<=0;beat_index_o<=0;beat_data_o<=0;beat_keep_o<=0;
            response_valid_o<=0;response_code_o<=0;response_value_o<=0;
            pending_response<=0;pending_value<=0;header_valid_o<=0;complete_o<=0;
            payload_bytes_o<=0;frame_count_o<=0;payload_crc32_o<=0;
            committed_bytes_o<=0;error_count_o<=0;
        end else begin
            if(beat_valid_o && beat_ready_i)beat_valid_o<=0;
            if(response_valid_o && response_ready_i)begin
                response_valid_o<=0;
                if(state==SEND_RESPONSE)state<=FIND_MAGIC;
            end
            if(begin_session_i)begin
                state<=FIND_MAGIC;magic_shift<=0;argument_data<=0;argument_count<=0;
                beat_valid_o<=0;response_valid_o<=0;header_valid_o<=0;complete_o<=0;
                payload_bytes_o<=0;frame_count_o<=0;payload_crc32_o<=0;
                committed_bytes_o<=0;global_crc<=32'hffffffff;error_count_o<=0;
            end else case(state)
                FIND_MAGIC:if(byte_valid_i)begin
                    magic_shift<=magic_with_byte[31:8];
                    if(magic_with_byte==MAGIC_HEADER || magic_with_byte==MAGIC_DATA ||
                       magic_with_byte==MAGIC_END)begin
                        command<=magic_with_byte==MAGIC_HEADER ? COMMAND_HEADER :
                            magic_with_byte==MAGIC_DATA ? COMMAND_DATA : COMMAND_END;
                        argument_length<=magic_with_byte==MAGIC_HEADER ? 5'd20 :
                            magic_with_byte==MAGIC_DATA ? 5'd12 : 5'd8;
                        argument_count<=0;argument_data<=0;state<=READ_ARGUMENTS;
                    end
                end
                READ_ARGUMENTS:if(byte_valid_i)begin
                    argument_data<=argument_with_byte;
                    if(argument_count+1'b1==argument_length)begin
                        if(command==COMMAND_HEADER)begin
                            // bytes, frames, payload CRC, sample rate, {bits,channels}
                            if(argument_with_byte[127:96]!=32'd48000 ||
                               argument_with_byte[135:128]!=8'd2 ||
                               argument_with_byte[143:136]!=8'd16 ||
                               argument_with_byte[31:0]==0 ||
                               argument_with_byte[31:0]>32'd67108864 ||
                               argument_with_byte[31:0] != argument_with_byte[63:32]*4)begin
                                pending_response<=ERROR_HEADER;pending_value<=0;
                                error_count_o<=error_count_o+1'b1;
                            end else begin
                                payload_bytes_o<=argument_with_byte[31:0];
                                frame_count_o<=argument_with_byte[63:32];
                                payload_crc32_o<=argument_with_byte[95:64];
                                committed_bytes_o<=0;global_crc<=32'hffffffff;
                                header_valid_o<=1;complete_o<=0;
                                pending_response<=ACK_HEADER;pending_value<=argument_with_byte[31:0];
                            end
                            state<=SEND_RESPONSE;
                        end else if(command==COMMAND_DATA)begin
                            packet_offset<=argument_with_byte[31:0];
                            packet_length<={16'd0,argument_with_byte[47:32]};
                            packet_expected_crc<=argument_with_byte[95:64];
                            if(!header_valid_o || argument_with_byte[31:0]!=committed_bytes_o ||
                               argument_with_byte[4:0]!=0 || argument_with_byte[47:32]==0 ||
                               {16'd0,argument_with_byte[47:32]}>MAX_PACKET_BYTES ||
                               {16'd0,argument_with_byte[47:32]}>payload_bytes_o-committed_bytes_o)begin
                                pending_response<=ERROR_SEQUENCE;pending_value<=committed_bytes_o;
                                error_count_o<=error_count_o+1'b1;state<=SEND_RESPONSE;
                            end else begin
                                packet_count<=0;packet_crc<=32'hffffffff;
                                global_crc_before_packet<=global_crc;pack_data<=0;pack_keep<=0;
                                pack_lane<=0;packet_enqueue_error<=0;state<=READ_DATA;
                            end
                        end else begin
                            if(!header_valid_o || committed_bytes_o!=payload_bytes_o ||
                               argument_with_byte[31:0]!=payload_bytes_o ||
                               argument_with_byte[63:32]!=payload_crc32_o ||
                               (global_crc^32'hffffffff)!=payload_crc32_o)begin
                                pending_response<=ERROR_FINAL;pending_value<=committed_bytes_o;
                                error_count_o<=error_count_o+1'b1;state<=SEND_RESPONSE;
                            end else begin
                                complete_o<=1;pending_response<=ACK_END;
                                pending_value<=committed_bytes_o;state<=SEND_RESPONSE;
                            end
                        end
                    end else argument_count<=argument_count+1'b1;
                end
                READ_DATA:if(byte_valid_i)begin
                    packet_crc<=next_packet_crc;global_crc<=next_global_crc;
                    packet_count<=packet_count+1'b1;pack_data<=pack_with_byte;pack_keep<=keep_with_byte;
                    if(beat_boundary)begin
                        if(beat_slot_available)begin
                            beat_valid_o<=1;
                            beat_index_o<=packet_offset[25:5]+packet_count[25:5];
                            beat_data_o<=pack_with_byte;beat_keep_o<=keep_with_byte;
                        end else packet_enqueue_error<=1;
                        pack_data<=0;pack_keep<=0;pack_lane<=0;
                    end else pack_lane<=pack_lane+1'b1;
                    if(packet_last)begin
                        if(!packet_crc_ok)begin
                            global_crc<=global_crc_before_packet;pending_response<=ERROR_PACKET_CRC;
                            pending_value<=committed_bytes_o;error_count_o<=error_count_o+1'b1;
                        end else if(packet_enqueue_error || (beat_boundary && !beat_slot_available))begin
                            global_crc<=global_crc_before_packet;pending_response<=ERROR_OVERFLOW;
                            pending_value<=committed_bytes_o;error_count_o<=error_count_o+1'b1;
                        end else begin
                            committed_bytes_o<=committed_bytes_o+packet_length;
                            pending_response<=ACK_DATA;pending_value<=committed_bytes_o+packet_length;
                        end
                        state<=DRAIN_DATA;
                    end
                end
                DRAIN_DATA:if(!beat_valid_o || beat_ready_i)state<=SEND_RESPONSE;
                SEND_RESPONSE:if(!response_valid_o)begin
                    response_valid_o<=1;response_code_o<=pending_response;
                    response_value_o<=pending_value;
                end
                COMPLETE:state<=COMPLETE;
                default:state<=FIND_MAGIC;
            endcase
        end
    end
endmodule
