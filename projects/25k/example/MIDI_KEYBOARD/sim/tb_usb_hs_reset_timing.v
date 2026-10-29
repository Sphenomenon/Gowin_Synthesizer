`timescale 1ns/1ps
module tb_usb_hs_reset_timing;
    reg clk = 0;
    always #8.333 clk = !clk;
    reg reset = 1;
    reg enable = 0;
    reg bus_active = 0;
    reg [1:0] line_state = 1;
    reg [14:0] se0_count = 0;
    wire [1:0] opmode, xcvr;
    wire termsel, dppd, dmpd, chirp, high_speed, bus_reset, suspended;
    wire [2:0] state;
    real reset_started, chirp_started_us, chirp_ended_us;
    integer checks = 0;

    always @(posedge clk or posedge reset)
        if (reset) se0_count <= 0;
        else if (line_state != 0) se0_count <= 0;
        else if (!se0_count[14]) se0_count <= se0_count + 1'b1;

    midi_usb_hs_phy dut (
        .clk(clk), .reset(reset), .enable(enable), .se0_reset(se0_count[14]),
        .bus_active(bus_active), .line_state(line_state), .opmode(opmode),
        .xcvr(xcvr), .termsel(termsel), .dppd(dppd), .dmpd(dmpd),
        .chirp(chirp), .high_speed(high_speed), .bus_reset(bus_reset),
        .suspended(suspended), .state(state)
    );

    task check;
        input condition;
        input [511:0] message;
        begin
            checks = checks + 1;
            if (!condition) $fatal(1, "%0s", message);
        end
    endtask

    task negotiate;
        input integer warm_reset;
        begin
            @(negedge clk);
            line_state = 0;
            bus_active = 0;
            reset_started = $realtime;
            wait (chirp);
            chirp_started_us = ($realtime - reset_started) / 1000.0;
            wait (!chirp);
            chirp_ended_us = ($realtime - reset_started) / 1000.0;
            $display("reset warm=%0d: device K starts %.3f us, ends %.3f us",
                     warm_reset, chirp_started_us, chirp_ended_us);
            check(chirp_ended_us < 7000.0, "device K must finish inside Host 7ms negotiation window");
            check(chirp_ended_us - chirp_started_us >= 1000.0, "device K retains its minimum duration");
            check(bus_reset, "device reset remains asserted during speed negotiation");
            for (integer chirp_phase = 0; chirp_phase < 6; chirp_phase = chirp_phase + 1) begin
                @(negedge clk);
                line_state = chirp_phase % 2 == 0 ? 2 : 1;
                repeat (3000) @(negedge clk);
            end
            check(high_speed && state == 5, "qualified Host K-J sequence establishes HS");
            check(opmode == 0 && xcvr == 0 && !termsel, "HS transceiver configuration restored");
            @(negedge clk);
            bus_active = 1;
            line_state = 0;
            repeat (1000) @(negedge clk);
            check(high_speed && !bus_reset, "HS traffic retains the negotiated session");
        end
    endtask

    initial begin
        #50000000;
        $fatal(1, "HS reset timing regression timed out");
    end

    initial begin
        repeat (10) @(negedge clk);
        reset = 0;
        enable = 1;
        wait (state == 1);
        negotiate(0);
        negotiate(1);
        negotiate(1);
        $display("PASS USB HS reset timing: %0d checks, cold and repeated HS warm reset finish before 7ms", checks);
        $finish;
    end
endmodule
