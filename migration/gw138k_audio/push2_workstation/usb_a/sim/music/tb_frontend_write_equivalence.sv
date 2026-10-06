`timescale 1ns/1ps
module frontend_pair #(parameter bit DDR=0)(output reg done=0);
    reg clk=0,rst=0,next_window=0,valid=0,finishing=0;
    reg signed [15:0] left=0,right=0;
    wire [1:0] ready,res_valid,we,full,drained,req;
    wire signed [15:0] q[0:1],data[0:1];
    wire [15:0] addr[0:1];
    wire [13:0] ca[0:1];
    wire signed [31:0] coefficient[0:1];
    wire cv;
    integer cycles=0,samples=0,writes=0,windows=0;
    always #10 clk=~clk;
    // Large signed coefficients exercise both saturation limits; independent
    // coefficient ports see the same function, with variable DDR backpressure.
    for(genvar g=0;g<2;g=g+1) begin
        assign coefficient[g] = ca[g][0] ? -32'sd257031 : 32'sd194517;
    end
    assign cv=!DDR || cycles%7==0 || cycles%7==3;
    basic_pitch_cqt_frontend_reference #(.WIN_LEN(128),.USE_DDR_COEFF(DDR)) a(
        .clk_i(clk),.rst_ni(rst),.next_window_i(next_window),.sample_valid_i(valid),
        .left_i(left),.right_i(right),.res_valid_o(res_valid[0]),.res_q_o(q[0]),
        .win_we_o(we[0]),.win_addr_o(addr[0]),.win_data_o(data[0]),.win_full_o(full[0]),
        .in_ready_o(ready[0]),.drained_o(drained[0]),.coeff_addr_o(ca[0]),
        .coeff_data_i(coefficient[0]),.coeff_req_o(req[0]),.coeff_valid_i(cv));
    basic_pitch_cqt_frontend #(.WIN_LEN(128),.USE_DDR_COEFF(DDR)) b(
        .clk_i(clk),.rst_ni(rst),.next_window_i(next_window),.sample_valid_i(valid),
        .left_i(left),.right_i(right),.res_valid_o(res_valid[1]),.res_q_o(q[1]),
        .win_we_o(we[1]),.win_addr_o(addr[1]),.win_data_o(data[1]),.win_full_o(full[1]),
        .in_ready_o(ready[1]),.drained_o(drained[1]),.coeff_addr_o(ca[1]),
        .coeff_data_i(coefficient[1]),.coeff_req_o(req[1]),.coeff_valid_i(cv));
    always @(posedge clk) begin
        cycles=cycles+1;
        if(rst) begin
            if(ready[0] !== ready[1] || full[0] !== full[1] || drained[0] !== drained[1] ||
               req[0] !== req[1] || ca[0] !== ca[1] || we[0] !== we[1] || res_valid[0] !== res_valid[1])
                $fatal(1,"frontend control mismatch DDR=%0d cycle=%0d",DDR,cycles);
            if(we[0]) begin
                if(data[0] !== data[1] || addr[0] !== addr[1] || q[0] !== q[1])
                    $fatal(1,"frontend sample mismatch DDR=%0d write=%0d a=%0d b=%0d",DDR,writes,data[0],data[1]);
                writes=writes+1;
            end
            if(valid && !next_window) samples=samples+1;
        end
        if(cycles>1000000) $fatal(1,"frontend equivalence timeout");
    end
    // Bursts fill the lag-limited ring, exercise wrap and overwrite protection.
    // A full-window transition can coincide with a queued PCM commit.
    always @(negedge clk) begin
        if(rst && !done) begin
            next_window=0;
            if(finishing) begin
                if(writes!=512 || samples<1000) $fatal(1,"insufficient ring coverage writes=%0d samples=%0d",writes,samples);
                $display("PASS frontend bit-exact DDR=%0d windows=%0d writes=%0d PCM=%0d cycles=%0d",DDR,windows,writes,samples,cycles);
                done=1;valid=0;
            end else if(full[0]) begin
                windows=windows+1;
                if(windows==4) begin
                    finishing=1;valid=0;
                end else next_window=1;
            end
            valid=!done && !finishing && ready[0] && cycles%11!=0;
            case(samples%5)
                0: begin left=16'sh7fff;right=16'sh7fff;end
                1: begin left=16'sh8000;right=16'sh8000;end
                2: begin left=16'sh8000;right=16'sh7fff;end
                3: begin left=16'(samples*131);right=16'(~(samples*53));end
                4: begin left=0;right=0;end
            endcase
        end
    end
    initial begin repeat(3) @(negedge clk);rst=1;end
endmodule
module tb_frontend_write_equivalence;
    wire a,b;
    frontend_pair #(.DDR(0)) local_pair(a);
    frontend_pair #(.DDR(1)) ddr_pair(b);
    initial begin wait(a && b);$display("PASS frontend write-decode equivalence both coefficient modes");$finish;end
endmodule
