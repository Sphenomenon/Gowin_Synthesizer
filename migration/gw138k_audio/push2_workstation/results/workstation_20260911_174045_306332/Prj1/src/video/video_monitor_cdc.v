`default_nettype none

// One-entry, acknowledged snapshot mailbox. This is an observation branch:
// while busy, new observations may be dropped; the audio source never stalls.
// Three separate 32-bit words remain stable from request through acknowledgment.
// Both resets must assert together (including on loss of video PLL lock).
module video_monitor_cdc (
    input wire source_clk,
    input wire source_reset_n,
    input wire [31:0] sample_data,
    input wire sample_valid,
    input wire [31:0] active_voices,
    input wire [31:0] status_data,
    input wire pixel_clk,
    input wire pixel_reset_n,
    output reg [31:0] pixel_sample,
    output reg [31:0] pixel_voices,
    output reg [31:0] pixel_status,
    output reg pixel_valid
);
    reg [31:0] held_sample;
    reg [31:0] held_voices;
    reg [31:0] held_status;
    reg request_toggle;
    reg acknowledge_toggle;
    (* ASYNC_REG = "TRUE" *) reg ack_meta;
    (* ASYNC_REG = "TRUE" *) reg ack_sync;
    (* ASYNC_REG = "TRUE" *) reg req_meta;
    (* ASYNC_REG = "TRUE" *) reg req_sync;
    reg req_settled;

    always @(posedge source_clk or negedge source_reset_n) begin
        if (!source_reset_n) begin
            ack_meta <= 0;
            ack_sync <= 0;
            request_toggle <= 0;
            held_sample <= 0;
            held_voices <= 0;
            held_status <= 0;
        end else begin
            ack_meta <= acknowledge_toggle;
            ack_sync <= ack_meta;
            if (sample_valid && (ack_sync == request_toggle)) begin
                held_sample <= sample_data;
                held_voices <= active_voices;
                held_status <= status_data;
                request_toggle <= ~request_toggle;
            end
        end
    end
    always @(posedge pixel_clk or negedge pixel_reset_n) begin
        if (!pixel_reset_n) begin
            req_meta <= 0;
            req_sync <= 0;
            req_settled <= 0;
            acknowledge_toggle <= 0;
            pixel_sample <= 0;
            pixel_voices <= 0;
            pixel_status <= 0;
            pixel_valid <= 0;
        end else begin
            req_meta <= request_toggle;
            req_sync <= req_meta;
            // An extra destination cycle gives the held buses settling time.
            req_settled <= req_sync;
            pixel_valid <= 0;
            if (req_settled != acknowledge_toggle) begin
                pixel_sample <= held_sample;
                pixel_voices <= held_voices;
                pixel_status <= held_status;
                pixel_valid <= 1;
                acknowledge_toggle <= req_settled;
            end
        end
    end
endmodule

`default_nettype wire
