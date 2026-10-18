// USB3300 ULPI setup followed by 3-pin Full-Speed serial-mode handover.
// DS00001783C sections 6.1.4, 6.1.5, 6.1.9.3 and 6.1.10.
// This module does not transmit USB packets. After init_done it releases all
// DATA pins and leaves STP low; the external serial pad mux takes ownership.
module usb2_serial_init #(
    parameter integer STARTUP_CYCLES = 32,
    parameter integer EXIT_MIN_CYCLES = 16,
    parameter integer TIMEOUT_CYCLES = 60000,
    parameter integer MAX_PREEMPTIONS = 3,
    parameter integer SERIAL_GUARD_CYCLES = 16,
    parameter integer DEBUG_SETTLE_CYCLES = 6000
) (
    input  wire        clk_ulpi60,
    input  wire        reset_n,
    input  wire        attach_request,
    input  wire [7:0]  ulpi_data_i,
    output wire [7:0]  ulpi_data_o,
    output wire        ulpi_data_oe,
    input  wire        ulpi_dir,
    input  wire        ulpi_nxt,
    output wire        ulpi_stp,
    output reg         init_done = 1'b0,
    output reg         error = 1'b0,
    output reg  [7:0]  stage = 8'h00,
    output reg  [15:0] vendor_id = 16'h0000,
    output reg  [15:0] product_id = 16'h0000,
    output reg         id_ok = 1'b0,
    output reg  [7:0]  func_ctrl = 8'h00,
    output reg  [7:0]  if_ctrl = 8'h00,
    output reg  [7:0]  otg_ctrl = 8'h00,
    output reg  [7:0]  phy_debug = 8'h00
);
    localparam [3:0] S_EXIT=0, S_START=1, S_LOAD=2, S_WAIT_FREE=3,
                     S_CMD=4, S_W_DATA=5, S_W_STOP=6, S_W_RELEASE=7,
                     S_R_WAIT=8, S_R_DATA=9, S_R_RELEASE=10,
                     S_COMPLETE=11, S_ATTACH=12, S_MODE=13, S_DONE=14,
                     S_DIAG_WAIT=15;
    reg [3:0] state = S_EXIT;
    reg dir_q = 1'b0;
    reg [31:0] timer = 0;
    reg [31:0] startup_timer = 0;
    reg [31:0] mode_timer = 0;
    reg [31:0] mode_guard = 0;
    reg [31:0] diagnostic_timer = 0;
    reg [7:0] preemptions = 0;
    reg write_op = 0;
    reg [5:0] reg_addr = 0;
    reg [7:0] write_data = 0;
    reg [7:0] read_data = 0;
    reg mode_pending = 0;
    reg link_active = 0;
    reg drive_armed = 0;
    reg [7:0] drive_data = 8'h00;

    // DIR immediately removes drive; dir_q keeps the return turnaround free.
    // During mode entry ALL pins remain high-Z, even if DIR falls unexpectedly.
    // Precompute the registered ownership/turnaround qualification so raw
    // DIR only crosses the final pad-enable gate. Keep drive_armed equal to
    // link_active && !dir_q at every edge, including ownership transitions.
    wire drive_en = drive_armed && !ulpi_dir;
    // Load the next state's bus value at the same edge as its state change.
    // This preserves command/data hold timing without decoding the FSM on
    // the pad data path. All other states drive ULPI Idle (00h).
    // Keep the raw DIR safety path in output-enable only. The top-level pad
    // mux owns the single IOB; placing a tristate here can synthesize DIR into
    // the data path when ULPI and serial pin owners share the same pads.
    assign ulpi_data_o = drive_data;
    assign ulpi_data_oe = drive_en;
    // STP works asynchronously before CLKOUT starts and exits a previous
    // serial/suspended state. An ambiguous mode-entry failure also requests
    // exit while keeping DATA high-Z. Success keeps STP low indefinitely.
    assign ulpi_stp = !reset_n || state == S_EXIT || state == S_W_STOP ||
                      (error && mode_pending);

    wire transaction_active = state >= S_WAIT_FREE && state <= S_R_RELEASE;
    task fail_init;
        input [2:0] reason;
        begin
            init_done <= 1'b0;
            error <= 1'b1;
            link_active <= 1'b0;
            drive_armed <= 1'b0;
            drive_data <= 8'h00;
            stage <= {reason, stage[4:0]};
            state <= S_DONE;
        end
    endtask

    always @(posedge clk_ulpi60 or negedge reset_n) begin
        if (!reset_n) begin
            state <= S_EXIT;
            dir_q <= 1'b0;
            timer <= 0;
            startup_timer <= 0;
            mode_timer <= 0;
            mode_guard <= 0;
            diagnostic_timer <= 0;
            preemptions <= 0;
            write_op <= 0;
            reg_addr <= 0;
            write_data <= 0;
            read_data <= 0;
            mode_pending <= 0;
            link_active <= 0;
            drive_armed <= 0;
            drive_data <= 8'h00;
            init_done <= 0;
            error <= 0;
            stage <= 0;
            vendor_id <= 0;
            product_id <= 0;
            id_ok <= 0;
            func_ctrl <= 0;
            if_ctrl <= 0;
            otg_ctrl <= 0;
            phy_debug <= 0;
        end else begin
            dir_q <= ulpi_dir;
            drive_armed <= link_active && !ulpi_dir;
            drive_data <= 8'h00;
            if (transaction_active && timer >= TIMEOUT_CYCLES-1) begin
                fail_init(3'd1);
            end else begin
                if (transaction_active) timer <= timer + 1'b1;
                case (state)
                    S_EXIT: begin
                        // STP remains high until clocks exist, a minimum hold
                        // elapsed, and DIR has returned low for a full cycle.
                        if (timer >= TIMEOUT_CYCLES-1) fail_init(3'd1);
                        else begin
                            timer <= timer + 1'b1;
                            if (timer >= EXIT_MIN_CYCLES-1 && !ulpi_dir && !dir_q) begin
                                startup_timer <= 0;
                                link_active <= 1'b1;
                                drive_armed <= 1'b1;
                                state <= S_START;
                            end
                        end
                    end
                    S_START: begin
                        if (startup_timer >= STARTUP_CYCLES-1) begin
                            stage <= 8'h01;
                            state <= S_LOAD;
                        end else startup_timer <= startup_timer + 1'b1;
                    end
                    S_LOAD: begin
                        write_op <= 0;
                        write_data <= 0;
                        timer <= 0;
                        preemptions <= 0;
                        state <= S_WAIT_FREE;
                        case (stage)
                            8'h01: reg_addr <= 6'h00;
                            8'h02: reg_addr <= 6'h01;
                            8'h03: reg_addr <= 6'h02;
                            8'h04: reg_addr <= 6'h03;
                            8'h05: begin reg_addr<=6'h16; write_op<=1; write_data<=8'h55; end
                            8'h06: reg_addr <= 6'h16;
                            8'h07: begin reg_addr<=6'h16; write_op<=1; write_data<=8'haa; end
                            8'h08: reg_addr <= 6'h16;
                            8'h09: begin reg_addr<=6'h04; write_op<=1; write_data<=8'h41; end
                            8'h0a: reg_addr <= 6'h04;
                            8'h0b: begin reg_addr<=6'h0a; write_op<=1; write_data<=8'h00; end
                            8'h0c: reg_addr <= 6'h0a;
                            8'h0d: begin reg_addr<=6'h07; write_op<=1; write_data<=8'h08; end
                            8'h0e: reg_addr <= 6'h07;
                            8'h10: begin reg_addr<=6'h04; write_op<=1; write_data<=8'h45; end
                            8'h11: reg_addr <= 6'h04;
                            8'h12: begin reg_addr<=6'h07; write_op<=1; write_data<=8'h0a; end
                            8'h15: reg_addr <= 6'h15;
                            8'h16: reg_addr <= 6'h13;
                            default: fail_init(3'd3);
                        endcase
                    end
                    S_WAIT_FREE: begin
                        if (!ulpi_dir && !dir_q && !ulpi_nxt) begin
                            drive_data <= {write_op ? 2'b10 : 2'b11, reg_addr};
                            state <= S_CMD;
                        end
                    end
                    S_CMD: begin
                        if (ulpi_dir) begin
                            if (preemptions >= MAX_PREEMPTIONS-1) fail_init(3'd2);
                            else begin
                                preemptions <= preemptions + 1'b1;
                                state <= S_WAIT_FREE;
                            end
                        end else if (!dir_q && ulpi_nxt) begin
                            if (write_op) begin
                                drive_data <= write_data;
                                state <= S_W_DATA;
                            end
                            else state <= S_R_WAIT;
                        end else drive_data <= {write_op ? 2'b10 : 2'b11, reg_addr};
                    end
                    S_W_DATA: begin
                        if (ulpi_dir) fail_init(3'd7);
                        else if (ulpi_nxt) begin
                            if (stage == 8'h12) mode_pending <= 1'b1;
                            state <= S_W_STOP;
                        end else drive_data <= write_data;
                    end
                    S_W_STOP: begin
                        if (ulpi_dir) fail_init(3'd7);
                        else if (stage == 8'h12) begin
                            // The final write intentionally changes the bus
                            // protocol. Do NOT wait for ordinary ULPI release.
                            if_ctrl <= 8'h0a; // write shadow, not post-mode readback
                            link_active <= 1'b0;
                            drive_armed <= 1'b0;
                            stage <= 8'h13;
                            mode_timer <= 0;
                            mode_guard <= 0;
                            state <= S_MODE;
                        end else state <= S_W_RELEASE;
                    end
                    S_W_RELEASE: begin
                        if (!ulpi_dir && !dir_q && !ulpi_nxt) state <= S_COMPLETE;
                    end
                    S_R_WAIT: begin
                        if (ulpi_dir) state <= S_R_DATA; // first high is turnaround
                    end
                    S_R_DATA: begin
                        if (!ulpi_dir || !dir_q || ulpi_nxt) fail_init(3'd3);
                        else begin
                            read_data <= ulpi_data_i;
                            state <= S_R_RELEASE;
                        end
                    end
                    S_R_RELEASE: begin
                        if (!ulpi_dir && !dir_q) state <= S_COMPLETE;
                    end
                    S_COMPLETE: begin
                        state <= S_LOAD;
                        stage <= stage + 1'b1;
                        case (stage)
                            8'h01: vendor_id[7:0] <= read_data;
                            8'h02: vendor_id[15:8] <= read_data;
                            8'h03: product_id[7:0] <= read_data;
                            8'h04: begin
                                product_id[15:8] <= read_data;
                                if (vendor_id == 16'h0424 &&
                                    {read_data, product_id[7:0]} == 16'h0004) id_ok <= 1;
                                else fail_init(3'd4);
                            end
                            8'h06: if (read_data != 8'h55) fail_init(3'd5);
                            8'h08: if (read_data != 8'haa) fail_init(3'd5);
                            8'h0a: begin
                                func_ctrl <= read_data;
                                if (read_data != 8'h41) fail_init(3'd6);
                            end
                            8'h0c: begin
                                otg_ctrl <= read_data;
                                if (read_data != 8'h00) fail_init(3'd6);
                            end
                            8'h0e: begin
                                if_ctrl <= read_data;
                                if (read_data != 8'h08) fail_init(3'd6);
                                else state <= S_ATTACH;
                            end
                            8'h11: begin
                                func_ctrl <= read_data;
                                if (read_data != 8'h45) fail_init(3'd6);
                                else begin
                                    stage <= 8'h15;
                                    diagnostic_timer <= 0;
                                    state <= S_DIAG_WAIT;
                                end
                            end
                            8'h15: begin
                                phy_debug <= {6'b0, read_data[1:0]};
                                stage <= 8'h16;
                            end
                            8'h16: begin
                                phy_debug[3:2] <= {read_data[3], read_data[2]};
                                stage <= 8'h12;
                            end
                            default: begin end
                        endcase
                    end
                    S_ATTACH: begin
                        // The protocol core counts its existing 2-second
                        // attach delay independently. No operation timeout
                        // applies while this explicit request is absent.
                        if (attach_request) begin
                            stage <= 8'h10;
                            state <= S_LOAD;
                        end
                    end
                    S_DIAG_WAIT: begin
                        // Let the enabled D+ pull-up and cable line settle
                        // before taking read-only line/session snapshots.
                        // This wait is not part of any ULPI transaction and
                        // deliberately does not consume its timeout budget.
                        if (diagnostic_timer >= DEBUG_SETTLE_CYCLES-1)
                            state <= S_LOAD;
                        else diagnostic_timer <= diagnostic_timer + 1'b1;
                    end
                    S_MODE: begin
                        // DS00001783C says entry asserts DIR and takes at least
                        // 5 clocks. There is no separate serial-ready indication
                        // or specified maximum latency with CLKOUT retained.
                        // Wait 16 consecutive DIR-high clocks (default), with
                        // DATA high-Z throughout. This is a conservative guard,
                        // NOT a readback proof that the analog serial path works.
                        if (mode_timer >= TIMEOUT_CYCLES-1) fail_init(3'd1);
                        else begin
                            mode_timer <= mode_timer + 1'b1;
                            if (!ulpi_dir) mode_guard <= 0;
                            else if (mode_guard >= SERIAL_GUARD_CYCLES-1) begin
                                stage <= 8'h14;
                                init_done <= 1'b1;
                                state <= S_DONE;
                            end else mode_guard <= mode_guard + 1'b1;
                        end
                    end
                    S_DONE: begin end
                    default: fail_init(3'd3);
                endcase
            end
        end
    end
endmodule
