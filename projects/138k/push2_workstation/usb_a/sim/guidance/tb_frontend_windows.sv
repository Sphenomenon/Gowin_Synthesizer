`timescale 1ns/1ps
module tb_frontend_windows;
    reg clk=0,rst_n=0,next_window=0,sample_valid=0;
    reg signed [15:0] left=0,right=0;
    wire sample_ready,res_valid,win_we,win_full,drained;
    wire signed [15:0] res_q,win_data;
    wire [15:0] win_addr;
    integer writes=0;
    always #10 clk=~clk;
    basic_pitch_cqt_frontend #(.PHASES(1),.DOWN(1),.DELAY(0),
        .TAPS(1),.WIN_LEN(4),.USE_DDR_COEFF(1'b0)) dut(
        .clk_i(clk),.rst_ni(rst_n),.next_window_i(next_window),
        .sample_valid_i(sample_valid && sample_ready),.left_i(left),.right_i(right),
        .res_valid_o(res_valid),.res_q_o(res_q),.win_we_o(win_we),
        .win_addr_o(win_addr),.win_data_o(win_data),.win_full_o(win_full),
        .in_ready_o(sample_ready),.drained_o(drained),.coeff_addr_o(),
        .coeff_data_i(32'sd32768),.coeff_req_o(),.coeff_valid_i(1'b1));
    always @(posedge clk) if(rst_n && win_we) begin
        if(writes>=12 || win_addr !== (writes%4) || win_data !== (100+writes))
            $fatal(1,"output %0d addr=%0d data=%0d",writes,win_addr,win_data);
        writes=writes+1;
    end
    task automatic send(input integer i);
        @(negedge clk);
        while(!sample_ready) @(negedge clk);
        left=16'(100+i);right=16'(100+i);sample_valid=1;
        @(negedge clk);sample_valid=0;
    endtask
    task automatic advance;
        wait(win_full);
        @(negedge clk);next_window=1;
        @(negedge clk);next_window=0;
    endtask
    initial begin
        repeat(3) @(negedge clk);rst_n=1;
        fork
            begin for(integer i=0;i<12;i=i+1) send(i);end
            begin advance();advance();wait(win_full);end
        join
        repeat(3) @(negedge clk);
        if(writes!=12 || dut.n_recv!=12)
            $fatal(1,"windows dropped samples writes=%0d received=%0d",writes,dut.n_recv);
        $display("PASS frontend: 3 consecutive windows, 12 exact samples");
        $finish;
    end
    initial begin #2000000;$fatal(1,"frontend window timeout");end
endmodule
