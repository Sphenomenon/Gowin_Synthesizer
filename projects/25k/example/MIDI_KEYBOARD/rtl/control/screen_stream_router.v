`timescale 1ns/1ps
// Serialize the MK settings and PL pixel protocols over one USB byte stream.
// Each request owns the stream until its complete reply has been accepted.
module screen_stream_router #(
    parameter integer CLK_HZ = 50000000,
    parameter integer TIMEOUT_MS = 100
) (
    input wire clk,
    input wire reset,
    input wire rx_valid,
    output reg rx_ready,
    input wire [7:0] rx_data,
    output reg tx_valid,
    input wire tx_ready,
    output reg [7:0] tx_data,
    output reg mk_rx_valid,
    input wire mk_rx_ready,
    output reg [7:0] mk_rx_data,
    input wire mk_tx_valid,
    output reg mk_tx_ready,
    input wire [7:0] mk_tx_data,
    output reg pl_rx_valid,
    input wire pl_rx_ready,
    output reg [7:0] pl_rx_data,
    input wire pl_tx_valid,
    output reg pl_tx_ready,
    input wire [7:0] pl_tx_data,
    output reg mk_reset,
    output reg pl_reset
);
    function integer bits_for;
        input [63:0] value;
        reg [63:0] work;
        begin
            bits_for = 0;
            work = value;
            while (work != 0) begin
                bits_for = bits_for + 1;
                work = work >> 1;
            end
            if (bits_for == 0) bits_for = 1;
        end
    endfunction

    localparam [63:0] TIMEOUT_CYCLES =
        (CLK_HZ < 1 || TIMEOUT_MS < 1) ? 64'd1 :
        ((CLK_HZ * 64'd1 * TIMEOUT_MS) + 64'd999) / 64'd1000;
    localparam integer TIMER_BITS = bits_for(TIMEOUT_CYCLES - 64'd1);
    localparam [2:0] FIND_FIRST = 3'd0, FIND_SECOND = 3'd1,
        REPLAY_FIRST = 3'd2, REPLAY_SECOND = 3'd3,
        RECEIVE = 3'd4, REPLY = 3'd5;

    reg [2:0] state;
    reg [7:0] first_magic;
    reg owner_pl;
    reg owner_valid;
    reg [9:0] rx_index;
    reg [9:0] tx_index;
    reg [9:0] request_bytes;
    reg [9:0] reply_bytes;
    reg [7:0] request_length_low;
    reg [7:0] reply_length_low;
    reg [TIMER_BITS-1:0] idle_count;

    wire selected_rx_ready = owner_pl ? pl_rx_ready : mk_rx_ready;
    wire selected_tx_valid = owner_pl ? pl_tx_valid : mk_tx_valid;
    wire [7:0] selected_tx_data = owner_pl ? pl_tx_data : mk_tx_data;
    wire request_transfer = rx_valid && rx_ready;
    wire reply_transfer = tx_valid && tx_ready;
    wire replay_transfer =
        (state == REPLAY_FIRST || state == REPLAY_SECOND) && selected_rx_ready;
    // An offered reply byte must survive arbitrarily long host backpressure.
    // Only an absent byte can consume the response interbyte timeout.
    wire progress = request_transfer || replay_transfer ||
        (state == REPLY && selected_tx_valid);
    wire timed_out = state != FIND_FIRST && !progress &&
        idle_count == TIMEOUT_CYCLES - 64'd1;

    always @* begin
        rx_ready = 1'b0;
        tx_valid = 1'b0;
        tx_data = 8'd0;
        mk_rx_valid = 1'b0;
        mk_rx_data = 8'd0;
        mk_tx_ready = 1'b0;
        pl_rx_valid = 1'b0;
        pl_rx_data = 8'd0;
        pl_tx_ready = 1'b0;
        if (!reset) begin
            if (state == FIND_FIRST || state == FIND_SECOND)
                rx_ready = 1'b1;
            if (state == REPLAY_FIRST || state == REPLAY_SECOND || state == RECEIVE) begin
                if (owner_pl) begin
                    pl_rx_valid = (state == RECEIVE) ? rx_valid : 1'b1;
                    pl_rx_data = (state == REPLAY_FIRST) ? 8'h50 :
                        ((state == REPLAY_SECOND) ? 8'h4c : rx_data);
                end else begin
                    mk_rx_valid = (state == RECEIVE) ? rx_valid : 1'b1;
                    mk_rx_data = (state == REPLAY_FIRST) ? 8'h4d :
                        ((state == REPLAY_SECOND) ? 8'h4b : rx_data);
                end
                if (state == RECEIVE) rx_ready = selected_rx_ready;
            end
            if (state == REPLY) begin
                tx_valid = selected_tx_valid;
                tx_data = selected_tx_data;
                if (owner_pl) pl_tx_ready = tx_ready;
                else mk_tx_ready = tx_ready;
            end
        end
    end

    always @(posedge clk) begin
        if (reset) begin
            state <= FIND_FIRST;
            first_magic <= 0;
            owner_pl <= 1'b0;
            owner_valid <= 1'b0;
            rx_index <= 0;
            tx_index <= 0;
            request_bytes <= 10'd16;
            reply_bytes <= 10'd16;
            request_length_low <= 0;
            reply_length_low <= 0;
            idle_count <= 0;
            mk_reset <= 1'b0;
            pl_reset <= 1'b0;
        end else begin
            mk_reset <= 1'b0;
            pl_reset <= 1'b0;
            if (state == FIND_FIRST || progress) idle_count <= 0;
            else if (!timed_out) idle_count <= idle_count + 1'b1;

            if (timed_out) begin
                state <= FIND_FIRST;
                idle_count <= 0;
                owner_valid <= 1'b0;
                if (owner_valid) begin
                    if (owner_pl) pl_reset <= 1'b1;
                    else mk_reset <= 1'b1;
                end
            end else begin
                case (state)
                    FIND_FIRST: if (request_transfer) begin
                        if (rx_data == 8'h4d || rx_data == 8'h50) begin
                            first_magic <= rx_data;
                            state <= FIND_SECOND;
                        end
                    end
                    FIND_SECOND: if (request_transfer) begin
                        if ((first_magic == 8'h4d && rx_data == 8'h4b) ||
                            (first_magic == 8'h50 && rx_data == 8'h4c)) begin
                            owner_pl <= first_magic == 8'h50;
                            owner_valid <= 1'b1;
                            request_bytes <= 10'd16;
                            reply_bytes <= 10'd16;
                            rx_index <= 10'd2;
                            tx_index <= 0;
                            request_length_low <= 0;
                            reply_length_low <= 0;
                            state <= REPLAY_FIRST;
                        end else if (rx_data == 8'h4d || rx_data == 8'h50) begin
                            // Retain an overlapping candidate, e.g. M P L.
                            first_magic <= rx_data;
                        end else state <= FIND_FIRST;
                    end
                    REPLAY_FIRST: if (replay_transfer) state <= REPLAY_SECOND;
                    REPLAY_SECOND: if (replay_transfer) state <= RECEIVE;
                    RECEIVE: if (request_transfer) begin
                        if (owner_pl && rx_index == 10'd12)
                            request_length_low <= rx_data;
                        if (owner_pl && rx_index == 10'd13 &&
                            {rx_data, request_length_low} > 16'd512) begin
                            pl_reset <= 1'b1;
                            owner_valid <= 1'b0;
                            state <= FIND_FIRST;
                            idle_count <= 0;
                        end else begin
                            if (owner_pl && rx_index == 10'd13)
                                request_bytes <= 10'd16 + {rx_data, request_length_low};
                            if (rx_index == request_bytes - 10'd1) begin
                                tx_index <= 0;
                                state <= REPLY;
                            end else rx_index <= rx_index + 1'b1;
                        end
                    end
                    REPLY: if (reply_transfer) begin
                        if (owner_pl && tx_index == 10'd12)
                            reply_length_low <= selected_tx_data;
                        if (owner_pl && tx_index == 10'd13 &&
                            {selected_tx_data, reply_length_low} > 16'd512) begin
                            // A malformed endpoint response cannot monopolize
                            // the stream or wrap the bounded byte counter.
                            pl_reset <= 1'b1;
                            owner_valid <= 1'b0;
                            state <= FIND_FIRST;
                            idle_count <= 0;
                        end else begin
                            if (owner_pl && tx_index == 10'd13)
                                reply_bytes <= 10'd16 + {selected_tx_data, reply_length_low};
                            if (tx_index == reply_bytes - 10'd1) begin
                                owner_valid <= 1'b0;
                                state <= FIND_FIRST;
                            end else tx_index <= tx_index + 1'b1;
                        end
                    end
                    default: begin
                        state <= FIND_FIRST;
                        owner_valid <= 1'b0;
                    end
                endcase
            end
        end
    end
endmodule
