`timescale 1ns/1ps
module tb_scope_workstation;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0,ce=0,cpu_valid=0,midi_valid=0;
    reg [7:0] midi_byte=0;
    reg [17:0] event_data=0;
    wire cpu_ready,valid,synth_valid,clip;
    wire signed [31:0] left,right,synth;
    wire [31:0] active,deadline,overflow,dropped,scope_status,tf_control;
    wire [5:0] count;
    wire [2:0] effects;
    wire [9:0] epoch;
    integer n,latency,max_latency=0;
    reg [31:0] previous_cue_time;
    reg signed [31:0] expected_x,expected_y;
    gw138k_event_workstation #(.DELAY_BITS(6),.ECHO_SAMPLES(17)) dut(
        .delay_mem_clk_i(clk),.delay_mem_rst_ni(rst_n),.delay_dwr_valid_o(),.delay_dwr_data_o(),.delay_dwr_pop_i(1'b1),
        .delay_drd_push_i(1'b0),.delay_drd_data_i(65'd0),.delay_drd_ready_o(),
        .clk_i(clk),.rst_ni(rst_n),.midi_byte_valid_i(midi_valid),.midi_byte_i(midi_byte),
        .pc_byte_valid_i(1'b0),.pc_byte_i(8'd0),.held_notes_o(),.applied_events_o(),.pc_overflow_o(),.control_options_o(),
        .panic_epoch_o(epoch),.cpu_event_valid_i(cpu_valid),.cpu_event_i(event_data),.cpu_event_ready_o(cpu_ready),
        .sample_ce_i(ce),.pcm_left_i(32'sd0),.pcm_right_i(32'sd0),.sample_valid_o(valid),.left_o(left),.right_o(right),
        .synth_valid_o(synth_valid),.synth_o(synth),.active_mask_o(active),.active_voice_count_o(count),.mode_o(),.pitch_q20_o(),
        .deadline_miss_o(deadline),.midi_overflow_o(overflow),.note_drop_o(dropped),.clip_o(clip),.synth_gain_o(),.pcm_gain_o(),
        .route_o(),.profile_o(),.effect_mask_o(effects),.effect_order_o(),.panel_event_valid_o(),.panel_command_o(),.scope_status_o(scope_status),.tf_scope_control_o(tf_control));
    task automatic control(input integer cc,value);
        begin
            event_data={4'd2,7'(cc),7'(value)};cpu_valid=1;
            @(posedge clk);
            while(!cpu_ready)@(posedge clk);
            @(negedge clk);cpu_valid=0;
            repeat(32)@(negedge clk);
        end
    endtask
    task automatic byte_send(input [7:0] value);
        begin midi_byte=value;midi_valid=1;@(negedge clk);midi_valid=0;repeat(16)@(negedge clk);end
    endtask
    task automatic frame(input bit compare_xy);
        begin
            ce=1;@(negedge clk);ce=0;latency=0;
            while(!valid) begin
                @(negedge clk);latency=latency+1;
                if(latency==1600)$fatal(1,"workstation missed 1600-cycle budget");
            end
            if(latency>max_latency)max_latency=latency;
            if(compare_xy && (left!==dut.held_vec_l || right!==dut.held_vec_r))
                $fatal(1,"final dry L/R changed vector: %0d/%0d expected %0d/%0d",left,right,dut.held_vec_l,dut.held_vec_r);
            repeat(1599-latency)@(negedge clk);
        end
    endtask
    initial begin
        #100000000;$fatal(1,"global TB timeout");
    end
    initial begin
        repeat(4)@(negedge clk);rst_n=1;
        repeat(256)frame(0);
        control(90,127);
        if(effects!=0 || !scope_status[8])$fatal(1,"scope default dry/enable");
        // Real MIDI byte stream, through the existing decoder and event FIFO.
        byte_send(8'h90);byte_send(8'd36);byte_send(8'd127);
        repeat(400)frame(1);
        if(count!=1 || active!=1)$fatal(1,"live note must allocate vector only");
        if(dut.legacy_engines.vector_engine.shape[0]!=0)$fatal(1,"pad36 geometry mapping");
        control(93,0);repeat(256)frame(1);
        if(left!=0 || right!=0)$fatal(1,"live scale mute");
        control(93,127);control(91,6);control(92,80);control(94,32);
        repeat(256)frame(1);
        // Seven more distinct notes: maximum concurrency and deadline.
        for(n=37;n<=43;n=n+1)begin byte_send(8'h90);byte_send(8'(n));byte_send(8'd50);end
        repeat(256)frame(1);
        if(count!=8)$fatal(1,"workstation vector concurrency");
        control(90,0); // must fail while active, rather than strand held notes
        if(!scope_status[8] || !scope_status[11] || dropped==0)$fatal(1,"active-mode switch must fail explicit");
        control(120,0);repeat(32)frame(0);
        if(count!=0 || left!=0 || right!=0)$fatal(1,"panic clear vector and effects");
        control(96,127);repeat(256)frame(1);
        if(!dut.cue_running || count!=1)$fatal(1,"live scene start did not dispatch control notes");
        previous_cue_time=dut.cue_time;control(103,127);repeat(128)frame(1);
        if(dut.cue_time-previous_cue_time!=256)$fatal(1,"live scene 2x speed");
        control(95,64);repeat(256)frame(1);
        if(left!=0 || right!=0)$fatal(1,"live mute overlay on scene");
        control(95,64);repeat(256)frame(1);
        if(dut.scope_muted)$fatal(1,"stateless mute toggle must restore");
        control(120,0);repeat(32)frame(0);
        if(dut.cue_running || count!=0 || left!=0 || right!=0)$fatal(1,"panic stops cue and voices");
        control(90,64);
        if(scope_status[8])$fatal(1,"stateless Select toggle disable after cue");
        control(90,64);
        if(!scope_status[8])$fatal(1,"stateless Select toggle enable");
        byte_send(8'h90);byte_send(8'd96);byte_send(8'd127);repeat(16)frame(0);
        if(count!=0 || dut.held[96] || dropped<2)$fatal(1,"unsupported high pad must reject without held latch");
        control(104,127);
        if(!tf_control[12] || !tf_control[13] || scope_status[8]) $fatal(1,"accepted TF entry must own output");
        byte_send(8'h90);byte_send(8'd36);byte_send(8'd100);repeat(32)frame(0);
        if(count!=0 || dut.held[36]) $fatal(1,"TF mode allocated a hidden synth voice");
        control(105,64);if(tf_control[13]) $fatal(1,"accepted TF pause");
        control(105,127);if(!tf_control[13] || tf_control[31:16]!=2) $fatal(1,"accepted TF restart");
        control(106,3);if(tf_control[11:8]!=3) $fatal(1,"accepted TF track");
        control(120,0);if(tf_control[13]) $fatal(1,"accepted TF PANIC");
        control(90,127);if(tf_control[12] || !scope_status[8]) $fatal(1,"accepted live takeover");
        if(deadline!=0 || overflow!=0)$fatal(1,"deadline or FIFO overflow");
        $display("M workstation_max_cycles %0d",max_latency);
        $display("PASS scope_workstation real MIDI, allocator, join, exact dry stereo, live controls, panic");$finish;
    end
endmodule
