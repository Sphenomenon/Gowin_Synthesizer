`timescale 1ns/1ps
module tb_usb2_serial_activity;
    reg clk=0, reset_n=0, init_done=0, usb_oe=0, usb_reset_released=0;
    reg [2:0] raw_data=0;
    wire [15:0] raw_transition_count;
    wire [7:0] event_flags, raw_seen_mask;
    always #8.333 clk=~clk;
    usb2_serial_activity dut (
        .clk_ulpi60(clk), .reset_n(reset_n), .init_done(init_done),
        .raw_data(raw_data), .usb_oe(usb_oe),
        .usb_reset_released(usb_reset_released),
        .raw_transition_count(raw_transition_count),
        .event_flags(event_flags), .raw_seen_mask(raw_seen_mask)
    );
    task automatic sample(input [2:0] value);
        begin
            @(negedge clk); raw_data=value;
            @(posedge clk); #1;
        end
    endtask
    integer i;
    initial begin
        repeat(2) @(posedge clk);
        @(negedge clk); reset_n=1; usb_oe=1;
        sample(3'd7); sample(3'd2); sample(3'd5);
        if(raw_transition_count!==0 || raw_seen_mask!==0 || event_flags!==0)
            $fatal(1,"init activity/reset/TX was counted");
        @(negedge clk); init_done=1; usb_oe=0; usb_reset_released=1; raw_data=0;
        sample(0); sample(0); sample(0);
        if(raw_transition_count!==0 || raw_seen_mask!==8'h01 || event_flags!==8'h01)
            $fatal(1,"initial/stable raw sample or reset-released flag incorrect");
        sample(2); sample(6); sample(0);
        if(raw_transition_count!==3 || raw_seen_mask!==8'h45)
            $fatal(1,"transition count or raw seen bit indexing incorrect");
        @(negedge clk); usb_reset_released=0;
        sample(0);
        if(event_flags!==8'h03) $fatal(1,"post-init reset assertion missing");
        @(negedge clk); usb_reset_released=1; usb_oe=1;
        sample(0);
        @(negedge clk); usb_oe=0;
        sample(0);
        if(event_flags!==8'h07) $fatal(1,"TX/reset event flags not sticky");
        @(negedge clk); init_done=0; usb_reset_released=0;
        sample(7); sample(4);
        if(raw_transition_count!==3 || raw_seen_mask!==8'h45 || event_flags!==8'h07)
            $fatal(1,"inactive gap changed captured evidence");
        @(negedge clk); init_done=1; usb_reset_released=1; raw_data=3;
        sample(3);
        if(raw_transition_count!==3) $fatal(1,"inactive gap created transition");
        for(i=0;i<8;i=i+1) sample(i[2:0]);
        if(raw_seen_mask!==8'hff) $fatal(1,"not all eight raw states recorded");
        // Force only the otherwise impractically long counter precondition;
        // real clocked DATA transitions must saturate it rather than wrap.
        @(negedge clk);
        force dut.raw_transition_count=16'hfffe;
        #1; release dut.raw_transition_count;
        sample(0);
        if(raw_transition_count!==16'hffff) $fatal(1,"counter missed saturation boundary");
        sample(1); sample(2);
        if(raw_transition_count!==16'hffff) $fatal(1,"counter wrapped after saturation");
        @(negedge clk); reset_n=0;
        @(posedge clk); #1;
        if(raw_transition_count!==0 || raw_seen_mask!==0 || event_flags!==0)
            $fatal(1,"reset did not clear all activity evidence");
        $display("PASS: raw activity ignores init/gaps, stable inputs, transitions, all seen-mask bits, sticky post-init reset/release/TX events, 16-bit saturation and reset clear");
        $finish;
    end
    initial begin #100000; $fatal(1,"activity test timeout"); end
endmodule
