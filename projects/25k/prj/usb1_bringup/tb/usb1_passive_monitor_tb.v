`timescale 1ns/1ps
module usb1_passive_monitor_tb;
    reg clk = 0;
    always #10 clk = !clk;
    reg rst = 1;
    reg dp = 1;
    reg dm = 0;
    wire [1:0] state;
    wire [31:0] transitions;
    wire activity, se0_long, se0_seen, se1_seen;
    usb1_passive_monitor dut (
        .clk(clk), .rst(rst), .usb_dp(dp), .usb_dm(dm),
        .line_state(state), .transition_count(transitions),
        .activity_seen(activity), .se0_long(se0_long),
        .se0_long_seen(se0_seen), .se1_long_seen(se1_seen)
    );
    task tick;
        input integer n;
        integer k;
        begin for (k = 0; k < n; k = k+1) begin @(posedge clk); #1; end end
    endtask
    task check;
        input condition;
        input [511:0] message;
        begin if (condition !== 1'b1) begin
            $display("FAIL: %0s", message); $fatal(1);
        end end
    endtask
    initial begin
        tick(3);
        @(negedge clk); rst = 0;
        tick(8);
        check(state == 2'b10, "J line state after synchronization");
        check(transitions == 0 && !activity, "ignore reset-release transitions");
        check(!se0_seen && !se1_seen, "initial synchronizer zeros are ignored");

        @(negedge clk); dp = 0; dm = 1;
        tick(6);
        check(state == 2'b01 && transitions == 1 && activity, "J to K observed once");

        // A USB packet EOP can include a short SE0; do not call it long.
        @(negedge clk); dm = 0;
        tick(12);
        check(!se0_long && !se0_seen, "short SE0 is not persistent");
        @(negedge clk); dp = 1;
        tick(6);
        check(!se0_long && !se0_seen, "short SE0 duration clears");

        @(negedge clk); dp = 0;
        tick(151);
        check(!se0_long, "3us threshold not early");
        tick(1);
        check(se0_long && se0_seen, "150 synchronized SE0 clocks detected");
        @(negedge clk); dp = 1;
        tick(5);
        check(!se0_long && se0_seen, "SE0 level clears and history remains");

        // Qualify SE1 so one-clock skew/glitches do not create a sticky error.
        @(negedge clk); dm = 1;
        tick(10);
        check(!se1_seen, "short SE1 is ignored");
        @(negedge clk); dm = 0;
        tick(5);
        @(negedge clk); dm = 1;
        tick(155);
        check(se1_seen, "long SE1 is latched");

        // Saturation is deliberate: a busy bus must not wrap to zero.
        @(negedge clk); dut.transition_count = 32'hffffffff; dm = 0;
        tick(5);
        check(transitions == 32'hffffffff, "transition counter saturates");
        @(negedge clk); rst = 1;
        tick(1);
        check(transitions == 0 && !activity && !se0_seen && !se1_seen,
              "reset clears accumulated diagnostics");
        $display("PASS: passive USB1 line monitor scenarios");
        $finish;
    end
endmodule
