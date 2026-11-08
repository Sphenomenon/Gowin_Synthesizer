`timescale 1ns/1ps

// Real native consumers; the model uses direct integer160/147 arithmetic.
// Parameter commits are registered, including the last legal edge before CE.
module tb_pitch_capture_boundary;
    logic clk=0, rst=0, panic=0, ce=0, rate_commit=0, rate44=0;
    always #5 clk=~clk;
    logic parameter_commit=0;
    logic [21:0] next_target=1048576, target=1048576;
    logic [15:0] next_glide=0, glide=0;
    logic [20:0] glide_div147=0;
    logic [6:0] next_depth=0, depth=0;
    always_ff @(posedge clk) if(parameter_commit) begin
        target<=next_target;glide<=next_glide;depth<=next_depth;
        glide_div147<={13'((13*int'(next_glide))/147),8'((13*int'(next_glide))%147)};
    end
    logic event_valid=0, note_on=0, scope=0;
    logic [6:0] note=48;
    wire rate_ready, applied44, quiet, synth_ready, vec_ready, event_ready, vec_event_ready;
    wire synth_valid, vec_valid;
    wire signed [31:0] synth, left, right;
    wire [31:0] allocated, active;
    wire [7:0] vec_active;
    wire [5:0] count;
    wire [3:0] vec_count;
    wire config_error, frequency_error;
    workstation_runtime_render_engines #(.RUNTIME_RATE_ENABLE(1),.COMMITTED_GLIDE_COEFFICIENT(1)) dut (
        .clk_i(clk),.rst_ni(rst),.panic_i(panic),.sample_ce_i(ce),
        .rate_commit_i(rate_commit),.rate_44100_i(rate44),.rate_ready_o(rate_ready),
        .applied_rate_44100_o(applied44),.quiescent_o(quiet),
        .target_ratio_q20_i(target),.glide_step_q20_i(glide),.glide_div147_i(glide_div147),.vibrato_depth_i(depth),.pitch_q20_o(),
        .mode_set_valid_i(1'b0),.mode_set_ready_o(),.mode_i(2'd0),.current_mode_o(),
        .event_valid_i(event_valid),.event_note_on_i(note_on),.scope_enable_i(scope),
        .event_profile_i(3'd0),.event_note_i(note),.event_off_note_i(note),.event_velocity_i(7'd100),
        .synth_event_ready_o(event_ready),.vector_event_ready_o(vec_event_ready),
        .synth_event_slot_ready_o(),.expression_slot_ready_o(),
        .expression_valid_i(1'b0),.expression_note_i(7'd0),.expression_value_i(7'd0),.expression_ready_o(),
        .synth_sample_ready_o(synth_ready),.synth_valid_o(synth_valid),.synth_o(synth),
        .allocated_mask_o(allocated),.synth_active_mask_o(active),.synth_active_count_o(count),
        .load_busy_o(),.mix_busy_o(),.issued_slot_count_o(),
        .vector_shape_i(3'd0),.vector_morph_shape_i(3'd1),.vector_morph_q15_i(16'd0),
        .vector_scale_q15_i(16'd32768),.vector_rotation_i(7'd0),
        .vector_cal_x_q14_i(16'sd16384),.vector_cal_y_q14_i(16'sd16384),
        .vector_offset_x_i(32'sd0),.vector_offset_y_i(32'sd0),
        .vector_sample_ready_o(vec_ready),.vector_valid_o(vec_valid),.vector_busy_o(),
        .vector_left_o(left),.vector_right_o(right),.vector_active_mask_o(vec_active),.vector_active_count_o(vec_count),
        .vector_rejected_o(),.vector_config_error_o(config_error),.vector_frequency_error_o(frequency_error),.vector_clip_o()
    );

    integer clocks=0, captures=0, frames=0, full_frames=0, synth_outputs=0, vec_outputs=0;
    integer nonzero_synth=0, nonzero_vector=0, last_ce=0, max_synth_latency=0, max_vector_latency=0;
    integer next_ce=0, cadence_fraction=0, cadence_checks=0, commits=0, switches=0, panic_cases=0;
    longint unsigned model_glide=1048576, fraction=73;
    logic [31:0] model_phase=32'h40000000;
    longint signed model_modulation=0;
    bit model_rate=0;
    always @(posedge clk) begin: reference_and_consumers
        longint signed combined, triangle;
        longint unsigned increment, numerator;
        logic [21:0] expected;
        clocks=clocks+1;
        if(!rst) begin
            model_glide=1048576;fraction=73;model_phase=32'h40000000;
            model_modulation=0;model_rate=0;
        end else begin
            combined=longint'(model_glide)+(model_modulation >>> 8);
            if(combined<524288)expected=524288;
            else if(combined>2097152)expected=2097152;
            else expected=22'(combined);
            triangle=longint'({1'b0,model_phase[30:15]});
            if(model_phase[31])triangle=65535-triangle;
            model_modulation=(triangle-32768)*longint'(depth);
            if(ce) begin
                if(panic || parameter_commit || !synth_ready || !vec_ready)
                    $fatal(1,"CAPTURE_ADMISSION clock=%0d",clocks);
                if(last_ce!=0)begin
                    if(model_rate ? ((clocks-last_ce!=1741) && (clocks-last_ce!=1742)) : (clocks-last_ce!=1600))
                        $fatal(1,"SAMPLE_CADENCE previous=%0d current=%0d",last_ce,clocks);
                    cadence_checks++;
                end
                last_ce=clocks;
                numerator=160*longint'(glide)+fraction;
                increment=model_rate ? numerator/147:longint'(glide);
                if(model_rate && glide!=0)fraction=numerator%147;
                if(glide==0)model_glide=longint'(target);
                else if(longint'(target)>model_glide)begin
                    if(longint'(target)-model_glide>increment)model_glide=model_glide+increment;
                    else model_glide=longint'(target);
                end else begin
                    if(model_glide-longint'(target)>increment)model_glide=model_glide-increment;
                    else model_glide=longint'(target);
                end
                model_phase=model_phase+(model_rate ? 32'd486957:32'd447392);
            end
            if(rate_commit) begin
                if(!rate_ready)$fatal(1,"RATE_ADMISSION");
                model_rate=rate44;switches++;
            end
            if(parameter_commit)commits++;
            if(synth_valid)begin
                synth_outputs++;if(synth!=0)nonzero_synth++;
                if(clocks-last_ce>max_synth_latency)max_synth_latency=clocks-last_ce;
            end
            if(vec_valid)begin
                vec_outputs++;if(left!=0 || right!=0)nonzero_vector++;
                if(clocks-last_ce>max_vector_latency)max_vector_latency=clocks-last_ce;
            end
            #1;
            if(applied44!==model_rate)$fatal(1,"COMMITTED_RATE");
            if(ce) begin
                if(dut.oscillator.sample_pitch_q20!==expected || dut.vector_engine.frame_pitch!==expected)
                    $fatal(1,"PITCH_CAPTURE frame=%0d expected=%0d oscillator=%0d vector=%0d",frames,expected,dut.oscillator.sample_pitch_q20,dut.vector_engine.frame_pitch);
                captures+=2;
            end
        end
    end
    task automatic idle;
        integer n=0;
        begin
            @(negedge clk);
            while(!quiet)begin @(negedge clk);n++;if(n>1800)$fatal(1,"DRAIN_TIMEOUT");end
        end
    endtask
    task automatic send(input bit on_value,input integer midi);
        begin
            idle();while(!(scope ? vec_event_ready:event_ready))@(negedge clk);
            note=7'(midi);note_on=on_value;event_valid=1;
            @(negedge clk);event_valid=0;note_on=0;idle();
        end
    endtask
    task automatic frame(input integer lead,input integer t,input integer g,input integer d);
        integer period;
        begin
            period=1600;
            if(applied44)begin
                period=1741;cadence_fraction+=73;
                if(cadence_fraction>=147)begin period++;cadence_fraction-=147;end
            end
            if(next_ce==0)next_ce=clocks;
            next_ce+=period;
            if(clocks>next_ce-lead-1)$fatal(1,"MISSED_SAMPLE_DEADLINE");
            while(clocks<next_ce-lead-1)@(negedge clk);
            next_target=22'(t);next_glide=16'(g);next_depth=7'(d);parameter_commit=1;
            @(negedge clk);parameter_commit=0;
            while(clocks<next_ce-1)@(negedge clk);
            ce=1;@(negedge clk);ce=0;frames++;
            idle();
            if(config_error || frequency_error)$fatal(1,"ENGINE_ERROR");
            if(allocated==32'hffffffff && active==32'hffffffff && count==32 && vec_active==8'hff && vec_count==8)full_frames++;
        end
    endtask
    task automatic commit_rate(input bit value);
        begin idle();rate44=value;rate_commit=1;@(negedge clk);rate_commit=0;idle();end
    endtask
    initial begin
        repeat(5)@(negedge clk);rst=1;idle();
        scope=0;for(integer v=0;v<32;v++)send(1,48+v);
        scope=1;for(integer v=0;v<8;v++)send(1,48+v);
        // Last-edge updates stress input precomputation; two-edge depth
        // updates stress the existing continuous modulation/output capture.
        for(integer rate=0;rate<3;rate++)begin
            commit_rate(rate==1);
            for(integer i=0;i<12;i++)begin
                frame(1+(i%2),i[0] ? 1179648:917504,
                      i%4==0 ? 0:(i%4==1 ? 65535:(i%4==2 ? 1:147)),
                      i[0] ? 127:0);
            end
        end
        idle();panic=1;@(negedge clk);panic=0;panic_cases++;idle();
        if(allocated!=0 || vec_active!=0)$fatal(1,"PANIC_ALLOCATION");
        scope=0;send(1,60);scope=1;send(1,69);
        frame(1,1048576,0,0);frame(2,1048576,65535,127);
        idle();
        if(captures!=2*frames || synth_outputs!=frames || vec_outputs!=frames ||
           full_frames!=36 || cadence_checks!=frames-1 || nonzero_synth==0 || nonzero_vector==0 ||
           max_synth_latency>=1600 || max_vector_latency>=1600)$fatal(1,"COVERAGE_MISSING");
        $display("PASS pitch_capture_boundary frames=%0d captures=%0d full32_vector8=%0d cadence_checks=%0d commits=%0d switches=%0d panic_cases=%0d synth_outputs=%0d vector_outputs=%0d nonzero_synth=%0d nonzero_vector=%0d max_synth_clocks=%0d max_vector_clocks=%0d",frames,captures,full_frames,cadence_checks,commits,switches,panic_cases,synth_outputs,vec_outputs,nonzero_synth,nonzero_vector,max_synth_latency,max_vector_latency);
        $finish;
    end
    initial begin #10000000;$fatal(1,"TIMEOUT");end
endmodule
