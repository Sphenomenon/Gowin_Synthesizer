`timescale 1ns/1ps
module tb_workstation_runtime_render_engines;
    logic clk=0, rst=0, panic=0, ce=0, rate_commit=0, rate44=0;
    always #5 clk=~clk;
    logic event_valid=0, note_on=0, scope=0, expression_valid=0, mode_valid=0;
    logic [6:0] note=60, off_note=60, velocity=100, pressure_note=60, pressure=127;
    logic [2:0] profile=0, shape=0;
    logic [1:0] mode=0;
    logic [21:0] target=1048576;
    logic [15:0] glide=0, morph=0, scale=32768;
    logic [6:0] vibrato=0, rotation=0;
    wire rate_ready, applied44, quiet;
    wire [21:0] pitch, ref_pitch;
    wire mode_ready, ref_mode_ready, event_ready, ref_event_ready, expr_ready, ref_expr_ready;
    wire vec_event_ready, ref_vec_event_ready, synth_ready, ref_synth_ready, vec_ready, ref_vec_ready;
    wire synth_valid, ref_synth_valid, vec_valid, ref_vec_valid;
    wire signed [31:0] synth, ref_synth, left, right, ref_left, ref_right;
    wire [31:0] allocated, ref_allocated, active, ref_active, rejected, ref_rejected;
    wire [5:0] count, ref_count;
    wire [7:0] vec_active, ref_vec_active, issued, ref_issued;
    wire [3:0] vec_count, ref_vec_count;
    wire load_busy, ref_load_busy, mix_busy, ref_mix_busy, vec_busy, ref_vec_busy;
    wire config_error, ref_config_error, freq_error, ref_freq_error, clip, ref_clip;
    wire [1:0] current_mode, ref_current_mode;
    integer clocks=0, compared=0, frames=0, switches=0, busy_rejects=0;
    integer panic_cases=0, max_latency=0, last_latency=0;
    integer audible_synth44=0;
    bit compare48=1;
    integer synth_received=0,synth_reference_received=0,vector_received=0,vector_reference_received=0;
    integer synth_paired=0,vector_paired=0;
    logic signed [31:0] synth_queue[0:4095],synth_reference_queue[0:4095];
    logic signed [63:0] vector_queue[0:4095],vector_reference_queue[0:4095];

    workstation_runtime_render_engines #(.RUNTIME_RATE_ENABLE(1)) dut (
        .clk_i(clk), .rst_ni(rst), .panic_i(panic), .sample_ce_i(ce),
        .rate_commit_i(rate_commit), .rate_44100_i(rate44), .rate_ready_o(rate_ready),
        .applied_rate_44100_o(applied44), .quiescent_o(quiet),
        .target_ratio_q20_i(target), .glide_step_q20_i(glide), .vibrato_depth_i(vibrato), .pitch_q20_o(pitch),
        .mode_set_valid_i(mode_valid), .mode_set_ready_o(mode_ready), .mode_i(mode), .current_mode_o(current_mode),
        .event_valid_i(event_valid), .event_note_on_i(note_on), .scope_enable_i(scope),
        .event_profile_i(profile), .event_note_i(note), .event_off_note_i(off_note), .event_velocity_i(velocity),
        .synth_event_ready_o(event_ready), .vector_event_ready_o(vec_event_ready),
        .expression_valid_i(expression_valid), .expression_note_i(pressure_note), .expression_value_i(pressure),
        .expression_ready_o(expr_ready), .synth_sample_ready_o(synth_ready), .synth_valid_o(synth_valid), .synth_o(synth),
        .allocated_mask_o(allocated), .synth_active_mask_o(active), .synth_active_count_o(count),
        .load_busy_o(load_busy), .mix_busy_o(mix_busy), .issued_slot_count_o(issued),
        .vector_shape_i(shape), .vector_morph_shape_i(3'd1), .vector_morph_q15_i(morph), .vector_scale_q15_i(scale),
        .vector_rotation_i(rotation), .vector_cal_x_q14_i(16'sd16384), .vector_cal_y_q14_i(16'sd16384),
        .vector_offset_x_i(32'sd0), .vector_offset_y_i(32'sd0),
        .vector_sample_ready_o(vec_ready), .vector_valid_o(vec_valid), .vector_busy_o(vec_busy),
        .vector_left_o(left), .vector_right_o(right), .vector_active_mask_o(vec_active), .vector_active_count_o(vec_count),
        .vector_rejected_o(rejected), .vector_config_error_o(config_error), .vector_frequency_error_o(freq_error), .vector_clip_o(clip)
    );
    pitch_expression #(.SAMPLE_RATE_HZ(48000)) reference_pitch (
        .clk_i(clk), .rst_ni(rst), .sample_ce_i(ce), .target_ratio_q20_i(target),
        .glide_step_q20_i(glide), .vibrato_depth_i(vibrato), .ratio_q20_o(ref_pitch));
    unified_oscillator_engine #(.EXPRESSION_ENABLE(1),.SAMPLE_RATE_HZ(48000),.SEPARATE_OFF_NOTE(1)) reference_engine (
        .clk_i(clk), .rst_ni(rst), .panic_i(panic), .sample_ce_i(ce),
        .mode_set_valid_i(mode_valid), .mode_set_ready_o(ref_mode_ready), .mode_i(mode), .current_mode_o(ref_current_mode),
        .event_valid_i(event_valid && !scope), .event_ready_o(ref_event_ready), .event_note_on_i(note_on),
        .event_profile_i(profile), .event_midi_note_i(note), .event_off_note_i(off_note), .event_velocity_i(velocity),
        .expression_valid_i(expression_valid && !scope), .expression_ready_o(ref_expr_ready),
        .expression_note_i(pressure_note), .expression_value_i(pressure), .pitch_ratio_q20_i(ref_pitch),
        .sample_ready_o(ref_synth_ready), .sample_valid_o(ref_synth_valid), .sample_o(ref_synth),
        .allocated_mask_o(ref_allocated), .active_mask_o(ref_active), .active_voice_count_o(ref_count),
        .load_busy_o(ref_load_busy), .mix_busy_o(ref_mix_busy), .issued_slot_count_o(ref_issued));
    scope_vec_engine #(.SEPARATE_OFF_NOTE(1)) reference_vector (
        .clk_i(clk), .rst_ni(rst), .panic_i(panic), .sample_ce_i(ce),
        .sample_ready_o(ref_vec_ready), .sample_valid_o(ref_vec_valid), .left_o(ref_left), .right_o(ref_right),
        .event_valid_i(event_valid && scope), .event_ready_o(ref_vec_event_ready), .event_note_on_i(note_on),
        .event_note_i(note), .event_off_note_i(off_note), .event_velocity_i(velocity), .event_profile_i(profile),
        .event_shape_i(shape), .event_morph_shape_i(3'd1), .event_pitch_q20_i(22'd1048576), .pitch_q20_i(ref_pitch),
        .morph_q15_i(morph), .scale_q15_i(scale), .rotation_i(rotation),
        .cal_x_q14_i(16'sd16384), .cal_y_q14_i(16'sd16384), .offset_x_i(32'sd0), .offset_y_i(32'sd0),
        .active_mask_o(ref_vec_active), .active_count_o(ref_vec_count), .rejected_events_o(ref_rejected),
        .config_error_o(ref_config_error), .frequency_error_o(ref_freq_error), .clip_o(ref_clip), .busy_o(ref_vec_busy));

    always @(negedge clk) begin
        clocks=clocks+1;
        if(rst && compare48) begin
            // Runtime arithmetic changes latency. Pair completed frames in
            // order and compare stored state only after the real tails drain.
            // The standalone default-call regression retains the original
            // non-runtime48 per-cycle ready/busy/valid comparison.
            if(synth_valid)begin synth_queue[synth_received]=synth;synth_received++;end
            if(ref_synth_valid)begin synth_reference_queue[synth_reference_received]=ref_synth;synth_reference_received++;end
            if(vec_valid)begin vector_queue[vector_received]={left,right};vector_received++;end
            if(ref_vec_valid)begin vector_reference_queue[vector_reference_received]={ref_left,ref_right};vector_reference_received++;end
            while(synth_paired<synth_received && synth_paired<synth_reference_received)begin
                if(synth_queue[synth_paired]!==synth_reference_queue[synth_paired])$fatal(1,"combined48 synth frame mismatch");
                synth_paired++;compared++;
            end
            while(vector_paired<vector_received && vector_paired<vector_reference_received)begin
                if(vector_queue[vector_paired]!==vector_reference_queue[vector_paired])$fatal(1,"combined48 vector frame mismatch");
                vector_paired++;compared++;
            end
            if(quiet && (synth_received!=synth_reference_received || vector_received!=vector_reference_received ||
                {pitch,current_mode,allocated,active,count,vec_active,vec_count,rejected,config_error,freq_error} !==
                {ref_pitch,ref_current_mode,ref_allocated,ref_active,ref_count,ref_vec_active,ref_vec_count,ref_rejected,ref_config_error,ref_freq_error}))
                $fatal(1,"combined48 drained control/frame ledger mismatch clock=%0d",clocks);
        end
        if(rst && quiet && (dut.oscillator.u_sine_interp.valid_s0 || dut.oscillator.u_sine_interp.valid_s1 ||
            dut.oscillator.u_sine_interp.valid_s2 || dut.oscillator.u_sine_interp.valid_s3 ||
            dut.oscillator.u_sine_interp.valid_o || dut.oscillator.gain_product_valid ||
            dut.oscillator.envelope_product_valid || dut.oscillator.finalize_valid ||
            dut.oscillator.quantizer.magnitude_low_valid || dut.oscillator.quantizer.magnitude_valid ||
            dut.oscillator.quantizer.scale_low_valid || dut.oscillator.quantizer.scaled_valid ||
            dut.oscillator.quantizer.rounded_valid || dut.oscillator.quantizer.valid_o || vec_valid || vec_busy))
            $fatal(1,"combined quiescent hid a real pipeline tail");
    end
    task automatic idle;
        integer n;
        begin
            @(negedge clk);n=0;
            while(!quiet)begin @(negedge clk);n=n+1;if(n>1800)$fatal(1,"combined idle timeout");end
        end
    endtask
    task automatic send(input bit on_value,input integer midi);
        begin
            idle();while(!(scope ? vec_event_ready:event_ready))@(negedge clk);
            note=7'(midi);off_note=7'(midi);note_on=on_value;event_valid=1;
            @(negedge clk);event_valid=0;note_on=0;idle();
        end
    endtask
    task automatic clear;
        begin @(negedge clk);panic=1;@(negedge clk);panic=0;idle();end
    endtask
    task automatic setmode(input integer m);
        begin idle();mode=2'(m);mode_valid=1;@(negedge clk);mode_valid=0;idle();end
    endtask
    task automatic render(input integer capture_tag,input bit disturb);
        bit sv,vv;
        integer n;
        begin
            idle();if(!synth_ready || !vec_ready)$fatal(1,"render readiness");
            ce=1;@(negedge clk);ce=0;n=0;sv=0;vv=0;
            while(!sv || !vv)begin
                if(synth_valid)begin sv=1;if(applied44 && synth!=0)audible_synth44=audible_synth44+1;end
                if(vec_valid)begin vv=1;if(capture_tag>=0)$display("PCM %0d %0d %0d",capture_tag,left,right);end
                if(disturb && n==2)begin rate44=!applied44;rate_commit=1;if(rate_ready)$fatal(1,"busy rate ready");end
                if(disturb && n==3)begin rate_commit=0;busy_rejects=busy_rejects+1;end
                @(negedge clk);n=n+1;if(n>1600)$fatal(1,"combined frame deadline");
            end
            frames=frames+1;last_latency=n;if(n>max_latency)max_latency=n;idle();
        end
    endtask
    task automatic commit(input bit value);
        logic [79:0] slots[0:1023];
        logic [23:0] levels[0:31];
        logic [2:0] states[0:31];
        logic [31:0] phases[0:7];
        logic [23:0] vec_levels[0:7];
        logic [31:0] lfo;
        logic [21:0] saved_glide;
        logic [31:0] mask;
        logic [7:0] vector_mask;
        begin
            idle();while(!rate_ready)@(negedge clk);
            for(integer i=0;i<1024;i=i+1)slots[i]=dut.oscillator.slot_mem[i];
            for(integer i=0;i<32;i=i+1)begin levels[i]=dut.oscillator.envelope_level_q24[i];states[i]=dut.oscillator.envelope_state[i];end
            for(integer i=0;i<8;i=i+1)begin phases[i]=dut.vector_engine.phase[i];vec_levels[i]=dut.vector_engine.envelope[i];end
            lfo=dut.pitch.phase;saved_glide=dut.pitch.glide_ratio;mask=allocated;vector_mask=vec_active;
            rate44=value;rate_commit=1;@(negedge clk);rate_commit=0;
            if(applied44!==value || allocated!==mask || vec_active!==vector_mask ||
                dut.pitch.phase!==lfo || dut.pitch.glide_ratio!==saved_glide)$fatal(1,"rate commit changed held control state");
            for(integer i=0;i<1024;i=i+1)if(slots[i]!==dut.oscillator.slot_mem[i])$fatal(1,"rate commit changed partial state");
            for(integer i=0;i<32;i=i+1)if(levels[i]!==dut.oscillator.envelope_level_q24[i] || states[i]!==dut.oscillator.envelope_state[i])$fatal(1,"rate commit changed envelope state");
            for(integer i=0;i<8;i=i+1)if(phases[i]!==dut.vector_engine.phase[i] || vec_levels[i]!==dut.vector_engine.envelope[i])$fatal(1,"rate commit changed vector state");
            switches=switches+1;
        end
    endtask
    initial begin
        repeat(5)@(negedge clk);rst=1;
        for(integer m=0;m<3;m=m+1)for(integer p=0;p<5;p=p+1)begin
            clear();setmode(m);profile=3'(p);scope=0;
            for(integer v=0;v<32;v=v+1)begin velocity=7'(40+(v*13)%88);send(1,48+v);end
            scope=1;for(integer v=0;v<8;v=v+1)begin shape=3'(v);send(1,48+v);end
            if(allocated!=32'hffffffff || vec_active!=8'hff)$fatal(1,"full engines not allocated");
            glide=16'(p*97);vibrato=7'(p*13);target=22'(1048576+p*4096);
            morph=16'(p*7000);rotation=7'(p*19);
            repeat(20)render(-1,1);
            scope=0;pressure_note=48;pressure=0;expression_valid=1;@(negedge clk);expression_valid=0;
            render(-1,0);pressure=127;expression_valid=1;@(negedge clk);expression_valid=0;render(-1,0);
            for(integer v=0;v<32;v=v+1)send(0,48+v);
            scope=1;for(integer v=0;v<8;v=v+1)send(0,48+v);
            repeat(4)render(-1,0);
        end
        $display("EQUIVALENCE combined48 ordered_outputs=%0d frames=%0d",compared,frames);
        compare48=0;clear();glide=0;vibrato=0;target=1048576;morph=0;rotation=0;shape=0;profile=0;velocity=127;
        scope=0;send(1,60);scope=1;send(1,69);
        repeat(256)render(-1,0);
        repeat(1024)render(48,0);
        commit(1);repeat(1024)render(44,1);if(!applied44)$fatal(1,"busy rate pulse changed committed rate");
        commit(0);repeat(1024)render(49,0);
        // Admission guards cover input acceptance, as well as stored pipelines.
        idle();rate44=1;rate_commit=1;event_valid=1;note_on=0;
        #1;if(rate_ready)$fatal(1,"event/rate commit collision");
        @(negedge clk);event_valid=0;rate_commit=0;if(applied44)$fatal(1,"event collision committed rate");busy_rejects=busy_rejects+1;
        idle();rate_commit=1;ce=1;#1;if(rate_ready)$fatal(1,"sample/rate commit collision");
        @(negedge clk);ce=0;rate_commit=0;if(applied44)$fatal(1,"sample collision committed rate");busy_rejects=busy_rejects+1;idle();
        // Cancellation sweeps include loading and late ROM/quantizer tails.
        for(integer offset=0;offset<48;offset=offset+1)begin
            clear();scope=0;send(1,60);ce=1;@(negedge clk);ce=0;
            repeat(offset)@(negedge clk);panic=1;rate_commit=1;
            #1;if(rate_ready)$fatal(1,"PANIC/rate collision");
            @(negedge clk);panic=0;rate_commit=0;idle();
            repeat(24)begin @(negedge clk);if(synth_valid || vec_valid || !quiet)$fatal(1,"false combined drain");end
            commit(offset[0]);panic_cases=panic_cases+1;
        end
        clear();scope=0;note=64;off_note=64;note_on=1;event_valid=1;
        @(negedge clk);event_valid=0;note_on=0;rate_commit=1;rate44=!applied44;
        if(rate_ready)$fatal(1,"loader/rate collision");
        @(negedge clk);rate_commit=0;busy_rejects=busy_rejects+1;idle();
        if(allocated!=1)$fatal(1,"busy commit destroyed accepted note");
        if(audible_synth44==0)$fatal(1,"native44 synth output never became audible");
        $display("PASS runtime_render_engines: compared_outputs=%0d frames=%0d switches=%0d busy_rejects=%0d panic_cases=%0d max_latency=%0d audible_synth44=%0d",compared,frames,switches,busy_rejects,panic_cases,max_latency,audible_synth44);
        $finish;
    end
    initial begin #100000000;$fatal(1,"timeout");end
endmodule
