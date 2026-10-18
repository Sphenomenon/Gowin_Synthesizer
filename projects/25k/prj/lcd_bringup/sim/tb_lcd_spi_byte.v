`timescale 1ns/1ps
module tb_lcd_spi_byte;
    reg clk=0, reset=1, start=0;
    always #10 clk=!clk;
    reg [7:0] data=0;
    wire busy, done, sck, mosi;
    // Use the real default divider: 50 MHz input, 1 MHz SCK.
    lcd_spi_byte dut (.clk(clk), .reset(reset), .start(start), .data(data),
                     .busy(busy), .done(done), .sck(sck), .mosi(mosi));
    integer value, bits=0, received_count=0;
    reg [7:0] assembled=0, expected=0;
    time last_edge=0;
    always @(posedge sck) begin
        if (!busy) $fatal(1, "SPI edge outside busy");
        if ($time-last_edge < 500) $fatal(1, "default low interval under 500 ns");
        last_edge=$time;
        assembled={assembled[6:0],mosi};
        bits=bits+1;
        if (bits==8) begin
            if (assembled !== expected)
                $fatal(1, "default-divider data got %h expected %h", assembled, expected);
            bits=0;
            received_count=received_count+1;
        end
    end
    always @(negedge sck) begin
        if (!reset && $time-last_edge != 500) $fatal(1, "default high interval is not 500 ns");
        last_edge=$time;
    end
    initial begin
        repeat(3) @(negedge clk);
        reset=0;
        for (value=0; value<256; value=value+1) begin
            @(negedge clk);
            expected=value;
            data=value;
            start=1;
            @(negedge clk);
            start=0;
            // Input mutations and another start during busy must not corrupt the byte.
            repeat(5) @(negedge clk);
            data=~value;
            start=1;
            repeat(2) @(negedge clk);
            start=0;
            wait(done);
            #1;
            if (busy || sck || bits!=0) $fatal(1, "incorrect byte completion state");
        end
        if (received_count != 256) $fatal(1, "incorrect byte count");
        $display("PASS: default 1 MHz SPI; all 256 byte values; busy/start rejection; complete final low edge");
        $finish;
    end
    initial begin
        #5000000;
        $fatal(1, "SPI byte test timeout");
    end
endmodule
