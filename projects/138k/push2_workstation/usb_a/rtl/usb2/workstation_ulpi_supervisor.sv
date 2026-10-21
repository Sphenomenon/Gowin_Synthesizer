module workstation_ulpi_supervisor #(
    parameter integer HEARTBEAT_WIDTH = 5,
    parameter integer EXIT_HOLD_REF_CYCLES = 500,
    parameter integer QUALIFY_EDGES = 8,
    parameter integer CLOCK_TIMEOUT_REF_CYCLES = 5000
)(
    input wire clk_ref,
    input wire clk_ulpi,
    input wire reset_n,
    input wire enable_i,
    output wire link_reset_n_o,
    output wire force_stp_o,
    output wire running_o,
    output wire clock_present_o,
    output wire failed_o,
    output reg [1:0] failure_code_o
);
    localparam [2:0] DISABLED = 0;
    localparam [2:0] EXIT_HOLD = 1;
    localparam [2:0] QUALIFY = 2;
    localparam [2:0] RUNNING = 3;
    localparam [2:0] FAILED = 4;
    localparam integer HOLD_WIDTH = EXIT_HOLD_REF_CYCLES < 2 ? 1 : $clog2(EXIT_HOLD_REF_CYCLES);
    localparam integer QUIET_WIDTH = CLOCK_TIMEOUT_REF_CYCLES < 2 ? 1 : $clog2(CLOCK_TIMEOUT_REF_CYCLES);
    localparam integer EDGE_WIDTH = QUALIFY_EDGES < 2 ? 1 : $clog2(QUALIFY_EDGES);
    localparam [HOLD_WIDTH-1:0] HOLD_LIMIT = HOLD_WIDTH'(EXIT_HOLD_REF_CYCLES - 1);
    localparam [QUIET_WIDTH-1:0] QUIET_LIMIT = QUIET_WIDTH'(CLOCK_TIMEOUT_REF_CYCLES - 1);
    localparam [EDGE_WIDTH-1:0] EDGE_LIMIT = EDGE_WIDTH'(QUALIFY_EDGES - 1);
    reg [HEARTBEAT_WIDTH-1:0] heartbeat_q;
    (* ASYNC_REG = "TRUE" *) reg [1:0] heartbeat_release_q;
    (* ASYNC_REG = "TRUE" *) reg heartbeat_meta_q;
    (* ASYNC_REG = "TRUE" *) reg heartbeat_sync_q;
    reg heartbeat_seen_q;
    reg edge_seen_q;
    reg [QUIET_WIDTH-1:0] quiet_q;
    reg [HOLD_WIDTH-1:0] hold_q;
    reg [EDGE_WIDTH-1:0] qualified_q;
    reg [2:0] state_q;
    (* ASYNC_REG = "TRUE" *) reg [1:0] release_q;
    wire heartbeat_edge = heartbeat_sync_q != heartbeat_seen_q;
    wire heartbeat_reset_n = heartbeat_release_q[1];
    wire run_ref = reset_n && state_q == RUNNING;

    assign running_o = run_ref;
    assign force_stp_o = !run_ref;
    assign link_reset_n_o = release_q[1];
    assign clock_present_o = reset_n && edge_seen_q && quiet_q != QUIET_LIMIT;
    assign failed_o = reset_n && state_q == FAILED;

    always @(posedge clk_ulpi or negedge reset_n) begin
        if (!reset_n)
            heartbeat_release_q <= 2'b00;
        else
            heartbeat_release_q <= {heartbeat_release_q[0], 1'b1};
    end

    always @(posedge clk_ulpi or negedge heartbeat_reset_n) begin
        if (!heartbeat_reset_n)
            heartbeat_q <= {HEARTBEAT_WIDTH{1'b0}};
        else
            heartbeat_q <= heartbeat_q + 1'b1;
    end

    always @(posedge clk_ref or negedge reset_n) begin
        if (!reset_n) begin
            heartbeat_meta_q <= 1'b0;
            heartbeat_sync_q <= 1'b0;
            heartbeat_seen_q <= 1'b0;
        end else begin
            heartbeat_meta_q <= heartbeat_q[HEARTBEAT_WIDTH-1];
            heartbeat_sync_q <= heartbeat_meta_q;
            heartbeat_seen_q <= heartbeat_sync_q;
        end
    end

    always @(posedge clk_ulpi or negedge run_ref) begin
        if (!run_ref)
            release_q <= 2'b00;
        else
            release_q <= {release_q[0], 1'b1};
    end

    always @(posedge clk_ref or negedge reset_n) begin
        if (!reset_n) begin
            state_q <= DISABLED;
            quiet_q <= {QUIET_WIDTH{1'b0}};
            hold_q <= {HOLD_WIDTH{1'b0}};
            qualified_q <= {EDGE_WIDTH{1'b0}};
            edge_seen_q <= 1'b0;
            failure_code_o <= 2'd0;
        end else begin
            if (heartbeat_edge) begin
                quiet_q <= {QUIET_WIDTH{1'b0}};
                edge_seen_q <= 1'b1;
            end else if (quiet_q != QUIET_LIMIT)
                quiet_q <= quiet_q + 1'b1;

            if (!enable_i) begin
                state_q <= DISABLED;
                hold_q <= {HOLD_WIDTH{1'b0}};
                qualified_q <= {EDGE_WIDTH{1'b0}};
                quiet_q <= {QUIET_WIDTH{1'b0}};
                edge_seen_q <= 1'b0;
                failure_code_o <= 2'd0;
            end else begin
                case (state_q)
                    DISABLED: state_q <= EXIT_HOLD;
                    EXIT_HOLD: begin
                        if (quiet_q == QUIET_LIMIT && !heartbeat_edge) begin
                            state_q <= FAILED;
                            failure_code_o <= 2'd1;
                        end else if (hold_q == HOLD_LIMIT) begin
                            state_q <= QUALIFY;
                            qualified_q <= {EDGE_WIDTH{1'b0}};
                        end else
                            hold_q <= hold_q + 1'b1;
                    end
                    QUALIFY: begin
                        if (quiet_q == QUIET_LIMIT && !heartbeat_edge) begin
                            state_q <= FAILED;
                            failure_code_o <= 2'd1;
                        end else if (heartbeat_edge) begin
                            if (qualified_q == EDGE_LIMIT)
                                state_q <= RUNNING;
                            else
                                qualified_q <= qualified_q + 1'b1;
                        end
                    end
                    RUNNING: begin
                        if (quiet_q == QUIET_LIMIT && !heartbeat_edge) begin
                            state_q <= FAILED;
                            failure_code_o <= 2'd2;
                        end
                    end
                    FAILED: begin end
                    default: begin
                        state_q <= FAILED;
                        failure_code_o <= 2'd3;
                    end
                endcase
            end
        end
    end
endmodule
