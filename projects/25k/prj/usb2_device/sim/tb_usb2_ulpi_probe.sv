`timescale 1ns/1ps
module tb_usb2_ulpi_probe;
    reg clk = 0;
    always #8.333 clk = !clk;
    reg reset_n = 0;
    tri [7:0] data;
    reg dir = 0, nxt = 0, phy_oe = 0;
    reg [7:0] phy_data = 0;
    wire stp, done, id_ok, scratch_ok, error;
    wire [7:0] stage, fc, ifc, otg, last_read;
    wire [15:0] vid, pid, rxcmd_count, rxdata_count;
    assign data = phy_oe ? phy_data : 8'hzz;
    usb2_ulpi_probe #(.STARTUP_CYCLES(4), .TIMEOUT_CYCLES(80)) dut (
        .clk_ulpi60(clk), .reset_n(reset_n), .ulpi_data(data),
        .ulpi_dir(dir), .ulpi_nxt(nxt), .ulpi_stp(stp),
        .probe_done(done), .id_ok(id_ok), .scratch_ok(scratch_ok),
        .error(error), .stage(stage), .vendor_id(vid), .product_id(pid),
        .func_ctrl(fc), .if_ctrl(ifc), .otg_ctrl(otg), .last_read(last_read),
        .rxcmd_count(rxcmd_count), .rxdata_count(rxdata_count)
    );

    // PHY model samples Link signals on clock edges, then updates its outputs
    // with nonblocking assignments. It does not use the Link's FSM to ACK.
    localparam P_IDLE=0, P_CMD_STALL=1, P_CMD_ACK=2, P_R_TURN=3,
               P_R_DATA=4, P_R_RELEASE=5, P_W_WAIT=6, P_W_DATA=7,
               P_W_STOP=8, P_W_RELEASE=9, P_RX_TURN=10,
               P_RX_CMD=11, P_RX_DATA=12, P_RX_RELEASE=13,
               P_SHORT=14, P_HOLD=15;
    integer ps = P_IDLE, stall = 0, scenario = 0;
    integer accepted = 0, writes = 0, reads = 0;
    reg [7:0] regs [0:63];
    reg [7:0] command_byte = 0, captured_write = 0;
    reg [5:0] addr = 0;
    reg wr = 0, preempted = 0, post_traffic = 0, post_sent = 0;
    integer i;
    always @(posedge clk) begin
        if (!reset_n) begin
            dir <= 0; nxt <= 0; phy_oe <= 0; phy_data <= 0;
            ps <= P_IDLE; stall <= 0; addr <= 0; wr <= 0;
            command_byte <= 0; captured_write <= 0;
            preempted <= 0; post_sent <= 0;
            accepted <= 0; writes <= 0; reads <= 0;
            for (i=0;i<64;i=i+1) regs[i] <= 0;
            regs[0] <= 8'h24; regs[1] <= 8'h04;
            regs[2] <= scenario == 2 ? 8'h07 : 8'h04;
            regs[3] <= 0; regs[4] <= 8'h41; regs[7] <= 0;
            regs[10] <= 8'h06;
        end else if (done && error) begin
            // Fault scenarios end at Link's bounded abort; release the modeled
            // PHY before resetting for the next independent scenario.
            dir <= 0; nxt <= 0; phy_oe <= 0; ps <= P_IDLE;
        end else begin
            case(ps)
                P_IDLE: begin
                    nxt <= 0; dir <= 0; phy_oe <= 0;
                    if (post_traffic && !post_sent) begin
                        post_sent <= 1; dir <= 1; ps <= P_RX_TURN;
                    end else if (!stp && (data[7:6] == 2'b10 || data[7:6] == 2'b11)) begin
                        if ((scenario == 0 && !preempted) || scenario == 6) begin
                            preempted <= 1; dir <= 1; ps <= P_RX_TURN;
                        end else begin
                            command_byte <= data; addr <= data[5:0]; wr <= !data[6];
                            stall <= 2 + data[1:0]; ps <= P_CMD_STALL;
                        end
                    end
                end
                P_CMD_STALL: begin
                    if (stp || data !== command_byte) $fatal(1,"command changed before NXT");
                    if (scenario != 3) begin
                        if (stall == 0) begin nxt <= 1; ps <= P_CMD_ACK; end
                        else stall <= stall - 1;
                    end
                end
                P_CMD_ACK: begin
                    if (stp || data !== command_byte) $fatal(1,"command invalid at ACK");
                    accepted <= accepted + 1;
                    nxt <= 0;
                    if (wr) begin
                        stall <= 3; ps <= P_W_WAIT;
                    end else begin
                        reads <= reads + 1;
                        if (scenario == 9) ps <= P_HOLD;
                        else begin dir <= 1; phy_oe <= 0; ps <= P_R_TURN; end
                    end
                end
                P_R_TURN: begin
                    // Unknown data throughout the first DIR-high cycle.
                    if (scenario == 4) begin dir <= 0; ps <= P_SHORT; end
                    else begin
                        phy_oe <= 1; phy_data <= regs[addr];
                        if (scenario == 1 && addr == 6'h16) phy_data <= 8'h54;
                        if (scenario == 8 && addr == 6'h07 && writes >= 3) phy_data <= 8'h02;
                        if (scenario == 5) nxt <= 1;
                        ps <= P_R_DATA;
                    end
                end
                P_R_DATA: begin
                    if (scenario == 11) ps <= P_HOLD;
                    else begin dir <= 0; nxt <= 0; phy_oe <= 0; ps <= P_R_RELEASE; end
                end
                P_R_RELEASE: begin
                    if (data !== 8'hzz) $fatal(1,"Link drove during PHY->Link turnaround");
                    ps <= P_IDLE;
                end
                P_W_WAIT: begin
                    if (stp) $fatal(1,"STP before write data acceptance");
                    if (scenario == 7) begin dir <= 1; ps <= P_RX_TURN; end
                    else if (scenario != 10) begin
                        if (stall == 0) begin nxt <= 1; ps <= P_W_DATA; end
                        else stall <= stall - 1;
                    end
                end
                P_W_DATA: begin
                    if (stp) $fatal(1,"write data and STP overlapped");
                    captured_write <= data; ps <= P_W_STOP;
                end
                P_W_STOP: begin
                    if (!stp || data !== 8'h00) $fatal(1,"write stop must assert STP and Idle00");
                    // Check every actual write against the exact safe script.
                    case(writes)
                        0: if (addr != 6'h16 || captured_write != 8'h55) $fatal(1,"first write");
                        1: if (addr != 6'h16 || captured_write != 8'haa) $fatal(1,"second write");
                        2: if (addr != 6'h07 || captured_write != 8'h00) $fatal(1,"interface write");
                        3: if (addr != 6'h0a || captured_write != 8'h00) $fatal(1,"unsafe OTG write");
                        4: if (addr != 6'h04 || captured_write != 8'h45) $fatal(1,"unsafe function write");
                        default: $fatal(1,"unexpected extra write");
                    endcase
                    regs[addr] <= captured_write; writes <= writes + 1;
                    nxt <= 0; ps <= P_W_RELEASE;
                end
                P_W_RELEASE: begin
                    if (stp || data !== 8'h00) $fatal(1,"write release not Idle00/STP0");
                    ps <= P_IDLE;
                end
                P_RX_TURN: begin phy_oe <= 1; phy_data <= 8'h44; nxt <= 0; ps <= P_RX_CMD; end
                P_RX_CMD: begin phy_data <= 8'ha5; nxt <= 1; ps <= P_RX_DATA; end
                P_RX_DATA: begin dir <= 0; nxt <= 0; phy_oe <= 0; ps <= P_RX_RELEASE; end
                P_RX_RELEASE: begin
                    if (data !== 8'hzz) $fatal(1,"preemption return turnaround drive");
                    ps <= P_IDLE;
                end
                P_SHORT: ps <= P_IDLE;
                P_HOLD: begin end
                default: $fatal(1,"PHY invalid state");
            endcase
        end
    end

    always @(negedge clk) begin
        #1; // allow reset/continuous drive gates to settle
        if (!reset_n) begin
            if (stp !== 1 || dut.drive_en !== 0) $fatal(1,"reset startup protection");
        end else begin
            if (dir && dut.drive_en) $fatal(1,"Link drove while DIR high");
            if (!dir && dut.dir_q && dut.drive_en) $fatal(1,"missing return turnaround");
            if (phy_oe && dut.drive_en) $fatal(1,"bus contention");
        end
    end

    integer cycles;
    reg [91:0] frozen;
    task run_case;
        input integer sc;
        input [2:0] expected_reason;
        input [4:0] expected_step;
        begin
            @(negedge clk); reset_n=0; scenario=sc; post_traffic=0;
            repeat(3) @(negedge clk);
            reset_n=1;
            cycles=0;
            while (!done && cycles < 2000) begin @(posedge clk); #1; cycles=cycles+1; end
            if (!done) $fatal(1,"scenario %0d never completes",sc);
            if (stage !== {expected_reason,expected_step})
                $fatal(1,"scenario %0d stage got=%02x expected=%02x",sc,stage,{expected_reason,expected_step});
            if (error !== (expected_reason != 0)) $fatal(1,"scenario %0d error flag",sc);
            if (sc == 0) begin
                if (!id_ok || !scratch_ok || vid!==16'h0424 || pid!==16'h0004 ||
                    fc!==8'h45 || ifc!==0 || otg!==0 || last_read!==8'h45)
                    $fatal(1,"success outputs invalid");
                if (writes != 5 || reads != 12 || accepted != 17)
                    $fatal(1,"script count writes%0d reads%0d accepted%0d",writes,reads,accepted);
                if (rxcmd_count != 1 || rxdata_count != 1) $fatal(1,"preemption RX monitor");
                frozen={done,id_ok,scratch_ok,error,stage,vid,pid,fc,ifc,otg,last_read,16'b0};
                @(negedge clk); post_traffic=1;
                repeat(12) @(negedge clk);
                if (rxcmd_count != 2 || rxdata_count != 2) $fatal(1,"post-probe RX monitor");
                if (frozen !== {done,id_ok,scratch_ok,error,stage,vid,pid,fc,ifc,otg,last_read,16'b0})
                    $fatal(1,"completed result changed");
                if (stp || data!==0) $fatal(1,"completed Link not idle");
            end else begin
                repeat(4) @(negedge clk);
                if (stp) $fatal(1,"failed probe STP remained high");
                if (sc == 2 && writes != 0) $fatal(1,"writes after ID mismatch");
                if (sc == 1 && writes != 1) $fatal(1,"writes after scratch mismatch");
            end
            $display("PASS ULPI scenario=%0d stage=%02x cycles=%0d writes=%0d",sc,stage,cycles,writes);
        end
    endtask
    initial begin
        run_case(0,0,5'h12); // waits, preemption, both turnarounds, safe config, stable results
        run_case(1,5,5'h09); // scratch mismatch
        run_case(2,4,5'h04); // wrong PID (0007 instead of USB3300's 0004)
        run_case(3,1,5'h01); // command NXT never arrives
        run_case(4,3,5'h01); // DIR high only for turnaround, no read byte
        run_case(5,3,5'h01); // RX data where a register return should be
        run_case(6,2,5'h01); // repeated preemption before ACK
        run_case(7,7,5'h08); // write data phase preempted; no retry
        run_case(8,6,5'h0f); // final configuration readback mismatch
        run_case(9,1,5'h01); // ACK but no read DIR
        run_case(10,1,5'h08); // write data NXT never arrives
        run_case(11,1,5'h01); // read byte present, PHY never returns bus
        $display("PASS usb2_ulpi_probe all scenarios");
        $finish;
    end
endmodule
