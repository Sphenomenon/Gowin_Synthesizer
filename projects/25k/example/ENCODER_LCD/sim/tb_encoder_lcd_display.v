`timescale 1ns/1ps
module tb_encoder_lcd_display;
    reg clk = 0;
    always #10 clk = !clk;
    reg reset = 1;
    localparam integer SIM_TICKS = 2;
    localparam integer SIM_DIV = 1;
    localparam integer SIM_GAP_MS = 2;
    localparam integer FULL_BYTES = 142*428*2;
    localparam integer PART_BYTES = 126*98*2;
    wire ncs, dc, sck, mosi, snapshot;
    wire [15:0] pixel_x, pixel_y;
    wire [31:0] completed_refreshes;
    reg [15:0] live_source = 16'h1234;
    reg [15:0] held_source = 0;
    reg perturb_low = 0;

    function [15:0] source_pixel;
        input integer x;
        input integer y;
        input [15:0] source;
        begin
            // Exercise both byte lanes and both coordinate axes.
            source_pixel = source ^ (x*257) ^ (y*73);
        end
    endfunction
    wire [15:0] pixel_color = source_pixel(pixel_x,pixel_y,held_source) ^
                               (perturb_low ? 16'h005a : 16'h0000);
    encoder_lcd_display #(
        .MS_TICKS(SIM_TICKS), .SPI_HALF_PERIOD(SIM_DIV),
        .BOOT_MS(3), .POST_INIT_MS(150), .REFRESH_GAP_MS(SIM_GAP_MS)
    ) dut (
        .clk(clk), .reset(reset), .pixel_color(pixel_color),
        .pixel_x(pixel_x), .pixel_y(pixel_y), .snapshot(snapshot),
        .completed_refreshes(completed_refreshes),
        .lcd_ncs(ncs), .lcd_dc(dc), .lcd_sck(sck), .lcd_mosi(mosi)
    );

    reg [17:0] init_expected [0:250];
    integer cycle = 0;
    integer snapshots = 0;
    integer snapshot_cycle = 0;
    integer previous_snapshot_cycle = 0;
    integer last_pair_end_cycle = 0;
    reg previous_snapshot = 0;
    reg [15:0] expected_source = 0;
    integer window_number = 0; // 0 full, then upper/lower/upper/lower
    always @(posedge clk) begin
        cycle = cycle + 1;
        // Emulate the top's snapshot latch: changes to live encoder values
        // become visible only when this pulse is sampled.
        if (!reset && snapshot) begin
            if (previous_snapshot) $fatal(1, "snapshot lasted more than one clock");
            held_source <= live_source;
            expected_source = live_source;
            snapshots = snapshots + 1;
            previous_snapshot_cycle = snapshot_cycle;
            snapshot_cycle = cycle;
            if (snapshots > 1 && window_number != 1 && window_number != 3 && window_number != 5)
                $fatal(1, "snapshot split the two partial windows");
            if (snapshots > 2 && cycle-last_pair_end_cycle < SIM_GAP_MS*SIM_TICKS)
                $fatal(1, "refresh gap shorter than %0d simulated ms", SIM_GAP_MS);
        end
        previous_snapshot = snapshot;
        #1;
        if (!reset && dut.tx_start && dut.tx_busy)
            $fatal(1, "SPI engine received start while busy");
        if (!reset && dut.tx_start && !dut.waiting_tx)
            $fatal(1, "byte issued without completion handshake");
    end

    integer bits = 0;
    integer phase = 0; // 0: init, 1: window header, 2: pixels, 3: between windows
    integer init_index = 0;
    integer header_index = 0;
    integer pixel_byte = 0;
    integer last_byte_cycle = 0;
    integer ended_windows = 0;
    integer start_transactions = 0;
    integer completed_transactions = 0;
    integer expected_width;
    integer expected_height;
    integer expected_x;
    integer expected_y;
    reg [7:0] assembled = 0;
    reg byte_dc;
    reg last_tx_start = 0;
    time last_sck_change = 0;
    time last_mosi_change = 0;
    time last_dc_change = 0;

    // Independent explicit headers: full native panel, then the two panels.
    function [8:0] expected_header;
        input integer number;
        input integer index;
        integer translated_index;
        begin
            if (number == 0) begin
                case (index)
                    0: expected_header=9'h036;
                    1: expected_header=9'h100;
                    2: expected_header=9'h020;
                    3: expected_header=9'h02a;
                    4: expected_header=9'h100;
                    5: expected_header=9'h10c;
                    6: expected_header=9'h100;
                    7: expected_header=9'h199;
                    8: expected_header=9'h02b;
                    9: expected_header=9'h100;
                    10: expected_header=9'h100;
                    11: expected_header=9'h101;
                    12: expected_header=9'h1ab;
                    default: expected_header=9'h02c;
                endcase
            end else begin
                case (index)
                    0: expected_header=9'h02a;
                    1: expected_header=9'h100;
                    2: expected_header=9'h114; // logical x=8 + offset 12
                    3: expected_header=9'h100;
                    4: expected_header=9'h191; // logical x=133 + offset 12
                    5: expected_header=9'h02b;
                    6: expected_header=number%2 ? 9'h100 : 9'h101;
                    7: expected_header=number%2 ? 9'h148 : 9'h100;
                    8: expected_header=number%2 ? 9'h100 : 9'h101;
                    9: expected_header=number%2 ? 9'h1a9 : 9'h161;
                    default: expected_header=9'h02c;
                endcase
            end
        end
    endfunction

    task check_byte;
        input [7:0] value;
        input value_dc;
        integer required_delay;
        integer pixel_number;
        reg [15:0] expected_color;
        reg [7:0] expected_byte;
        begin
            if (phase == 0) begin
                required_delay = 0;
                while (init_expected[init_index][17:16] == 2) begin
                    required_delay = required_delay + init_expected[init_index][15:0]*SIM_TICKS;
                    init_index = init_index + 1;
                end
                if (cycle-last_byte_cycle < required_delay)
                    $fatal(1, "init delay shortened at token %0d", init_index);
                if ({value_dc,value} !== {init_expected[init_index][16],init_expected[init_index][7:0]})
                    $fatal(1, "init token %0d got %h/%h expected %h", init_index, value_dc, value, init_expected[init_index]);
                init_index = init_index + 1;
                if (init_index == 251) phase = 1;
            end else begin
                if (phase == 3) begin
                    if (ended_windows != window_number)
                        $fatal(1, "window started before prior CS deassertion");
                    phase = 1;
                    header_index = 0;
                end
                if (phase == 1) begin
                    if (header_index == 0) begin
                        if (window_number == 0 && cycle-last_byte_cycle < 150*SIM_TICKS)
                            $fatal(1, "post-init delay shortened");
                        if (snapshots != (window_number+1)/2+1)
                            $fatal(1, "wrong snapshot count %0d for window %0d", snapshots, window_number);
                        if ((window_number == 0 || window_number%2 == 1) && cycle-snapshot_cycle < 32)
                            $fatal(1, "renderer settling time shorter than 32 clocks");
                    end
                    if ({value_dc,value} !== expected_header(window_number,header_index))
                        $fatal(1, "window %0d header %0d got %h/%h expected %h", window_number, header_index, value_dc, value, expected_header(window_number,header_index));
                    header_index = header_index + 1;
                    if (header_index == (window_number == 0 ? 14 : 11)) begin
                        pixel_byte = 0;
                        phase = 2;
                    end
                end else if (phase == 2) begin
                    if (!value_dc) $fatal(1, "pixel byte appeared with command DC");
                    expected_width = window_number == 0 ? 142 : 126;
                    expected_height = window_number == 0 ? 428 : 98;
                    pixel_number = pixel_byte/2;
                    expected_x = pixel_number%expected_width + (window_number == 0 ? 0 : 8);
                    expected_y = pixel_number/expected_width +
                        (window_number == 0 ? 0 : window_number%2 ? 72 : 256);
                    expected_color = source_pixel(expected_x,expected_y,expected_source);
                    expected_byte = pixel_byte%2 ? expected_color[7:0] : expected_color[15:8];
                    if (value !== expected_byte)
                        $fatal(1, "window %0d pixel byte %0d (%0d,%0d) got %h expected %h", window_number, pixel_byte, expected_x, expected_y, value, expected_byte);
                    // Change only the low byte of renderer output after each
                    // high byte. The driver's RGB565 latch must preserve it.
                    perturb_low = pixel_byte%2 == 0;
                    if (window_number == 1 && pixel_byte == 100)
                        live_source = 16'h5678;
                    if (window_number == 3 && pixel_byte == 100)
                        live_source = 16'h9abc;
                    pixel_byte = pixel_byte + 1;
                    if (pixel_byte == expected_width*expected_height*2) begin
                        phase = 3;
                        window_number = window_number + 1;
                    end
                end
            end
            last_byte_cycle = cycle;
        end
    endtask

    always @(posedge clk) begin
        if (!reset) begin
            if (dut.tx_start) begin
                if (last_tx_start) $fatal(1, "tx_start lasted more than one clock");
                start_transactions = start_transactions + 1;
            end
            if (dut.tx_done) begin
                completed_transactions = completed_transactions + 1;
                if (completed_transactions > start_transactions)
                    $fatal(1, "SPI completion without a start");
            end
        end
        last_tx_start = dut.tx_start;
    end
    always @(mosi) begin
        if (sck === 1'b1) $fatal(1, "MOSI changed while SCK high");
        last_mosi_change = $time;
    end
    always @(dc) begin
        if (sck === 1'b1) $fatal(1, "DC changed while SCK high");
        last_dc_change = $time;
    end
    always @(ncs) begin
        if (sck === 1'b1) $fatal(1, "CS changed while SCK high");
    end
    always @(posedge ncs) begin
        if (!reset) begin
            if (sck !== 1'b0 || bits != 0)
                $fatal(1, "CS deasserted mid-byte or with SCK high");
            if (phase == 3) begin
                ended_windows = ended_windows + 1;
                if (window_number == 3 || window_number == 5)
                    last_pair_end_cycle = cycle;
                if (window_number == 5) begin
                    #1;
                    if (completed_refreshes !== 3 || snapshots != 3)
                        $fatal(1, "wrong completed refresh/snapshot count: %0d/%0d", completed_refreshes, snapshots);
                    if (completed_transactions != start_transactions)
                        $fatal(1, "SPI start/completion counts differ");
                    $display("PASS: exact NV3007 init; full 142x428 frame; two 126x98 window pairs; all %0d pixel bytes; coherent snapshots; latched RGB565; mode-0 timing and handshake", FULL_BYTES+4*PART_BYTES);
                    $finish;
                end
            end
        end
    end
    always @(negedge sck) begin
        if (!reset && $time-last_sck_change != 20*SIM_DIV)
            $fatal(1, "SPI high half-period incorrect");
        last_sck_change = $time;
    end
    always @(posedge sck) begin
        if (ncs !== 1'b0) $fatal(1, "SCK rose while CS inactive");
        if ($time-last_sck_change < 20*SIM_DIV) $fatal(1, "SPI low half-period too short");
        if ($time-last_mosi_change < 20*SIM_DIV) $fatal(1, "MOSI setup too short");
        if ($time-last_dc_change < 20*SIM_DIV) $fatal(1, "DC setup too short");
        last_sck_change = $time;
        if (bits == 0) byte_dc = dc;
        else if (byte_dc !== dc) $fatal(1, "DC changed within byte");
        assembled = {assembled[6:0],mosi};
        bits = bits + 1;
        if (bits == 8) begin
            check_byte(assembled,byte_dc);
            bits = 0;
        end
    end

    initial begin
        $readmemh("sim/init_expected.mem",init_expected);
        repeat (5) @(negedge clk);
        reset = 0;
        #160000000;
        $fatal(1, "timeout phase=%0d window=%0d pixel_byte=%0d",phase,window_number,pixel_byte);
    end

    // A second instance audits the hardware-default 5 MHz SPI divider. It is
    // reset independently and stops after two bytes, so the full-frame audit
    // above remains fast while the actual SCK timing is covered explicitly.
    reg default_reset = 1'b1;
    wire default_ncs, default_dc, default_sck, default_mosi;
    reg [15:0] default_pixel = 16'h55aa;
    wire [15:0] default_x, default_y;
    wire default_snapshot;
    wire [31:0] default_completed;
    encoder_lcd_display #(
        .MS_TICKS(SIM_TICKS), .SPI_HALF_PERIOD(5),
        .BOOT_MS(0), .POST_INIT_MS(0), .REFRESH_GAP_MS(SIM_GAP_MS)
    ) default_spi_dut (
        .clk(clk), .reset(default_reset), .pixel_color(default_pixel),
        .pixel_x(default_x), .pixel_y(default_y), .snapshot(default_snapshot),
        .completed_refreshes(default_completed), .lcd_ncs(default_ncs),
        .lcd_dc(default_dc), .lcd_sck(default_sck), .lcd_mosi(default_mosi)
    );
    integer default_edges = 0;
    time default_last_transition = 0;
    reg default_seen_transition = 0;
    reg default_seen_edge = 0;
    reg default_audit_done = 0;
    always @(default_mosi or default_dc or default_ncs) begin
        if (!default_reset && default_sck === 1'b1)
            $fatal(1, "default SPI CS/DC/MOSI changed while SCK high");
    end
    always @(default_sck) begin
        if (!default_reset && (default_sck === 1'b0 || default_sck === 1'b1)) begin
            if (default_seen_transition) begin
                // HALF_PERIOD_CYCLES=5 at a 50 MHz clock is 100 ns. The
                // low phase may be longer at byte boundaries while CS stays
                // asserted; every high phase must remain exactly one half.
                if (default_sck === 1'b0 && $time-default_last_transition !== 100)
                    $fatal(1, "default SPI high half-period not 100 ns: %0t", $time-default_last_transition);
                if (default_sck === 1'b1 && $time-default_last_transition < 100)
                    $fatal(1, "default SPI low half-period shorter than 100 ns: %0t", $time-default_last_transition);
            end
            default_last_transition = $time;
            default_seen_transition = 1'b1;
            if (default_sck === 1'b1) begin
                if (default_ncs !== 1'b0) $fatal(1, "default SPI rose while CS inactive");
                default_edges = default_edges + 1;
                default_seen_edge = 1'b1;
            end
        end
    end
    initial begin
        repeat (5) @(negedge clk);
        default_reset = 1'b0;
        wait (default_edges >= 16);
        if (!default_seen_edge) $fatal(1, "default SPI produced no edge");
        default_audit_done = 1'b1;
        $display("PASS: default SPI divider produces 5 MHz SCK with mode-0 edge discipline");
    end
endmodule
