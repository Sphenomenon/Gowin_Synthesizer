`timescale 1ns/1ps
// Test the actual pitch module against the original integer formula. Direct
// state injection is limited to the combinational exhaustive domain sweep;
// the transaction test below exercises actual reset/CE/rate/state updates.
module tb_pitch_div147_exact;
    reg clk=0,rst_n=0,ce=0,rate44=1;
    reg [21:0] target=1048576;
    reg [15:0] step=0;
    reg [6:0] depth=0;
    wire [21:0] ratio;
    workstation_rate_pitch_expression dut(.clk_i(clk),.rst_ni(rst_n),.sample_ce_i(ce),
        .rate_44k1_i(rate44),.target_ratio_q20_i(target),.glide_step_q20_i(step),
        .vibrato_depth_i(depth),.ratio_q20_o(ratio));
    integer cases=0,transactions=0;
    integer numerator,expected_q,expected_r,model_rem,model_glide,model_step;
    reg [31:0] model_phase,random_state=32'habe14d29;
    reg signed [16:0] model_triangle;
    reg signed [24:0] model_modulation,model_combined;
    reg [21:0] expected_ratio;

    task automatic combinational_case(input integer s,input integer r);
        begin
            step=16'(s);dut.glide_remainder=8'(r);rate44=1;#1;
            numerator=s*160+r;expected_q=numerator/147;expected_r=numerator%147;
            if(dut.current_glide_step!==17'(expected_q) ||
               dut.next_glide_remainder!==8'(expected_r))
                $fatal(1,"DOMAIN step=%0d rem=%0d q=%0d expected=%0d r=%0d expected=%0d",
                    s,r,dut.current_glide_step,expected_q,dut.next_glide_remainder,expected_r);
            cases=cases+1;
        end
    endtask
    task automatic reset;
        begin
            clk=0;rst_n=1;#1;rst_n=0;#1;clk=1;#1;clk=0;rst_n=1;#1;
            model_rem=73;model_glide=1048576;model_phase=32'h40000000;model_modulation=0;
            if(dut.glide_remainder!==8'd73)$fatal(1,"RESET remainder must be73");
        end
    endtask
    task automatic transaction;
        begin
            // Independent model retains the original / and % operations.
            model_triangle=model_phase[31] ? $signed({1'b0,~model_phase[30:15]})-17'sd32768
                : $signed({1'b0,model_phase[30:15]})-17'sd32768;
            model_modulation=model_triangle*$signed({1'b0,depth});
            if(ce)begin
                numerator=160*int'(step)+model_rem;
                model_step=rate44 ? numerator/147 : int'(step);
                if(rate44 && step!=0)model_rem=numerator%147;
                if(model_step==0)model_glide=int'(target);
                else if(int'(target)>model_glide)
                    model_glide=int'(target)-model_glide>model_step ? model_glide+model_step : int'(target);
                else model_glide=model_glide-int'(target)>model_step ? model_glide-model_step : int'(target);
                model_phase=model_phase+(rate44 ? 32'd486957 : 32'd447392);
            end
            #1;clk=1;#1;
            if(dut.glide_remainder!==8'(model_rem) || dut.glide_ratio!==22'(model_glide) ||
               dut.phase!==model_phase || dut.modulation!==model_modulation)
                $fatal(1,"STATE transaction=%0d step=%0d rate44=%0b ce=%0b rem=%0d expected=%0d",
                    transactions,step,rate44,ce,dut.glide_remainder,model_rem);
            model_combined=$signed(25'(model_glide))+(model_modulation>>>8);
            if(model_combined<25'sd524288)expected_ratio=22'd524288;
            else if(model_combined>25'sd2097152)expected_ratio=22'd2097152;
            else expected_ratio=model_combined[21:0];
            if(ratio!==expected_ratio)$fatal(1,"OUTPUT transaction=%0d",transactions);
            clk=0;#1;transactions=transactions+1;
        end
    endtask
    initial begin
        // Witnesses reject both adjacent reciprocal constants and a16-bit q.
        combinational_case(1,134);
        combinational_case(31470,137);
        combinational_case(65535,146);
        combinational_case(65535,255);
        if(!$test$plusargs("QUICK"))begin
            for(integer s=0;s<65536;s=s+1)
                for(integer r=0;r<256;r=r+1)combinational_case(s,r);
            rate44=0;
            for(integer s=0;s<65536;s=s+1)begin
                step=16'(s);#1;
                if(dut.current_glide_step!==17'(s))$fatal(1,"48K API step=%0d",s);
            end
        end
        reset();ce=1;rate44=1;step=0;target=22'd2000000;
        repeat(5)transaction(); // Zero-step must retain reset73 and follow target.
        step=1;transaction(); // Establish a nonreset remainder.
        step=0;repeat(5)transaction();
        rate44=0;step=65535;target=22'd600000;repeat(3)transaction();
        rate44=1;step=65535;repeat(3)transaction();
        for(integer j=0;j<40000;j=j+1)begin
            random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
            target=random_state[21:0];depth=random_state[29:23];
            step=j%7==0 ? 0 : random_state[31:16];
            ce=random_state[3] && random_state[7];rate44=random_state[13];
            transaction();
        end
        $display("PASS pitch exact147: combinational_cases=%0d transactions=%0d",cases,transactions);
        $finish;
    end
endmodule
