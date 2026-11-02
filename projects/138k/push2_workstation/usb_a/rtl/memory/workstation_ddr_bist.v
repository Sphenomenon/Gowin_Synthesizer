`include "src/memory/ddr_address_map.vh"

module ddr3_bist #(
    parameter integer ENABLE_BIST = 1,
    parameter integer BURSTS = `PRJ1_DDR_BIST_BEATS,
    parameter integer TIMEOUT_CYCLES = 10000000
) (
    input  wire         clk,
    input  wire         rst_n,
    output wire         req_valid,
    input  wire         req_ready,
    output wire         req_write,
    output wire [28:0]  req_addr,
    output wire [255:0] req_wdata,
    input  wire         rsp_valid,
    input  wire [255:0] rsp_data,
    output reg          done,
    output reg          failed,
    output reg [31:0]   error_count,
    output reg [28:0]   first_error_addr
);
    localparam [1:0] WRITE = 2'd0, READ_REQUEST = 2'd1,
                     READ_RESPONSE = 2'd2, FINISHED = 2'd3;
    localparam [28:0] LAST_ADDR = (BURSTS - 1) * 8;
    localparam integer WATCHDOG_WIDTH = (TIMEOUT_CYCLES < 2) ? 1 :
                                        $clog2(TIMEOUT_CYCLES);
    reg [1:0] state;
    reg [28:0] address;
    reg inverted;
    reg [WATCHDOG_WIDTH-1:0] watchdog;
    reg [255:0] expected_rdata;

    function [255:0] test_pattern;
        input [28:0] word_address;
        input invert_pattern;
        integer lane;
        reg [31:0] lane_word;
        begin
            for (lane = 0; lane < 8; lane = lane + 1) begin
                lane_word = {3'b101, word_address} ^
                            (32'h9e3779b9 * (lane + 1));
                test_pattern[lane*32 +: 32] = invert_pattern ?
                                              ~lane_word : lane_word;
            end
        end
    endfunction

    assign req_valid = ENABLE_BIST && rst_n && ((state == WRITE) || (state == READ_REQUEST));
    assign req_write = ENABLE_BIST && (state == WRITE);
    assign req_addr = ENABLE_BIST ? address : 29'd0;
    assign req_wdata = ENABLE_BIST ? test_pattern(address, inverted) : 256'd0;

    wire request_accepted = req_valid && req_ready;
    wire response_accepted = (state == READ_RESPONSE) && rsp_valid;
    wire [31:0] mismatch_bytes;
    genvar byte_index;
    generate
        for (byte_index = 0; byte_index < 32; byte_index = byte_index + 1) begin: g_compare_byte
            assign mismatch_bytes[byte_index] =
                rsp_data[byte_index*8 +: 8] != expected_rdata[byte_index*8 +: 8];
        end
    endgenerate
    wire mismatch = |mismatch_bytes;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= WRITE;
            address <= 29'd0;
            inverted <= 1'b0;
            watchdog <= 0;
            expected_rdata <= 0;
            done <= 1'b0;
            failed <= 1'b0;
            error_count <= 0;
            first_error_addr <= 0;
        end else if (!ENABLE_BIST) begin
            // Reset is released only after DDR calibration by the owning
            // display/memory subsystem. No request or destructive test runs.
            done <= 1'b1;
        end else if (state != FINISHED) begin
            if (request_accepted || response_accepted) begin
                watchdog <= 0;
                case (state)
                    WRITE: begin
                        if (address == LAST_ADDR) begin
                            address <= 0;
                            state <= READ_REQUEST;
                        end else begin
                            address <= address + 29'd8;
                        end
                    end
                    READ_REQUEST: begin
                        expected_rdata <= test_pattern(address, inverted);
                        state <= READ_RESPONSE;
                    end
                    READ_RESPONSE: begin
                        if (mismatch) begin
                            if (!failed)
                                first_error_addr <= address;
                            failed <= 1'b1;
                            if (error_count != 32'hffffffff)
                                error_count <= error_count + 1'b1;
                        end
                        if (address == LAST_ADDR) begin
                            address <= 0;
                            if (inverted) begin
                                done <= 1'b1;
                                state <= FINISHED;
                            end else begin
                                inverted <= 1'b1;
                                state <= WRITE;
                            end
                        end else begin
                            address <= address + 29'd8;
                            state <= READ_REQUEST;
                        end
                    end
                    default: state <= FINISHED;
                endcase
            end else if (watchdog == TIMEOUT_CYCLES - 1) begin
                if (!failed)
                    first_error_addr <= address;
                failed <= 1'b1;
                done <= 1'b1;
                if (error_count != 32'hffffffff)
                    error_count <= error_count + 1'b1;
                state <= FINISHED;
            end else begin
                watchdog <= watchdog + 1'b1;
            end
        end
    end
endmodule
