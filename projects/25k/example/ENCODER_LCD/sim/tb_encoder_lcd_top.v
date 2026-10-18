`timescale 1ns/1ps
module tb_encoder_lcd_top;
    reg clk=0;
    always #10 clk=~clk;
    reg [1:0] ab1=3, ab2=3;
    reg key1=1, key2=1;
    wire cs, dc, sck, mosi;
    encoder_lcd_top #(.AB_FILTER_CYCLES(3), .KEY_FILTER_CYCLES(5),
        // Keep filter clocks accelerated, while exercising the hardware
        // default 5 MHz SPI and the production 2 ms pair gap.
        .MS_TICKS(2), .SPI_HALF_PERIOD(5), .BOOT_MS(3),
        .POST_INIT_MS(150), .REFRESH_GAP_MS(2)) dut (
        .clk(clk), .sw1_a(ab1[1]), .sw1_b(ab1[0]), .sw1_key_n(key1),
        .sw2_a(ab2[1]), .sw2_b(ab2[0]), .sw2_key_n(key2),
        .lcd_te(1'b0), .lcd_ncs(cs), .lcd_dc(dc), .lcd_sck(sck), .lcd_mosi(mosi)
    );
    task clocks;
        input integer n;
        begin repeat(n) @(negedge clk); end
    endtask
    task turn1;
        input integer positive;
        begin
            ab1=positive ? 2'b01 : 2'b10; clocks(12);
            ab1=0; clocks(12);
            ab1=positive ? 2'b10 : 2'b01; clocks(12);
            ab1=3; clocks(12);
        end
    endtask
    task turn2;
        input integer positive;
        begin
            ab2=positive ? 2'b01 : 2'b10; clocks(12);
            ab2=0; clocks(12);
            ab2=positive ? 2'b10 : 2'b01; clocks(12);
            ab2=3; clocks(12);
        end
    endtask
    integer snapshots=0;
    integer sck_edges=0;
    always @(posedge sck) sck_edges=sck_edges+1;
    always @(posedge clk) begin
        if (!dut.reset && dut.snapshot) begin
            snapshots=snapshots+1;
            case(snapshots)
                1: begin
                    if (dut.position1 !== 16'sd2 || dut.position2 !== -16'sd2 ||
                        dut.press_count1 !== 16'd1 || dut.press_count2 !== 16'd1 ||
                        dut.key1 !== 0 || dut.key2 !== 1)
                        $fatal(1,"first snapshot did not capture both encoders");
                end
                2: begin
                    if (dut.position1 !== 16'sd4 || dut.position2 !== -16'sd4 ||
                        dut.press_count1 !== 16'd2 || dut.press_count2 !== 16'd1 ||
                        dut.key1 !== 1 || dut.key2 !== 0)
                        $fatal(1,"rotation/press lost during full-screen SPI transfer");
                end
                3: begin
                    if (dut.position1 !== 16'sd2 || dut.position2 !== 16'sd0 ||
                        dut.press_count2 !== 16'd2 || dut.key2 !== 1 ||
                        dut.direction1 !== -2'sd1 || dut.direction2 !== 2'sd1 ||
                        dut.invalid_count1 !== 0 || dut.invalid_count2 !== 0)
                        $fatal(1,"independent reversals/press lost during partial refresh");
                end
            endcase
        end
    end
    initial begin
        wait(!dut.reset); clocks(16);
        turn1(1); turn2(0);
        key1=0; key2=0; clocks(16); key1=1; clocks(16);
        wait(snapshots==1); clocks(40);
        turn1(1); turn2(0);
        key1=0; key2=1; clocks(16);
        if(sck_edges < 100) $fatal(1,"encoder stimulus did not overlap active SPI");
        wait(snapshots==2); clocks(40);
        turn1(0); turn2(1); turn2(1);
        key2=0; clocks(16);
        wait(snapshots==3); clocks(40);
        if(dut.completed_refreshes !== 2) $fatal(1,"refresh sequencing failed");
        $display("PASS: integrated SW1/SW2 remain independent during full and partial SPI refresh; signed turns, reversals, held/released keys and three coherent snapshots");
        $finish;
    end
    initial begin
        #500000000;
        $fatal(1,"integrated encoder LCD simulation timed out");
    end
endmodule
