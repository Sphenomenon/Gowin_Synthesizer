`timescale 1ns/1ps
// Pin-level USB3300 register model for the fixed voltage-measurement image.
// The model checks transaction order independently of the DUT state machine.
module tb_usb2_measure;
    reg clk50=0,clk60=0,clock_run=1;
    always #10 clk50=!clk50;
    always begin #8.333;if(clock_run) clk60=!clk60;else clk60=0;end
    reg phy_reset_n=0,dir=0,nxt=0,phy_oe=0;
    reg [7:0] phy_data=0;
    tri [7:0] data;
    assign data=phy_oe ? phy_data : 8'hzz;
    wire stp,led_ready,led_done;
    usb2_device_top #(.TIMEOUT_CYCLES(2000),.STARTUP_CYCLES(8),
        .POLL_GAP_CYCLES(9)) dut (
        .clk_50mhz(clk50),.clk_ulpi60(clk60),.ulpi_data(data),
        .ulpi_dir(dir),.ulpi_nxt(nxt),.ulpi_stp(stp),
        .led_ready(led_ready),.led_done(led_done));

    localparam P_IDLE=0,P_CMD_WAIT=1,P_CMD_ACK=2,P_R_TURN=3,P_R_DATA=4,
        P_R_RELEASE=5,P_W_WAIT=6,P_W_ACK=7,P_W_STOP=8,P_W_RELEASE=9,P_HOLD=10;
    integer ps=P_IDLE,scenario=0,stall=0,transactions=0,writes=0,reads=0;
    integer debug_responses=0,i;
    reg [7:0] regs[0:63];
    reg [7:0] command=0,held_write=0,last_debug_response=0;
    reg [3:0] expected_debug_mask=0;
    reg [5:0] addr=0;
    reg wr=0,write_valid=0;
    wire link_oe=dut.drive_ready && !dir;

    function [5:0] expected_addr;
        input integer index;
        begin
            case(index)
                0:expected_addr=0;1:expected_addr=1;
                2:expected_addr=2;3:expected_addr=3;
                4,5,6,7:expected_addr=6'h16;
                8,9:expected_addr=6'h07;
                10,11:expected_addr=6'h0a;
                12,13:expected_addr=6'h04;
                default:expected_addr=6'h15;
            endcase
        end
    endfunction
    function expected_write;
        input integer index;
        begin expected_write=index==4 || index==6 || index==8 || index==10 || index==12;end
    endfunction
    function [7:0] expected_data;
        input integer index;
        begin
            case(index)
                4:expected_data=8'h55;6:expected_data=8'haa;
                8:expected_data=8'h00;10:expected_data=8'h04;
                12:expected_data=8'h45;
                default:expected_data=8'hxx;
            endcase
        end
    endfunction

    always @(posedge clk60) begin
        if(!phy_reset_n) begin
            ps<=P_IDLE;dir<=0;nxt<=0;phy_oe<=0;phy_data<=0;
            stall<=0;transactions<=0;writes<=0;reads<=0;
            debug_responses<=0;last_debug_response<=0;expected_debug_mask<=0;
            command<=0;addr<=0;wr<=0;held_write<=0;write_valid<=0;
            for(i=0;i<64;i=i+1) regs[i]<=0;
            regs[0]<=8'h24;regs[1]<=8'h04;
            regs[2]<=scenario==1 ? 8'h05 : 8'h04;regs[3]<=0;
            regs[4]<=8'h41;regs[7]<=0;regs[10]<=6;
        end else if(dut.error) begin
            nxt<=0;phy_oe<=0;dir<=0;ps<=P_HOLD;
        end else case(ps)
            P_IDLE: begin
                dir<=0;nxt<=0;phy_oe<=0;
                if(!stp && link_oe && (data[7:6]==2'b10 || data[7:6]==2'b11)) begin
                    if(data[5:0]!==expected_addr(transactions) ||
                       (!data[6])!==expected_write(transactions))
                        $fatal(1,"measurement register order index=%0d command=%02x",transactions,data);
                    command<=data;addr<=data[5:0];wr<=!data[6];
                    stall<=2;ps<=P_CMD_WAIT;
                end
            end
            P_CMD_WAIT: begin
                if(stp || data!==command || !link_oe) $fatal(1,"command changed before NXT");
                if(stall==0) begin nxt<=1;ps<=P_CMD_ACK;end
                else stall<=stall-1;
            end
            P_CMD_ACK: begin
                if(stp || data!==command || !link_oe) $fatal(1,"invalid command acceptance");
                nxt<=0;transactions<=transactions+1;
                if(wr) begin stall<=3;write_valid<=0;ps<=P_W_WAIT;end
                else begin
                    reads<=reads+1;
                    if(scenario==6 || (scenario==7 && addr==6'h15 && debug_responses>=3)) ps<=P_HOLD;
                    else begin dir<=1;phy_oe<=0;ps<=P_R_TURN;end
                end
            end
            P_R_TURN: begin
                if(link_oe) $fatal(1,"Link drives read turnaround");
                phy_oe<=1;phy_data<=regs[addr];
                if(addr==6'h15) begin
                    if(regs[4]!==8'h45 || regs[7]!==0 || regs[10]!==8'h04 || writes!=5)
                        $fatal(1,"Debug polled before fixed FC/IF/OTG configuration");
                    // Upper bits vary too: verify the whole Debug byte is live.
                    phy_data<={debug_responses[5:0],debug_responses[1:0]};
                end
                if(scenario==2 && addr==6'h16) phy_data<=regs[addr]^8'h01;
                if(scenario==3 && addr==6'h07) phy_data<=8'h02;
                if(scenario==4 && addr==6'h0a) phy_data<=8'h00;
                if(scenario==5 && addr==6'h04) phy_data<=8'h41;
                ps<=P_R_DATA;
            end
            P_R_DATA: begin
                if(link_oe || !dir || nxt) $fatal(1,"invalid register response ownership");
                if(addr==6'h15) begin
                    debug_responses<=debug_responses+1;
                    last_debug_response<=phy_data;
                    expected_debug_mask<=expected_debug_mask | (4'b0001 << phy_data[1:0]);
                end
                dir<=0;phy_oe<=0;ps<=P_R_RELEASE;
            end
            P_R_RELEASE: begin
                if(link_oe) $fatal(1,"Link drives PHY-to-Link turnaround");
                ps<=P_IDLE;
            end
            P_W_WAIT: begin
                if(stp || !link_oe) $fatal(1,"write data absent while stalled");
                if(write_valid && data!==held_write) $fatal(1,"write data changed before NXT");
                held_write<=data;write_valid<=1;
                if(stall==0) begin nxt<=1;ps<=P_W_ACK;end
                else stall<=stall-1;
            end
            P_W_ACK: begin
                if(stp || !link_oe || data!==held_write) $fatal(1,"invalid write acceptance");
                if(data!==expected_data(transactions-1))
                    $fatal(1,"incorrect configuration write index=%0d data=%02x",transactions-1,data);
                // This image must never suspend, enter serial mode, or drive VBUS.
                if((addr==4 && !data[6]) || (addr==7 && data!=0) ||
                   (addr==10 && data!=8'h04)) $fatal(1,"unexpected suspend/serial/VBUS command");
                regs[addr]<=data;writes<=writes+1;nxt<=0;ps<=P_W_STOP;
            end
            P_W_STOP: if(stp) ps<=P_W_RELEASE;
            P_W_RELEASE: if(!stp) ps<=P_IDLE;
            P_HOLD: begin end
            default:$fatal(1,"unknown PHY BFM state");
        endcase
    end

    // Debug result checking observes each 50 MHz count update, rather than
    // assuming a fixed CDC latency or using DUT state to select PHY responses.
    reg [19:0] previous_debug_count=0;
    always @(negedge clk50) begin
        if(phy_reset_n && dut.reset_n) begin
            if(link_oe && phy_oe) $fatal(1,"measurement DATA contention");
            if(dut.debug_read_count!=previous_debug_count) begin
                if(dut.debug_read_count!==debug_responses || dut.debug_last!==last_debug_response ||
                   dut.debug_seen_mask!==expected_debug_mask || !dut.done || !dut.id_ok || dut.error)
                    $fatal(1,"Debug result did not update live count=%0d model=%0d last=%02x model_last=%02x mask=%x model_mask=%x",dut.debug_read_count,debug_responses,dut.debug_last,last_debug_response,dut.debug_seen_mask,expected_debug_mask);
            end
        end
        previous_debug_count=dut.debug_read_count;
    end

    // Verify actual top page packing and metadata against the committed
    // runtime values; a queued commit only becomes current at the next page 0.
    reg [127:0] queued_pages=0,expected_pages=0;
    reg [7:0] queued_stage=0,expected_stage=0;
    reg [4:0] queued_flags=0,expected_flags=0;
    reg [1:0] previous_page=0;
    reg previous_heartbeat=0,have_heartbeat=0;
    integer checked_pages=0;
    always @(posedge clk50) begin
        if(dut.page_phase==31) begin
            queued_pages={dut.vid,dut.pid,dut.fc,dut.if_ctrl,dut.otg,4'b0,dut.errorcode,
                dut.debug_last,dut.debug_seen_mask,dut.debug_read_count,32'b0};
            queued_stage=dut.stage;
            queued_flags={1'b0,dut.done,dut.id_ok,dut.error,dut.clock_alive};
        end
    end
    reg [31:0] expected_payload;
    always @(negedge clk50) begin
        if(previous_page==3 && dut.status_50mhz[2:1]==0) begin
            expected_pages=queued_pages;expected_stage=queued_stage;expected_flags=queued_flags;
        end
        case(dut.status_50mhz[2:1])
            0:expected_payload=expected_pages[127:96];
            1:expected_payload=expected_pages[95:64];
            2:expected_payload=expected_pages[63:32];
            3:expected_payload=expected_pages[31:0];
        endcase
        if(dut.status_50mhz[63:32]!==expected_payload ||
           dut.status_50mhz[31:16]!==16'h0000 ||
           dut.status_50mhz[15:8]!==expected_stage ||
           dut.status_50mhz[7:3]!==expected_flags)
            $fatal(1,"measurement page packing/metadata mismatch status=%016x expected_payload=%08x",dut.status_50mhz,expected_payload);
        if(have_heartbeat && dut.status_50mhz[0]===previous_heartbeat)
            $fatal(1,"measurement 50MHz status heartbeat stopped");
        checked_pages=checked_pages+1;have_heartbeat=1;
        previous_heartbeat=dut.status_50mhz[0];previous_page=dut.status_50mhz[2:1];
    end

    task run_case;
        input integer n;
        input integer expected_error;
        integer ticks;
        begin
            scenario=n;phy_reset_n=0;clock_run=1;
            force dut.powerup=13'h0000;
            repeat(10) @(negedge clk50);
            phy_reset_n=1;
            if(n==9) begin clock_run=0;clk60=0;end
            force dut.powerup=13'h1000;
            ticks=0;
            if(n==0 || n==8) begin
                while(dut.debug_read_count<8 && !dut.error && ticks<10000) begin
                    @(negedge clk50);ticks=ticks+1;
                end
                if(dut.error || ticks>=10000 || !led_done || !dut.id_ok ||
                   dut.vid!==16'h0424 || dut.pid!==16'h0004 ||
                   dut.fc!==8'h45 || dut.if_ctrl!==0 || dut.otg!==8'h04 ||
                   dut.debug_seen_mask!==4'hf || writes!=5)
                    $fatal(1,"measurement normal init/poll failed scenario=%0d stage=%02x",n,dut.stage);
                if(n==8) begin
                    while(ps!=P_IDLE && ticks<10000) begin @(negedge clk50);ticks=ticks+1;end
                    if(ticks>=10000) $fatal(1,"model never idle before clock-stop");
                    // Only stop at a falling edge; all following progress and
                    // the watchdog continue on the independent 50MHz clock.
                    @(negedge clk60);clock_run=0;
                end else begin
                    repeat(400) @(negedge clk50);
                    if(dut.error || writes!=5 || regs[4]!==8'h45 || regs[7]!==0 || regs[10]!==4 ||
                        dut.debug_read_count<16) $fatal(1,"configuration changed during continuous polling");
                end
            end
            if(expected_error!=0) begin
                ticks=0;
                while(!dut.error && ticks<10000) begin @(negedge clk50);ticks=ticks+1;end
                if(ticks>=10000 || dut.errorcode!==expected_error[3:0] || dut.done || led_done ||
                    !stp || dut.drive_ready)
                    $fatal(1,"scenario %0d expected code=%0d actual code=%0d stage=%02x STP=%b OE=%b",n,expected_error,dut.errorcode,dut.stage,stp,dut.drive_ready);
                if(n==8 || n==9) begin
                    #1;if(data!==8'hzz) $fatal(1,"stopped-clock timeout failed asynchronous pad release");
                end
            end
            $display("PASS measure scenario %0d error=%0d stage=%02x debug_reads=%0d writes=%0d",n,dut.errorcode,dut.stage,dut.debug_read_count,writes);
            phy_reset_n=0;clock_run=1;force dut.powerup=13'h0000;
            repeat(5) @(negedge clk50);
        end
    endtask
    initial begin
        run_case(0,0); // initialization, all four Debug line values, continuous live polling
        run_case(1,3); // incorrect product ID
        run_case(2,4); // incorrect Scratch readback
        run_case(3,6); // incorrect Interface Control readback
        run_case(4,6); // incorrect OTG Control readback
        run_case(5,6); // incorrect Function Control readback
        run_case(6,1); // first register read response never arrives
        run_case(7,1); // live Debug reads stop responding after done
        run_case(8,1); // CLKOUT stops after valid runtime Debug samples
        run_case(9,1); // no CLKOUT at startup
        if(checked_pages<100) $fatal(1,"measurement page checks not exercised");
        $display("PASS usb2_measure 10 independent PHY scenarios and %0d four-page/status cycles",checked_pages);
        $finish;
    end
endmodule
