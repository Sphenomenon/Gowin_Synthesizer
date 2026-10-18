`timescale 1ns/1ps
module tb_lcd_bringup;
    reg clk = 0;
    always #10 clk = !clk;
    localparam integer SIM_TICKS=2, SIM_DIV=2;
    wire ncs, dc, sck, mosi;
    lcd_bringup_top #(
        .MS_TICKS(SIM_TICKS), .SPI_HALF_PERIOD(SIM_DIV),
        .BOOT_MS(3), .POST_INIT_MS(150), .FRAME_GAP_MS(500)
    ) dut (.clk(clk), .lcd_te(1'b0), .lcd_ncs(ncs), .lcd_dc(dc),
           .lcd_sck(sck), .lcd_mosi(mosi));

    wire off_ncs, off_dc, off_sck, off_mosi;
    lcd_bringup_top #(.ENABLE_PANEL_INIT(0), .ENABLE_ROW_LABELS(0)) disabled_dut (
        .clk(clk), .lcd_te(1'b0), .lcd_ncs(off_ncs), .lcd_dc(off_dc),
        .lcd_sck(off_sck), .lcd_mosi(off_mosi));

    reg [17:0] init_expected [0:250];
    reg [8:0] header_expected [0:13];
    integer cycle = 0;
    always @(posedge clk) begin
        cycle = cycle + 1;
        #1;
        if (!disabled_dut.reset && {off_ncs,off_dc,off_sck,off_mosi} !== 4'b1000)
            $fatal(1, "disabled configuration did not hold safe SPI outputs");
        if (!dut.reset && dut.tx_start && dut.tx_busy)
            $fatal(1, "byte engine received start while busy");
    end

    integer bits = 0;
    integer phase = 0; // init, first header, pixels, wait/gap, second header
    integer init_index = 0;
    integer header_index = 0;
    integer pixel_byte = 0;
    integer last_byte_cycle = 0;
    integer gap_cycle = 0;
    reg byte_dc;
    reg [7:0] assembled = 0;
    time last_sck_change = 0;
    time last_mosi_change = 0;
    time last_dc_change = 0;
    reg saw_frame_end = 0;

    // Reference uses byte-wide font rows and arithmetic decimal conversion,
    // independent of the DUT's packed glyphs and constant BCD lookup.
    function [4:0] reference_digit_row;
        input integer digit;
        input integer row;
        reg [55:0] rows;
        begin
            case (digit)
                0: rows=56'h0e11111111110e;
                1: rows=56'h040c040404040e;
                2: rows=56'h0e11010204081f;
                3: rows=56'h1e01010e01011e;
                4: rows=56'h02060a121f0202;
                5: rows=56'h1f10101e01011e;
                6: rows=56'h0e10101e11110e;
                7: rows=56'h1f010204080808;
                8: rows=56'h0e11110e11110e;
                9: rows=56'h0e11110f01010e;
                default: rows=0;
            endcase
            reference_digit_row = rows >> ((6-row)*8);
        end
    endfunction

    function [15:0] reference_pixel;
        input integer x;
        input integer y;
        integer bar;
        integer label_value;
        integer digit;
        integer glyph_x;
        reg [4:0] glyph_row;
        reg ink;
        begin
            // Exact default panel thresholds, independent of the DUT function.
            if (x == 0 || x == 141 || y == 0 || y == 427)
                reference_pixel = 16'hffff;
            else if (x >= 2 && x <= 25 && y%32 >= 1 && y%32 <= 10) begin
                label_value = (y/32)*32;
                digit = 0;
                glyph_x = -1;
                ink = 0;
                if (x >= 3 && x <= 7) begin
                    digit = label_value/100; glyph_x = x-3;
                end else if (x >= 9 && x <= 13) begin
                    digit = (label_value/10)%10; glyph_x = x-9;
                end else if (x >= 15 && x <= 19) begin
                    digit = label_value%10; glyph_x = x-15;
                end
                if (glyph_x >= 0 && y%32 >= 2 && y%32 <= 8) begin
                    glyph_row = reference_digit_row(digit, y%32-2);
                    ink = glyph_row[4-glyph_x];
                end
                if (x >= 21 && x <= 24 && y%32 == 5) ink=1;
                reference_pixel = ink ? 16'h0000 : 16'hffff;
            end
            else begin
                if (x < 17) bar=0;
                else if (x < 35) bar=1;
                else if (x < 53) bar=2;
                else if (x < 71) bar=3;
                else if (x < 88) bar=4;
                else if (x < 106) bar=5;
                else if (x < 124) bar=6;
                else bar=7;
                case (bar)
                    0: reference_pixel=16'hffff;
                    1: reference_pixel=16'hffe0;
                    2: reference_pixel=16'h07ff;
                    3: reference_pixel=16'h07e0;
                    4: reference_pixel=16'hf81f;
                    5: reference_pixel=16'hf800;
                    6: reference_pixel=16'h001f;
                    default: reference_pixel=16'h0000;
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
                    $fatal(1, "init delay shortened: got %0d, need %0d", cycle-last_byte_cycle, required_delay);
                if ({value_dc,value} !== {init_expected[init_index][16],init_expected[init_index][7:0]})
                    $fatal(1, "init token %0d: DC/data got %h/%h expected %h", init_index, value_dc, value, init_expected[init_index]);
                init_index = init_index + 1;
                if (init_index == 251) phase = 1;
            end else if (phase == 1 || phase == 4) begin
                if (header_index == 0 && phase == 1 && cycle-last_byte_cycle < 150*SIM_TICKS)
                    $fatal(1, "post-init delay shortened");
                if ({value_dc,value} !== header_expected[header_index])
                    $fatal(1, "window byte %0d got %h/%h expected %h", header_index, value_dc, value, header_expected[header_index]);
                header_index = header_index + 1;
                if (header_index == 14) begin
                    if (phase == 4) begin
                        if (dut.completed_frames !== 1)
                            $fatal(1, "incorrect completed frame counter");
                        $display("PASS: 250 init SPI bytes; delay/DC/CS/mode0 timing; exact 142x428 RGB565 frame and decimal row labels (121552 bytes); col12/row0 next-frame window; disabled safe state");
                        $finish;
                    end
                    phase = 2;
                end
            end else if (phase == 2) begin
                if (value_dc !== 1'b1) $fatal(1, "pixel appeared with command DC");
                pixel_number = pixel_byte/2;
                expected_color = reference_pixel(pixel_number%142, pixel_number/142);
                expected_byte = pixel_byte%2 ? expected_color[7:0] : expected_color[15:8];
                if (value !== expected_byte)
                    $fatal(1, "pixel byte %0d got %h expected %h", pixel_byte, value, expected_byte);
                pixel_byte = pixel_byte + 1;
                if (pixel_byte == 142*428*2) phase = 3;
            end else if (phase == 3) begin
                if (!saw_frame_end) $fatal(1, "no CS deassertion after full frame");
                if (cycle-gap_cycle < 500*SIM_TICKS) $fatal(1, "frame gap shortened");
                phase = 4;
                header_index = 0;
                if ({value_dc,value} !== header_expected[0]) $fatal(1, "next frame did not restart header");
                header_index = 1;
            end
            last_byte_cycle = cycle;
        end
    endtask

    always @(mosi) begin
        if (sck === 1'b1) $fatal(1, "MOSI changed while SCK high");
        last_mosi_change = $time;
    end
    always @(dc) begin
        if (sck === 1'b1) $fatal(1, "DC changed while SCK high");
        last_dc_change = $time;
    end
    always @(posedge ncs) begin
        if (!dut.reset) begin
            if (sck !== 1'b0 || bits != 0) $fatal(1, "CS deasserted mid-byte/high clock");
            if (phase == 3) begin
                saw_frame_end = 1;
                gap_cycle = cycle;
            end
        end
    end
    always @(negedge sck) begin
        if (!dut.reset && $time-last_sck_change != 20*SIM_DIV)
            $fatal(1, "SPI high half-period incorrect");
        last_sck_change = $time;
    end
    always @(posedge sck) begin
        if (ncs !== 1'b0) $fatal(1, "SCK rose while CS inactive");
        if ($time-last_sck_change < 20*SIM_DIV) $fatal(1, "SPI low half-period too short");
        if ($time-last_mosi_change < 20*SIM_DIV) $fatal(1, "MOSI setup time too short");
        if ($time-last_dc_change < 20*SIM_DIV) $fatal(1, "DC setup time too short");
        last_sck_change = $time;
        if (bits == 0) byte_dc = dc;
        else if (byte_dc !== dc) $fatal(1, "DC changed inside byte");
        assembled = {assembled[6:0],mosi};
        bits = bits + 1;
        if (bits == 8) begin
            check_byte(assembled, byte_dc);
            bits = 0;
        end
    end

    initial begin
        $readmemh("sim/init_expected.mem", init_expected);
        header_expected[0]=9'h036; header_expected[1]=9'h100;
        header_expected[2]=9'h020; header_expected[3]=9'h02a;
        // Independent expected CASET window: x=12..153 = 000C..0099.
        header_expected[4]=9'h100; header_expected[5]=9'h10c;
        header_expected[6]=9'h100; header_expected[7]=9'h199;
        header_expected[8]=9'h02b; header_expected[9]=9'h100;
        // Independent expected RASET window: y=0..427 = 0000..01AB.
        header_expected[10]=9'h100; header_expected[11]=9'h101;
        header_expected[12]=9'h1ab; header_expected[13]=9'h02c;
        // Hand-picked coordinates prove label orientation, decimal digits,
        // backing/tick, untouched bars and white border without a font lookup.
        if (dut.color_at(4,2) !== 16'h0000 || dut.color_at(3,2) !== 16'hffff ||
            dut.color_at(5,130) !== 16'h0000 || dut.color_at(3,130) !== 16'hffff ||
            dut.color_at(10,130) !== 16'h0000 || dut.color_at(9,130) !== 16'hffff ||
            dut.color_at(6,418) !== 16'h0000 || dut.color_at(11,418) !== 16'h0000 ||
            dut.color_at(15,421) !== 16'h0000 || dut.color_at(21,421) !== 16'h0000 ||
            dut.color_at(21,420) !== 16'hffff || dut.color_at(25,11) !== 16'hffe0 ||
            dut.color_at(141,418) !== 16'hffff || dut.color_at(21,427) !== 16'hffff ||
            disabled_dut.color_at(4,2) !== 16'hffff)
            $fatal(1, "row-label representative coordinates or disable control incorrect");
        #200000000;
        $fatal(1, "timeout: phase %0d, init %0d, pixel bytes %0d", phase, init_index, pixel_byte);
    end
endmodule
