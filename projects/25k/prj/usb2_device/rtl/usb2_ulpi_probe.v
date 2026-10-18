// USB3300 ULPI register-only bring-up. This is not a USB packet/device core.
// Datasheet DS00001783C: VID 0424, PID 0004; FS peripheral FC=45 IF=00 OTG=00.
module usb2_ulpi_probe #(
    parameter integer STARTUP_CYCLES = 32,
    parameter integer TIMEOUT_CYCLES = 60000,
    parameter integer MAX_PREEMPTIONS = 3
) (
    input  wire        clk_ulpi60,
    input  wire        reset_n,
    inout  wire [7:0]  ulpi_data,
    input  wire        ulpi_dir,
    input  wire        ulpi_nxt,
    output wire        ulpi_stp,
    output reg         probe_done = 1'b0,
    output reg         id_ok = 1'b0,
    output reg         scratch_ok = 1'b0,
    output reg         error = 1'b0,
    output reg  [7:0]  stage = 8'h00,
    output reg  [15:0] vendor_id = 16'h0000,
    output reg  [15:0] product_id = 16'h0000,
    output reg  [7:0]  func_ctrl = 8'h00,
    output reg  [7:0]  if_ctrl = 8'h00,
    output reg  [7:0]  otg_ctrl = 8'h00,
    output reg  [7:0]  last_read = 8'h00,
    output reg  [15:0] rxcmd_count = 16'h0000,
    output reg  [15:0] rxdata_count = 16'h0000
);
    localparam [3:0] S_START=0, S_LOAD=1, S_WAIT_FREE=2, S_CMD=3,
                     S_W_DATA=4, S_W_STOP=5, S_W_RELEASE=6,
                     S_R_WAIT=7, S_R_DATA=8, S_R_RELEASE=9,
                     S_COMPLETE=10, S_DONE=11;
    reg [3:0] state = S_START;
    reg dir_q = 1'b0;
    reg [31:0] timer = 0;
    reg [31:0] startup_timer = 0;
    reg [7:0] preemptions = 0;
    reg write_op = 0;
    reg [5:0] reg_addr = 0;
    reg [7:0] write_data = 0;
    reg [7:0] read_data = 0;

    // Raw DIR immediately removes FPGA drive. dir_q additionally preserves
    // the full PHY->Link turnaround cycle after DIR drops.
    wire drive_en = reset_n && !ulpi_dir && !dir_q;
    wire [7:0] drive_data = state == S_CMD ?
                           {write_op ? 2'b10 : 2'b11, reg_addr} :
                           state == S_W_DATA ? write_data : 8'h00;
    assign ulpi_data = drive_en ? drive_data : 8'hzz;
    // Startup protection is asserted even before a 60 MHz clock exists.
    assign ulpi_stp = !reset_n || state == S_W_STOP;

    wire transaction_active = state >= S_WAIT_FREE && state <= S_R_RELEASE;
    task fail_probe;
        input [2:0] reason;
        begin
            probe_done <= 1'b1;
            error <= 1'b1;
            stage <= {reason, stage[4:0]};
            state <= S_DONE;
        end
    endtask

    always @(posedge clk_ulpi60 or negedge reset_n) begin
        if (!reset_n) begin
            state <= S_START;
            dir_q <= 1'b0;
            timer <= 0;
            startup_timer <= 0;
            preemptions <= 0;
            write_op <= 0;
            reg_addr <= 0;
            write_data <= 0;
            read_data <= 0;
            probe_done <= 0;
            id_ok <= 0;
            scratch_ok <= 0;
            error <= 0;
            stage <= 0;
            vendor_id <= 0;
            product_id <= 0;
            func_ctrl <= 0;
            if_ctrl <= 0;
            otg_ctrl <= 0;
            last_read <= 0;
            rxcmd_count <= 0;
            rxdata_count <= 0;
        end else begin
            dir_q <= ulpi_dir;
            // These count ULPI bytes, not USB packets. Register-read return
            // bytes and both DIR turnaround cycles are excluded.
            if (ulpi_dir && dir_q && state != S_R_DATA &&
                state != S_R_RELEASE && state != S_R_WAIT) begin
                if (ulpi_nxt) begin
                    if (rxdata_count != 16'hffff)
                        rxdata_count <= rxdata_count + 1'b1;
                end else begin
                    if (rxcmd_count != 16'hffff)
                        rxcmd_count <= rxcmd_count + 1'b1;
                end
            end

            if (transaction_active && timer >= TIMEOUT_CYCLES-1) begin
                fail_probe(3'd1);
            end else begin
                if (transaction_active) timer <= timer + 1'b1;
                case (state)
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
                            8'h05: reg_addr <= 6'h04;
                            8'h06: reg_addr <= 6'h07;
                            8'h07: reg_addr <= 6'h0a;
                            8'h08: begin reg_addr<=6'h16; write_op<=1; write_data<=8'h55; end
                            8'h09: reg_addr <= 6'h16;
                            8'h0a: begin reg_addr<=6'h16; write_op<=1; write_data<=8'haa; end
                            8'h0b: reg_addr <= 6'h16;
                            8'h0c: begin reg_addr<=6'h07; write_op<=1; write_data<=8'h00; end
                            8'h0d: begin reg_addr<=6'h0a; write_op<=1; write_data<=8'h00; end
                            8'h0e: begin reg_addr<=6'h04; write_op<=1; write_data<=8'h45; end
                            8'h0f: reg_addr <= 6'h07;
                            8'h10: reg_addr <= 6'h0a;
                            8'h11: reg_addr <= 6'h04;
                            default: fail_probe(3'd3);
                        endcase
                    end
                    S_WAIT_FREE: begin
                        if (!ulpi_dir && !dir_q && !ulpi_nxt)
                            state <= S_CMD;
                    end
                    S_CMD: begin
                        if (ulpi_dir) begin
                            // No accepted command exists yet. A PHY receive or
                            // RxCmd owns the bus; retry only after turnaround.
                            if (preemptions >= MAX_PREEMPTIONS-1)
                                fail_probe(3'd2);
                            else begin
                                preemptions <= preemptions + 1'b1;
                                state <= S_WAIT_FREE;
                            end
                        end else if (!dir_q && ulpi_nxt) begin
                            if (write_op) state <= S_W_DATA;
                            else state <= S_R_WAIT;
                        end
                    end
                    S_W_DATA: begin
                        if (ulpi_dir) fail_probe(3'd7);
                        else if (ulpi_nxt) state <= S_W_STOP;
                    end
                    S_W_STOP: begin
                        if (ulpi_dir) fail_probe(3'd7);
                        else state <= S_W_RELEASE;
                    end
                    S_W_RELEASE: begin
                        if (!ulpi_dir && !dir_q && !ulpi_nxt)
                            state <= S_COMPLETE;
                    end
                    S_R_WAIT: begin
                        // First sampled DIR=1 is the Link->PHY turnaround.
                        if (ulpi_dir) state <= S_R_DATA;
                    end
                    S_R_DATA: begin
                        if (!ulpi_dir || !dir_q || ulpi_nxt)
                            fail_probe(3'd3);
                        else begin
                            read_data <= ulpi_data;
                            last_read <= ulpi_data;
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
                                    {read_data,product_id[7:0]} == 16'h0004)
                                    id_ok <= 1;
                                else fail_probe(3'd4);
                            end
                            8'h05: func_ctrl <= read_data;
                            8'h06: if_ctrl <= read_data;
                            8'h07: otg_ctrl <= read_data;
                            8'h09: if (read_data != 8'h55) fail_probe(3'd5);
                            8'h0b: begin
                                if (read_data == 8'haa) scratch_ok <= 1;
                                else fail_probe(3'd5);
                            end
                            8'h0f: begin
                                if_ctrl <= read_data;
                                if (read_data != 8'h00) fail_probe(3'd6);
                            end
                            8'h10: begin
                                otg_ctrl <= read_data;
                                if (read_data != 8'h00) fail_probe(3'd6);
                            end
                            8'h11: begin
                                func_ctrl <= read_data;
                                if (read_data != 8'h45) fail_probe(3'd6);
                                else begin
                                    probe_done <= 1;
                                    stage <= 8'h12;
                                    state <= S_DONE;
                                end
                            end
                            default: begin end
                        endcase
                    end
                    S_DONE: begin end
                    default: fail_probe(3'd3);
                endcase
            end
        end
    end
endmodule
