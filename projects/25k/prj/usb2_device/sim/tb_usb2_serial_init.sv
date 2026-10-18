`timescale 1ns/1ps
module tb_usb2_serial_init;
    reg clk = 0;
    always #8.333 clk = !clk;
    reg reset_n = 0, phy_por_n = 0, attach_request = 0;
    tri [7:0] data;
    reg dir = 0, nxt = 0, phy_oe = 0;
    reg [7:0] phy_data = 0;
    wire [7:0] link_data;
    wire link_oe, stp, done, error, id_ok;
    wire [7:0] stage, fc, ifc, otg, phy_debug;
    wire [15:0] vid, pid;
    assign data = phy_oe ? phy_data : 8'hzz;
    assign data = link_oe ? link_data : 8'hzz;
    usb2_serial_init #(.STARTUP_CYCLES(4), .EXIT_MIN_CYCLES(8),
        .TIMEOUT_CYCLES(100), .SERIAL_GUARD_CYCLES(16)) dut (
        .clk_ulpi60(clk), .reset_n(reset_n), .attach_request(attach_request),
        .ulpi_data_i(data), .ulpi_data_o(link_data), .ulpi_data_oe(link_oe),
        .ulpi_dir(dir), .ulpi_nxt(nxt), .ulpi_stp(stp),
        .init_done(done), .error(error), .stage(stage),
        .vendor_id(vid), .product_id(pid), .id_ok(id_ok),
        .func_ctrl(fc), .if_ctrl(ifc), .otg_ctrl(otg), .phy_debug(phy_debug)
    );

    // Independent clocked ULPI PHY BFM. Only PHY POR resets its registers;
    // FPGA reset must recover a PHY left in serial mode using STP alone.
    localparam P_IDLE=0, P_CMD_STALL=1, P_CMD_ACK=2, P_R_TURN=3,
        P_R_DATA=4, P_R_RELEASE=5, P_W_WAIT=6, P_W_DATA=7,
        P_W_STOP=8, P_W_RELEASE=9, P_RX_TURN=10,
        P_RX_CMD=11, P_RX_DATA=12, P_RX_RELEASE=13,
        P_SHORT=14, P_HOLD=15, P_MODE=16, P_SERIAL=17, P_EXIT=18;
    integer ps=0, stall=0, scenario=0, accepted=0, writes=0, reads=0;
    integer serial_exit_count=0, mode_cycles=0, sampled_mode_high=0, stage15_ticks=0, i;
    reg [7:0] regs[0:63];
    reg [7:0] command_byte=0, captured_write=0, write_hold=0;
    reg [5:0] addr=0;
    reg wr=0, preempted=0, serial_active=0, write_hold_valid=0;
    always @(posedge clk) begin
        if (!phy_por_n) begin
            dir <= scenario==14 || scenario==15; nxt<=0; phy_oe<=scenario==14 || scenario==15;
            phy_data<=8'bzzzz001z;
            ps<=scenario==14 ? P_SERIAL : scenario==15 ? P_HOLD : P_IDLE;
            stall<=0; addr<=0; wr<=0; command_byte<=0; captured_write<=0;
            preempted<=0; accepted<=0; writes<=0; reads<=0;
            write_hold_valid<=0; write_hold<=0;
            serial_active<=scenario==14; serial_exit_count<=0; mode_cycles<=0;
            for(i=0;i<64;i=i+1) regs[i]<=0;
            regs[0]<=8'h24; regs[1]<=8'h04;
            regs[2]<=scenario==2 ? 8'h07 : 8'h04;
            regs[3]<=0; regs[4]<=8'h41;
            regs[7]<=scenario==14 ? 8'h0a : 0;
            regs[10]<=8'h06;
            regs[6'h13]<=8'h06;
            regs[6'h15]<=8'h01;
        end else if ((serial_active || ps==P_MODE) && stp) begin
            // STP is the exit request even when FPGA reset is asserted.
            if(serial_exit_count==2) begin
                dir<=0; nxt<=0; phy_oe<=0; serial_active<=0;
                regs[7]<=regs[7]&8'hfc; ps<=P_EXIT;
                serial_exit_count<=0;
            end else serial_exit_count<=serial_exit_count+1;
        end else if (error) begin
            // A bounded abort ends each injected bad transaction.
            dir<=0; nxt<=0; phy_oe<=0; ps<=P_IDLE;
        end else begin
            serial_exit_count<=0;
            case(ps)
                P_IDLE: begin
                    nxt<=0; dir<=0; phy_oe<=0;
                    if(!stp && (data[7:6]==2'b10 || data[7:6]==2'b11)) begin
                        if((scenario==0 && !preempted) || scenario==6) begin
                            preempted<=1; dir<=1; ps<=P_RX_TURN;
                        end else begin
                            if(data==8'hd5 && stage15_ticks<6000)
                                $fatal(1,"Debug sampled before 100us settling interval");
                            command_byte<=data; addr<=data[5:0]; wr<=!data[6];
                            stall<=2+data[1:0]; ps<=P_CMD_STALL;
                        end
                    end
                end
                P_CMD_STALL: begin
                    if(stp || data!==command_byte) $fatal(1,"command changed before NXT");
                    if(scenario!=3) begin
                        if(stall==0) begin nxt<=1; ps<=P_CMD_ACK; end
                        else stall<=stall-1;
                    end
                end
                P_CMD_ACK: begin
                    if(stp || data!==command_byte) $fatal(1,"invalid command ACK");
                    accepted<=accepted+1; nxt<=0;
                    if(wr) begin stall<=3; write_hold_valid<=0; ps<=P_W_WAIT; end
                    else begin
                        case(reads%12)
                            0: if(addr!=6'h00) $fatal(1,"VID low read order");
                            1: if(addr!=6'h01) $fatal(1,"VID high read order");
                            2: if(addr!=6'h02) $fatal(1,"PID low read order");
                            3: if(addr!=6'h03) $fatal(1,"PID high read order");
                            4,5: if(addr!=6'h16) $fatal(1,"scratch read order");
                            6,9: if(addr!=6'h04) $fatal(1,"function read order");
                            7: if(addr!=6'h0a) $fatal(1,"OTG read order");
                            8: if(addr!=6'h07) $fatal(1,"interface read order");
                            10: if(addr!=6'h15) $fatal(1,"Debug read order");
                            11: if(addr!=6'h13) $fatal(1,"Status read order");
                        endcase
                        reads<=reads+1;
                        if(scenario==9) ps<=P_HOLD;
                        else begin dir<=1; phy_oe<=0; ps<=P_R_TURN; end
                    end
                end
                P_R_TURN: begin
                    if(scenario==4) begin dir<=0; ps<=P_SHORT; end
                    else begin
                        phy_oe<=1; phy_data<=regs[addr];
                        if(scenario==1 && addr==6'h16) phy_data<=8'h54;
                        if(scenario==8 && addr==6'h07) phy_data<=8'h00;
                        if(scenario==5) nxt<=1;
                        ps<=P_R_DATA;
                    end
                end
                P_R_DATA: begin
                    if(scenario==11) ps<=P_HOLD;
                    else begin dir<=0; nxt<=0; phy_oe<=0; ps<=P_R_RELEASE; end
                end
                P_R_RELEASE: begin
                    if(link_oe) $fatal(1,"PHY->Link turnaround driven");
                    ps<=P_IDLE;
                end
                P_W_WAIT: begin
                    if(stp) $fatal(1,"STP before data acceptance");
                    if(write_hold_valid && data!==write_hold) $fatal(1,"write data changed before NXT");
                    else begin write_hold<=data; write_hold_valid<=1; end
                    if(scenario==7) begin dir<=1; ps<=P_RX_TURN; end
                    else if(scenario!=10) begin
                        if(stall==0) begin nxt<=1; ps<=P_W_DATA; end
                        else stall<=stall-1;
                    end
                end
                P_W_DATA: begin
                    if(stp) $fatal(1,"data/STP overlap");
                    if(data!==write_hold) $fatal(1,"write data changed at acceptance");
                    captured_write<=data; ps<=P_W_STOP;
                end
                P_W_STOP: begin
                    if(!stp || data!==8'h00) $fatal(1,"write STOP not STP1/Idle00");
                    // Safe script checks every completed write independently.
                    case(writes%7)
                        0: if(addr!=6'h16 || captured_write!=8'h55) $fatal(1,"scratch55 write");
                        1: if(addr!=6'h16 || captured_write!=8'haa) $fatal(1,"scratchAA write");
                        2: if(addr!=6'h04 || captured_write!=8'h41) $fatal(1,"FS detached write");
                        3: if(addr!=6'h0a || captured_write!=8'h00) $fatal(1,"unsafe VBUS/pulldown write");
                        4: if(addr!=6'h07 || captured_write!=8'h08) $fatal(1,"clock must be retained before serial entry");
                        5: if(addr!=6'h04 || captured_write!=8'h45 || !attach_request) $fatal(1,"premature attach");
                        6: if(addr!=6'h07 || captured_write!=8'h0a || regs[7]!=8'h08 || regs[4]!=8'h45)
                               $fatal(1,"serial entry order");
                    endcase
                    regs[addr]<=captured_write; writes<=writes+1;
                    if(addr==6'h07 && captured_write==8'h0a) begin
                        // DIR changes when STOP is accepted. NXT deliberately
                        // stays high: no ordinary ULPI release follows entry.
                        dir<=scenario!=12; nxt<=1; phy_oe<=1;
                        phy_data<=8'h44; mode_cycles<=0; ps<=P_MODE;
                    end else begin nxt<=0; ps<=P_W_RELEASE; end
                end
                P_W_RELEASE: begin
                    if(stp || data!==8'h00) $fatal(1,"ordinary write release invalid");
                    ps<=P_IDLE;
                end
                P_RX_TURN: begin phy_oe<=1; phy_data<=8'h44; nxt<=0; ps<=P_RX_CMD; end
                P_RX_CMD: begin phy_data<=8'ha5; nxt<=1; ps<=P_RX_DATA; end
                P_RX_DATA: begin dir<=0; nxt<=0; phy_oe<=0; ps<=P_RX_RELEASE; end
                P_RX_RELEASE: begin
                    if(link_oe) $fatal(1,"preemption return turnaround driven");
                    ps<=P_IDLE;
                end
                P_SHORT: ps<=P_IDLE;
                P_HOLD: begin end
                P_MODE: begin
                    if(link_oe || stp) $fatal(1,"mode entry must release DATA and STP");
                    mode_cycles<=mode_cycles+1;
                    if(scenario==13 && mode_cycles==5) dir<=0;
                    if(scenario==13 && mode_cycles==6) dir<=1;
                    if(mode_cycles>=7 && scenario!=12) begin
                        phy_data<=8'bzzzz001z; serial_active<=1; ps<=P_SERIAL;
                    end
                end
                P_SERIAL: begin
                    if(link_oe) $fatal(1,"initializer drove in serial mode");
                    mode_cycles<=mode_cycles+1;
                end
                P_EXIT: if(!stp) ps<=P_IDLE;
                default: $fatal(1,"PHY invalid state");
            endcase
        end
    end

    always @(posedge clk) begin
        if(!reset_n || !dir) sampled_mode_high<=0;
        else if(stage==8'h13) sampled_mode_high<=sampled_mode_high+1;
        if(!reset_n || stage!=8'h15) stage15_ticks<=0;
        else stage15_ticks<=stage15_ticks+1;
    end

    always @(negedge clk) begin
        #1;
        if(!reset_n) begin
            if(stp!==1 || link_oe!==0) $fatal(1,"reset protection");
        end else begin
            if(dir && link_oe) $fatal(1,"drive while DIR1");
            if(!dir && dut.dir_q && link_oe) $fatal(1,"return turnaround");
            if(phy_oe && link_oe) $fatal(1,"PHY/Link contention");
            if((error || done || stage==8'h13) && link_oe) $fatal(1,"late DATA ownership");
            if(done && sampled_mode_high<16) $fatal(1,"guard ignored DIR glitch");
        end
    end

    integer cycles, held_cycles;
    reg [83:0] frozen;
    task wait_result;
        input integer sc;
        input [2:0] reason;
        input [4:0] step;
        begin
            cycles=0; held_cycles=0;
            while(!done && !error && cycles<10000) begin
                @(negedge clk); cycles=cycles+1;
                if(stage==8'h0f && !attach_request) begin
                    held_cycles=held_cycles+1;
                    // The attach wait must survive over twice the operation
                    // timeout, while preserving the detached PHY setting.
                    if(regs[4]!==8'h41 || writes%7!=5) $fatal(1,"attach wait altered PHY");
                    if(held_cycles==230) attach_request=1;
                end
            end
            if(!done && !error) $fatal(1,"scenario %0d no bounded result",sc);
            if(stage!=={reason,step} || error!==(reason!=0) || done!==(reason==0))
                $fatal(1,"scenario%0d got stage%02x err%0b done%0b expected%02x",sc,stage,error,done,{reason,step});
            if(reason==0) begin
                if(!id_ok || vid!==16'h0424 || pid!==16'h0004 ||
                    fc!==8'h45 || ifc!==8'h0a || otg!==0 || phy_debug!==8'h05 || !serial_active)
                    $fatal(1,"success result mismatch");
                if(writes%7!=0 || reads%12!=0 || accepted%19!=0)
                    $fatal(1,"script count writes%0d reads%0d accepted%0d",writes,reads,accepted);
                if(held_cycles!=230) $fatal(1,"attach wait was not exercised");
                frozen={done,error,stage,vid,pid,id_ok,fc,ifc,otg,phy_debug,9'b0};
                repeat(24) @(negedge clk);
                if(stp || link_oe || frozen!=={done,error,stage,vid,pid,id_ok,fc,ifc,otg,phy_debug,9'b0})
                    $fatal(1,"post-completion changed");
            end else begin
                frozen={done,error,stage,vid,pid,id_ok,fc,ifc,otg,phy_debug,9'b0};
                repeat(5) @(negedge clk);
                if(link_oe || stp!==(sc==12) ||
                    frozen!=={done,error,stage,vid,pid,id_ok,fc,ifc,otg,phy_debug,9'b0})
                    $fatal(1,"unsafe/unstable failure state");
                if(sc==2 && writes!=0) $fatal(1,"write after identity failure");
                if(sc==1 && writes!=1) $fatal(1,"write after scratch failure");
            end
            $display("PASS serial-init scenario=%0d stage=%02x cycles=%0d writes=%0d",sc,stage,cycles,writes);
        end
    endtask
    task run_case;
        input integer sc;
        input [2:0] reason;
        input [4:0] step;
        begin
            @(negedge clk); reset_n=0; phy_por_n=0; attach_request=0; scenario=sc;
            repeat(4) @(negedge clk);
            phy_por_n=1;
            repeat(4) @(negedge clk);
            reset_n=1;
            wait_result(sc,reason,step);
        end
    endtask
    initial begin
        run_case(0,0,5'h14); // NXT stalls, one preemption, late attach, NXT held on entry
        // FPGA reset alone: PHY starts in serial mode with all registers intact.
        @(negedge clk); reset_n=0; attach_request=0;
        repeat(4) @(negedge clk);
        reset_n=1;
        wait_result(100,0,5'h14);
        run_case(1,5,5'h06); // scratch readback mismatch
        run_case(2,4,5'h04); // wrong PID, no writes
        run_case(3,1,5'h01); // command NXT timeout
        run_case(4,3,5'h01); // truncated read turnaround
        run_case(5,3,5'h01); // wrong register-return framing
        run_case(6,2,5'h01); // repeated command preemption
        run_case(7,7,5'h05); // write-data preemption, abort without retry
        run_case(8,6,5'h0e); // retained-clock readback mismatch
        run_case(9,1,5'h01); // read ACK without DIR
        run_case(10,1,5'h05); // write-data NXT timeout
        run_case(11,1,5'h01); // read returned, PHY keeps ownership forever
        run_case(12,1,5'h13); // no serial-mode DIR indication
        run_case(13,0,5'h14); // guard restarts after DIR glitch
        run_case(14,0,5'h14); // PHY already in serial mode at FPGA startup
        run_case(15,1,5'h00); // PHY never drops DIR during startup/exit
        $display("PASS usb2_serial_init all 17 scenarios");
        $finish;
    end
endmodule
