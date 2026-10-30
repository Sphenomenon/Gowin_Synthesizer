`timescale 1ns/1ps
module tb_workstation_runtime_scope_vec_resource;
    reg clk=0,rst_n=0,panic=0,ce=0,rate44=0,ev=0,note_on=0;
    always #6.510416667 clk=~clk;
    reg [6:0] note=69,off_note=69,velocity=127,rotation=0;
    reg [2:0] shape=0,destination=1,profile=0;
    reg [21:0] pitch=1048576,own_pitch=1048576;
    reg [15:0] morph=0,scale=32768;
    reg signed [15:0] cal_x=16384,cal_y=16384;
    reg signed [31:0] offset_x=0,offset_y=0;
    wire ready,valid,event_ready,busy,ref_ready,ref_valid,ref_event_ready,ref_busy;
    wire signed [31:0] left,right,ref_left,ref_right;
    wire [7:0] active,ref_active;
    wire [3:0] count,ref_count;
    wire [31:0] rejected,ref_rejected;
    wire cfg,freq,clipped,ref_cfg,ref_freq,ref_clip;
    workstation_runtime_scope_vec #(.ADSR_FILE("adsr.mem"),.SEPARATE_OFF_NOTE(1)) dut(
        .clk_i(clk),.rst_ni(rst_n),.panic_i(panic),.sample_ce_i(ce),.rate_44k1_i(rate44),
        .sample_ready_o(ready),.sample_valid_o(valid),.left_o(left),.right_o(right),
        .event_valid_i(ev),.event_note_on_i(note_on),.event_ready_o(event_ready),
        .event_note_i(note),.event_off_note_i(off_note),.event_velocity_i(velocity),
        .event_shape_i(shape),.event_morph_shape_i(destination),.event_profile_i(profile),
        .event_pitch_q20_i(own_pitch),.pitch_q20_i(pitch),.morph_q15_i(morph),.scale_q15_i(scale),.rotation_i(rotation),
        .cal_x_q14_i(cal_x),.cal_y_q14_i(cal_y),.offset_x_i(offset_x),.offset_y_i(offset_y),
        .active_mask_o(active),.active_count_o(count),.rejected_events_o(rejected),
        .config_error_o(cfg),.frequency_error_o(freq),.clip_o(clipped),.busy_o(busy));
    workstation_runtime_scope_vec_reference #(.ADSR_FILE("adsr.mem"),.SEPARATE_OFF_NOTE(1)) reference_engine(
        .clk_i(clk),.rst_ni(rst_n),.panic_i(panic),.sample_ce_i(ce),.rate_44k1_i(rate44),
        .sample_ready_o(ref_ready),.sample_valid_o(ref_valid),.left_o(ref_left),.right_o(ref_right),
        .event_valid_i(ev),.event_note_on_i(note_on),.event_ready_o(ref_event_ready),
        .event_note_i(note),.event_off_note_i(off_note),.event_velocity_i(velocity),
        .event_shape_i(shape),.event_morph_shape_i(destination),.event_profile_i(profile),
        .event_pitch_q20_i(own_pitch),.pitch_q20_i(pitch),.morph_q15_i(morph),.scale_q15_i(scale),.rotation_i(rotation),
        .cal_x_q14_i(cal_x),.cal_y_q14_i(cal_y),.offset_x_i(offset_x),.offset_y_i(offset_y),
        .active_mask_o(ref_active),.active_count_o(ref_count),.rejected_events_o(ref_rejected),
        .config_error_o(ref_cfg),.frequency_error_o(ref_freq),.clip_o(ref_clip),.busy_o(ref_busy));
    integer compared_clocks=0,frames48=0,frames44=0,max_latency=0,held_switches=0;
    integer frames_by_profile[0:9];
    integer panic_inflight=0,overflow_frames=0,cache_checks=0,phase_checks=0;
    reg [4:0] envelope_states_seen=0;
    reg [53:0] probe=0;
    wire [61:0] probe_n={8'd0,probe}*62'd160+62'd77070336;
    wire [41:0] probe_hi=probe_n[61:20];
    wire [34:0] probe_old=35'(probe_n/62'd154140672),probe_new=35'(probe_hi/42'd147);
    always @(posedge clk)begin
        #1;
        if(rst_n)begin
            compared_clocks=compared_clocks+1;
            if({ready,valid,left,right,event_ready,busy,active,count,rejected,cfg,freq,clipped}!==
               {ref_ready,ref_valid,ref_left,ref_right,ref_event_ready,ref_busy,ref_active,ref_count,ref_rejected,ref_cfg,ref_freq,ref_clip})
                $fatal(1,"native outputs differ clock=%0d rate=%b profile=%d",compared_clocks,rate44,profile);
            if({dut.state,dut.voice_index,dut.frame_44k1,dut.frame_pitch,dut.morph,dut.scale,dut.rotation,
                dut.slew_remainder,dut.rotation_remainder,dut.effective_step}!==
               {reference_engine.state,reference_engine.voice_index,reference_engine.frame_44k1,reference_engine.frame_pitch,
                reference_engine.morph,reference_engine.scale,reference_engine.rotation,reference_engine.slew_remainder,
                reference_engine.rotation_remainder,reference_engine.effective_step})
                $fatal(1,"native schedule/control/phase quotient differ clock=%0d",compared_clocks);
            for(integer voice=0;voice<8;voice=voice+1)begin
                if({dut.phase[voice],dut.base_step[voice],dut.own_pitch[voice],dut.note[voice],dut.shape[voice],
                    dut.morph_shape[voice],dut.envelope[voice],dut.env_state[voice],dut.attack[voice],dut.decay[voice],
                    dut.sustain[voice],dut.release_step[voice],dut.velocity[voice]}!==
                   {reference_engine.phase[voice],reference_engine.base_step[voice],reference_engine.own_pitch[voice],
                    reference_engine.note[voice],reference_engine.shape[voice],reference_engine.morph_shape[voice],
                    reference_engine.envelope[voice],reference_engine.env_state[voice],reference_engine.attack[voice],
                    reference_engine.decay[voice],reference_engine.sustain[voice],reference_engine.release_step[voice],reference_engine.velocity[voice]})
                    $fatal(1,"native held voice state differs voice=%0d clock=%0d",voice,compared_clocks);
                if(dut.attack_44[voice]!==reference_engine.envelope_step(reference_engine.attack[voice],1'b1) ||
                   dut.decay_44[voice]!==reference_engine.envelope_step(reference_engine.decay[voice],1'b1) ||
                   dut.release_44[voice]!==reference_engine.envelope_step(reference_engine.release_step[voice],1'b1))
                    $fatal(1,"cached coefficient lost canonical value/profile voice=%0d",voice);
                cache_checks=cache_checks+3;
                envelope_states_seen[reference_engine.env_state[voice]]=1;
            end
            if(probe_old!==probe_new)$fatal(1,"unsigned phase quotient mismatch probe=%h",probe);
            phase_checks=phase_checks+1;
        end
    end
    task automatic send(input bit on_value,input integer midi);
        begin
            @(negedge clk);if(!event_ready)$fatal(1,"event not ready");
            ev=1;note_on=on_value;
            if(on_value)note=7'(midi);else off_note=7'(midi);
            @(negedge clk);ev=0;
        end
    endtask
    task automatic clear;
        begin @(negedge clk);panic=1;@(negedge clk);panic=0;end
    endtask
    task automatic frame(input bit perturb);
        integer latency;
        reg original_rate;
        begin
            @(negedge clk);if(!ready)$fatal(1,"frame not ready");ce=1;original_rate=rate44;
            @(negedge clk);ce=0;latency=0;
            while(!valid)begin
                @(negedge clk);latency=latency+1;
                if(perturb && latency==7)rate44=~rate44;
                if(latency>200)$fatal(1,"render deadline");
            end
            if(dut.frame_44k1!==original_rate)$fatal(1,"rate not frozen at frame acceptance");
            if(perturb)rate44=original_rate;
            if(original_rate)frames44=frames44+1;else frames48=frames48+1;
            if(latency>max_latency)max_latency=latency;
            @(negedge clk);
        end
    endtask
    reg [31:0] saved_phase[0:7];
    reg [23:0] saved_env[0:7];
    task automatic switch_held;
        begin
            for(integer k=0;k<8;k=k+1)begin saved_phase[k]=dut.phase[k];saved_env[k]=dut.envelope[k];end
            @(negedge clk);rate44=~rate44;repeat(9)@(negedge clk);
            for(integer k=0;k<8;k=k+1)
                if(dut.phase[k]!==saved_phase[k] || dut.envelope[k]!==saved_env[k])$fatal(1,"rate switch reloaded held voice");
            held_switches=held_switches+1;
        end
    endtask
    integer rate_index,profile_index,voice_index,frame_index;
    reg stress;
    reg [31:0] before_rejected;
    initial begin
        stress=$test$plusargs("STRESS_ADSR");
        for(integer k=0;k<10;k=k+1)frames_by_profile[k]=0;
        repeat(5)@(negedge clk);rst_n=1;
        // Probe bounds and random values across the unsigned54 product range,
        // including values rejected before audible output.
        probe=0;repeat(2)@(negedge clk);
        probe=54'h3fffffffffffff;
        repeat(4)@(negedge clk);
        probe=54'd1;
        for(integer k=0;k<10000;k=k+1)begin
            @(negedge clk);probe={probe[52:0],probe[53]^probe[52]^probe[17]^probe[0]};
        end
        for(rate_index=0;rate_index<2;rate_index=rate_index+1)begin
            for(profile_index=0;profile_index<5;profile_index=profile_index+1)begin
                clear();rate44=1'(rate_index);profile=3'(profile_index);
                morph=16'(profile_index*7000);rotation=7'(profile_index*21);
                cal_x=16'(16384+profile_index*311);cal_y=16'(16384-profile_index*211);
                offset_x=profile_index*123;offset_y=-profile_index*321;
                for(voice_index=0;voice_index<8;voice_index=voice_index+1)begin
                    shape=3'(voice_index);destination=3'(7-voice_index);velocity=7'(50+voice_index*9);
                    own_pitch=22'(1048576+voice_index*1321);send(1,48+voice_index);
                end
                if(active!=8'hff || count!=8)$fatal(1,"lost eight-voice capacity");
                before_rejected=rejected;send(1,60);
                if(rejected!=before_rejected+1 || count!=8)$fatal(1,"full voice rejection changed");
                repeat(72)begin frame(1);frames_by_profile[rate_index*5+profile_index]=frames_by_profile[rate_index*5+profile_index]+1;end
                // Changing an unrelated live profile during held notes must
                // never recompute their cached coefficients from that profile.
                profile=3'((profile_index+2)%5);switch_held();repeat(24)frame(0);
                switch_held();repeat(24)frame(0);
                for(voice_index=0;voice_index<8;voice_index=voice_index+1)send(0,48+voice_index);
                repeat(72)frame(0);
                if(stress && count!=0)$fatal(1,"stress release did not finish");
            end
        end
        // Invalid accumulated pitch mutes while preserving held state, then
        // lower pitch recovers the same voice without Note On or reallocation.
        clear();profile=0;shape=0;destination=1;own_pitch=4194303;pitch=4194303;send(1,69);
        for(rate_index=0;rate_index<2;rate_index=rate_index+1)begin
            rate44=1'(rate_index);repeat(8)begin frame(0);overflow_frames=overflow_frames+1;end
            if(!freq || left!=0 || right!=0 || count!=1)$fatal(1,"overflow/frequency policy changed");
        end
        pitch=524288;repeat(16)frame(0);
        if(left==0 && right==0)$fatal(1,"held pitch recovery failed");
        // Abort a real frame at each rate; both implementations must preserve
        // the original cancellation schedule and emit no late frame.
        for(rate_index=0;rate_index<2;rate_index=rate_index+1)begin
            rate44=1'(rate_index);
            own_pitch=1048576;pitch=1048576;profile=4;send(1,69);
            @(negedge clk);ce=1;@(negedge clk);ce=0;repeat(19)@(negedge clk);
            clear();panic_inflight=panic_inflight+1;
            repeat(160)begin @(negedge clk);if(valid)$fatal(1,"PANIC leaked old render");end
            frame(0);if(active!=0 || left!=0 || right!=0)$fatal(1,"PANIC residue");
        end
        for(integer k=0;k<10;k=k+1)if(frames_by_profile[k]!=72)$fatal(1,"missing rate/profile coverage");
        if(stress && envelope_states_seen!=5'b11111)$fatal(1,"stress ADSR state coverage=%b",envelope_states_seen);
        $display("PASS vector_resource: compared_clocks=%0d frames48=%0d frames44=%0d profiles_per_rate=5 voices=8 max_render_clocks=%0d held_switches=%0d panic_inflight=%0d overflow_frames=%0d cache_checks=%0d phase_checks=%0d envelope_states=%0d stress=%0d",compared_clocks,frames48,frames44,max_latency,held_switches,panic_inflight,overflow_frames,cache_checks,phase_checks,envelope_states_seen,stress);
        $finish;
    end
    initial begin #20000000;$fatal(1,"vector resource regression deadline");end
endmodule
