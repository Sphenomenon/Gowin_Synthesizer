// Recover USB3300 from serial/suspend mode, verify the ordinary ULPI bus,
// then hand a detached PHY to the high-speed protocol controller.
// This block deliberately does not attach the device or negotiate chirps.
module usb2_hs_boot #(
    parameter integer STARTUP_CYCLES = 32,
    parameter integer EXIT_MIN_CYCLES = 16,
    parameter integer TIMEOUT_CYCLES = 60000,
    parameter integer MAX_PREEMPTIONS = 3,
    parameter integer HANDOFF_GUARD_CYCLES = 4
) (
    input  wire        clk_ulpi60,
    input  wire        reset_n,
    input  wire [7:0]  data_i,
    output wire [7:0]  data_o,
    output wire        data_oe,
    output wire        drive_ready,
    input  wire        dir,
    input  wire        nxt,
    output wire        stp,
    output reg         done = 1'b0,
    output reg         error = 1'b0,
    output reg  [7:0]  stage = 8'h00,
    output reg  [15:0] vid = 16'h0000,
    output reg  [15:0] pid = 16'h0000
);
    localparam [3:0] S_EXIT=0, S_START=1, S_LOAD=2, S_WAIT_FREE=3,
                     S_CMD=4, S_W_DATA=5, S_W_STOP=6, S_W_RELEASE=7,
                     S_R_WAIT=8, S_R_DATA=9, S_R_RELEASE=10,
                     S_COMPLETE=11, S_HANDOFF=12, S_DONE=13;
    reg [3:0] state = S_EXIT;
    reg dir_q = 1'b0;
    reg [31:0] timer = 0, startup_timer = 0, handoff_guard = 0;
    reg [7:0] preemptions = 0;
    reg write_op = 0;
    reg [5:0] reg_addr = 0;
    reg [7:0] write_data = 0, read_data = 0;
    reg link_active = 0, drive_armed = 0;
    reg [7:0] drive_data = 8'h00;

    // Registered DATA and ownership keep the pad data path independent of
    // DIR. Raw DIR is used only at the final OE gate for immediate release;
    // dir_q suppresses drive for the PHY-to-link turnaround cycle.
    assign data_o = drive_data;
    assign data_oe = drive_armed && !dir;
    // Top-level per-pad safety LUT supplies the immediate DIR gate.
    assign drive_ready = drive_armed;
    // STP must work before CLKOUT is restored. It exits a previous IF=0Ah
    // serial mode or low-power state without FPGA driving any DATA pins.
    assign stp = !reset_n || state == S_EXIT || state == S_W_STOP;
    wire transaction_active = state >= S_WAIT_FREE && state <= S_R_RELEASE;

    task fail_boot;
        input [2:0] reason;
        begin
            done <= 1'b0;
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
            handoff_guard <= 0;
            preemptions <= 0;
            write_op <= 0;
            reg_addr <= 0;
            write_data <= 0;
            read_data <= 0;
            link_active <= 0;
            drive_armed <= 0;
            drive_data <= 8'h00;
            done <= 0;
            error <= 0;
            stage <= 0;
            vid <= 0;
            pid <= 0;
        end else begin
            dir_q <= dir;
            drive_armed <= link_active && !dir;
            drive_data <= 8'h00;
            if (transaction_active && timer >= TIMEOUT_CYCLES-1) begin
                fail_boot(3'd1);
            end else begin
                if (transaction_active) timer <= timer + 1'b1;
                case (state)
                    S_EXIT: begin
                        if (timer >= TIMEOUT_CYCLES-1) fail_boot(3'd1);
                        else begin
                            timer <= timer + 1'b1;
                            if (timer >= EXIT_MIN_CYCLES-1 && !dir && !dir_q) begin
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
                            8'h0b: begin reg_addr<=6'h07; write_op<=1; write_data<=8'h00; end
                            8'h0c: reg_addr <= 6'h07;
                            8'h0d: begin reg_addr<=6'h0a; write_op<=1; write_data<=8'h00; end
                            8'h0e: reg_addr <= 6'h0a;
                            default: fail_boot(3'd3);
                        endcase
                    end
                    S_WAIT_FREE: begin
                        if (!dir && !dir_q && !nxt) begin
                            drive_data <= {write_op ? 2'b10 : 2'b11, reg_addr};
                            state <= S_CMD;
                        end
                    end
                    S_CMD: begin
                        if (dir) begin
                            if (preemptions >= MAX_PREEMPTIONS-1) fail_boot(3'd2);
                            else begin
                                preemptions <= preemptions + 1'b1;
                                state <= S_WAIT_FREE;
                            end
                        end else if (!dir_q && nxt) begin
                            if (write_op) begin
                                drive_data <= write_data;
                                state <= S_W_DATA;
                            end else state <= S_R_WAIT;
                        end else drive_data <= {write_op ? 2'b10 : 2'b11, reg_addr};
                    end
                    S_W_DATA: begin
                        if (dir) fail_boot(3'd7);
                        else if (nxt) state <= S_W_STOP;
                        else drive_data <= write_data;
                    end
                    S_W_STOP: begin
                        if (dir) fail_boot(3'd7);
                        else state <= S_W_RELEASE;
                    end
                    S_W_RELEASE: begin
                        if (!dir && !dir_q && !nxt) state <= S_COMPLETE;
                    end
                    S_R_WAIT: begin
                        if (dir) state <= S_R_DATA;
                    end
                    S_R_DATA: begin
                        if (!dir || !dir_q || nxt) fail_boot(3'd3);
                        else begin
                            read_data <= data_i;
                            state <= S_R_RELEASE;
                        end
                    end
                    S_R_RELEASE: begin
                        if (!dir && !dir_q) state <= S_COMPLETE;
                    end
                    S_COMPLETE: begin
                        state <= S_LOAD;
                        stage <= stage + 1'b1;
                        case (stage)
                            8'h01: vid[7:0] <= read_data;
                            8'h02: vid[15:8] <= read_data;
                            8'h03: pid[7:0] <= read_data;
                            8'h04: begin
                                pid[15:8] <= read_data;
                                if (vid != 16'h0424 ||
                                    {read_data, pid[7:0]} != 16'h0004) fail_boot(3'd4);
                            end
                            8'h06: if (read_data != 8'h55) fail_boot(3'd5);
                            8'h08: if (read_data != 8'haa) fail_boot(3'd5);
                            8'h0a: if (read_data != 8'h41) fail_boot(3'd6);
                            8'h0c, 8'h0e: if (read_data != 8'h00) fail_boot(3'd6);
                            default: begin end
                        endcase
                        if (stage == 8'h0e && read_data == 8'h00) begin
                            timer <= 0;
                            handoff_guard <= 0;
                            state <= S_HANDOFF;
                        end
                    end
                    S_HANDOFF: begin
                        if (timer >= TIMEOUT_CYCLES-1) fail_boot(3'd1);
                        else begin
                            timer <= timer + 1'b1;
                            if (dir || dir_q || nxt) handoff_guard <= 0;
                            else if (handoff_guard >= HANDOFF_GUARD_CYCLES-1) begin
                                link_active <= 0;
                                drive_armed <= 0;
                                done <= 1;
                                stage <= 8'h12;
                                state <= S_DONE;
                            end else handoff_guard <= handoff_guard + 1'b1;
                        end
                    end
                    S_DONE: begin end
                    default: fail_boot(3'd3);
                endcase
            end
        end
    end
endmodule
