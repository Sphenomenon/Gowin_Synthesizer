`timescale 1ns/1ps
module tb_workstation_rate_pitch_expression;
    reg clk=0,rst_n=0,ce=0,mode=0;
    always #6.510416667 clk=!clk;
    reg [21:0] target=1048576;
    reg [15:0] glide=0;
    reg [6:0] depth=0;
    wire [21:0] actual,reference;
    workstation_rate_pitch_expression dut(.clk_i(clk),.rst_ni(rst_n),.sample_ce_i(ce),.rate_44k1_i(mode),
        .target_ratio_q20_i(target),.glide_step_q20_i(glide),.glide_div147_i(21'd0),.vibrato_depth_i(depth),.ratio_q20_o(actual));
    pitch_expression old(.clk_i(clk),.rst_ni(rst_n),.sample_ce_i(ce),
        .target_ratio_q20_i(target),.glide_step_q20_i(glide),.vibrato_depth_i(depth),.ratio_q20_o(reference));
    reg compare_48=1;
    integer compared=0;
    // Behavioral full-width /147 oracle is independent of the maintained
    // reciprocal multiply and subtract-borrow implementation. Check state
    // and continuous output at every cycle, including adjacent CE and rate/
    // parameter changes immediately before an accepted sample.
    reg [31:0] model_phase=32'h40000000;
    reg [21:0] model_glide=22'd1048576;
    reg [7:0] model_remainder=8'd73;
    integer model_modulation=0,model_triangle,model_numerator,model_step;
    integer model_combined,model_expected,model_clocks=0,model_samples=0;
    always @(posedge clk)begin
        if(!rst_n)begin
            model_phase<=32'h40000000;model_glide<=22'd1048576;
            model_remainder<=8'd73;model_modulation<=0;
        end else begin
            model_triangle=(model_phase[31] ? integer'({1'b0,~model_phase[30:15]}) :
                            integer'({1'b0,model_phase[30:15]}))-32768;
            model_modulation<=model_triangle*integer'({1'b0,depth});
            if(ce)begin
                model_samples=model_samples+1;
                model_phase<=model_phase+32'(64'd21474836480/(mode ? 64'd44100 : 64'd48000));
                model_numerator=integer'({1'b0,glide})*160+integer'({1'b0,model_remainder});
                model_step=mode ? model_numerator/147 : integer'({1'b0,glide});
                if(mode && glide!=0)model_remainder<=8'(model_numerator%147);
                if(model_step==0)model_glide<=target;
                else if(target>model_glide)
                    model_glide<=target-model_glide>model_step ? model_glide+22'(model_step) : target;
                else model_glide<=model_glide-target>model_step ? model_glide-22'(model_step) : target;
            end
        end
    end
    always @(negedge clk)if(rst_n)begin
        model_combined=integer'({1'b0,model_glide})+(model_modulation>>>8);
        model_expected=model_combined<524288 ? 524288 : model_combined>2097152 ? 2097152 : model_combined;
        if(actual!==22'(model_expected) || dut.phase!==model_phase || dut.glide_ratio!==model_glide ||
           dut.glide_remainder!==model_remainder || $signed(dut.modulation)!==model_modulation)
            $fatal(1,"independent pitch mismatch cycle=%0d samples=%0d rate44=%b",model_clocks,model_samples,mode);
        model_clocks=model_clocks+1;
    end
    always @(negedge clk) if(rst_n && compare_48) begin
        if(actual!==reference || dut.phase!==old.phase || dut.glide_ratio!==old.glide_ratio)
            $fatal(1,"48k differs from locked reference after %0d clocks",compared);
        compared=compared+1;
    end
    task automatic reset;
        begin @(negedge clk);rst_n=0;ce=0;repeat(3)@(negedge clk);rst_n=1;end
    endtask
    task automatic frames(input integer count);
        begin
            for(integer j=0;j<count;j=j+1)begin
                @(negedge clk);ce=1;@(negedge clk);ce=0;
                // Unequal intervals expose an accidental compute-clock LFO.
                repeat(1+j%5)@(negedge clk);
            end
        end
    endtask
    reg [31:0] random_state=32'hde398b19,saved_phase;
    reg [21:0] saved_glide;
    longint unsigned delta;
    integer glide_frames_48,glide_frames_44,expected_delta,boundary_step,boundary_increment,boundary_distance;
    real time48,time44;
    initial begin
        reset();
        // Bit equivalence includes non-frame depth changes and the full API
        // range, clamping, zero glide, upward/downward ramps and irregular CE.
        for(integer j=0;j<16000;j=j+1)begin
            @(posedge clk);#1;
            random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
            target=random_state[21:0];depth=random_state[29:23];
            glide=j%7==0 ? 0 : random_state[31:16];ce=random_state[7] && random_state[3];
        end
        @(posedge clk);#1;ce=0;compare_48=0;
        $display("EQUIVALENCE locked48 clocks=%0d",compared);
        for(integer j=0;j<32000;j=j+1)begin
            @(posedge clk);#1;
            random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
            target=j%19==0 ? 0 : j%19==1 ? 22'h3fffff : random_state[21:0];
            depth=random_state[29:23];mode=random_state[6];
            glide=j%11==0 ? 0 : j%11==1 ? 1 : j%11==2 ? 65535 : random_state[31:16];
            ce=j%4==0 || random_state[7];
        end
        @(posedge clk);#1;ce=0;
        // Preserve held LFO/glide state while rate changes between requests.
        saved_phase=dut.phase;saved_glide=dut.glide_ratio;
        @(negedge clk);mode=1;repeat(50)@(negedge clk);
        if(dut.phase!==saved_phase || dut.glide_ratio!==saved_glide)$fatal(1,"rate change reset held control state");
        depth=0;target=2097152;glide=2;reset();mode=1;
        saved_phase=dut.phase;frames(8820);
        delta={32'd0,dut.phase-saved_phase};
        if(delta < 64'd4294958476)$fatal(1,"44.1k5Hz LFO fails physical period: %0d",delta);
        // 8820 frames is0.2 seconds, almost exactly one modulo32-bit turn.
        expected_delta=(8820*2*160+73)/147;
        if(dut.glide_ratio!==22'(1048576+expected_delta))$fatal(1,"fractional glide speed drift");
        $display("PHYSICAL rate=44100 frames=8820 glide_delta=%0d lfo_modulo_turn=%0d",expected_delta,delta);
        // A one-octave ratio distance with the smallest production CC5 step
        // must have the same physical duration to within one output frame.
        target=22'd1048576+22'd65536;glide=2;mode=0;reset();glide_frames_48=0;
        while(dut.glide_ratio!=target)begin frames(1);glide_frames_48=glide_frames_48+1;end
        mode=1;reset();glide_frames_44=0;
        while(dut.glide_ratio!=target)begin frames(1);glide_frames_44=glide_frames_44+1;end
        time48=real'(glide_frames_48)/48000;time44=real'(glide_frames_44)/44100;
        if(time44-time48>1.0/44100 || time48-time44>1.0/44100)$fatal(1,"glide physical time differs %f %f",time48,time44);
        $display("GLIDE frames48=%0d frames44=%0d seconds48=%0.9f seconds44=%0.9f",glide_frames_48,glide_frames_44,time48,time44);
        // Full16-bit increments cannot truncate the44.1k quotient at65535.
        target=2097152;glide=65535;mode=1;reset();frames(1);
        if(dut.glide_ratio!=1048576+71331)$fatal(1,"full range glide increment truncated: %0d",dut.glide_ratio);
        // Reverse switch preserves phase and current glide exactly, then the
        // next48k frame advances by the original48k step.
        saved_phase=dut.phase;saved_glide=dut.glide_ratio;
        @(negedge clk);mode=0;repeat(12)@(negedge clk);
        if(dut.phase!==saved_phase || dut.glide_ratio!==saved_glide)$fatal(1,"reverse switch reset held controls");
        frames(1);
        if(dut.phase!=saved_phase+32'd447392 || dut.glide_ratio!=saved_glide+22'd65535)
            $fatal(1,"48k did not resume original increments");
        for(integer sample_rate=0;sample_rate<2;sample_rate=sample_rate+1)
            for(integer step_case=0;step_case<4;step_case=step_case+1)
                for(integer direction=0;direction<2;direction=direction+1)
                    for(integer adjacent=-1;adjacent<=1;adjacent=adjacent+1)begin
                        boundary_step=step_case==3 ? 65535 : step_case;
                        boundary_increment=sample_rate ? (boundary_step*160+73)/147 : boundary_step;
                        boundary_distance=boundary_increment+adjacent;
                        if(boundary_distance>=0)begin
                            mode=1'(sample_rate);glide=16'(boundary_step);depth=0;reset();
                            target=22'(direction ? 1048576-boundary_distance : 1048576+boundary_distance);
                            frames(1);
                        end
                    end
        $display("PASS runtime pitch: locked48 bit equivalence, held state,5Hz LFO, fractional glide timing, max increment, reverse switch");
        $display("INDEPENDENT_PITCH clocks=%0d samples=%0d full_api=1 adjacent_ce=1 rate_changes=1",model_clocks,model_samples);
        $finish;
    end
    initial begin #10000000;$fatal(1,"timeout");end
endmodule
