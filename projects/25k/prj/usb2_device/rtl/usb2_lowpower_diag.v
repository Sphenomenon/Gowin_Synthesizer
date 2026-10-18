// USB3300 low-power direct-LineState diagnostic, DS00001783C 6.1.9/Table 6-6.
// The 50 MHz clock never stops. It alone qualifies stopped CLKOUT, samples the
// asynchronous low-power DATA[1:0], and owns every timeout and wake request.
module usb2_lowpower_diag #(
    parameter integer TIMEOUT_CYCLES = 10000000,
    parameter integer STARTUP_CYCLES = 32,
    parameter integer CLOCK_QUIET_CYCLES = 50000,
    parameter integer SETTLE_CYCLES = 500000,
    parameter integer SAMPLE_GAP_CYCLES = 50000,
    parameter integer SAMPLES_PER_PHASE = 16,
    parameter [7:0] FS_OTG_CTRL = 8'h00
) (
    input wire clk50, clk60, reset_n,
    input wire [7:0] data_i,
    input wire dir, nxt,
    output wire [7:0] data_o,
    output wire drive_ready,
    output wire stp,
    output reg done = 0, error = 0,
    output reg [3:0] errorcode = 0,
    output reg [7:0] stage = 0,
    output reg id_ok = 0,
    output reg [15:0] vid = 0, pid = 0,
    output reg [7:0] fc = 0, if_ctrl = 0, otg = 0,
    output reg [15:0] direct_masks = 0,
    output reg [7:0] direct_last = 0,
    output reg [15:0] phase_flags = 0,
    output reg [31:0] sample_counts = 0,
    output reg clock_alive = 0,
    output reg clock_stop_seen = 0
);
    localparam [3:0] Q_START=0, Q_GUARD=1, Q_ISSUE=2, Q_ACK=3,
                     Q_STOP=4, Q_SETTLE=5, Q_SAMPLE=6, Q_WAKE=7,
                     Q_WAKE_GUARD=8, Q_DONE=9, Q_RESUME=10;
    reg [3:0] qstate = Q_START;
    reg [31:0] timer50 = 0, delay50 = 0;
    reg [1:0] phase = 0;
    reg [4:0] operation = 0;
    reg initial_ops = 1;
    reg [7:0] sample_number = 0;
    reg run_request50 = 1;
    reg force_stp50 = 1;
    reg request_toggle50 = 0;
    reg request_write50 = 0, request_suspend50 = 0;
    reg [5:0] request_addr50 = 0;
    reg [7:0] request_data50 = 0;
    (* syn_preserve=1 *) reg reset_meta60 = 0, reset_sync60 = 0;
    wire ack_toggle60, master_awake60, master_ready60, master_stp60;
    wire [7:0] response_data60;
    wire response_error60;
    (* syn_preserve=1 *) reg ack_meta50 = 0, ack_sync50 = 0;
    (* syn_preserve=1 *) reg awake_meta50 = 0, awake_sync50 = 0;
    (* syn_preserve=1 *) reg response_error_meta50 = 0, response_error_sync50 = 0;
    (* syn_preserve=1 *) reg [7:0] response_data_meta50 = 0, response_data_sync50 = 0;
    (* syn_preserve=1 *) reg dir_meta50 = 0, dir_sync50 = 0;
    (* syn_preserve=1 *) reg [1:0] line_meta50 = 0, line_sync50 = 0;
    reg [15:0] clock_binary60 = 0;
    (* syn_preserve=1 *) reg [15:0] clock_gray60 = 0;
    (* syn_preserve=1 *) reg [15:0] clock_gray_meta50 = 0, clock_gray_sync50 = 0;
    reg [15:0] clock_gray_prev50 = 0;
    reg [31:0] clock_quiet50 = 0;
    wire [7:0] target_fc = phase == 1 ? 8'h45 : phase == 2 ? 8'h46 : 8'h41;
    // Table 6-8: FS OTG04 keeps the DP pull-up and adds the DM pull-down.
    // Default 00 preserves the existing peripheral-only control.
    wire [7:0] target_otg = phase == 0 || phase == 3 ? 8'h06 :
                            phase == 1 ? FS_OTG_CTRL : 8'h00;

    // STP assertion is intentionally asynchronous to a stopped PHY clock.
    // run_request50 can only REMOVE output enable asynchronously; the master
    // registers the re-enable after its two-stage run synchronization.
    assign stp = !reset_n || force_stp50 || master_stp60;
    assign drive_ready = reset_n && run_request50 && master_ready60 && !error;
    usb2_lowpower_master u_master (
        .clk60(clk60), .reset_n(reset_sync60), .data_i(data_i), .dir(dir), .nxt(nxt),
        .run_request50(run_request50), .request_toggle50(request_toggle50),
        .request_write50(request_write50), .request_suspend50(request_suspend50),
        .request_addr50(request_addr50), .request_data50(request_data50),
        .data_o(data_o), .drive_ready(master_ready60), .stp(master_stp60),
        .awake(master_awake60), .ack_toggle(ack_toggle60),
        .response_data(response_data60), .response_error(response_error60)
    );

    always @(posedge clk60 or negedge reset_n) begin
        if (!reset_n) begin reset_meta60<=0; reset_sync60<=0; end
        else begin reset_meta60<=1; reset_sync60<=reset_meta60; end
    end

    // Gray counter CDC: constrain each clock_gray60 -> clock_gray_meta50 path
    // to <= one clk60 period. Keep meta50 -> sync50 timed normally; only the
    // asynchronous input into the first stage needs a CDC exception.
    always @(posedge clk60 or negedge reset_sync60) begin
        if (!reset_sync60) begin clock_binary60 <= 0; clock_gray60 <= 0; end
        else begin
            clock_binary60 <= clock_binary60 + 1'b1;
            clock_gray60 <= ((clock_binary60 + 16'd1) >> 1) ^ (clock_binary60 + 16'd1);
        end
    end
    always @(posedge clk50 or negedge reset_n) begin
        if (!reset_n) begin
            ack_meta50<=0; ack_sync50<=0; awake_meta50<=0; awake_sync50<=0;
            response_error_meta50<=0; response_error_sync50<=0;
            response_data_meta50<=0; response_data_sync50<=0;
            dir_meta50<=0; dir_sync50<=0; line_meta50<=0; line_sync50<=0;
            clock_gray_meta50<=0; clock_gray_sync50<=0; clock_gray_prev50<=0;
            clock_quiet50<=0; clock_alive<=0;
        end else begin
            ack_meta50<=ack_toggle60; ack_sync50<=ack_meta50;
            awake_meta50<=master_awake60; awake_sync50<=awake_meta50;
            response_error_meta50<=response_error60; response_error_sync50<=response_error_meta50;
            response_data_meta50<=response_data60; response_data_sync50<=response_data_meta50;
            dir_meta50<=dir; dir_sync50<=dir_meta50;
            line_meta50<=data_i[1:0]; line_sync50<=line_meta50;
            clock_gray_meta50<=clock_gray60; clock_gray_sync50<=clock_gray_meta50;
            clock_gray_prev50<=clock_gray_sync50;
            if (clock_gray_sync50 != clock_gray_prev50) begin
                clock_quiet50<=0; clock_alive<=1;
            end else if (clock_quiet50 < CLOCK_QUIET_CYCLES) begin
                clock_quiet50<=clock_quiet50+1'b1;
                if (clock_quiet50 >= CLOCK_QUIET_CYCLES-1) clock_alive<=0;
            end
        end
    end

    task fail_diag;
        input [3:0] reason;
        begin
            done<=0; error<=1; errorcode<=reason;
            run_request50<=0; force_stp50<=1; qstate<=Q_DONE;
        end
    endtask
    task issue_request;
        input wr;
        input [5:0] addr;
        input [7:0] value;
        input suspend_after;
        begin
            request_write50<=wr; request_addr50<=addr;
            request_data50<=value; request_suspend50<=suspend_after;
            request_toggle50<=!request_toggle50;
            timer50<=0; qstate<=Q_ACK;
        end
    endtask

    always @(posedge clk50 or negedge reset_n) begin
        if (!reset_n) begin
            qstate<=Q_START; timer50<=0; delay50<=0; phase<=0; operation<=0;
            initial_ops<=1; sample_number<=0;
            run_request50<=1; force_stp50<=1;
            request_toggle50<=0; request_write50<=0; request_suspend50<=0;
            request_addr50<=0; request_data50<=0;
            done<=0; error<=0; errorcode<=0; stage<=0; id_ok<=0;
            vid<=0; pid<=0; fc<=0; if_ctrl<=0; otg<=0;
            direct_masks<=0; direct_last<=0; phase_flags<=0; sample_counts<=0;
            clock_stop_seen<=0;
        end else if (qstate != Q_DONE) begin
            // This watchdog is independent of CLKOUT and covers every wait.
            if (timer50 >= TIMEOUT_CYCLES-1) fail_diag(1);
            else begin
                timer50<=timer50+1'b1;
                case (qstate)
                    Q_START: if (clock_alive && awake_sync50 && !dir_sync50) begin
                        force_stp50<=0; timer50<=0; delay50<=0; qstate<=Q_GUARD;
                    end
                    Q_GUARD: begin
                        if (delay50 >= STARTUP_CYCLES-1) begin
                            timer50<=0; qstate<=Q_ISSUE;
                        end else delay50<=delay50+1'b1;
                    end
                    Q_ISSUE: begin
                        if (initial_ops) begin
                            stage<=8'h01+operation;
                            case (operation)
                                0: issue_request(0,6'h00,0,0);
                                1: issue_request(0,6'h01,0,0);
                                2: issue_request(0,6'h02,0,0);
                                3: issue_request(0,6'h03,0,0);
                                4: issue_request(1,6'h16,8'h55,0);
                                5: issue_request(0,6'h16,0,0);
                                6: issue_request(1,6'h16,8'haa,0);
                                7: issue_request(0,6'h16,0,0);
                                8: issue_request(1,6'h07,8'h00,0);
                                9: issue_request(0,6'h07,0,0);
                                default: fail_diag(7);
                            endcase
                        end else begin
                            stage<=8'h20+{phase,4'b0000}+operation;
                            case (operation)
                                0: issue_request(1,6'h04,8'h41,0);
                                1: issue_request(0,6'h04,0,0);
                                2: issue_request(1,6'h0a,target_otg,0);
                                3: issue_request(0,6'h0a,0,0);
                                4: issue_request(1,6'h04,target_fc,0);
                                5: issue_request(0,6'h04,0,0);
                                6: issue_request(1,6'h07,8'h00,0);
                                7: issue_request(0,6'h07,0,0);
                                8: issue_request(1,6'h04,target_fc & 8'hbf,1);
                                9: issue_request(0,6'h04,0,0);
                                10: issue_request(0,6'h07,0,0);
                                default: fail_diag(7);
                            endcase
                        end
                    end
                    Q_ACK: if (ack_sync50 == request_toggle50) begin
                        timer50<=0;
                        if (response_error_sync50) fail_diag(2);
                        else if (initial_ops) begin
                            operation<=operation+1'b1; qstate<=Q_ISSUE;
                            case (operation)
                                0: vid[7:0]<=response_data_sync50;
                                1: vid[15:8]<=response_data_sync50;
                                2: pid[7:0]<=response_data_sync50;
                                3: begin
                                    pid[15:8]<=response_data_sync50;
                                    if (vid != 16'h0424 || {response_data_sync50,pid[7:0]} != 16'h0004) fail_diag(3);
                                    else id_ok<=1;
                                end
                                5: if (response_data_sync50 != 8'h55) fail_diag(4);
                                7: if (response_data_sync50 != 8'haa) fail_diag(4);
                                9: begin
                                    if_ctrl<=response_data_sync50;
                                    if (response_data_sync50 != 0) fail_diag(6);
                                    else begin initial_ops<=0; operation<=0; end
                                end
                                default: begin end
                            endcase
                        end else begin
                            operation<=operation+1'b1; qstate<=Q_ISSUE;
                            case (operation)
                                1: begin
                                    fc<=response_data_sync50;
                                    if (response_data_sync50 != 8'h41) fail_diag(6);
                                end
                                3: begin
                                    otg<=response_data_sync50;
                                    if (response_data_sync50 != target_otg) fail_diag(6);
                                end
                                5: begin
                                    fc<=response_data_sync50;
                                    if (response_data_sync50 != target_fc) fail_diag(6);
                                end
                                7: begin
                                    if_ctrl<=response_data_sync50;
                                    if (response_data_sync50 != 0) fail_diag(6);
                                end
                                8: begin
                                    run_request50<=0; qstate<=Q_STOP;
                                    stage<=8'h2b+{phase,4'b0000};
                                end
                                9: begin
                                    fc<=response_data_sync50;
                                    if (response_data_sync50 != target_fc) fail_diag(6);
                                end
                                10: begin
                                    if_ctrl<=response_data_sync50;
                                    if (response_data_sync50 != 0) fail_diag(6);
                                    else begin
                                        phase_flags[phase*4+3]<=1;
                                        if (phase==3) begin done<=1; stage<=8'h60; qstate<=Q_DONE; end
                                        else begin phase<=phase+1'b1; operation<=0; end
                                    end
                                end
                                default: begin end
                            endcase
                        end
                    end
                    Q_STOP: if (!clock_alive && dir_sync50) begin
                        clock_stop_seen<=1; phase_flags[phase*4+1]<=1;
                        delay50<=0; timer50<=0; qstate<=Q_SETTLE;
                    end
                    Q_SETTLE: begin
                        if (clock_alive || !dir_sync50) fail_diag(5);
                        else if (delay50 >= SETTLE_CYCLES-1) begin
                            timer50<=0; delay50<=0; sample_number<=0; qstate<=Q_SAMPLE;
                        end else delay50<=delay50+1'b1;
                    end
                    Q_SAMPLE: begin
                        if (clock_alive || !dir_sync50) fail_diag(5);
                        else if (delay50 == 0) begin
                            // Unknowns are rejected by simulation, and never
                            // manufacture a bit in the direct LineState mask.
                            case (line_sync50)
                                2'b00,2'b01,2'b10,2'b11: begin
                                    direct_masks[phase*4 +:4] <= direct_masks[phase*4 +:4] | (4'b0001 << line_sync50);
                                    direct_last[phase*2 +:2] <= line_sync50;
                                    sample_counts[phase*8 +:8] <= sample_number+1'b1;
                                    sample_number<=sample_number+1'b1;
                                    if (sample_number >= SAMPLES_PER_PHASE-1) begin
                                        phase_flags[phase*4]<=1;
                                        force_stp50<=1;
                                        timer50<=0; qstate<=Q_WAKE;
                                        stage<=8'h2c+{phase,4'b0000};
                                    end else delay50<=SAMPLE_GAP_CYCLES-1;
                                end
                                default: fail_diag(5);
                            endcase
                        end else delay50<=delay50-1'b1;
                    end
                    Q_WAKE: if (clock_alive && !dir_sync50) begin
                        // Keep run low while clocks restart, so even a PHY
                        // which stopped before seeing it observes the park
                        // handshake. Only then ask the master to drive Idle.
                        run_request50<=1; timer50<=0; qstate<=Q_RESUME;
                    end
                    Q_RESUME: if (clock_alive && awake_sync50 && !dir_sync50) begin
                        phase_flags[phase*4+2]<=1;
                        force_stp50<=0; delay50<=0; timer50<=0; qstate<=Q_WAKE_GUARD;
                    end
                    Q_WAKE_GUARD: begin
                        if (delay50 >= STARTUP_CYCLES-1) begin
                            operation<=9; timer50<=0; qstate<=Q_ISSUE;
                        end else delay50<=delay50+1'b1;
                    end
                    default: fail_diag(7);
                endcase
            end
        end
    end
endmodule

// Single outstanding toggle-mailbox ULPI register master. Request fields are
// held from issue until acknowledgement. Response fields are held until the
// next request. Suspend writes acknowledge at the end of their STOP cycle,
// release DATA immediately, and never wait for clocks or DIR to return low.
module usb2_lowpower_master (
    input wire clk60, reset_n,
    input wire [7:0] data_i,
    input wire dir, nxt,
    input wire run_request50, request_toggle50, request_write50, request_suspend50,
    input wire [5:0] request_addr50,
    input wire [7:0] request_data50,
    output reg [7:0] data_o = 0,
    output reg drive_ready = 0,
    output wire stp,
    output reg awake = 0,
    output reg ack_toggle = 0,
    output reg [7:0] response_data = 0,
    output reg response_error = 0
);
    localparam [3:0] M_PARK=0, M_IDLE=1, M_FREE=2, M_CMD=3, M_WDATA=4,
                     M_STOP=5, M_WRELEASE=6, M_RWAIT=7, M_RDATA=8, M_RRELEASE=9;
    reg [3:0] mstate = M_PARK;
    (* syn_preserve=1 *) reg run_meta60 = 0, run_sync60 = 0;
    (* syn_preserve=1 *) reg request_meta60 = 0, request_sync60 = 0;
    (* syn_preserve=1 *) reg write_meta60=0, write_sync60=0;
    (* syn_preserve=1 *) reg suspend_meta60=0, suspend_sync60=0;
    (* syn_preserve=1 *) reg [5:0] addr_meta60=0, addr_sync60=0;
    (* syn_preserve=1 *) reg [7:0] data_meta60=0, data_sync60=0;
    reg dir_q = 1;
    reg suspend_park = 0;
    reg write_op = 0, suspend_op = 0;
    reg [5:0] reg_addr = 0;
    reg [7:0] write_data = 0;
    reg [2:0] preemptions = 0;
    assign stp = mstate == M_STOP;
    task fail_master;
        begin
            response_error<=1; ack_toggle<=request_sync60;
            drive_ready<=0; awake<=0; data_o<=0;
            suspend_park<=1; mstate<=M_PARK;
        end
    endtask
    always @(posedge clk60 or negedge reset_n) begin
        if (!reset_n) begin
            run_meta60<=0; run_sync60<=0; request_meta60<=0; request_sync60<=0;
            write_meta60<=0; write_sync60<=0; suspend_meta60<=0; suspend_sync60<=0;
            addr_meta60<=0; addr_sync60<=0; data_meta60<=0; data_sync60<=0;
            mstate<=M_PARK; data_o<=0; drive_ready<=0; awake<=0;
            ack_toggle<=0; response_data<=0; response_error<=0;
            dir_q<=1; suspend_park<=0; write_op<=0; suspend_op<=0;
            reg_addr<=0; write_data<=0; preemptions<=0;
        end else begin
            run_meta60<=run_request50; run_sync60<=run_meta60;
            request_meta60<=request_toggle50; request_sync60<=request_meta60;
            write_meta60<=request_write50; write_sync60<=write_meta60;
            suspend_meta60<=request_suspend50; suspend_sync60<=suspend_meta60;
            addr_meta60<=request_addr50; addr_sync60<=addr_meta60;
            data_meta60<=request_data50; data_sync60<=data_meta60;
            dir_q<=dir;
            data_o<=0;
            drive_ready<=awake && !dir;
            if (!run_sync60) begin
                mstate<=M_PARK; suspend_park<=0;
                awake<=0; drive_ready<=0;
            end else case (mstate)
                M_PARK: begin
                    drive_ready<=0;
                    if (!suspend_park && !dir && !dir_q) begin
                        awake<=1; drive_ready<=1; mstate<=M_IDLE;
                    end
                end
                M_IDLE: if (request_sync60 != ack_toggle) begin
                    write_op<=write_sync60; suspend_op<=suspend_sync60;
                    reg_addr<=addr_sync60; write_data<=data_sync60;
                    response_error<=0; preemptions<=0; mstate<=M_FREE;
                end
                M_FREE: if (!dir && !dir_q && !nxt) begin
                    data_o<={write_op ? 2'b10 : 2'b11,reg_addr}; mstate<=M_CMD;
                end
                M_CMD: begin
                    if (dir) begin
                        if (preemptions >= 3) fail_master;
                        else begin preemptions<=preemptions+1'b1; mstate<=M_FREE; end
                    end else if (!dir_q && nxt) begin
                        if (write_op) begin data_o<=write_data; mstate<=M_WDATA; end
                        else mstate<=M_RWAIT;
                    end else data_o<={write_op ? 2'b10 : 2'b11,reg_addr};
                end
                M_WDATA: begin
                    if (dir) fail_master;
                    else if (nxt) mstate<=M_STOP;
                    else data_o<=write_data;
                end
                M_STOP: begin
                    if (dir && !suspend_op) fail_master;
                    else if (suspend_op) begin
                        // The just-completed STP pulse committed SuspendM=0.
                        // PHY may assert DIR and stop CLKOUT five edges later.
                        drive_ready<=0; awake<=0; suspend_park<=1;
                        ack_toggle<=request_sync60; mstate<=M_PARK;
                    end else mstate<=M_WRELEASE;
                end
                M_WRELEASE: if (!dir && !dir_q && !nxt) begin
                    ack_toggle<=request_sync60; mstate<=M_IDLE;
                end
                M_RWAIT: if (dir) mstate<=M_RDATA;
                M_RDATA: begin
                    if (!dir || !dir_q || nxt) fail_master;
                    else begin response_data<=data_i; mstate<=M_RRELEASE; end
                end
                M_RRELEASE: if (!dir && !dir_q) begin
                    ack_toggle<=request_sync60; mstate<=M_IDLE;
                end
                default: fail_master;
            endcase
        end
    end
endmodule
