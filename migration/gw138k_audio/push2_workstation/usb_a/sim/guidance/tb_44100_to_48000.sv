`timescale 1ns/1ps
module tb_44100_to_48000;
    reg clk=0,rst_n=0,valid_i=0,ready_i=1;
    reg signed [15:0] left_i=0,right_i=0;
    wire ready_o,valid_o;
    wire signed [15:0] left_o,right_o;
    integer sent=0,received=0,cycles=0;
    always #10 clk=~clk;
    basic_pitch_44100_to_48000 dut(.clk_i(clk),.rst_ni(rst_n),
        .valid_i,.ready_o,.left_i,.right_i,.valid_o,.ready_i,.left_o,.right_o);
    initial begin
        repeat(3)@(negedge clk);rst_n=1;
        while(received<160 && cycles<1000) begin
            @(negedge clk);
            ready_i=(cycles%7)!=0;
            valid_i=sent<147 && ready_o;
            left_i=sent;right_i=-sent;
            cycles=cycles+1;
            @(posedge clk);
            if(valid_i && ready_o)sent=sent+1;
            if(valid_o && ready_i)begin
                if(left_o>146 || right_o!=-left_o)$fatal(1,"sample mismatch");
                received=received+1;
            end
        end
        if(sent!=147 || received!=160)$fatal(1,"rate conversion %0d/%0d",sent,received);
        $display("PASS 147 input samples to 160 output samples with stalls");$finish;
    end
endmodule
