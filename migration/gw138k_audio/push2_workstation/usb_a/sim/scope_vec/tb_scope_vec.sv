`timescale 1ns/1ps
module tb_scope_vec;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0,panic=0,ce=0,event_valid=0,on=0;
    wire ready,valid,event_ready,busy;
    reg [6:0] note=69,velocity=127,rotation=0;
    reg [2:0] shape=0,destination=1,profile=0;
    reg [21:0] pitch=1048576,own_pitch=1048576;
    reg [15:0] morph=0,scale=32768;
    reg signed [15:0] cal_x=16384,cal_y=16384;
    reg signed [31:0] offset_x=0,offset_y=0;
    wire signed [31:0] left,right;
    wire [7:0] active;
    wire [3:0] count;
    wire [31:0] rejected;
    wire config_error,frequency_error;
    integer cycle_count=0,max_latency=0,measured_latency,n,j;
    scope_vec_engine #(.ADSR_FILE("scope_test_adsr.mem")) dut(
        .clk_i(clk),.rst_ni(rst_n),.panic_i(panic),.sample_ce_i(ce),.sample_ready_o(ready),
        .sample_valid_o(valid),.left_o(left),.right_o(right),.event_valid_i(event_valid),
        .event_note_on_i(on),.event_ready_o(event_ready),.event_note_i(note),.event_velocity_i(velocity),
        .event_shape_i(shape),.event_morph_shape_i(destination),.event_profile_i(profile),
        .event_pitch_q20_i(own_pitch),.pitch_q20_i(pitch),.morph_q15_i(morph),.scale_q15_i(scale),
        .rotation_i(rotation),.cal_x_q14_i(cal_x),.cal_y_q14_i(cal_y),.offset_x_i(offset_x),.offset_y_i(offset_y),
        .active_mask_o(active),.active_count_o(count),.rejected_events_o(rejected),
        .config_error_o(config_error),.frequency_error_o(frequency_error),.clip_o(),.busy_o(busy));
    wire raw_ready,raw_valid,raw_event_ready,raw_busy,raw_config_error,raw_frequency_error;
    wire signed [31:0] raw_left,raw_right;
    wire [7:0] raw_active;
    wire [3:0] raw_count;
    wire [31:0] raw_rejected;
    scope_vec_engine #(.PATH_FILE("raw_paths.mem"),.ADSR_FILE("scope_test_adsr.mem")) raw_dut(
        .clk_i(clk),.rst_ni(rst_n),.panic_i(panic),.sample_ce_i(ce),.sample_ready_o(raw_ready),
        .sample_valid_o(raw_valid),.left_o(raw_left),.right_o(raw_right),.event_valid_i(event_valid),
        .event_note_on_i(on),.event_ready_o(raw_event_ready),.event_note_i(note),.event_velocity_i(velocity),
        .event_shape_i(shape),.event_morph_shape_i(destination),.event_profile_i(profile),
        .event_pitch_q20_i(own_pitch),.pitch_q20_i(pitch),.morph_q15_i(morph),.scale_q15_i(scale),
        .rotation_i(rotation),.cal_x_q14_i(cal_x),.cal_y_q14_i(cal_y),.offset_x_i(offset_x),.offset_y_i(offset_y),
        .active_mask_o(raw_active),.active_count_o(raw_count),.rejected_events_o(raw_rejected),
        .config_error_o(raw_config_error),.frequency_error_o(raw_frequency_error),.clip_o(),.busy_o(raw_busy));
    task automatic event_send(input bit note_on,input integer midi,input integer form,input integer force_value);
        begin
            while(!event_ready) @(negedge clk);
            on=note_on;note=7'(midi);shape=3'(form);velocity=7'(force_value);event_valid=1;
            @(negedge clk);event_valid=0;
        end
    endtask
    task automatic frame(input integer tag);
        begin
            if(!ready)$fatal(1,"not ready at frame boundary");
            ce=1;@(negedge clk);ce=0;measured_latency=0;
            while(!valid) begin @(negedge clk);measured_latency=measured_latency+1;if(measured_latency>=1600)$fatal(1,"deadline");end
            if(measured_latency>max_latency)max_latency=measured_latency;
            if(!raw_valid)$fatal(1,"raw/smooth timing mismatch");
            if(tag==2 || tag==3)$display("S %0d %0d %0d",tag+100,raw_left,raw_right);
            if(tag>=0)$display("S %0d %0d %0d",tag,left,right);
            // Genuine 1600-cycle frame cadence, even when the engine finishes early.
            repeat(1599-measured_latency)@(negedge clk);
        end
    endtask
    task automatic clear;
        begin panic=1;@(negedge clk);panic=0;end
    endtask
    initial begin
        repeat(4)@(negedge clk);rst_n=1;
        repeat(130)frame(-1); // settle control slew
        event_send(1,69,0,127);
        repeat(100)frame(-1);
        repeat(8192)frame(0); // 440 Hz quadrature, Hann leakage
        clear();pitch=1048576;own_pitch=1048576;
        event_send(1,60,0,127);repeat(100)frame(-1);repeat(8192)frame(1);
        clear();event_send(1,69,3,127);repeat(100)frame(-1);repeat(8192)frame(2);
        clear();event_send(1,95,3,127);repeat(100)frame(-1);repeat(8192)frame(3);
        clear();event_send(1,69,0,127);repeat(100)frame(-1);
        morph=32768;repeat(512)frame(4);
        if(dut.morph!=32768)$fatal(1,"morph slew target");
        repeat(8192)frame(5);
        rotation=32;repeat(160)frame(6);
        if(dut.rotation!=128)$fatal(1,"rotation target");
        scale=0;repeat(256)frame(7);
        if(left!=0 || right!=0)$fatal(1,"live mute not exact zero");
        scale=32768;repeat(256)frame(8);
        event_send(0,69,0,0);repeat(300)frame(9);
        if(count!=0 || left!=0 || right!=0)$fatal(1,"release not silent");
        // All 8 voices run independent phase, note, velocity and own pitch.
        clear();morph=0;rotation=0;
        for(j=0;j<8;j=j+1)begin own_pitch=22'(1048576+j*1024);event_send(1,48+j,j,40+j*10);end
        if(count!=8)$fatal(1,"eight-voice allocation");
        event_send(1,60,0,127);
        if(rejected!=1)$fatal(1,"ninth voice must explicitly reject");
        repeat(2048)frame(10);
        for(j=0;j<8;j=j+1)event_send(0,48+j,j,0);
        repeat(300)frame(-1);
        if(count!=0)$fatal(1,"all releases");
        // Velocity, calibration and individual base rate.
        own_pitch=1048576;event_send(1,69,0,64);repeat(100)frame(-1);repeat(2048)frame(11);
        cal_x=20480;cal_y=12288;offset_x=1048576;offset_y=-1048576;repeat(2048)frame(12);
        clear();cal_x=16384;cal_y=16384;offset_x=0;offset_y=0;
        profile=1;event_send(1,69,0,127);repeat(256)frame(13); // zero-step ADSR semantics
        event_send(0,69,0,0);frame(-1);
        if(count!=0)$fatal(1,"zero release step");
        profile=2;event_send(1,69,0,127);repeat(16)frame(-1);
        if(dut.envelope[0]!=24'h400000 || dut.env_state[0]!=1)$fatal(1,"Q24 linear attack");
        repeat(48)frame(-1);
        if(dut.envelope[0]!=24'hffffff || dut.env_state[0]!=2)$fatal(1,"attack saturation");
        repeat(32)frame(-1);
        if(dut.envelope[0]!=24'h800000 || dut.env_state[0]!=3)$fatal(1,"decay to sustain");
        repeat(16)frame(-1);
        if(dut.envelope[0]!=24'h800000)$fatal(1,"sustain stability");
        event_send(0,69,0,0);repeat(32)frame(-1);
        if(dut.envelope[0]!=0 || count!=0)$fatal(1,"linear release to idle");
        profile=0;event_send(1,96,0,127); // out-of-band note
        if(rejected!=2 || !config_error)$fatal(1,"frequency config rejection");
        event_send(1,81,0,127);pitch=4194303;repeat(16)frame(14);
        if(!frequency_error || left!=0 || right!=0)$fatal(1,"bend out of band must fail explicit and mute frame");
        pitch=1048576;repeat(32)frame(-1);clear();
        event_send(1,69,0,127);repeat(100)frame(-1);
        for(n=0;n<1024;n=n+1) begin pitch=22'(524288+n*1024);frame(16);end
        pitch=1048576;clear();
        repeat(32)frame(15);
        if(left!=0 || right!=0)$fatal(1,"panic residue");
        $display("M max_cycles %0d",max_latency);
        $display("PASS scope_vec");$finish;
    end
endmodule
