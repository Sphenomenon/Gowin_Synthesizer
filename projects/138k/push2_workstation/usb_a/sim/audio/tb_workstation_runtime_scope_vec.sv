`timescale 1ns/1ps
module tb_workstation_runtime_scope_vec;
    reg clk=0,rst_n=0,panic=0,ce=0,rate44=0,ev=0,on=0;
    always #6.510416667 clk=!clk;
    reg [6:0] note=69,velocity=127,rotation=0;
    reg [2:0] shape=0,destination=1,profile=0;
    reg [21:0] pitch=1048576,own_pitch=1048576;
    reg [15:0] morph=0,scale=32768;
    reg signed [15:0] cal_x=16384,cal_y=16384;
    reg signed [31:0] offset_x=0,offset_y=0;
    wire ready,valid,event_ready,busy,reference_ready,reference_valid,reference_event_ready;
    wire signed [31:0] left,right,reference_left,reference_right;
    wire [7:0] active,reference_active;
    wire [3:0] count,reference_count;
    wire [31:0] rejected,reference_rejected;
    wire cfg,freq,clipped,reference_cfg,reference_freq,reference_clip;
    workstation_runtime_scope_vec #(.ADSR_FILE("adsr.mem")) dut(
        .clk_i(clk),.rst_ni(rst_n),.panic_i(panic),.sample_ce_i(ce),.rate_44k1_i(rate44),
        .sample_ready_o(ready),.sample_valid_o(valid),.left_o(left),.right_o(right),
        .event_valid_i(ev),.event_note_on_i(on),.event_ready_o(event_ready),
        .event_note_i(note),.event_velocity_i(velocity),.event_shape_i(shape),.event_morph_shape_i(destination),.event_profile_i(profile),
        .event_pitch_q20_i(own_pitch),.pitch_q20_i(pitch),.morph_q15_i(morph),.scale_q15_i(scale),.rotation_i(rotation),
        .cal_x_q14_i(cal_x),.cal_y_q14_i(cal_y),.offset_x_i(offset_x),.offset_y_i(offset_y),
        .active_mask_o(active),.active_count_o(count),.rejected_events_o(rejected),.config_error_o(cfg),.frequency_error_o(freq),.clip_o(clipped),
        .busy_o(busy),.event_off_note_i(note));
    scope_vec_engine #(.ADSR_FILE("adsr.mem")) reference_engine(
        .clk_i(clk),.rst_ni(rst_n),.panic_i(panic),.sample_ce_i(ce),
        .sample_ready_o(reference_ready),.sample_valid_o(reference_valid),.left_o(reference_left),.right_o(reference_right),
        .event_valid_i(ev),.event_note_on_i(on),.event_ready_o(reference_event_ready),
        .event_note_i(note),.event_velocity_i(velocity),.event_shape_i(shape),.event_morph_shape_i(destination),.event_profile_i(profile),
        .event_pitch_q20_i(own_pitch),.pitch_q20_i(pitch),.morph_q15_i(morph),.scale_q15_i(scale),.rotation_i(rotation),
        .cal_x_q14_i(cal_x),.cal_y_q14_i(cal_y),.offset_x_i(offset_x),.offset_y_i(offset_y),
        .active_mask_o(reference_active),.active_count_o(reference_count),.rejected_events_o(reference_rejected),
        .config_error_o(reference_cfg),.frequency_error_o(reference_freq),.clip_o(reference_clip),.busy_o(),.event_off_note_i(note));
    bit compare48=1;
    integer compared=0,frames48=0,max_latency=0,latency;
    always @(negedge clk) if(rst_n && compare48)begin
        if({ready,valid,left,right,event_ready,active,count,rejected,cfg,freq,clipped}!==
           {reference_ready,reference_valid,reference_left,reference_right,reference_event_ready,reference_active,reference_count,
            reference_rejected,reference_cfg,reference_freq,reference_clip})$fatal(1,"reference48 outputs differ cycle%0d",compared);
        for(integer i=0;i<8;i=i+1)
            if({dut.phase[i],dut.envelope[i],dut.env_state[i]}!==
               {reference_engine.phase[i],reference_engine.envelope[i],reference_engine.env_state[i]})
                $fatal(1,"reference48 held state differs voice%0d",i);
        compared=compared+1;
    end
    task automatic send(input bit is_on,input integer midi);
        begin
            @(negedge clk);wait(event_ready);ev=1;on=is_on;note=7'(midi);
            @(negedge clk);ev=0;
        end
    endtask
    task automatic clear;
        begin @(negedge clk);panic=1;@(negedge clk);panic=0;end
    endtask
    task automatic frame(input integer capture_tag,input bit perturb_rate);
        begin
            @(negedge clk);if(!ready)$fatal(1,"not ready");ce=1;
            @(negedge clk);ce=0;latency=0;
            while(!valid)begin
                @(negedge clk);latency=latency+1;
                if(perturb_rate && latency==8)rate44=!rate44;
                if(latency>1600)$fatal(1,"vector deadline");
            end
            if(perturb_rate)rate44=!rate44;
            if(latency>max_latency)max_latency=latency;
            if(compare48)frames48=frames48+1;
            if(capture_tag>=0)$display("S %0d %0d %0d",capture_tag,left,right);
            @(negedge clk);
        end
    endtask
    reg [31:0] saved_phase;
    reg [23:0] saved_envelope;
    integer attack48,attack44,control_frames;
    initial begin
        repeat(4)@(negedge clk);rst_n=1;
        // Allfive profiles,8 distinct phases/notes/velocities/shapes and
        // nontrivial render controls must preserve the native48k output.
        for(integer p=0;p<5;p=p+1)begin
            clear();profile=3'(p);morph=16'(p*7000);rotation=7'(p*19);
            cal_x=16'(16384+p*200);cal_y=16'(16384-p*200);offset_x=p*100;offset_y=-p*100;
            for(integer i=0;i<8;i=i+1)begin shape=3'(i);velocity=7'(50+i*9);own_pitch=22'(1048576+i*1024);send(1,48+i);end
            repeat(72)frame(-1,0);
            for(integer i=0;i<8;i=i+1)send(0,48+i);
            repeat(24)frame(-1,0);
        end
        $display("EQUIVALENCE vector48 frames=%0d clocks=%0d max_render_cycles=%0d",frames48,compared,max_latency);
        compare48=0;clear();shape=0;destination=1;profile=0;velocity=127;own_pitch=1048576;pitch=1048576;
        morph=0;rotation=0;cal_x=16384;cal_y=16384;offset_x=0;offset_y=0;
        repeat(300)frame(-1,0);send(1,69);
        repeat(200)frame(-1,0);
        repeat(1024)frame(48,0);
        saved_phase=dut.phase[0];saved_envelope=dut.envelope[0];
        @(negedge clk);rate44=1;repeat(12)@(negedge clk);
        if(dut.phase[0]!==saved_phase || dut.envelope[0]!==saved_envelope || count!=1)$fatal(1,"switch reset held voice");
        repeat(1024)frame(44,1); // Incoming rate changes during render must be ignored.
        saved_phase=dut.phase[0];saved_envelope=dut.envelope[0];
        @(negedge clk);rate44=0;repeat(12)@(negedge clk);
        if(dut.phase[0]!==saved_phase || dut.envelope[0]!==saved_envelope)$fatal(1,"reverse switch reset held voice");
        repeat(1024)frame(49,0);
        // Scaled max-step must still represent2000Hz, including accumulated
        // own/global pitch. An invalid frame mutes but does not destroy voices.
        own_pitch=4194303;clear();send(1,69);pitch=4194303;rate44=1;
        repeat(8)frame(-1,0);
        if(!freq || left || right || count!=1)$fatal(1,"rate44 invalid frequency not explicit");
        pitch=524288;repeat(8)frame(-1,0);
        if(left==0 && right==0)$fatal(1,"valid pitch could not recover held voice");
        // Compare physical attack time, retaining the existing vector table
        // (which intentionally differs from the main oscillator envelope).
        clear();pitch=1048576;own_pitch=1048576;rate44=0;profile=4;send(1,69);attack48=0;
        while(dut.env_state[0]==1)begin frame(-1,0);attack48=attack48+1;end
        clear();rate44=1;send(1,69);attack44=0;
        while(dut.env_state[0]==1)begin frame(-1,0);attack44=attack44+1;end
        $display("ATTACK profile=piano frames48=%0d frames44=%0d",attack48,attack44);
        if($abs(real'(attack48)/48000-real'(attack44)/44100)>0.00003)$fatal(1,"vector attack physical time drift");
        // Fractional control slew must reach the exact target without
        // overshooting an angular step when the nearest direction ends at1.
        morph=32768;scale=0;rotation=32;control_frames=0;
        while(dut.morph!=32768 || dut.scale!=0 || dut.rotation!=128)begin
            frame(-1,0);control_frames=control_frames+1;
            if(control_frames>119)$fatal(1,"rate44 control slew time drift or angular overshoot");
        end
        if(control_frames<117)$fatal(1,"control slew too fast");
        if(left || right)$fatal(1,"scale0 must produce exact mute");
        $display("CONTROLS rate44100 frames=%0d canonical48_frames=128",control_frames);
        clear();repeat(4)frame(-1,0);if(count || left || right)$fatal(1,"panic residue");
        $display("PASS runtime vector:48k equivalence, held forward/reverse switch, PCM frequency, frame-frozen rate, antialias recovery, envelope time");
        $finish;
    end
    initial begin #20000000;$fatal(1,"timeout");end
endmodule
