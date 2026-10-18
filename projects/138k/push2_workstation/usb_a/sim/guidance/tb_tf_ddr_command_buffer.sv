`timescale 1ns/1ps
module tb_tf_ddr_command_buffer;
    reg clk=0,rst_n=0,in_valid=0,in_write=0,out_ready=0;
    reg [28:0] in_address=0;
    reg [255:0] in_data=0;
    wire in_ready,out_valid,out_write;
    wire [28:0] out_address;
    wire [255:0] out_data;
    always #10 clk=~clk;
    tf_audio_ddr_command_buffer dut(.clk,.rst_n,.in_valid,.in_write,
        .in_address,.in_data,.in_ready,.out_valid,.out_write,
        .out_address,.out_data,.out_ready);
    initial begin
        repeat(3) @(negedge clk);rst_n=1;
        @(negedge clk);in_valid=1;in_write=1;in_address=29'h12345;in_data=256'hfeed;
        @(negedge clk);in_valid=0;in_address=0;in_data=0;
        if(in_ready || !out_valid || !out_write || out_address!=29'h12345 || out_data!=256'hfeed)
            $fatal(1,"buffer did not hold first command");
        repeat(5) @(negedge clk);
        if(in_ready || !out_valid || out_address!=29'h12345)
            $fatal(1,"stalled command changed");
        out_ready=1;
        @(negedge clk);out_ready=0;
        if(!in_ready || out_valid) $fatal(1,"buffer did not empty");
        in_valid=1;in_write=0;in_address=29'h45678;
        @(negedge clk);in_valid=0;
        if(!out_valid || out_write || out_address!=29'h45678)
            $fatal(1,"read command lost");
        $display("PASS TF DDR command buffer: stall and ordered read/write handshakes");
        $finish;
    end
endmodule
