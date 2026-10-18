// USB3300 digital termination diagnostic; no USB protocol or serial mode.
// Four phases: detached, FS D+ pull-up, LS D- pull-up, detached again.
// Register and termination definitions: DS00001783C sections 6.1.4/6.1.5/6.2.2.
module usb2_termination_probe #(
    parameter integer STARTUP_CYCLES = 32,
    parameter integer EXIT_MIN_CYCLES = 16,
    parameter integer TIMEOUT_CYCLES = 60000,
    parameter integer MAX_PREEMPTIONS = 3,
    parameter integer SETTLE_CYCLES = 600000,
    parameter integer SAMPLE_GAP_CYCLES = 60000,
    parameter integer SAMPLES_PER_PHASE = 16,
    parameter integer PHY_SOFT_RESET = 0,
    parameter integer RESET_WAIT_CYCLES = 60000,
    parameter integer FULL_SCRATCH_TEST = 0
) (
    input wire clk_ulpi60,
    input wire reset_n,
    input wire [7:0] ulpi_data_i,
    output wire [7:0] ulpi_data_o,
    output wire ulpi_data_oe,
    output wire ulpi_drive_ready,
    input wire ulpi_dir,
    input wire ulpi_nxt,
    output wire ulpi_stp,
    output reg done = 0,
    output reg error = 0,
    output reg [3:0] error_code = 0,
    output reg [7:0] stage = 0,
    output reg [15:0] vendor_id = 0,
    output reg [15:0] product_id = 0,
    output reg id_ok = 0,
    output reg [7:0] func_ctrl = 0,
    output reg [7:0] if_ctrl = 0,
    output reg [7:0] otg_ctrl = 0,
    output reg [15:0] line_seen_masks = 0,
    output reg [15:0] phase_last_status = 0,
    output reg [15:0] rxcmd_count = 0,
    output reg [15:0] rxdata_count = 0,
    output reg [15:0] rxcmd_seen_masks = 0,
    output reg [31:0] phase_last_rxcmd = 0,
    output reg [8:0] scratch_verified_count = 0,
    output reg [7:0] scratch_mismatch_expected = 0,
    output reg [7:0] scratch_mismatch_actual = 0
);
    localparam [3:0] S_EXIT=0, S_START=1, S_LOAD=2, S_WAIT_FREE=3,
                     S_CMD=4, S_W_DATA=5, S_W_STOP=6, S_W_RELEASE=7,
                     S_R_WAIT=8, S_R_DATA=9, S_R_RELEASE=10,
                     S_COMPLETE=11, S_SETTLE=12, S_GAP=13, S_DONE=14,
                     S_RESET_WAIT=15;
    reg [3:0] state = S_EXIT;
    reg dir_q = 0;
    reg [31:0] timer = 0, startup_timer = 0, wait_timer = 0;
    reg [31:0] sample_number = 0;
    reg [7:0] preemptions = 0;
    reg [1:0] phase = 0;
    reg [1:0] sampled_line = 0;
    reg write_op = 0;
    reg [5:0] reg_addr = 0;
    reg [7:0] write_data = 0, read_data = 0;
    reg link_active = 0, drive_armed = 0;
    reg [7:0] drive_data = 0;
    wire [7:0] target_fc = phase == 1 ? 8'h45 : phase == 2 ? 8'h46 : 8'h41;
    wire [7:0] target_otg = phase == 0 || phase == 3 ? 8'h06 : 8'h00;
    wire phase_stage = stage >= 8'h20 && stage <= 8'h58;
    wire transaction_active = state >= S_WAIT_FREE && state <= S_R_RELEASE;
    wire register_response = state == S_R_WAIT || state == S_R_DATA || state == S_R_RELEASE;

    // Only the final OE gate sees raw DIR. A high DIR releases immediately;
    // registered dir_q leaves the PHY->Link turnaround clock undriven.
    assign ulpi_data_o = drive_data;
    assign ulpi_data_oe = drive_armed && !ulpi_dir;
    assign ulpi_drive_ready = drive_armed;
    assign ulpi_stp = !reset_n || state == S_EXIT || state == S_W_STOP;

    task fail_probe;
        input [3:0] reason;
        begin
            done <= 0;
            error <= 1;
            error_code <= reason;
            link_active <= 0;
            drive_armed <= 0;
            drive_data <= 0;
            stage <= stage; // preserve the operation which failed
            state <= S_DONE;
        end
    endtask

    always @(posedge clk_ulpi60 or negedge reset_n) begin
        if (!reset_n) begin
            state <= S_EXIT;
            dir_q <= 0;
            timer <= 0;
            startup_timer <= 0;
            wait_timer <= 0;
            sample_number <= 0;
            preemptions <= 0;
            phase <= 0;
            sampled_line <= 0;
            write_op <= 0;
            reg_addr <= 0;
            write_data <= 0;
            read_data <= 0;
            link_active <= 0;
            drive_armed <= 0;
            drive_data <= 0;
            done <= 0;
            error <= 0;
            error_code <= 0;
            stage <= 0;
            vendor_id <= 0;
            product_id <= 0;
            id_ok <= 0;
            func_ctrl <= 0;
            if_ctrl <= 0;
            otg_ctrl <= 0;
            line_seen_masks <= 0;
            phase_last_status <= 0;
            rxcmd_count <= 0;
            rxdata_count <= 0;
            rxcmd_seen_masks <= 0;
            phase_last_rxcmd <= 0;
            scratch_verified_count <= 0;
            scratch_mismatch_expected <= 0;
            scratch_mismatch_actual <= 0;
        end else begin
            dir_q <= ulpi_dir;
            drive_armed <= link_active && !ulpi_dir;
            drive_data <= 0;

            // Only a complete PHY-owned cycle can be an unsolicited RX
            // transfer. Register-response bytes and both turnarounds do not
            // count. These counters are observations, not USB packet counts.
            if (link_active && !error && ulpi_dir && dir_q && !register_response) begin
                if (ulpi_nxt) begin
                    if (rxdata_count != 16'hffff) rxdata_count <= rxdata_count + 1'b1;
                end else begin
                    if (rxcmd_count != 16'hffff) rxcmd_count <= rxcmd_count + 1'b1;
                    // A zero phase mask means no unsolicited command was
                    // observed. Startup commands and register responses must
                    // never manufacture a phase line-state observation.
                    if (phase_stage) begin
                        rxcmd_seen_masks[phase*4 +: 4] <=
                            rxcmd_seen_masks[phase*4 +: 4] | (4'b0001 << ulpi_data_i[1:0]);
                        phase_last_rxcmd[phase*8 +: 8] <= ulpi_data_i;
                    end
                end
            end

            if (transaction_active && timer >= TIMEOUT_CYCLES-1) fail_probe(1);
            else begin
                if (transaction_active) timer <= timer + 1'b1;
                case (state)
                    S_EXIT: begin
                        if (timer >= TIMEOUT_CYCLES-1) fail_probe(1);
                        else begin
                            timer <= timer + 1'b1;
                            if (timer >= EXIT_MIN_CYCLES-1 && !ulpi_dir && !dir_q) begin
                                startup_timer <= 0;
                                link_active <= 1;
                                drive_armed <= 1;
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
                        if (phase_stage) begin
                            case (stage[3:0])
                                0: begin reg_addr<=6'h04; write_op<=1; write_data<=8'h41; end
                                1,5: reg_addr <= 6'h04;
                                2: begin reg_addr<=6'h0a; write_op<=1; write_data<=target_otg; end
                                3: reg_addr <= 6'h0a;
                                4: begin reg_addr<=6'h04; write_op<=1; write_data<=target_fc; end
                                7: reg_addr <= 6'h15;
                                8: reg_addr <= 6'h13;
                                default: fail_probe(3);
                            endcase
                        end else begin
                            case (stage)
                                8'h01: reg_addr <= 6'h00;
                                8'h02: reg_addr <= 6'h01;
                                8'h03: reg_addr <= 6'h02;
                                8'h04: reg_addr <= 6'h03;
                                8'h05: begin reg_addr<=6'h16; write_op<=1; write_data<=8'h55; end
                                8'h06: reg_addr <= 6'h16;
                                8'h07: begin reg_addr<=6'h16; write_op<=1; write_data<=8'haa; end
                                8'h08: reg_addr <= 6'h16;
                                8'h09: begin reg_addr<=6'h07; write_op<=1; write_data<=8'h08; end
                                8'h0a: reg_addr <= 6'h07;
                                8'h0b: begin reg_addr<=6'h04; write_op<=1; write_data<=8'h61; end
                                8'h0d: reg_addr <= 6'h04;
                                // The optional exhaustive bus test uses only
                                // the documented read/write Scratch register.
                                8'h10: begin reg_addr<=6'h16; write_op<=1; write_data<=scratch_verified_count[7:0]; end
                                8'h11: reg_addr <= 6'h16;
                                default: fail_probe(3);
                            endcase
                        end
                    end
                    S_WAIT_FREE: begin
                        if (!ulpi_dir && !dir_q && !ulpi_nxt) begin
                            drive_data <= {write_op ? 2'b10 : 2'b11, reg_addr};
                            state <= S_CMD;
                        end
                    end
                    S_CMD: begin
                        if (ulpi_dir) begin
                            if (preemptions >= MAX_PREEMPTIONS-1) fail_probe(2);
                            else begin
                                preemptions <= preemptions + 1'b1;
                                state <= S_WAIT_FREE;
                            end
                        end else if (!dir_q && ulpi_nxt) begin
                            if (write_op) begin drive_data <= write_data; state <= S_W_DATA; end
                            else state <= S_R_WAIT;
                        end else drive_data <= {write_op ? 2'b10 : 2'b11, reg_addr};
                    end
                    S_W_DATA: begin
                        if (ulpi_dir) fail_probe(7);
                        else if (ulpi_nxt) state <= S_W_STOP;
                        else drive_data <= write_data;
                    end
                    S_W_STOP: begin
                        if (ulpi_dir) fail_probe(7);
                        else state <= S_W_RELEASE;
                    end
                    S_W_RELEASE: begin
                        if (!ulpi_dir && !dir_q && !ulpi_nxt) state <= S_COMPLETE;
                    end
                    S_R_WAIT: if (ulpi_dir) state <= S_R_DATA;
                    S_R_DATA: begin
                        if (!ulpi_dir || !dir_q || ulpi_nxt) fail_probe(3);
                        else begin read_data <= ulpi_data_i; state <= S_R_RELEASE; end
                    end
                    S_R_RELEASE: if (!ulpi_dir && !dir_q) state <= S_COMPLETE;
                    S_COMPLETE: begin
                        state <= S_LOAD;
                        stage <= stage + 1'b1;
                        if (phase_stage) begin
                            case (stage[3:0])
                                1: begin
                                    func_ctrl <= read_data;
                                    if (read_data != 8'h41) fail_probe(6);
                                end
                                3: begin
                                    otg_ctrl <= read_data;
                                    if (read_data != target_otg) fail_probe(6);
                                end
                                5: begin
                                    func_ctrl <= read_data;
                                    if (read_data != target_fc) fail_probe(6);
                                    else begin wait_timer <= 0; state <= S_SETTLE; end
                                end
                                7: sampled_line <= read_data[1:0];
                                8: begin
                                    line_seen_masks[phase*4 +: 4] <=
                                        line_seen_masks[phase*4 +: 4] | (4'b0001 << sampled_line);
                                    phase_last_status[phase*4 +: 4] <=
                                        {read_data[3], read_data[2], sampled_line};
                                    sample_number <= sample_number + 1'b1;
                                    if (sample_number >= SAMPLES_PER_PHASE-1) begin
                                        sample_number <= 0;
                                        if (phase == 3) begin
                                            stage <= 8'h60;
                                            done <= 1;
                                            state <= S_DONE;
                                        end else begin
                                            phase <= phase + 1'b1;
                                            stage <= stage + 8'h08;
                                        end
                                    end else begin
                                        wait_timer <= 0;
                                        stage <= stage - 1'b1;
                                        state <= S_GAP;
                                    end
                                end
                                default: begin end
                            endcase
                        end else begin
                            case (stage)
                                8'h01: vendor_id[7:0] <= read_data;
                                8'h02: vendor_id[15:8] <= read_data;
                                8'h03: product_id[7:0] <= read_data;
                                8'h04: begin
                                    product_id[15:8] <= read_data;
                                    if (vendor_id == 16'h0424 && {read_data,product_id[7:0]} == 16'h0004) begin
                                        id_ok <= 1;
                                        if (FULL_SCRATCH_TEST) stage <= 8'h10;
                                    end
                                    else fail_probe(4);
                                end
                                8'h06: if (read_data != 8'h55) fail_probe(5);
                                8'h08: if (read_data != 8'haa) fail_probe(5);
                                8'h0a: begin
                                    if_ctrl <= read_data;
                                    if (read_data != 8'h08) fail_probe(6);
                                    else if (PHY_SOFT_RESET) stage <= 8'h0b;
                                    else begin stage <= 8'h20; phase <= 0; end
                                end
                                8'h0b: begin
                                    // Function Reset affects the transceiver,
                                    // not the ULPI interface/register set.
                                    wait_timer <= 0;
                                    state <= S_RESET_WAIT;
                                end
                                8'h0d: begin
                                    func_ctrl <= read_data;
                                    // The explicit completion interval is
                                    // bounded independently of transactions.
                                    if (read_data[5]) fail_probe(1);
                                    else if (read_data != 8'h41) fail_probe(6);
                                    else begin stage <= 8'h20; phase <= 0; end
                                end
                                8'h11: begin
                                    if (read_data != scratch_verified_count[7:0]) begin
                                        scratch_mismatch_expected <= scratch_verified_count[7:0];
                                        scratch_mismatch_actual <= read_data;
                                        fail_probe(5);
                                    end else begin
                                        scratch_verified_count <= scratch_verified_count + 1'b1;
                                        if (scratch_verified_count == 9'd255) stage <= 8'h05;
                                        else stage <= 8'h10;
                                    end
                                end
                                default: begin end
                            endcase
                        end
                    end
                    S_SETTLE: begin
                        if (wait_timer >= SETTLE_CYCLES-1) begin
                            stage <= stage + 1'b1;
                            state <= S_LOAD;
                        end else wait_timer <= wait_timer + 1'b1;
                    end
                    S_GAP: begin
                        if (wait_timer >= SAMPLE_GAP_CYCLES-1) state <= S_LOAD;
                        else wait_timer <= wait_timer + 1'b1;
                    end
                    S_RESET_WAIT: begin
                        if (wait_timer >= RESET_WAIT_CYCLES-1) begin
                            stage <= 8'h0d;
                            state <= S_LOAD;
                        end else wait_timer <= wait_timer + 1'b1;
                    end
                    // Keep ULPI idle driven after success. The last complete
                    // phase has read back FC41/OTG06; no device is attached.
                    S_DONE: begin end
                    default: fail_probe(3);
                endcase
            end
        end
    end
endmodule
