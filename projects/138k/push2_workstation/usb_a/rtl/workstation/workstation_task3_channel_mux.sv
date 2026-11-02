`timescale 1ns/1ps
// Single-clock logical transaction hub. This is not an LCD wire format or CDC.
// Each producer owns valid until ready, or explicitly reports its own dropped
// real-time tap sample. A full queue NEVER consumes or silently discards input.
module workstation_task3_channel_mux #(
    parameter integer CHANNELS = 8,
    parameter integer WIDTH = 256,
    parameter integer DEPTH = 4,
    parameter integer COUNTER_WIDTH = 32,
    parameter integer CHANNEL_BITS = (CHANNELS > 1) ? $clog2(CHANNELS) : 1
) (
    input wire clk_i, reset_ni,
    input wire flush_i, link_ready_i, link_down_i, panic_i,
    input wire [CHANNELS-1:0] in_valid_i,
    output reg [CHANNELS-1:0] in_ready_o,
    input wire [CHANNELS*WIDTH-1:0] in_data_i,
    output reg out_valid_o,
    input wire out_ready_i,
    output reg [CHANNEL_BITS-1:0] out_channel_o,
    output reg [WIDTH-1:0] out_data_o,
    output reg [CHANNELS-1:0] full_o,
    output reg [CHANNELS-1:0] overflow_o,
    output wire [CHANNELS*COUNTER_WIDTH-1:0] overflow_count_o
);
    localparam integer PTR_BITS = (DEPTH > 1) ? $clog2(DEPTH) : 1;
    localparam integer COUNT_BITS = $clog2(DEPTH+1);
    reg [WIDTH-1:0] memory [0:CHANNELS-1][0:DEPTH-1];
    reg [PTR_BITS-1:0] read_pointer [0:CHANNELS-1];
    reg [PTR_BITS-1:0] write_pointer [0:CHANNELS-1];
    reg [COUNT_BITS-1:0] count [0:CHANNELS-1];
    reg [COUNTER_WIDTH-1:0] overflow_count [0:CHANNELS-1];
    reg [CHANNEL_BITS-1:0] next_channel, held_channel;
    reg held_valid;
    wire fence = !reset_ni || flush_i || !link_ready_i || link_down_i || panic_i;
    integer offset, candidate, channel;
    reg found;
    wire pop = out_valid_o && out_ready_i;

    // These counters count full offered cycles, including a legal retry held
    // under backpressure. They are NOT dropped-transaction or lost-frame counts.
    // Flush/down/PANIC retain diagnostics; common reset clears them.
    genvar g;
    generate for (g=0; g<CHANNELS; g=g+1) begin: g_count
        assign overflow_count_o[g*COUNTER_WIDTH +: COUNTER_WIDTH] = overflow_count[g];
    end endgenerate

    initial begin
        if (CHANNELS < 1 || WIDTH < 1 || DEPTH < 1 || COUNTER_WIDTH < 1 ||
            CHANNEL_BITS != ((CHANNELS > 1) ? $clog2(CHANNELS) : 1))
            $fatal(1, "invalid task3 channel mux geometry");
    end

    always @* begin
        out_valid_o = 1'b0;
        out_channel_o = {CHANNEL_BITS{1'b0}};
        out_data_o = {WIDTH{1'b0}};
        found = 1'b0;
        candidate = 0;
        if (!fence) begin
            // Once offered, an output is pinned until accepted. New arrivals
            // in an earlier channel cannot alter a backpressured transaction.
            if (held_valid) begin
                out_valid_o = 1'b1;
                out_channel_o = held_channel;
                out_data_o = memory[held_channel][read_pointer[held_channel]];
            end else begin
                for (offset=0; offset<CHANNELS; offset=offset+1) begin
                    candidate = integer'(next_channel) + offset;
                    if (candidate >= CHANNELS) candidate = candidate - CHANNELS;
                    if (!found && count[candidate] != 0) begin
                        found = 1'b1;
                        out_valid_o = 1'b1;
                        out_channel_o = CHANNEL_BITS'(candidate);
                        out_data_o = memory[candidate][read_pointer[candidate]];
                    end
                end
            end
        end
    end

    always @* begin
        for (channel=0; channel<CHANNELS; channel=channel+1) begin
            full_o[channel] = !fence && count[channel] == COUNT_BITS'(DEPTH);
            // A simultaneously accepted head frees exactly one slot, even
            // for DEPTH=1. Empty queues have no combinational input bypass.
            in_ready_o[channel] = !fence &&
                (count[channel] < COUNT_BITS'(DEPTH) ||
                 (pop && out_channel_o == CHANNEL_BITS'(channel)));
            overflow_o[channel] = !fence && in_valid_i[channel] && !in_ready_o[channel];
        end
    end

    integer q;
    always @(posedge clk_i or negedge reset_ni) begin
        if (!reset_ni) begin
            next_channel <= 0;
            held_channel <= 0;
            held_valid <= 1'b0;
            for (q=0; q<CHANNELS; q=q+1) begin
                read_pointer[q] <= 0;
                write_pointer[q] <= 0;
                count[q] <= 0;
                overflow_count[q] <= 0;
            end
        end else begin
            if (fence) begin
                next_channel <= 0;
                held_channel <= 0;
                held_valid <= 1'b0;
                for (q=0; q<CHANNELS; q=q+1) begin
                    read_pointer[q] <= 0;
                    write_pointer[q] <= 0;
                    count[q] <= 0;
                end
            end else begin
                if (out_valid_o && !out_ready_i) begin
                    held_valid <= 1'b1;
                    held_channel <= out_channel_o;
                end else if (pop) begin
                    held_valid <= 1'b0;
                    if (out_channel_o == CHANNEL_BITS'(CHANNELS-1)) next_channel <= 0;
                    else next_channel <= out_channel_o + 1'b1;
                end
                for (q=0; q<CHANNELS; q=q+1) begin
                    if (in_valid_i[q] && in_ready_o[q]) begin
                        memory[q][write_pointer[q]] <= in_data_i[q*WIDTH +: WIDTH];
                        if (write_pointer[q] == PTR_BITS'(DEPTH-1)) write_pointer[q] <= 0;
                        else write_pointer[q] <= write_pointer[q] + 1'b1;
                    end
                    if (pop && out_channel_o == CHANNEL_BITS'(q)) begin
                        if (read_pointer[q] == PTR_BITS'(DEPTH-1)) read_pointer[q] <= 0;
                        else read_pointer[q] <= read_pointer[q] + 1'b1;
                    end
                    case ({in_valid_i[q] && in_ready_o[q], pop && out_channel_o == CHANNEL_BITS'(q)})
                        2'b10: count[q] <= count[q] + 1'b1;
                        2'b01: count[q] <= count[q] - 1'b1;
                        default: ;
                    endcase
                    if (overflow_o[q] && !(&overflow_count[q]))
                        overflow_count[q] <= overflow_count[q] + 1'b1;
                end
            end
        end
    end
endmodule
