`timescale 1ns/1ps
// Independent USB3300 PHY BFM for DS00001783C sections 6.1.9.1/6.1.9.2,
// Table 6-6. In particular, CLKOUT really stops; the test never substitutes
// decoded ULPI RxCmd bits for asynchronous low-power DATA[1:0].
module tb_usb2_lowpower_diag #(
    parameter [7:0] FS_OTG_CTRL=8'h00
);
    localparam integer SAMPLES=16;
    reg clk50=0,clk60=0,clock_run=1;
    always #10 clk50=!clk50;
    always begin
        #8.333;
        if(clock_run) clk60=!clk60;
        else clk60=0;
    end
    reg reset_n=0,phy_reset_n=0;
    tri [7:0] data;
    wire [7:0] data_o;
    wire drive_ready,stp,done,error,id_ok,clock_alive,clock_stop_seen;
    wire [3:0] errorcode;
    wire [7:0] stage,fc,if_ctrl,otg,direct_last;
    wire [15:0] vid,pid,direct_masks,phase_flags;
    wire [31:0] sample_counts;
    reg dir=0,nxt=0,phy_oe=0;
    reg [7:0] phy_data=0;
    wire link_oe=drive_ready && !dir;
    reg lowpower=0;
    localparam P_IDLE=0,P_CMD_WAIT=1,P_CMD_ACK=2,P_R_TURN=3,P_R_DATA=4,
        P_R_RELEASE=5,P_W_WAIT=6,P_W_ACK=7,P_W_STOP=8,P_W_RELEASE=9,
        P_SUSPEND=10,P_SLEEP=11,P_WAKE=12,P_HOLD=13;
    integer ps=P_IDLE,stall=0,stop_edges=0,wake_edges=0,wake_ticks=0;
    integer scenario=0,phase=-1,lp_ticks=0;
    reg [1:0] raw_line;
    always @* begin
        case(phase)
            1: raw_line=2'b01;
            2: raw_line=2'b10;
            default: raw_line=2'b00;
        endcase
        if(scenario==1 && (phase==1 || phase==2)) raw_line=2'b11;
        // Cycle the physical receiver output independently of DUT internals.
        if(scenario==2) raw_line=(lp_ticks/11)%4;
        if(scenario==13 && lowpower) raw_line=2'bxx;
    end
    wire [7:0] asleep_data={4'b0000,1'b1,1'b0,raw_line};
    assign data=phy_oe ? ((lowpower || ps==P_SUSPEND || ps==P_WAKE) ? asleep_data : phy_data) : 8'hzz;
    assign data=link_oe ? data_o : 8'hzz;

    usb2_lowpower_diag #(.STARTUP_CYCLES(8),.TIMEOUT_CYCLES(2000),
        .CLOCK_QUIET_CYCLES(20),.SETTLE_CYCLES(30),
        .SAMPLE_GAP_CYCLES(9),.SAMPLES_PER_PHASE(SAMPLES),
        .FS_OTG_CTRL(FS_OTG_CTRL)) dut (
        .clk50(clk50),.clk60(clk60),.reset_n(reset_n),.data_i(data),
        .data_o(data_o),.drive_ready(drive_ready),.dir(dir),.nxt(nxt),.stp(stp),
        .done(done),.error(error),.errorcode(errorcode),.stage(stage),
        .id_ok(id_ok),.vid(vid),.pid(pid),.fc(fc),.if_ctrl(if_ctrl),.otg(otg),
        .direct_masks(direct_masks),.direct_last(direct_last),
        .phase_flags(phase_flags),.sample_counts(sample_counts),
        .clock_alive(clock_alive),.clock_stop_seen(clock_stop_seen)
    );

    integer reads=0,writes=0,suspend_writes=0,readbacks=0,startup_wakes=0;
    integer i;
    reg [7:0] regs[0:63];
    reg [7:0] command=0,held_write=0;
    reg [5:0] addr=0;
    reg wr=0,write_valid=0,waking=0,wake_stp_seen=0;
    reg [31:0] previous_counts=0;
    reg sample_valid_before=0;
    integer total_sleep_ticks=0,turnaround_checks=0;

    // Model register transactions only from the pins. Command and write-data
    // NXT stalls are independent, and read DIR has a full turnaround cycle.
    always @(posedge clk60) begin
        if(!phy_reset_n) begin
            ps<=P_IDLE;dir<=0;nxt<=0;phy_oe<=0;phy_data<=0;
            stall<=0;stop_edges<=0;wake_edges<=0;phase<=-1;
            reads<=0;writes<=0;suspend_writes<=0;readbacks<=0;
            command<=0;addr<=0;wr<=0;held_write<=0;write_valid<=0;
            for(i=0;i<64;i=i+1) regs[i]<=0;
            regs[0]<=8'h24;regs[1]<=8'h04;
            regs[2]<=scenario==6 ? 8'h05 : 8'h04;regs[3]<=0;
            regs[4]<=8'h41;regs[7]<=0;regs[10]<=6;
        end else if(error) begin
            nxt<=0;phy_oe<=0;dir<=0;ps<=P_HOLD;
        end else if(!lowpower) begin
            case(ps)
                P_IDLE: begin
                    dir<=0;nxt<=0;phy_oe<=0;
                    if(!stp && link_oe && (data[7:6]==2'b10 || data[7:6]==2'b11)) begin
                        command<=data;addr<=data[5:0];wr<=!data[6];
                        stall<=2;ps<=P_CMD_WAIT;
                    end
                end
                P_CMD_WAIT: begin
                    if(stp || data!==command || !link_oe)
                        $fatal(1,"command changed while NXT stalled, scenario %0d",scenario);
                    if(scenario!=10) begin
                        if(stall==0) begin nxt<=1;ps<=P_CMD_ACK;end
                        else stall<=stall-1;
                    end
                end
                P_CMD_ACK: begin
                    if(stp || data!==command || !link_oe) $fatal(1,"invalid command acceptance");
                    nxt<=0;
                    if(wr) begin stall<=3;write_valid<=0;ps<=P_W_WAIT;end
                    else begin
                        reads<=reads+1;
                        if(scenario==11) ps<=P_HOLD;
                        else begin dir<=1;phy_oe<=0;ps<=P_R_TURN;end
                    end
                end
                P_R_TURN: begin
                    if(link_oe) $fatal(1,"Link drives read turnaround");
                    phy_oe<=1;phy_data<=regs[addr];
                    if(scenario==7 && addr==6'h16) phy_data<=regs[addr]^8'h01;
                    if(scenario==8 && addr==6'h07) phy_data<=8'h02;
                    if(scenario==9 && addr==6'h04 && suspend_writes>0) phy_data<=regs[addr]^8'h01;
                    ps<=P_R_DATA;
                end
                P_R_DATA: begin
                    if(link_oe || !dir || nxt) $fatal(1,"invalid register response ownership");
                    if(suspend_writes>0 && (addr==6'h04 || addr==6'h07)) readbacks<=readbacks+1;
                    dir<=0;phy_oe<=0;ps<=P_R_RELEASE;
                end
                P_R_RELEASE: begin
                    // One undriven turnaround cycle follows DIR deassertion.
                    if(link_oe) $fatal(1,"Link drives PHY-to-Link turnaround");
                    ps<=P_IDLE;
                end
                P_W_WAIT: begin
                    if(stp || !link_oe) $fatal(1,"write data absent while stalled");
                    if(write_valid && data!==held_write) $fatal(1,"write data changed before NXT");
                    held_write<=data;write_valid<=1;
                    if(stall==0) begin
                        if(scenario==12) begin dir<=1;phy_oe<=0;ps<=P_HOLD;end
                        else begin nxt<=1;ps<=P_W_ACK;end
                    end else stall<=stall-1;
                end
                P_W_ACK: begin
                    if(stp || !link_oe || data!==held_write) $fatal(1,"invalid write acceptance");
                    regs[addr]<=data;writes<=writes+1;nxt<=0;ps<=P_W_STOP;
                end
                P_W_STOP: begin
                    if(stp) begin
                        if(addr==6'h04 && !regs[4][6]) begin
                            phase<=phase+1;suspend_writes<=suspend_writes+1;
                            case(phase+1)
                                0,3: if(regs[4]!==8'h01 || regs[10]!==8'h06) $fatal(1,"detached termination mismatch");
                                1: if(regs[4]!==8'h05 || regs[10]!==FS_OTG_CTRL) $fatal(1,"FS termination mismatch");
                                2: if(regs[4]!==8'h06 || regs[10]!==8'h00) $fatal(1,"LS termination mismatch");
                                default: $fatal(1,"too many low-power entries");
                            endcase
                            if(regs[7]!==8'h00) $fatal(1,"serial mode enabled in low-power diagnostic");
                            dir<=1;phy_oe<=0;stop_edges<=0;ps<=P_SUSPEND;
                        end else ps<=P_W_RELEASE;
                    end
                end
                P_W_RELEASE: begin
                    if(!stp) ps<=P_IDLE;
                end
                P_SUSPEND: begin
                    stop_edges<=stop_edges+1;phy_oe<=1;
                    // The single write STOP is legal. It must not be treated
                    // as an asynchronous wake and must fall before CLK stops.
                    if(stop_edges>=2 && stp) $fatal(1,"write STOP persisted into suspend");
                end
                P_WAKE: begin
                    if(!stp && dir) $fatal(1,"false resume: STP fell before DIR");
                    wake_edges<=wake_edges+1;
                    if(wake_edges==5) begin
                        dir<=0;phy_oe<=0;regs[4]<=regs[4] | 8'h40;ps<=P_W_RELEASE;
                    end
                end
                P_HOLD: begin end
                default: $fatal(1,"unknown PHY BFM state");
            endcase
        end
    end

    // Stop only on a falling edge and only after six complete rising edges
    // following DIR assertion; this exceeds the mandatory five-edge minimum.
    always @(negedge clk60) begin
        if(phy_reset_n && ps==P_SUSPEND && stop_edges>=6 && scenario!=4) begin
            if(stp) $fatal(1,"STP high at entry to clock-stopped low power");
            clock_run=0;lowpower=1;ps=P_SLEEP;lp_ticks=0;
        end
    end

    // The always-running 50 MHz side models PHY asynchronous wake detection.
    // CLKOUT remains stopped for a finite startup delay after STP assertion.
    always @(posedge clk50) begin
        if(!phy_reset_n) begin
            wake_ticks=0;waking=0;wake_stp_seen=0;lp_ticks=0;
        end else if(lowpower) begin
            lp_ticks=lp_ticks+1;total_sleep_ticks=total_sleep_ticks+1;
            if(scenario==14 && phase==0 && lp_ticks==45) dir=0;
            if(scenario==15 && phase==0 && lp_ticks==50) begin
                clock_run=1;lowpower=0;ps=P_HOLD;
            end
            if(stp) begin
                wake_stp_seen=1;waking=1;wake_ticks=wake_ticks+1;
                if(scenario!=5 && scenario!=16 && wake_ticks==12) begin
                    if(phase==-1) startup_wakes=startup_wakes+1;
                    clock_run=1;lowpower=0;ps=P_WAKE;wake_edges=0;
                    wake_ticks=0;waking=0;
                end
            end else if(waking) $fatal(1,"STP fell during stopped-clock wake");
        end
    end

    // These assertions observe only outputs and physical bus state. All
    // progress, failures, and the watchdog use clk50, never the stopped clock.
    always @(posedge clk50) begin
        sample_valid_before <= lowpower && !clock_run && dir && !stp;
    end
    always @(negedge clk50) begin
        if(reset_n) begin
            if(link_oe && phy_oe) $fatal(1,"DATA bus contention, scenario %0d",scenario);
            if(dir && drive_ready) begin
                // Top-level raw-DIR gating must always win immediately.
                if(link_oe) $fatal(1,"raw DIR failed immediate Link release");
                turnaround_checks=turnaround_checks+1;
            end
            if(sample_counts!==previous_counts) begin
                if(!sample_valid_before)
                    $fatal(1,"sample counted outside genuine clock-stopped low power");
                if((^raw_line)===1'bx) $fatal(1,"unknown DATA accepted as a sample");
            end
        end
        previous_counts=sample_counts;
    end

    task run_case;
        input integer n;
        input integer expected_error;
        integer ticks,k;
        reg [3:0] nibble;
        begin
            scenario=n;reset_n=0;phy_reset_n=0;
            clock_run=1;lowpower=0;waking=0;
            repeat(10) @(negedge clk50);
            // Recover a warm-started PHY whose clock is already absent.
            if(n==3 || n==16) begin
                @(negedge clk60);
                clock_run=0;lowpower=1;ps=P_SLEEP;
                dir=1;phy_oe=1;nxt=0;phase=-1;
            end
            phy_reset_n=1;
            @(negedge clk50);reset_n=1;
            ticks=0;
            while(!done && !error && ticks<30000) begin
                @(negedge clk50);ticks=ticks+1;
            end
            if(ticks>=30000) $fatal(1,"50 MHz watchdog: scenario %0d stage=%02x",n,stage);
            if(expected_error==0) begin
                if(error || !done || stage!==8'h60)
                    $fatal(1,"scenario %0d unexpected failure code=%0d stage=%02x",n,errorcode,stage);
                if(!id_ok || vid!==16'h0424 || pid!==16'h0004)
                    $fatal(1,"incorrect VID/PID");
                if(suspend_writes!=4 || fc!==8'h41 || if_ctrl!==0 || otg!==6)
                    $fatal(1,"incomplete phases/final detach");
                if(phase_flags!==16'hffff || sample_counts!==32'h10101010 || !clock_stop_seen)
                    $fatal(1,"missing phase completion flags=%04x samples=%08x",phase_flags,sample_counts);
                if(n==0 || n==3) begin
                    if(direct_masks!==16'h1421 || direct_last!==8'h24)
                        $fatal(1,"normal low-power pins decoded incorrectly masks=%04x last=%02x",direct_masks,direct_last);
                end else if(n==1) begin
                    if(direct_masks!==16'h1881 || direct_last!==8'h3c)
                        $fatal(1,"SE1 control observations lost masks=%04x last=%02x",direct_masks,direct_last);
                end else if(n==2) begin
                    for(k=0;k<4;k=k+1) begin
                        nibble=direct_masks[k*4 +:4];
                        if(nibble!==4'hf) $fatal(1,"mixed raw line samples not preserved phase=%0d mask=%x",k,nibble);
                    end
                end
                if(n==3 && startup_wakes==0) $fatal(1,"stopped-clock startup was never exercised");
            end else begin
                if(!error || done || errorcode!==expected_error[3:0])
                    $fatal(1,"scenario %0d expected error=%0d got done=%b err=%b code=%0d stage=%02x",n,expected_error,done,error,errorcode,stage);
                if((n==4 || n==13) && (sample_counts!==0 || phase_flags[0]))
                    $fatal(1,"invalid/no sampling marked phase valid");
                if(n==16 && (!stp || drive_ready || sample_counts!==0))
                    $fatal(1,"stuck-clock startup did not remain parked with STP asserted");
            end
            $display("PASS lowpower scenario %0d code=%0d stage=%02x masks=%04x counts=%08x ticks=%0d",n,errorcode,stage,direct_masks,sample_counts,ticks);
            reset_n=0;phy_reset_n=0;clock_run=1;lowpower=0;
            repeat(5) @(negedge clk50);
        end
    endtask

    initial begin
        run_case(0,0);  // detached / FS / LS / detached, actual stopped clock
        run_case(1,0);  // SE1 is recorded, never mistaken for normal J
        run_case(2,0);  // asynchronous mixed line-state masks
        run_case(3,0);  // startup with CLKOUT already stopped and DIR high
        run_case(4,1);  // PHY fails to stop clock
        run_case(5,1);  // PHY fails to wake while Link holds STP
        run_case(6,3);  // wrong product ID
        run_case(7,4);  // Scratch data mismatch
        run_case(8,6);  // Interface Control readback mismatch
        run_case(9,6);  // Function Control does not restore after wake
        run_case(10,1); // register command never ACKed
        run_case(11,1); // register read response never arrives
        run_case(12,2); // PHY steals a write-data cycle
        run_case(13,5); // unknown asynchronous pins cannot become mask bit 0
        run_case(14,5); // DIR drops during low-power observation
        run_case(15,5); // CLKOUT resumes without an explicit wake
        run_case(16,1); // CLKOUT is absent at startup and never wakes
        if(total_sleep_ticks==0) $fatal(1,"test never entered clock-stopped low power");
        $display("PASS usb2_lowpower_diag FS_OTG_CTRL=%02x 17 scenarios; sleep_ticks=%0d raw-DIR checks=%0d",FS_OTG_CTRL,total_sleep_ticks,turnaround_checks);
        $finish;
    end
endmodule
