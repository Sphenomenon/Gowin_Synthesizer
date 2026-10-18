`timescale 1ns / 1ps
`include "sim/tb_touch_i2c_model.v"
`timescale 1ns / 1ps
module tb_touch_i2c_recovery;
    reg clk = 0; always #10 clk = ~clk;
    reg reset = 1, request = 0, read_request = 0;
    reg nack_all = 0, hold_sda = 0, hold_scl = 0;
    reg [7:0] pointer = 8'h70;
    reg [6:0] count = 4;
    reg [127:0] payload = 128'h44332211;
    wire scl_low, sda_low, busy, done;
    wire [127:0] read_data;
    wire [7:0] error_code;
    wire [2:0] ack_mask;
    tri1 scl, sda;
    assign scl = scl_low || hold_scl ? 1'b0 : 1'bz;
    assign sda = sda_low || hold_sda ? 1'b0 : 1'bz;
    midi_i2c_register_master #(.HALF_CYCLES(5), .BUS_FREE_CYCLES(8), .TIMEOUT_CYCLES(80)) dut (
        .clk(clk), .reset(reset), .scl_in(scl), .sda_in(sda), .request(request),
        .read_request(read_request), .register_address(pointer), .byte_count(count), .write_data(payload),
        .scl_low(scl_low), .sda_low(sda_low), .busy(busy), .done(done),
        .read_data(read_data), .error_code(error_code), .ack_mask(ack_mask));
    midi_i2c_slave_model device(.scl(scl), .sda(sda), .nack_all(nack_all));
    task transact(input reading, input [7:0] expected_error);
        begin
            @(negedge clk); read_request = reading; request = 1;
            @(negedge clk); request = 0;
            @(posedge done); #1;
            if (error_code !== expected_error) $fatal(1,"I2C error %02h expected %02h",error_code,expected_error);
            if (busy || scl_low || sda_low) $fatal(1,"I2C bus not released at done");
            repeat (4) @(negedge clk);
        end
    endtask
    integer recovery_clocks;
    initial begin
        repeat (5) @(negedge clk); reset = 0;
        transact(0,0);
        if ({device.mem[8'h73],device.mem[8'h72],device.mem[8'h71],device.mem[8'h70]} !== 32'h44332211)
            $fatal(1,"Write byte ordering incorrect");
        transact(1,0);
        if (read_data !== payload || ack_mask !== 7 || device.final_nacks < 1)
            $fatal(1,"Read byte ordering/ACK/NACK incorrect");
        nack_all = 1; transact(0,1); nack_all = 0;
        fork
            transact(0,0);
            begin
                wait(dut.state == 3); hold_scl = 1;
                repeat (40) @(negedge clk); hold_scl = 0;
            end
        join
        fork
            transact(0,8'h80);
            begin
                wait(dut.state == 3); hold_scl = 1;
                wait(done); hold_scl = 0;
            end
        join
        // A slave abandoned while sending a byte holds SDA low. The master
        // must supply all nine recovery clocks and STOP, then allow retry.
        @(negedge clk); hold_sda = 1;
        fork
            transact(0,8'h40);
            begin
                wait(dut.state == 20); recovery_clocks = 0;
                repeat (9) begin @(posedge scl); recovery_clocks = recovery_clocks + 1; end
                @(negedge scl); hold_sda = 0;
            end
        join
        if (recovery_clocks != 9) $fatal(1,"Missing recovery clocks");
        transact(0,0); transact(1,0);
        if (read_data !== payload) $fatal(1,"Recovered bus could not transfer again");
        count = 0; transact(0,8'hff);
        count = 4;
        @(negedge clk); request = 1;
        @(negedge clk); request = 0;
        wait(busy); @(negedge clk); reset = 1; @(negedge clk);
        if (busy || done || scl_low || sda_low || error_code) $fatal(1,"Reset did not clear transaction engine");
        $display("PASS I2C: actual slave read/write/ACK/NACK, stretch, timeout, nine-clock SDA recovery, retry, invalid length and reset");
        $finish;
    end
    initial begin #2_000_000; $fatal(1,"I2C timeout state=%d code=%h scl=%b sda=%b",dut.state,error_code,scl,sda); end
endmodule
