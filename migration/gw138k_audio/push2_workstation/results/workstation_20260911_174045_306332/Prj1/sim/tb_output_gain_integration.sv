`timescale 1ns/1ps
module tb_output_gain_integration;
    reg clk=0,rst=0; always #10 clk=~clk;
    reg [31:0] cmd_data=0;reg cmd_valid=0,cmd_first=0,cmd_last=0;
    wire cmd_ready,rsp_valid; wire [31:0] rsp_data;
    wire tick,mix_valid,frame_start,voice_event,final_valid,trace_event,bck,ws,din,pa;
    wire signed [31:0] legacy_sample,voice_sample,left_sample,right_sample;
    wire signed [39:0] mix_sum;
    wire [4:0] voice_index;
    wire [31:0] master,balance,mix_ref,final_ref,final_mask,trace_mask,frame_ref;
    wire [23:0] trace_revision;
    wire [31:0] active,underruns,frames,observed,observed_ref;
    wire observed_valid;
    synth_engine engine(.clk(clk),.rst_n(rst),.sample_tick(tick),.cmd_data(cmd_data),.cmd_valid(cmd_valid),
        .cmd_ready(cmd_ready),.cmd_first(cmd_first),.cmd_last(cmd_last),.rsp_data(rsp_data),.rsp_valid(rsp_valid),.rsp_ready(1'b1),
        .sample_data(legacy_sample),.sample_valid(mix_valid),.active_voices(active),.trigger_reference(mix_ref),
        .memory_flags(8'd0),.video_diagnostics(128'd0),.latency_diagnostics(512'd0),
        .onset_query_request(),.onset_query_voice(),.onset_query_done(1'b0),.onset_query_data(256'd0),
        .trace_commit(),.trace_header(),.trace_revision(),.trace_frame_start(frame_start),.trace_sample_event(),
        .trace_sample_revision(),.trace_nonzero_voices(),.sample_nonzero_voices(),
        .mix_sum(mix_sum),.voice_sample_event(voice_event),.voice_sample_data(voice_sample),.voice_sample_index(voice_index),
        .master_volume(master),.lr_balance(balance));
    audio_output_stage stage(.clk(clk),.reset_n(rst),.frame_start(frame_start),.master_target(master),.balance_target(balance),
        .mix_sum(mix_sum),.mix_valid(mix_valid),.mix_reference(mix_ref),.voice_sample_event(voice_event),
        .voice_sample_data(voice_sample),.voice_sample_index(voice_index),.sample_left(left_sample),.sample_right(right_sample),
        .sample_valid(final_valid),.sample_reference(final_ref),.sample_nonzero_voices(final_mask),
        .trace_sample_event(trace_event),.trace_sample_revision(trace_revision),.trace_nonzero_voices(trace_mask));
    pt8211_tx #(.STEREO_ENABLE(1)) tx(.clk(clk),.reset_n(rst),.sample_data(left_sample),.sample_right(right_sample),
        .sample_valid(final_valid),.sample_tick(tick),.hp_bck(bck),.hp_ws(ws),.hp_din(din),.pa_en(pa),
        .underrun_count(underruns),.frame_count(frames),.sample_revision(final_ref[31:8]),.sample_nonzero_voices(final_mask),
        .sample_trigger_reference(final_ref),.frame_trigger_reference(frame_ref),
        .trace_dac_done(),.trace_dac_revision(),.trace_dac_nonzero_voices());
    pt8211_observer observer(.clk(clk),.reset_n(rst),.bck(bck),.ws(ws),.din(din),.frame_reference(frame_ref),
        .pcm_pair(observed),.sample_valid(observed_valid),.trigger_reference(observed_ref));
    integer ticks=0,cycle=0,last_tick=0,start_cycle=0,checked=0,bit_count=0,observations=0;
    reg [15:0] serial_shift=0,serial_right=0;
    reg [31:0] serial_pair=0,pending_pair=0,frame_expected=0,pending_ref=0,expected_ref=0;
    reg pending=0;
    function [15:0] pcm16;
        input signed [31:0] value;
        reg signed [63:0] rounded;
        begin
            // Independent division/magnitude oracle, ties away from zero.
            rounded=value<0 ? -((-64'sd1*value+32768)/65536) : (64'sd1*value+32768)/65536;
            if(rounded>32767) pcm16=16'h7fff;
            else if(rounded< -32768) pcm16=16'h8000;
            else pcm16=rounded[15:0];
        end
    endfunction
    always @(posedge clk) if(rst) begin
        cycle=cycle+1;
        if(frame_start) start_cycle=cycle;
        if(trace_event && cycle-start_cycle!=234) $fatal(1,"postgain compute latency %0d",cycle-start_cycle);
    end
    always @(negedge clk) if(rst) begin
        if(tick) begin
            if(ticks!=0 && cycle-last_tick!=1024) $fatal(1,"audio cadence changed");
            ticks=ticks+1;last_tick=cycle;
            frame_expected=pending ? pending_pair : 0;expected_ref=pending ? pending_ref : 0;pending=0;
        end
        if(final_valid) begin pending_pair={pcm16(left_sample),pcm16(right_sample)};pending_ref=final_ref;pending=1;end
        if(observed_valid) begin
            if(observed!==serial_pair || observed_ref!==expected_ref) $fatal(1,"final display observer mismatch");
            observations=observations+1;
        end
    end
    always @(posedge bck) if(rst) begin
        if(ws !== (bit_count>=16)) $fatal(1,"PT8211 channel order");
        serial_shift={serial_shift[14:0],din};
        if(bit_count==15) serial_right=serial_shift;
        if(bit_count==31) begin
            serial_pair={serial_shift,serial_right};checked=checked+1;
            if(serial_pair!==frame_expected) $fatal(1,"PCM pair tore/swapped: %h expected %h",serial_pair,frame_expected);
            bit_count=0;
        end else bit_count=bit_count+1;
    end
    task send_word(input [31:0] data,input first,last);
        begin
            @(negedge clk);cmd_data=data;cmd_first=first;cmd_last=last;cmd_valid=1;
            @(posedge clk);while(!cmd_ready)@(posedge clk);
            @(negedge clk);cmd_valid=0;cmd_first=0;cmd_last=0;
        end
    endtask
    task command(input [7:0] op,voice,input [31:0] value,input [7:0] status);
        begin
            send_word({8'h42,op,voice,8'd0},1,0);
            send_word(value,0,1);
            wait(rsp_valid);@(negedge clk);
            if(rsp_data[23:16]!==status || rsp_data[7:0]!==op) $fatal(1,"global/voice command rejected %h => %h",op,rsp_data);
        end
    endtask
    task wait_frames(input integer count);
        integer goal;
        begin goal=observations+count;while(observations<goal)@(negedge clk);end
    endtask
    task stable_pair(input [31:0] expected,input [31:0] mask);
        integer i;
        begin
            wait_frames(260);
            for(i=0;i<4;i=i+1) begin
                wait_frames(1);
                if(observed!==expected || final_mask!==mask) $fatal(1,"gain/balance output %h mask %h expected %h/%h",observed,final_mask,expected,mask);
            end
        end
    endtask
    integer v;
    initial begin
        repeat(4)@(negedge clk);rst=1;
        for(v=0;v<2;v=v+1) begin
            command(5,v,1,0);command(4,v,32'h80000000,0);
            command(6,v,0,0);command(7,v,0,0);command(8,v,32'h80000000,0);
        end
        command(1,0,0,0);wait_frames(4);
        if(observed!==32'h7fff7fff) $fatal(1,"single voice still divided by32: %h",observed);
        command(1,1,0,0);wait_frames(4);
        if(mix_sum!==40'sd4294967294 || observed!==32'h7fff7fff) $fatal(1,"wide sum/saturation wrong");
        command(8'h10,255,32'h20000000,0);
        stable_pair(32'h40004000,3); // Two full voices * 1/4, not clipped first.
        command(8'h11,255,0,0);stable_pair(32'h40000000,3);
        command(8'h11,255,32'h80000000,0);stable_pair(32'h00004000,3);
        command(8'h11,255,32'h60000000,0);stable_pair(32'h20004000,3);
        command(8'h10,255,0,0);stable_pair(0,0);
        command(8'h10,0,32'h80000000,2);command(8'h11,0,0,2);
        command(8'h10,255,32'h80000001,3);command(8'h11,255,32'hffffffff,3);
        if(master!==0 || balance!==32'h60000000) $fatal(1,"invalid global command changed state");
        command(8'h11,255,32'h40000000,0);command(8'h10,255,32'h20000000,0);
        stable_pair(32'h40004000,3);
        command(8'h0a,255,0,0);wait_frames(5);
        if(observed!==0 || active!==0 || underruns!==0 || checked<1500 || observations<1500)
            $fatal(1,"panic/continuity/coverage failed");
        $display("PASS output gain integration: fullscale solo, unscaled40-bit mix before master, true serial L/R/center/intermediate/mute, invalid globals, postgain234-clock events, observer/tag alignment, panic and zero underruns over %0d stereo frames",checked);
        $finish;
    end
    initial begin #45000000;$fatal(1,"output integration timeout ticks=%0d obs=%0d decoded=%0d cmd=%h ready=%b rsp=%b pending=%b header=%h",ticks,observations,checked,cmd_data,cmd_ready,rsp_valid,engine.command_pending,engine.command_header);end
endmodule
