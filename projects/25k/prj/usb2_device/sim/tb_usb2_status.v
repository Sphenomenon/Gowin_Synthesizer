`timescale 1ns/1ps
`default_nettype none
module tb_usb2_status;
    localparam WINDOW = 5000; // 100 us; 60 MHz predicts 6000 edges (600000 per 10 ms).
    localparam SNAPSHOT = 40;
    reg clk50 = 0;
    reg clk60 = 0;
    reg clock60_enabled = 0;
    always #10 clk50 = ~clk50;
    always begin
        #8.333;
        if (clock60_enabled) clk60 = ~clk60;
        else clk60 = 0;
    end

    reg [23:0] source_tag = 0;
    reg [127:0] live_snapshot = 128'ha0000000_b0000000_c0000000_d0000000;
    // Change every source clock, including within each displayed page cycle.
    // Four distinct page markers share one tag, so torn snapshots are visible.
    always @(negedge clk60) begin
        if (clock60_enabled) begin
            source_tag = source_tag + 1'b1;
            live_snapshot = {8'ha0, source_tag, 8'hb0, source_tag,
                             8'hc0, source_tag, 8'hd0, source_tag};
        end
    end
    wire [63:0] raw_status;
    wire [3:0] result_flags;
    wire clock_alive;
    usb2_status_50mhz #(.WINDOW_CYCLES(WINDOW), .SNAPSHOT_CYCLES(SNAPSHOT)) dut (
        .clk_50mhz(clk50), .clk_ulpi60(clk60), .live_snapshot(live_snapshot),
        .status_50mhz(raw_status), .result_flags(result_flags),
        .clock_alive(clock_alive)
    );
    // Match the root top's additional preserved capture register.
    reg [63:0] status = 0;
    always @(posedge clk50) status <= raw_status;

    integer samples = 0;
    integer coherent_cycles = 0;
    integer nonzero_cycles = 0;
    integer run_length = 0;
    reg previous_hb = 0;
    reg [1:0] previous_page = 0;
    reg boundary_seen = 0;
    reg collecting = 0;
    reg expect_zero = 1;
    reg [23:0] expected_tag = 0;
    reg [7:0] expected_marker;
    reg [1:0] page;
    reg [31:0] payload;
    always @(negedge clk50) begin
        samples = samples + 1;
        page = status[2:1];
        payload = status[63:32];
        if (samples > 1 && status[0] === previous_hb)
            $fatal(1, "50 MHz GAO heartbeat stopped at sample %0d", samples);
        previous_hb = status[0];
        if (samples == 1 || page != previous_page) begin
            if (samples > 1) begin
                if (boundary_seen && run_length != 8)
                    $fatal(1, "Page %0d length %0d, expected eight", previous_page, run_length);
                if (page != ((previous_page + 1) & 3))
                    $fatal(1, "Page sequence %0d -> %0d", previous_page, page);
                boundary_seen = 1;
                if (previous_page == 3 && collecting) begin
                    coherent_cycles = coherent_cycles + 1;
                    if (!expect_zero) nonzero_cycles = nonzero_cycles + 1;
                end
            end
            run_length = 1;
            if (page == 0 && samples > 1) begin
                collecting = 1;
                expect_zero = payload == 0;
                expected_tag = payload[23:0];
            end
        end else run_length = run_length + 1;
        if (collecting) begin
            if (expect_zero) begin
                if (payload !== 0)
                    $fatal(1, "Snapshot changed from zero within page cycle");
            end else begin
                case (page)
                    0: expected_marker = 8'ha0;
                    1: expected_marker = 8'hb0;
                    2: expected_marker = 8'hc0;
                    3: expected_marker = 8'hd0;
                endcase
                if (payload[31:24] !== expected_marker || payload[23:0] !== expected_tag)
                    $fatal(1, "Torn page cycle: page=%0d payload=%h tag=%h", page, payload, expected_tag);
            end
        end
        previous_page = page;
    end

    task wait50;
        input integer count;
        begin
            repeat (count) @(posedge clk50);
            #1;
        end
    endtask
    task check_running_frequency;
        integer count;
        begin
            count = status[31:12];
            // Gray synchronization can shift the window endpoints by a few edges.
            if (count < 5997 || count > 6003)
                $fatal(1, "60 MHz frequency count %0d, expected about 6000 / 100 us", count);
            if (!status[3] || !clock_alive)
                $fatal(1, "clock_alive absent with %0d edges", count);
            $display("RUNNING: %0d edges / 100 us; equivalent %0d edges / 10 ms", count, count * 100);
        end
    endtask

    initial begin
        wait50(WINDOW * 2 + 4);
        if (status[31:12] !== 0 || status[63:32] !== 0 || status[3] || clock_alive)
            $fatal(1, "Initial absent clock: status=%h count=%h payload=%h alive=%b binary=%h gray=%h",
                   status, status[31:12], status[63:32], clock_alive, dut.binary_count, dut.gray_sync);
        $display("ABSENT: zero count and payload; 50 MHz heartbeat/page monitor remains active");
        @(negedge clk50);
        clock60_enabled = 1;
        wait50(WINDOW * 2 + 4);
        check_running_frequency;
        wait50(WINDOW);
        check_running_frequency;
        if (nonzero_cycles < 5)
            $fatal(1, "Too few nonzero coherent snapshots: %0d", nonzero_cycles);
        @(negedge clk50);
        clock60_enabled = 0;
        wait50(WINDOW * 2 + 4);
        if (status[31:12] !== 0 || status[3] || clock_alive)
            $fatal(1, "Stopped 60 MHz clock did not yield a complete zero-count window");
        if (samples < 30000 || coherent_cycles < 100)
            $fatal(1, "Insufficient monitor coverage");
        $display("PASS: absent/running/stopped PHY clock, %0d heartbeat samples, %0d coherent page cycles (%0d nonzero)",
                 samples, coherent_cycles, nonzero_cycles);
        $finish;
    end
    initial begin
        #2000000;
        $fatal(1, "Test timeout");
    end
endmodule
`default_nettype wire
