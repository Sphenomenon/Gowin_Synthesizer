`timescale 1ns/1ps
module tb_video_tmds;
    reg clk=0;
    always #(500.0/148.5) clk=~clk;
    reg reset=1, den=0;
    reg [7:0] data=0;
    reg [1:0] ctrl=0;
    wire [9:0] tmds;
    dvi_tx_tmds_enc dut(clk,reset,den,data,ctrl,tmds);
    // Sample at N is encoded at N+3; use an independent input history queue.
    reg history_den[0:2];
    reg [7:0] history_data[0:2];
    reg [1:0] history_ctrl[0:2];
    wire last_den=history_den[2];
    wire [7:0] last_data=history_data[2];
    wire [1:0] last_ctrl=history_ctrl[2];
    reg [8:0] q;
    reg [9:0] expected;
    integer rd=0, ones, balance, bit_index, checked=0, value, control, stage;
    // Independent executable DVI transition-minimization/DC-balance reference.
    always @(posedge clk) begin
        if(reset) begin
            rd=0; expected=0;
            for(stage=0;stage<3;stage=stage+1) begin
                history_den[stage]=0;history_data[stage]=0;history_ctrl[stage]=0;
            end
        end else begin
            if (!last_den) begin
                case(last_ctrl)
                    0: expected=10'b1101010100;
                    1: expected=10'b0010101011;
                    2: expected=10'b0101010100;
                    3: expected=10'b1010101011;
                endcase
                rd=0;
            end else begin
                ones=0;
                for(bit_index=0;bit_index<8;bit_index=bit_index+1) ones=ones+last_data[bit_index];
                q[8]=!(ones>4 || (ones==4 && !last_data[0]));
                q[0]=last_data[0];
                for(bit_index=1;bit_index<8;bit_index=bit_index+1)
                    q[bit_index]=q[bit_index-1] ^ last_data[bit_index] ^ !q[8];
                ones=0;
                for(bit_index=0;bit_index<8;bit_index=bit_index+1) ones=ones+q[bit_index];
                balance=2*ones-8;
                if(rd==0 || balance==0) begin
                    expected={~q[8],q[8],q[8] ? q[7:0] : ~q[7:0]};
                    rd=rd+(q[8] ? balance : -balance);
                end else if((rd>0 && balance>0)||(rd<0 && balance<0)) begin
                    expected={1'b1,q[8],~q[7:0]};
                    rd=rd+2*q[8]-balance;
                end else begin
                    expected={1'b0,q[8],q[7:0]};
                    rd=rd-2*(!q[8])+balance;
                end
            end
            for(stage=2;stage>0;stage=stage-1) begin
                history_data[stage]=history_data[stage-1];
                history_den[stage]=history_den[stage-1];
                history_ctrl[stage]=history_ctrl[stage-1];
            end
            history_data[0]=data;history_den[0]=den;history_ctrl[0]=ctrl;
        end
        #1;
        if(tmds!==expected) $fatal(1,"TMDS mismatch: got %b expected %b",tmds,expected);
        if($signed(dut.cnt_q)!=rd) $fatal(1,"TMDS running disparity mismatch");
        if(!reset) checked=checked+1;
    end
    initial begin
        repeat(3) @(negedge clk); reset=0;
        for(control=0;control<4;control=control+1) begin
            @(negedge clk); den=0; ctrl=control;
            for(value=0;value<256;value=value+1) begin
                @(negedge clk); den=1; data=value;
            end
        end
        repeat(1024) begin @(negedge clk); den=1; data=$random; end
        // Adjacent active/control words exercise every pipeline transition.
        repeat(4096) begin
            @(negedge clk);den=$random;data=$random;ctrl=$random;
        end
        // Flush a reset while pixels are still in flight, then recover.
        @(negedge clk);reset=1;
        repeat(2) @(negedge clk);
        reset=0;
        repeat(512) begin @(negedge clk);den=$random;data=$random;ctrl=$random;end
        @(negedge clk); den=0;
        repeat(6) @(negedge clk);
        if(checked<6500) $fatal(1,"insufficient TMDS coverage");
        $display("PASS tb_video_tmds: pipelined 148.5MHz interface, all 256 values, four controls, 5632 random words, disparity, active/control boundaries and in-flight reset");
        $finish;
    end
endmodule
