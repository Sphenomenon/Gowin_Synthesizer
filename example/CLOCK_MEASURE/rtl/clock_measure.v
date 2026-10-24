// Independent oscillator counters, registered Gray CDC, exact reference gates.
module clock_measure #(
    parameter integer GATE_CYCLES = 500000000,
    parameter integer WARMUP_CYCLES = 128,
    parameter integer COUNTER_WIDTH = 32
) (
    input wire clk_ref, clk_a, clk_b, restart_n,
    output reg [31:0] window_id = 0,
    output reg [31:0] count_a = 0, count_b = 0,
    output reg [31:0] endpoint_a = 0, endpoint_b = 0,
    output reg [31:0] heartbeat = 0
);
    (* ASYNC_REG="TRUE" *) reg [1:0] reset_ref = 0, reset_a = 0, reset_b = 0;
    always @(posedge clk_ref or negedge restart_n)
        if (!restart_n) reset_ref <= 0; else reset_ref <= {reset_ref[0],1'b1};
    always @(posedge clk_a or negedge restart_n)
        if (!restart_n) reset_a <= 0; else reset_a <= {reset_a[0],1'b1};
    always @(posedge clk_b or negedge restart_n)
        if (!restart_n) reset_b <= 0; else reset_b <= {reset_b[0],1'b1};

    reg [COUNTER_WIDTH-1:0] bin_a = 0, bin_b = 0, gray_a = 0, gray_b = 0;
    wire [COUNTER_WIDTH-1:0] next_a = bin_a + 1'b1, next_b = bin_b + 1'b1;
    always @(posedge clk_a or negedge restart_n) begin
        if (!restart_n) begin bin_a <= 0; gray_a <= 0; end
        else if (!reset_a[1]) begin bin_a <= 0; gray_a <= 0; end
        else begin bin_a <= next_a; gray_a <= (next_a >> 1) ^ next_a; end
    end
    always @(posedge clk_b or negedge restart_n) begin
        if (!restart_n) begin bin_b <= 0; gray_b <= 0; end
        else if (!reset_b[1]) begin bin_b <= 0; gray_b <= 0; end
        else begin bin_b <= next_b; gray_b <= (next_b >> 1) ^ next_b; end
    end
    (* ASYNC_REG="TRUE" *) reg [COUNTER_WIDTH-1:0] a_meta = 0, a_sync = 0;
    (* ASYNC_REG="TRUE" *) reg [COUNTER_WIDTH-1:0] b_meta = 0, b_sync = 0;
    function [COUNTER_WIDTH-1:0] decode_gray;
        input [COUNTER_WIDTH-1:0] value;
        integer i;
        begin
            decode_gray[COUNTER_WIDTH-1] = value[COUNTER_WIDTH-1];
            for (i=COUNTER_WIDTH-2; i>=0; i=i-1)
                decode_gray[i] = decode_gray[i+1] ^ value[i];
        end
    endfunction
    wire [COUNTER_WIDTH-1:0] current_a = decode_gray(a_sync);
    wire [COUNTER_WIDTH-1:0] current_b = decode_gray(b_sync);
    reg [COUNTER_WIDTH-1:0] previous_a = 0, previous_b = 0;
    wire [COUNTER_WIDTH-1:0] delta_a = current_a - previous_a;
    wire [COUNTER_WIDTH-1:0] delta_b = current_b - previous_b;
    reg [31:0] gate = 0, warmup = 0;
    reg started = 0;
    always @(posedge clk_ref) begin
        if (!reset_ref[1]) begin
            a_meta <= 0; a_sync <= 0; b_meta <= 0; b_sync <= 0;
            previous_a <= 0; previous_b <= 0;
            count_a <= 0; count_b <= 0; endpoint_a <= 0; endpoint_b <= 0;
            gate <= 0; warmup <= 0; started <= 0; window_id <= 0; heartbeat <= 0;
        end else begin
            a_meta <= gray_a; a_sync <= a_meta;
            b_meta <= gray_b; b_sync <= b_meta;
            heartbeat <= heartbeat + 1'b1;
            if (!started) begin
                if (warmup == WARMUP_CYCLES-1) begin
                    previous_a <= current_a; previous_b <= current_b;
                    started <= 1; gate <= 0;
                end else warmup <= warmup + 1'b1;
            end else if (gate == GATE_CYCLES-1) begin
                count_a <= delta_a; count_b <= delta_b;
                endpoint_a <= current_a; endpoint_b <= current_b;
                previous_a <= current_a; previous_b <= current_b;
                window_id <= window_id + 1'b1; gate <= 0;
            end else gate <= gate + 1'b1;
        end
    end
endmodule
