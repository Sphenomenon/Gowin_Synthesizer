`timescale 1ns/1ps
module usb_boot_retry_case #(parameter integer PERMANENT=0)(output reg finished=0);
    localparam integer COOLDOWN=24,TIMEOUT=48;
    reg clk=0;always #10 clk=~clk;
    reg reset_n=0,dir=0,nxt=0;
    reg [7:0] phy_data=0;
    wire [7:0] data_o;
    wire data_oe,drive_ready,stp,done,error;
    wire [7:0] stage;
    wire [15:0] vid,pid;
    tri [7:0] data_bus;
    assign data_bus=data_oe?data_o:8'bz;
    assign data_bus=dir?phy_data:8'bz;
    midi_usb2_boot #(.STARTUP_CYCLES(3),.EXIT_MIN_CYCLES(4),
        .TIMEOUT_CYCLES(TIMEOUT),.MAX_PREEMPTIONS(3),.HANDOFF_GUARD_CYCLES(3),
        .RETRY_CYCLES(COOLDOWN)) dut(
        .clk_ulpi60(clk),.reset_n(reset_n),.data_i(data_bus),.data_o(data_o),
        .data_oe(data_oe),.drive_ready(drive_ready),.dir(dir),.nxt(nxt),.stp(stp),
        .done(done),.error(error),.stage(stage),.vid(vid),.pid(pid));
    integer failures=0,commands=0,cycles=0,prior_failure=-1000;
    time failure_at;
    always @(posedge clk)cycles=cycles+1;
    always @(posedge error)begin
        if(failures>0&&cycles-prior_failure<COOLDOWN+TIMEOUT)
            $fatal(1,"Permanent boot failure retried too quickly");
        prior_failure=cycles;failures=failures+1;failure_at=$time;
    end
    always @(negedge error)if(reset_n&&failures>0)
        if($time-failure_at<COOLDOWN*20)$fatal(1,"USB boot cooldown shorter than configured bound");
    always @(posedge clk)begin
        #1;
        if(dir&&data_oe)$fatal(1,"Boot drives DATA while PHY owns DIR");
        if(error&&(data_oe||drive_ready||stp||done))$fatal(1,"Boot must release DATA/STP throughout retry cooldown");
        if(data_oe!==((drive_ready&&!dir)))$fatal(1,"Immediate DIR ownership gate missing");
    end
    task wait_command(input [7:0] command);
        begin
            do @(negedge clk);while(!data_oe||data_o!==command||dir||nxt);
        end
    endtask
    task read_register(input [5:0] address,input [7:0] value);
        begin
            wait_command({2'b11,address});commands=commands+1;nxt=1;
            @(posedge clk);@(negedge clk);nxt=0;phy_data=value;dir=1;
            repeat(2)@(posedge clk);
            @(negedge clk);dir=0;phy_data=0;
        end
    endtask
    task write_register(input [5:0] address,input [7:0] value);
        begin
            wait_command({2'b10,address});commands=commands+1;nxt=1;
            @(posedge clk);@(negedge clk);
            if(!data_oe||data_o!==value)$fatal(1,"Wrong ULPI register write addr%02h data%02h expected%02h",address,data_o,value);
            @(posedge clk);@(negedge clk);nxt=0;
            if(!stp)$fatal(1,"ULPI write did not assert STP");
            @(posedge clk);@(negedge clk);
            if(stp)$fatal(1,"ULPI write STP did not release");
        end
    endtask
    initial begin
        repeat(4)@(negedge clk);reset_n=1;
        if(PERMANENT)begin
            // Never acknowledge the first register command. Repeated errors
            // must remain bounded in rate and must never claim completion.
            wait(failures==3);
            repeat(COOLDOWN-2)@(negedge clk);
            if(done||!error||failures!=3)$fatal(1,"Permanent error did not remain in bounded cooldown");
            finished=1;
        end else begin
            // An unresponsive first command must not permanently lock boot.
            wait_command(8'hc0);wait(error);wait(!error);
            // Also preempt the next attempt once. Raw DIR must suppress pad
            // drive immediately, before another ULPI clock edge can occur.
            wait_command(8'hc0);dir=1;phy_data=8'h5a;#1;
            if(data_oe||data_bus!==8'h5a)$fatal(1,"DIR did not release DATA immediately");
            repeat(3)@(posedge clk);@(negedge clk);dir=0;phy_data=0;
            read_register(0,8'h24);read_register(1,8'h04);read_register(2,8'h04);read_register(3,8'h00);
            write_register(6'h16,8'h55);read_register(6'h16,8'h55);
            write_register(6'h16,8'haa);read_register(6'h16,8'haa);
            write_register(6'h04,8'h41);read_register(6'h04,8'h41);
            write_register(6'h07,8'h00);read_register(6'h07,8'h00);
            write_register(6'h0a,8'h00);read_register(6'h0a,8'h00);
            wait(done);#1;
            if(error||vid!==16'h0424||pid!==16'h0004||stage!==8'h12||commands!=14||failures!=1)
                $fatal(1,"Retry did not perform complete verified initialization");
            repeat(COOLDOWN*3)@(negedge clk);
            if(!done||error||data_oe||drive_ready||stp||commands!=14||failures!=1)
                $fatal(1,"Successful handoff unexpectedly retried or held bus");
            finished=1;
        end
    end
endmodule
module tb_usb_board_boot;
    wire transient_done,permanent_done;
    usb_boot_retry_case transient_case(transient_done);
    usb_boot_retry_case #(.PERMANENT(1)) permanent_case(permanent_done);
    initial begin
        wait(transient_done&&permanent_done);
        $display("PASS USB3300 boot: first-command timeout recovers, complete VID/PID/scratch/config verification, immediate DIR release, permanent faults rate-limited with DATA released, success stays handed off");
        $finish;
    end
    initial begin #100_000;$fatal(1,"USB boot retry timeout transient=%b permanent=%b",transient_done,permanent_done);end
endmodule
