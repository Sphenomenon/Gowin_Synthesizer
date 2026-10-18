`timescale 1ns/1ps
module tb_usb2_termination_probe #(
    parameter integer PHY_SOFT_RESET=0,
    parameter integer FULL_SCRATCH_TEST=0
);
    reg clk=0;
    always #8.333 clk=!clk;
    reg reset_n=0, phy_por_n=0;
    tri [7:0] data;
    reg dir=0, nxt=0, phy_oe=0;
    reg [7:0] phy_data=0;
    wire [7:0] link_data;
    wire link_oe,stp,done,error,id_ok;
    wire [3:0] error_code;
    wire [7:0] stage,fc,ifc,otg;
    wire [15:0] vid,pid,masks,last_status,rxcmd_count,rxdata_count;
    wire [15:0] rxcmd_masks;
    wire [31:0] last_rxcmd;
    wire [8:0] scratch_verified_count;
    wire [7:0] scratch_mismatch_expected,scratch_mismatch_actual;
    assign data=phy_oe ? phy_data : 8'hzz;
    assign data=link_oe ? link_data : 8'hzz;

    // Settling deliberately exceeds transaction timeout. Both settle and
    // inter-sample gaps are scaled; the real 16 samples/phase are retained.
    usb2_termination_probe #(.STARTUP_CYCLES(4),.EXIT_MIN_CYCLES(8),
        .TIMEOUT_CYCLES(100),.MAX_PREEMPTIONS(3),.SETTLE_CYCLES(230),
        .SAMPLE_GAP_CYCLES(9),.SAMPLES_PER_PHASE(16),
        .PHY_SOFT_RESET(PHY_SOFT_RESET),.RESET_WAIT_CYCLES(130),
        .FULL_SCRATCH_TEST(FULL_SCRATCH_TEST)) dut (
        .clk_ulpi60(clk),.reset_n(reset_n),.ulpi_data_i(data),
        .ulpi_data_o(link_data),.ulpi_data_oe(link_oe),
        .ulpi_dir(dir),.ulpi_nxt(nxt),.ulpi_stp(stp),
        .done(done),.error(error),.error_code(error_code),.stage(stage),
        .vendor_id(vid),.product_id(pid),.id_ok(id_ok),.func_ctrl(fc),
        .if_ctrl(ifc),.otg_ctrl(otg),.line_seen_masks(masks),
        .phase_last_status(last_status),.rxcmd_count(rxcmd_count),
        .rxdata_count(rxdata_count),.rxcmd_seen_masks(rxcmd_masks),
        .phase_last_rxcmd(last_rxcmd),.scratch_verified_count(scratch_verified_count),
        .scratch_mismatch_expected(scratch_mismatch_expected),
        .scratch_mismatch_actual(scratch_mismatch_actual)
    );

    // Clocked PHY BFM: command and data each stall independently. The PHY
    // changes DIR first and starts driving only after the turnaround edge.
    localparam P_IDLE=0,P_CMD_STALL=1,P_CMD_ACK=2,P_R_TURN=3,
        P_R_DATA=4,P_R_RELEASE=5,P_W_WAIT=6,P_W_DATA=7,
        P_W_STOP=8,P_W_RELEASE=9,P_RX_TURN=10,P_RX_CMD=11,
        P_RX_DATA=12,P_RX_RELEASE=13,P_SHORT=14,P_HOLD=15,
        P_SERIAL=16,P_EXIT=17,P_PHASE_CMD2=18;
    integer ps=0,stall=0,scenario=0,accepted=0,writes=0,reads=0;
    integer i,phase_index,serial_exit_count=0,preempt_total=0;
    integer settle_ticks[0:3],debug_reads[0:3],status_reads[0:3];
    reg [7:0] regs[0:63];
    reg [7:0] command_byte=0,captured_write=0,write_hold=0;
    reg [5:0] addr=0;
    reg wr=0,preempted=0,write_hold_valid=0;
    reg phase_rx_burst=0;
    reg [3:0] phase_rx_injected=0;
    integer rx_phase=0;
    integer reset_age=0,reset_writes=0,reset_reads=0,reset_wait_ticks=0;
    integer full_scratch_writes=0,full_scratch_reads=0;
    reg soft_reset_pending=0;

    function [7:0] phase_rxcmd;
        input integer phase;
        input integer second;
        begin
            case(phase)
                0: phase_rxcmd=second ? 8'h81 : 8'h80;
                1: phase_rxcmd=second ? 8'h92 : 8'h91;
                2: phase_rxcmd=second ? 8'ha3 : 8'ha2;
                3: phase_rxcmd=second ? 8'hb0 : 8'hb3;
                default: phase_rxcmd=8'hxx;
            endcase
        end
    endfunction

    function [1:0] sample_line;
        input integer phase;
        input integer n;
        begin
            case(phase)
                0: sample_line=n[0] ? 2'b01 : 2'b00;
                1: sample_line=n[0] ? 2'b10 : 2'b01;
                2: sample_line=2'b10;
                3: sample_line=n[0] ? 2'b11 : 2'b00;
                default: sample_line=2'bxx;
            endcase
        end
    endfunction
    function [7:0] phase_status;
        input integer phase;
        begin
            case(phase)
                0: phase_status=8'h08;
                1: phase_status=8'h04;
                2: phase_status=8'h0c;
                3: phase_status=8'h00;
                default: phase_status=8'hxx;
            endcase
        end
    endfunction
    function [7:0] target_fc;
        input integer phase;
        begin
            case(phase)
                0,3: target_fc=8'h41;
                1: target_fc=8'h45;
                2: target_fc=8'h46;
                default: target_fc=8'hxx;
            endcase
        end
    endfunction
    function [7:0] target_otg;
        input integer phase;
        begin target_otg=(phase==0 || phase==3) ? 8'h06 : 8'h00; end
    endfunction

    always @(posedge clk) begin
        if(!phy_por_n) begin
            dir<=scenario==14 || scenario==15;
            nxt<=0;phy_oe<=scenario==14 || scenario==15;
            phy_data<=8'bzzzz001z;
            ps<=scenario==14 ? P_SERIAL : scenario==15 ? P_HOLD : P_IDLE;
            stall<=0;addr<=0;wr<=0;command_byte<=0;captured_write<=0;
            preempted<=0;accepted<=0;writes<=0;reads<=0;
            write_hold_valid<=0;write_hold<=0;serial_exit_count<=0;
            preempt_total<=0;
            phase_rx_burst<=0;phase_rx_injected<=0;rx_phase<=0;
            reset_age<=0;reset_writes<=0;reset_reads<=0;
            reset_wait_ticks<=0;soft_reset_pending<=0;
            full_scratch_writes<=0;full_scratch_reads<=0;
            for(i=0;i<64;i=i+1) regs[i]<=0;
            for(i=0;i<4;i=i+1) begin
                settle_ticks[i]<=0;debug_reads[i]<=0;status_reads[i]<=0;
            end
            regs[0]<=8'h24;regs[1]<=8'h04;
            regs[2]<=scenario==2 ? 8'h07 : 8'h04;
            regs[3]<=0;regs[4]<=8'h41;
            regs[7]<=scenario==14 ? 8'h0a : 8'h00;
            regs[10]<=8'h06;
        end else if(ps==P_SERIAL && stp) begin
            if(serial_exit_count==2) begin
                dir<=0;nxt<=0;phy_oe<=0;regs[7]<=8'h08;
                ps<=P_EXIT;serial_exit_count<=0;
            end else serial_exit_count<=serial_exit_count+1;
        end else if(error) begin
            dir<=0;nxt<=0;phy_oe<=0;ps<=P_IDLE;
        end else begin
            serial_exit_count<=0;
            // Model only the documented software-reset bit's self clearing;
            // the wrapper's clock is intentionally continuous. Register mode
            // remains retained and detached before the four test phases.
            if(soft_reset_pending) begin
                reset_age<=reset_age+1;
                if(reset_age==60 && scenario!=20) begin
                    regs[4]<=scenario==21 ? 8'h40 : 8'h41;
                    soft_reset_pending<=0;
                end
            end
            if(stage==8'h0c) reset_wait_ticks<=reset_wait_ticks+1;
            phase_index=(stage[7:4]>=2 && stage[7:4]<=5) ? stage[7:4]-2 : -1;
            if(phase_index>=0 && stage[3:0]==6)
                settle_ticks[phase_index]<=settle_ticks[phase_index]+1;
            case(ps)
                P_IDLE: begin
                    nxt<=0;dir<=0;phy_oe<=0;
                    // Legal asynchronous bursts are independent of register
                    // read responses. Two RxCmd values and one RX data byte
                    // exercise each phase's mask and complete last byte.
                    if(scenario==0 && phase_index>=0 && stage[3:0]==6 &&
                        settle_ticks[phase_index]>=4 && !phase_rx_injected[phase_index]) begin
                        if(phase_index==0 && (rxcmd_masks!==0 || last_rxcmd!==0 ||
                            rxcmd_count!==16'd1 || rxdata_count!==16'd1))
                            $fatal(1,"startup preemption polluted phase RxCmd capture");
                        phase_rx_injected[phase_index]<=1;phase_rx_burst<=1;
                        rx_phase<=phase_index;dir<=1;ps<=P_RX_TURN;
                    end else if(!stp && (data[7:6]==2'b10 || data[7:6]==2'b11)) begin
                        if((scenario==0 && !preempted) || scenario==6) begin
                            preempted<=1;preempt_total<=preempt_total+1;
                            phase_rx_burst<=0;
                            dir<=1;ps<=P_RX_TURN;
                        end else begin
                            if(data==8'hd5 && (phase_index<0 || settle_ticks[phase_index]<230))
                                $fatal(1,"Debug read before complete settle stage=%02x",stage);
                            if(stage==8'h0d && reset_wait_ticks<130)
                                $fatal(1,"Function Control read before reset wait elapsed");
                            command_byte<=data;addr<=data[5:0];wr<=!data[6];
                            stall<=2+data[1:0];ps<=P_CMD_STALL;
                        end
                    end
                end
                P_CMD_STALL: begin
                    if(stp || data!==command_byte) $fatal(1,"command changed before NXT");
                    if(scenario!=3) begin
                        if(stall==0) begin nxt<=1;ps<=P_CMD_ACK;end
                        else stall<=stall-1;
                    end
                end
                P_CMD_ACK: begin
                    if(stp || data!==command_byte) $fatal(1,"invalid command ACK");
                    accepted<=accepted+1;nxt<=0;
                    if(wr) begin stall<=3;write_hold_valid<=0;ps<=P_W_WAIT;end
                    else begin
                        reads<=reads+1;
                        case(stage)
                            8'h01: if(addr!=0) $fatal(1,"VID low read order");
                            8'h02: if(addr!=1) $fatal(1,"VID high read order");
                            8'h03: if(addr!=2) $fatal(1,"PID low read order");
                            8'h04: if(addr!=3) $fatal(1,"PID high read order");
                            8'h06,8'h08: if(addr!=6'h16) $fatal(1,"scratch read order");
                            8'h0a: if(addr!=6'h07) $fatal(1,"IF read order");
                            8'h0d: begin
                                if(!PHY_SOFT_RESET || addr!=6'h04 || reset_writes!=1)
                                    $fatal(1,"soft reset read order");
                                reset_reads<=reset_reads+1;
                            end
                            8'h11: begin
                                if(!FULL_SCRATCH_TEST || addr!=6'h16 ||
                                    full_scratch_reads!=full_scratch_writes-1 ||
                                    scratch_verified_count!==full_scratch_reads)
                                    $fatal(1,"full scratch read order/count");
                                full_scratch_reads<=full_scratch_reads+1;
                            end
                            default: begin
                                if(phase_index<0) $fatal(1,"unexpected read stage %02x",stage);
                                case(stage[3:0])
                                    1,5: if(addr!=4) $fatal(1,"FC read order");
                                    3: if(addr!=10) $fatal(1,"OTG read order");
                                    7: begin
                                        if(addr!=6'h15 || debug_reads[phase_index]!=status_reads[phase_index])
                                            $fatal(1,"Debug sample order");
                                        debug_reads[phase_index]<=debug_reads[phase_index]+1;
                                    end
                                    8: begin
                                        if(addr!=6'h13 || debug_reads[phase_index]!=status_reads[phase_index]+1)
                                            $fatal(1,"Status sample order");
                                        status_reads[phase_index]<=status_reads[phase_index]+1;
                                    end
                                    default: $fatal(1,"unexpected phase read %02x",stage);
                                endcase
                            end
                        endcase
                        if(scenario==9 || (scenario==24 && stage==8'h11 && full_scratch_reads==8)) ps<=P_HOLD;
                        else begin dir<=1;phy_oe<=0;ps<=P_R_TURN;end
                    end
                end
                P_R_TURN: begin
                    if(scenario==4) begin dir<=0;ps<=P_SHORT;end
                    else begin
                        phy_oe<=1;phy_data<=regs[addr];
                        if(addr==6'h15) phy_data<={6'b0,sample_line(phase_index,debug_reads[phase_index]-1)};
                        if(addr==6'h13) phy_data<=phase_status(phase_index);
                        if(scenario==1 && addr==6'h16) phy_data<=8'h54;
                        if(scenario==8 && addr==6'h07) phy_data<=8'h00;
                        if(scenario==13 && stage==8'h35) phy_data<=8'h41;
                        if(scenario==22 && stage==8'h11)
                            phy_data<={regs[addr][7:2],regs[addr][0],regs[addr][1]};
                        if(scenario==23 && stage==8'h11) phy_data<=regs[addr] | 8'h80;
                        if(scenario==5) nxt<=1;
                        ps<=P_R_DATA;
                    end
                end
                P_R_DATA: begin
                    if(scenario==11) ps<=P_HOLD;
                    else begin dir<=0;nxt<=0;phy_oe<=0;ps<=P_R_RELEASE;end
                end
                P_R_RELEASE: begin
                    if(link_oe) $fatal(1,"PHY-to-Link turnaround driven");
                    ps<=P_IDLE;
                end
                P_W_WAIT: begin
                    if(stp) $fatal(1,"STP before write data acceptance");
                    if(write_hold_valid && data!==write_hold) $fatal(1,"write data changed before NXT");
                    else begin write_hold<=data;write_hold_valid<=1;end
                    if(scenario==7) begin dir<=1;ps<=P_RX_TURN;end
                    else if(scenario!=10 && !(scenario==25 && stage==8'h10 && full_scratch_writes==8)) begin
                        if(stall==0) begin nxt<=1;ps<=P_W_DATA;end
                        else stall<=stall-1;
                    end
                end
                P_W_DATA: begin
                    if(stp || data!==write_hold) $fatal(1,"invalid write acceptance");
                    captured_write<=data;ps<=P_W_STOP;
                end
                P_W_STOP: begin
                    if(!stp || data!==8'h00) $fatal(1,"write STOP not STP1/Idle00");
                    if(addr==6'h0a && (captured_write!=8'h00 && captured_write!=8'h06))
                        $fatal(1,"unsafe OTG VBUS/pulldown write %02x",captured_write);
                    case(stage)
                        8'h05: if(addr!=6'h16 || captured_write!=8'h55) $fatal(1,"scratch55 write");
                        8'h07: if(addr!=6'h16 || captured_write!=8'haa) $fatal(1,"scratchAA write");
                        8'h09: if(addr!=7 || captured_write!=8'h08) $fatal(1,"unsafe IF mode");
                        8'h0b: begin
                            if(!PHY_SOFT_RESET || addr!=4 || captured_write!=8'h61 ||
                                regs[7]!==8'h08 || reset_writes!=0)
                                $fatal(1,"soft reset write order/value");
                            reset_writes<=reset_writes+1;reset_age<=0;soft_reset_pending<=1;
                        end
                        8'h10: begin
                            if(!FULL_SCRATCH_TEST || addr!=6'h16 ||
                                captured_write!==full_scratch_writes[7:0] ||
                                full_scratch_writes!=full_scratch_reads ||
                                scratch_verified_count!==full_scratch_writes)
                                $fatal(1,"full scratch write order/value/count");
                            full_scratch_writes<=full_scratch_writes+1;
                        end
                        default: begin
                            if(phase_index<0) $fatal(1,"unexpected write stage %02x",stage);
                            case(stage[3:0])
                                0: if(addr!=4 || captured_write!=8'h41) $fatal(1,"phase must detach first");
                                2: if(addr!=10 || captured_write!=target_otg(phase_index))
                                       $fatal(1,"phase OTG mismatch");
                                4: if(addr!=4 || captured_write!=target_fc(phase_index))
                                       $fatal(1,"phase FC mismatch");
                                default: $fatal(1,"unexpected phase write %02x",stage);
                            endcase
                        end
                    endcase
                    regs[addr]<=captured_write;writes<=writes+1;nxt<=0;ps<=P_W_RELEASE;
                end
                P_W_RELEASE: begin
                    if(stp || data!==8'h00) $fatal(1,"ordinary write release invalid");
                    ps<=P_IDLE;
                end
                P_RX_TURN: begin
                    phy_oe<=1;phy_data<=phase_rx_burst ? phase_rxcmd(rx_phase,0) : 8'h44;
                    nxt<=0;ps<=P_RX_CMD;
                end
                P_RX_CMD: begin
                    if(phase_rx_burst) begin
                        phy_data<=phase_rxcmd(rx_phase,1);nxt<=0;ps<=P_PHASE_CMD2;
                    end else begin phy_data<=8'ha5;nxt<=1;ps<=P_RX_DATA;end
                end
                P_PHASE_CMD2: begin phy_data<=8'hfe;nxt<=1;ps<=P_RX_DATA;end
                P_RX_DATA: begin dir<=0;nxt<=0;phy_oe<=0;ps<=P_RX_RELEASE;end
                P_RX_RELEASE: begin
                    if(link_oe) $fatal(1,"preemption return turnaround driven");
                    ps<=P_IDLE;
                end
                P_SHORT: ps<=P_IDLE;
                P_HOLD: begin end
                P_SERIAL: if(link_oe) $fatal(1,"link drove previous serial mode");
                P_EXIT: if(!stp) ps<=P_IDLE;
                default: $fatal(1,"invalid BFM state");
            endcase
        end
    end

    // Test the combinational safety path immediately after DIR rises, not
    // merely a full cycle after it has been registered by the link.
    always @(posedge dir) begin
        #0.001;
        if(link_oe) $fatal(1,"raw DIR did not immediately release OE");
    end
    always @(negedge clk) begin
        #1;
        if(!reset_n) begin
            if(stp!==1 || link_oe!==0) $fatal(1,"reset protection");
        end else begin
            if(dir && link_oe) $fatal(1,"drive while DIR1");
            if(!dir && dut.dir_q && link_oe) $fatal(1,"return turnaround");
            if(phy_oe && link_oe) $fatal(1,"PHY/Link contention");
            if(error && link_oe) $fatal(1,"failed probe retained DATA ownership");
            if(done && !dir && !dut.dir_q && (!link_oe || data!==8'h00))
                $fatal(1,"successful probe must continue driving ULPI Idle");
        end
    end

    integer cycles;
    reg [207:0] frozen;
    task wait_result;
        input integer sc;
        input [3:0] expected_error;
        input [7:0] expected_stage;
        begin
            cycles=0;
            while(!done && !error && cycles<40000) begin @(negedge clk);cycles=cycles+1;end
            if(!done && !error) $fatal(1,"scenario %0d did not finish",sc);
            if(stage!==expected_stage || error_code!==expected_error ||
                error!==(expected_error!=0) || done!==(expected_error==0))
                $fatal(1,"scenario %0d stage=%02x error=%0b code=%0d done=%0b expected stage=%02x code=%0d",
                       sc,stage,error,error_code,done,expected_stage,expected_error);
            if(sc!=0 && (rxcmd_masks!==16'h0000 || last_rxcmd!==32'h00000000))
                $fatal(1,"register response/startup event polluted phase RxCmd capture");
            if(expected_error==0) begin
                if(!id_ok || vid!==16'h0424 || pid!==16'h0004 || fc!==8'h41 ||
                    ifc!==8'h08 || otg!==8'h06 || masks!==16'h9463 || last_status!==16'h3e69)
                    $fatal(1,"success snapshot mismatch masks=%04x status=%04x",masks,last_status);
                if(regs[4]!==8'h41 || regs[7]!==8'h08 || regs[10]!==8'h06)
                    $fatal(1,"PHY not left detached");
                if(writes!=15+PHY_SOFT_RESET+256*FULL_SCRATCH_TEST ||
                    reads!=147+PHY_SOFT_RESET+256*FULL_SCRATCH_TEST ||
                    accepted!=162+2*PHY_SOFT_RESET+512*FULL_SCRATCH_TEST)
                    $fatal(1,"script count writes=%0d reads=%0d accepted=%0d",writes,reads,accepted);
                if(scratch_verified_count!==9'd256*FULL_SCRATCH_TEST ||
                    full_scratch_writes!=256*FULL_SCRATCH_TEST ||
                    full_scratch_reads!=256*FULL_SCRATCH_TEST ||
                    scratch_mismatch_expected!==0 || scratch_mismatch_actual!==0)
                    $fatal(1,"full scratch coverage or mismatch outputs incorrect count=%0d writes=%0d reads=%0d",
                        scratch_verified_count,full_scratch_writes,full_scratch_reads);
                if(reset_writes!=PHY_SOFT_RESET || reset_reads!=PHY_SOFT_RESET ||
                    (PHY_SOFT_RESET && reset_wait_ticks<130))
                    $fatal(1,"soft reset was skipped, repeated, or read prematurely");
                for(i=0;i<4;i=i+1)
                    if(debug_reads[i]!=16 || status_reads[i]!=16)
                        $fatal(1,"phase %0d did not receive 16 paired samples",i);
                if(rxcmd_count!==(sc==0 ? 16'd9 : 16'd0) || rxdata_count!==(sc==0 ? 16'd5 : 16'd0))
                    $fatal(1,"register turnaround counted as RX: cmd=%0d data=%0d",rxcmd_count,rxdata_count);
                if(rxcmd_masks!==(sc==0 ? 16'h9c63 : 16'h0000) ||
                    last_rxcmd!==(sc==0 ? 32'hb0a39281 : 32'h00000000))
                    $fatal(1,"asynchronous RxCmd snapshot mismatch mask=%04x last=%08x",rxcmd_masks,last_rxcmd);
                if(sc==0 && phase_rx_injected!==4'hf)
                    $fatal(1,"not all four phase RxCmd bursts were injected");
            end
            frozen={done,error,error_code,stage,vid,pid,id_ok,fc,ifc,otg,masks,last_status,rxcmd_count,rxdata_count,rxcmd_masks,last_rxcmd,
                scratch_verified_count,scratch_mismatch_expected,scratch_mismatch_actual};
            repeat(24) @(negedge clk);
            if(link_oe!==(expected_error==0) || (expected_error==0 && data!==8'h00) || stp ||
                frozen!=={done,error,error_code,stage,vid,pid,id_ok,fc,ifc,otg,masks,last_status,rxcmd_count,rxdata_count,rxcmd_masks,last_rxcmd,
                    scratch_verified_count,scratch_mismatch_expected,scratch_mismatch_actual})
                $fatal(1,"unsafe/unstable final state");
            if(sc==2 && writes!=0) $fatal(1,"write after identity failure");
            if(sc==1 && writes!=1) $fatal(1,"write after scratch failure");
            if((sc==20 || sc==21) && (writes!=4+256*FULL_SCRATCH_TEST ||
                reads!=8+256*FULL_SCRATCH_TEST || reset_writes!=1 ||
                reset_reads!=1 || reset_wait_ticks<130 || masks!=0 || last_status!=0))
                $fatal(1,"failed reset was not bounded before termination phases");
            if(sc==22 && (scratch_verified_count!==9'd1 || scratch_mismatch_expected!==8'h01 ||
                scratch_mismatch_actual!==8'h02 || writes!=2 || reads!=6))
                $fatal(1,"swapped data bits not diagnosed at first divergent value");
            if(sc==23 && (scratch_verified_count!==9'd0 || scratch_mismatch_expected!==8'h00 ||
                scratch_mismatch_actual!==8'h80 || writes!=1 || reads!=5))
                $fatal(1,"stuck data bit not diagnosed at first divergent value");
            if(sc==24 && (scratch_verified_count!==9'd8 || writes!=9 || reads!=13 || cycles>1000))
                $fatal(1,"scratch read timeout did not preserve bounded progress");
            if(sc==25 && (scratch_verified_count!==9'd8 || writes!=8 || reads!=12 || cycles>1000))
                $fatal(1,"scratch write timeout did not preserve bounded progress");
            if(sc>=22 && (rxcmd_count!==0 || rxdata_count!==0 ||
                (sc>=24 && (scratch_mismatch_expected!==0 || scratch_mismatch_actual!==0))))
                $fatal(1,"scratch responses polluted RX or timeout mismatch diagnostics");
            $display("PASS termination scenario=%0d stage=%02x code=%0d cycles=%0d writes=%0d reads=%0d rxcmd=%0d rxdata=%0d rxmask=%04x rxlast=%08x",
                     sc,stage,error_code,cycles,writes,reads,rxcmd_count,rxdata_count,rxcmd_masks,last_rxcmd);
            if(FULL_SCRATCH_TEST)
                $display("PASS scratch snapshot verified=%0d full_writes=%0d full_reads=%0d expected=%02x actual=%02x",
                    scratch_verified_count,full_scratch_writes,full_scratch_reads,
                    scratch_mismatch_expected,scratch_mismatch_actual);
        end
    endtask
    task run_case;
        input integer sc;
        input [3:0] expected_error;
        input [7:0] expected_stage;
        begin
            @(negedge clk);reset_n=0;phy_por_n=0;scenario=sc;
            repeat(4) @(negedge clk);
            phy_por_n=1;
            repeat(4) @(negedge clk);
            reset_n=1;
            wait_result(sc,expected_error,expected_stage);
        end
    endtask
    initial begin
        run_case(0,0,8'h60);  // all phases, NXT stalls, one unsolicited RX preemption
        run_case(1,5,FULL_SCRATCH_TEST ? 8'h11 : 8'h06);  // scratch mismatch
        run_case(2,4,8'h04);  // wrong identity, no writes allowed
        run_case(3,1,8'h01);  // command NXT timeout
        run_case(4,3,8'h01);  // truncated read turnaround
        run_case(5,3,8'h01);  // invalid register data framing
        run_case(6,2,8'h01);  // bounded repeated preemption
        run_case(7,7,FULL_SCRATCH_TEST ? 8'h10 : 8'h05);  // DIR during write, no unsafe retry
        run_case(8,6,8'h0a);  // interface register readback mismatch
        run_case(9,1,8'h01);  // command accepted, no PHY DIR response
        run_case(10,1,FULL_SCRATCH_TEST ? 8'h10 : 8'h05); // write data NXT timeout
        run_case(11,1,8'h01); // PHY never releases read ownership
        run_case(13,6,8'h35); // phase target Function Control readback mismatch
        run_case(14,0,8'h60); // recover PHY already left in serial mode
        run_case(15,1,8'h00); // PHY never releases startup ownership
        if(PHY_SOFT_RESET) begin
            run_case(20,1,8'h0d); // reset bit stuck after bounded wait
            run_case(21,6,8'h0d); // reset clears to invalid Function Control
        end
        if(FULL_SCRATCH_TEST) begin
            run_case(22,5,8'h11); // DATA[1:0] swapped on Scratch response
            run_case(23,5,8'h11); // DATA[7] stuck high on Scratch response
            run_case(24,1,8'h11); // read response timeout after eight verified bytes
            run_case(25,1,8'h10); // write NXT timeout after eight verified bytes
        end
        $display("PASS usb2_termination_probe PHY_SOFT_RESET=%0d FULL_SCRATCH_TEST=%0d all %0d scenarios",
                 PHY_SOFT_RESET,FULL_SCRATCH_TEST,15+2*PHY_SOFT_RESET+4*FULL_SCRATCH_TEST);
        $finish;
    end
endmodule
