`timescale 1ns/1ps
module tb_music_ddr_command_buffer;
    logic clk=0,rst_n=0,in_valid=0,out_ready=0;
    logic [48:0] in_data=0;
    wire in_ready,out_valid;
    wire [48:0] out_data;
    always #10 clk=~clk;
    basic_pitch_ddr_command_buffer dut(
        .clk_i(clk),.rst_ni(rst_n),.in_valid_i(in_valid),
        .in_data_i(in_data),.in_ready_o(in_ready),
        .out_valid_o(out_valid),.out_data_o(out_data),
        .out_ready_i(out_ready));
    initial begin
        repeat(3) @(negedge clk);rst_n=1;
        in_valid=1;in_data=49'h1_1234_5678_9abc;
        @(negedge clk);in_valid=0;in_data=0;
        if(in_ready || !out_valid || out_data!=49'h1_1234_5678_9abc)
            $fatal(1,"first command not held");
        repeat(5) @(negedge clk);
        if(in_ready || !out_valid || out_data!=49'h1_1234_5678_9abc)
            $fatal(1,"stalled command changed");
        out_ready=1;
        @(negedge clk);out_ready=0;
        if(!in_ready || out_valid) $fatal(1,"command not consumed exactly once");
        in_valid=1;in_data=49'h0_0fed_cba9_8765;
        @(negedge clk);in_valid=0;
        if(!out_valid || out_data!=49'h0_0fed_cba9_8765)
            $fatal(1,"second command not delivered");
        $display("PASS CNN DDR command buffer ordering and backpressure");
        $finish;
    end
endmodule
