`timescale 1ns/1ps
`include "basic_pitch_flash_map.svh"
// Flash transport in front of the original, unchanged BPN1 UART->DDR parser.
// Pass 1 checks the entire NOR image before any parser byte is emitted. Pass 2
// rereads it, pacing each word through the existing 115200-baud 8N1 protocol.
// Only a word/byte is buffered, never a model ROM or PCM. The native DDR client,
// parser reset and instance hierarchy can remain exactly as in full85.
module basic_pitch_flash_serial_boot #(
    parameter integer WORDS = `BP_FLASH_MODEL_WORDS,
    parameter integer CLK_HZ = 50_000_000,
    parameter integer BAUD = 115200,
    parameter integer CLK_DIV = 4
)(
    input wire clk_i,rst_ni,boot_ready_i,serial_i,flash_miso_i,
    input wire [3:0] model_status_i,
    output wire serial_o,flash_cs_n_o,flash_clk_o,flash_mosi_o,
    output wire [1:0] source_o,
    output reg [1:0] error_stage_o,
    output wire [3:0] state_o
);
    localparam [3:0] WAIT_READY=0,CHECK_IMAGE=1,MAGIC=2,STREAM=3,
        CRC_TAIL=4,WAIT_MODEL=5,COMPLETE=6,FALLBACK=7,FAULT=8;
    reg [3:0] state;
    (* ASYNC_REG="TRUE" *) reg ready_meta,ready_sync;
    reg reader_reset_n,half_word,inflight;
    reg [1:0] byte_index;
    reg [31:0] image_crc;
    wire reader_done,reader_req,reader_write;
    wire [3:0] reader_status;
    wire [1:0] reader_error;
    wire [31:0] reader_crc,reader_actual,reader_addr;
    wire [15:0] reader_word;
    wire tx_ready,tx_done,tx_serial;
    reg [7:0] tx_data;
    wire tx_valid=!inflight && (state==MAGIC || state==CRC_TAIL ||
        (state==STREAM && reader_req && reader_write));
    wire reader_ready=state==CHECK_IMAGE ||
        (state==STREAM && half_word && tx_done);
    assign serial_o=state==FALLBACK ? serial_i : tx_serial;
    assign source_o=state==FALLBACK ? 2'd2 :
        ((state==COMPLETE || state==WAIT_MODEL) && model_status_i==14 ? 2'd1 : 2'd0);
    assign state_o=state;
    always @* begin
        if(state==MAGIC) case(byte_index)
            0:tx_data="B";1:tx_data="P";2:tx_data="N";default:tx_data="1";
        endcase
        else if(state==CRC_TAIL) tx_data=image_crc[byte_index*8 +: 8];
        else tx_data=half_word ? reader_word[15:8] : reader_word[7:0];
    end
    uart_tx #(.CLK_HZ(CLK_HZ),.BAUD(BAUD)) u_tx (
        .clk(clk_i),.rst_n(rst_ni),.data({24'd0,tx_data}),.valid(tx_valid),
        .ready(tx_ready),.serial_out(tx_serial),.byte_done(tx_done));
    basic_pitch_flash_model_loader #(.WORDS(WORDS),.CLK_DIV(CLK_DIV),.VERIFY_DDR(1'b0)) u_reader (
        .clk_i(clk_i),.rst_ni(rst_ni && reader_reset_n),.boot_ready_i(1'b1),
        .flash_miso_i(flash_miso_i),.flash_cs_n_o(flash_cs_n_o),
        .flash_clk_o(flash_clk_o),.flash_mosi_o(flash_mosi_o),
        .done_o(reader_done),.status_o(reader_status),.debug_expected_crc_o(reader_crc),
        .debug_actual_crc_o(reader_actual),.debug_error_stage_o(reader_error),
        .mem_req_o(reader_req),.mem_write_o(reader_write),.mem_byte_addr_o(reader_addr),
        .mem_wdata_o(reader_word),.mem_ready_i(reader_ready),
        .mem_rsp_valid_i(1'b0),.mem_rdata_i(16'd0));
    always @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni) begin ready_meta<=0;ready_sync<=0;end
        else begin ready_meta<=boot_ready_i;ready_sync<=ready_meta;end
    end
    always @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni) begin
            state<=WAIT_READY;reader_reset_n<=0;half_word<=0;inflight<=0;
            byte_index<=0;image_crc<=0;error_stage_o<=0;
        end else begin
            if(tx_valid && tx_ready) inflight<=1;
            if(tx_done) inflight<=0;
            case(state)
                WAIT_READY: if(ready_sync) begin state<=CHECK_IMAGE;reader_reset_n<=1;end
                CHECK_IMAGE: begin
                    if(reader_status==15) begin state<=FALLBACK;error_stage_o<=reader_error;reader_reset_n<=0;end
                    else if(reader_done) begin
                        image_crc<=reader_crc;reader_reset_n<=0;byte_index<=0;state<=MAGIC;
                    end
                end
                MAGIC: if(tx_done) begin
                    if(byte_index==3) begin state<=STREAM;reader_reset_n<=1;half_word<=0;end
                    else byte_index<=byte_index+1'b1;
                end
                STREAM: begin
                    if(tx_done) half_word<=!half_word;
                    if(reader_status==15) begin state<=FAULT;error_stage_o<=reader_error;end
                    else if(reader_done) begin
                        // A changed image between passes must not be committed.
                        if(reader_crc!=image_crc || reader_actual!=image_crc) begin state<=FAULT;error_stage_o<=2;end
                        else begin state<=CRC_TAIL;byte_index<=0;end
                    end
                end
                CRC_TAIL: if(tx_done) begin
                    if(byte_index==3) state<=WAIT_MODEL;
                    else byte_index<=byte_index+1'b1;
                end
                WAIT_MODEL: if(model_status_i==14) state<=COMPLETE;
                    else if(model_status_i==15) begin state<=FAULT;error_stage_o<=3;end
                default: begin end
            endcase
        end
    end
    initial if(CLK_HZ<BAUD*8 || BAUD<1) $fatal(1,"unsupported internal model UART rate");
endmodule
