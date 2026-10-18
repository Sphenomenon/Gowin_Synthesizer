`timescale 1ns/1ps
`default_nettype none
module usb2_status_50mhz #(
    parameter WINDOW_CYCLES = 500000,
    parameter SNAPSHOT_CYCLES = 50000
) (
    input wire clk_50mhz,
    input wire clk_ulpi60,
    input wire [127:0] live_snapshot,
    output wire [63:0] status_50mhz,
    output wire [3:0] result_flags,
    output wire clock_alive
);
    // Gray counter crosses independently of the probe: diagnostics continue
    // when the PHY clock is absent, stopped or at an unexpected frequency.
    reg [23:0] ulpi_counter = 0;
    reg [23:0] ulpi_gray = 0;
    wire [23:0] ulpi_next = ulpi_counter + 1'b1;
    always @(posedge clk_ulpi60) begin
        ulpi_counter <= ulpi_next;
        ulpi_gray <= (ulpi_next >> 1) ^ ulpi_next;
    end
    (* ASYNC_REG = "TRUE" *) reg [23:0] gray_meta = 0;
    (* ASYNC_REG = "TRUE" *) reg [23:0] gray_sync = 0;
    function [23:0] gray_to_binary;
        input [23:0] gray;
        integer i;
        begin
            gray_to_binary[23] = gray[23];
            for (i = 22; i >= 0; i = i - 1)
                gray_to_binary[i] = gray_to_binary[i+1] ^ gray[i];
        end
    endfunction
    wire [23:0] binary_count = gray_to_binary(gray_sync);
    reg [19:0] window_timer = 0;
    reg [23:0] previous_count = 0;
    reg [19:0] window_count = 0;
    wire [23:0] count_delta = binary_count - previous_count;
    assign clock_alive = (window_count != 0);

    // Bundled-data mailbox. The 60 MHz side holds the full snapshot stable
    // from acknowledgement until the next request. The destination samples
    // only after the acknowledgement traverses two FFs, plus a settling FF.
    reg request_toggle = 0;
    (* ASYNC_REG = "TRUE" *) reg request_meta = 0;
    (* ASYNC_REG = "TRUE" *) reg request_sync = 0;
    reg acknowledge = 0;
    reg [127:0] snapshot_hold = 0;
    always @(posedge clk_ulpi60) begin
        request_meta <= request_toggle;
        request_sync <= request_meta;
        if (request_sync != acknowledge) begin
            snapshot_hold <= live_snapshot;
            acknowledge <= request_sync;
        end
    end
    (* ASYNC_REG = "TRUE" *) reg ack_meta = 0;
    (* ASYNC_REG = "TRUE" *) reg ack_sync = 0;
    reg ack_settled = 0;
    reg [15:0] snapshot_timer = 0;
    reg waiting = 0;
    reg [127:0] snapshot_50 = 0;
    reg [4:0] phase = 0;
    reg heartbeat = 0;
    always @(posedge clk_50mhz) begin
        gray_meta <= ulpi_gray;
        gray_sync <= gray_meta;
        ack_meta <= acknowledge;
        ack_sync <= ack_meta;
        ack_settled <= ack_sync;
        phase <= phase + 1'b1;
        heartbeat <= ~heartbeat;
        if (window_timer == WINDOW_CYCLES-1) begin
            window_timer <= 0;
            window_count <= count_delta > 24'h0fffff ? 20'hfffff : count_delta[19:0];
            previous_count <= binary_count;
        end else window_timer <= window_timer + 1'b1;
        if (snapshot_timer == SNAPSHOT_CYCLES-1) begin
            snapshot_timer <= 0;
            if (!waiting) begin
                request_toggle <= ~request_toggle;
                waiting <= 1'b1;
            end
        end else snapshot_timer <= snapshot_timer + 1'b1;
        // Commit only before page 0. A complete 0,1,2,3 page rotation is one
        // coherent source snapshot even if the probe updates during capture.
        if (waiting && ack_settled == request_toggle && phase == 5'd31) begin
            snapshot_50 <= snapshot_hold;
            waiting <= 1'b0;
        end
    end
    wire [31:0] payload = phase[4:3] == 0 ? snapshot_50[127:96] :
                          phase[4:3] == 1 ? snapshot_50[95:64] :
                          phase[4:3] == 2 ? snapshot_50[63:32] : snapshot_50[31:0];
    assign result_flags = snapshot_50[51:48];
    assign status_50mhz = {payload, window_count, snapshot_50[59:56],
                          result_flags, clock_alive, phase[4:3], heartbeat};
endmodule
`default_nettype wire
