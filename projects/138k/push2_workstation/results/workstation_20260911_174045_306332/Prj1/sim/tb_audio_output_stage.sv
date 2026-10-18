`timescale 1ns/1ps
// External, integer arithmetic oracle: gain products use 80 bits, avoiding
// both RTL implementation slices and host/Verilog 64-bit overflow.
module tb_audio_output_stage;
    reg clk=0; always #10 clk=~clk;
    reg reset_n=0, frame_start=0, mix_valid=0, voice_sample_event=0;
    reg [31:0] master_target=32'h80000000, balance_target=32'h40000000;
    reg signed [39:0] mix_sum=0;
    reg [31:0] mix_reference=0;
    reg signed [31:0] voice_sample_data=0;
    reg [4:0] voice_sample_index=0;
    wire signed [31:0] sample_left, sample_right;
    wire sample_valid, trace_sample_event;
    wire [31:0] sample_reference, sample_nonzero_voices, trace_nonzero_voices;
    wire [23:0] trace_sample_revision;
    audio_output_stage dut(.*);

    reg signed [31:0] voices [0:31];
    reg [31:0] expected_master=32'h80000000, expected_balance=32'h40000000;
    reg [31:0] changed_master, changed_balance;
    integer frames=0, n;
    reg signed [31:0] previous_left;

    function [31:0] next_level(input [31:0] present,input [31:0] target);
        reg signed [32:0] difference;
        begin
            difference=$signed({1'b0,target})-$signed({1'b0,present});
            if(difference>33'sd8388608) next_level=present+32'd8388608;
            else if(difference < -33'sd8388608) next_level=present-32'd8388608;
            else next_level=target;
        end
    endfunction
    function signed [39:0] gain(input signed [39:0] value,input [31:0] level);
        reg signed [79:0] wide_value, wide_gain, multiplied;
        begin
            wide_value=value; wide_gain={1'b0,level};
            multiplied=wide_value*wide_gain;
            gain=multiplied >>> 31;
        end
    endfunction
    function signed [31:0] clip(input signed [39:0] value);
        begin
            if(value > 40'sd2147483647) clip=32'sh7fffffff;
            else if(value < -40'sd2147483648) clip=32'sh80000000;
            else clip=value;
        end
    endfunction
    task clear_voices;
        integer v;
        begin for(v=0;v<32;v=v+1) voices[v]=0; end
    endtask

    task frame(input signed [39:0] raw,input [31:0] reference,input change_midframe);
        integer v, cycle_number;
        reg [31:0] left_gain, right_gain, expected_mask;
        reg signed [39:0] mastered, contribution;
        reg signed [31:0] expected_left, expected_right, held_left, held_right;
        reg [31:0] held_reference, held_mask;
        begin
            if(sample_valid || trace_sample_event) $fatal(1,"old valid/trace persisted between frames");
            expected_master=next_level(expected_master,master_target);
            expected_balance=next_level(expected_balance,balance_target);
            left_gain=32'h80000000; right_gain=32'h80000000;
            if(expected_balance>32'h40000000) left_gain=(32'h80000000-expected_balance)*2;
            if(expected_balance<32'h40000000) right_gain=expected_balance*2;
            mastered=gain(raw,expected_master);
            expected_left=clip(gain(mastered,left_gain));
            expected_right=clip(gain(mastered,right_gain));
            expected_mask=0;
            for(v=0;v<32;v=v+1) begin
                contribution=gain(voices[v],expected_master);
                expected_mask[v]=contribution>=40'sd32768 || contribution<=-40'sd32768;
            end
            held_left=sample_left; held_right=sample_right;
            held_reference=sample_reference; held_mask=sample_nonzero_voices;
            @(negedge clk); frame_start=1;
            @(negedge clk); frame_start=0;
            repeat(5) @(negedge clk);
            for(v=0;v<32;v=v+1) begin
                voice_sample_event=1; voice_sample_data=voices[v]; voice_sample_index=v;
                @(negedge clk); voice_sample_event=0;
                // A changed slider target must not alter this frame's
                // established mix or per-voice diagnostic gain.
                if(change_midframe && v==15) begin
                    master_target=changed_master; balance_target=changed_balance;
                end
                repeat(6) @(negedge clk);
                if(sample_valid || trace_sample_event || sample_left!==held_left || sample_right!==held_right ||
                   sample_reference!==held_reference || sample_nonzero_voices!==held_mask)
                    $fatal(1,"frame %0d output changed during voice scan",frames);
            end
            mix_sum=raw; mix_reference=reference; mix_valid=1;
            @(negedge clk); mix_valid=0;
            // The output stage must have captured raw sum and metadata.
            mix_sum=40'sh5432109876; mix_reference=~reference;
            for(cycle_number=1;cycle_number<=8;cycle_number=cycle_number+1) begin
                @(negedge clk);
                if(sample_valid !== (cycle_number==7))
                    $fatal(1,"frame %0d output latency/valid mismatch at %0d",frames,cycle_number);
                if(trace_sample_event !== (cycle_number==6))
                    $fatal(1,"frame %0d pre-commit trace latency mismatch at %0d",frames,cycle_number);
                if(cycle_number<7 && (sample_left!==held_left || sample_right!==held_right ||
                   sample_reference!==held_reference || sample_nonzero_voices!==held_mask))
                    $fatal(1,"frame %0d public outputs changed before atomic commit",frames);
                if(trace_sample_event && (trace_sample_revision!==reference[31:8] || trace_nonzero_voices!==expected_mask))
                    $fatal(1,"frame %0d trace revision/nonzero mismatch",frames);
                if(sample_valid) begin
                    if(sample_left!==expected_left || sample_right!==expected_right)
                        $fatal(1,"frame %0d L/R got %0d/%0d expected %0d/%0d raw=%0d gain=%h balance=%h",
                            frames,sample_left,sample_right,expected_left,expected_right,raw,expected_master,expected_balance);
                    if(sample_reference!==reference || sample_nonzero_voices!==expected_mask)
                        $fatal(1,"frame %0d metadata/mask got %h/%h expected %h/%h",
                            frames,sample_reference,sample_nonzero_voices,reference,expected_mask);
                end
            end
            frames=frames+1;
        end
    endtask

    task reset_stage;
        begin
            @(negedge clk); reset_n=0; frame_start=0; mix_valid=0; voice_sample_event=0;
            repeat(3) @(negedge clk);
            if(sample_left!==0 || sample_right!==0 || sample_valid || trace_sample_event ||
               sample_reference!==0 || sample_nonzero_voices!==0)
                $fatal(1,"reset left stale output or metadata");
            reset_n=1; expected_master=32'h80000000; expected_balance=32'h40000000;
            master_target=32'h80000000; balance_target=32'h40000000;
        end
    endtask

    initial begin
        clear_voices; reset_stage;
        voices[0]=32'sh7fffffff;
        frame(40'sd2147483647,32'h12345607,0);
        if(sample_left!==32'sh7fffffff || sample_right!==32'sh7fffffff)
            $fatal(1,"single full-scale voice lost level");
        for(n=0;n<32;n=n+1) voices[n]=32'sh7fffffff;
        frame(40'sd68719476704,32'h12345705,0);
        master_target=32'h04000000;
        repeat(248) frame(40'sd68719476704,32'h12345800,0);
        if(sample_left!==32'sh7fffffff || sample_right!==32'sh7fffffff)
            $fatal(1,"wide32-voice sum clipped before master1/32");
        for(n=0;n<32;n=n+1) voices[n]=32'sh80000000;
        frame(-40'sd68719476736,32'h123459ff,0);
        if(sample_left!==32'sh80000000 || sample_right!==32'sh80000000)
            $fatal(1,"negative32-voice sum overflowed before master");

        clear_voices; voices[0]=-32'sd1073741827;
        master_target=32'h40000000;
        repeat(120) frame(-40'sd1073741827,32'h23456002,0);
        if(sample_left!==-32'sd536870914) $fatal(1,"negative half-gain floor changed");
        clear_voices; voices[0]=65535; voices[1]=65536; voices[2]=-65535; voices[3]=-65534;
        frame(40'sd2,32'h23456102,0);
        if(sample_nonzero_voices!==32'h00000006 || sample_left!==1)
            $fatal(1,"post-master PCM16 threshold ignored signed floor");
        clear_voices; voices[0]=-32'sd1073741827;
        master_target=32'h20000000;
        repeat(64) frame(-40'sd1073741827,32'h34567001,0);
        if(sample_left!==-32'sd268435457) $fatal(1,"negative quarter-gain floor changed");
        master_target=0;
        repeat(64) frame(-40'sd1073741827,32'h34567100,0);
        if(sample_left!==0 || sample_right!==0 || sample_nonzero_voices!==0)
            $fatal(1,"mute did not zero final samples and diagnostic mask");
        frame(-40'sd1073741827,32'h345672ff,0);

        clear_voices; voices[0]=32'sh40000000;
        master_target=32'h80000000; previous_left=sample_left;
        repeat(256) begin
            frame(40'sd1073741824,32'h45678003,0);
            if(sample_left-previous_left!==32'sd4194304)
                $fatal(1,"unmute slew was not exactly fullrange/256 per frame");
            previous_left=sample_left;
        end
        if(sample_left!==32'sh40000000 || sample_right!==32'sh40000000)
            $fatal(1,"center balance lost unity gain");
        balance_target=0;
        repeat(128) frame(40'sd1073741824,32'h56789004,0);
        if(sample_left!==32'sh40000000 || sample_right!==0) $fatal(1,"hard-left balance failed");
        balance_target=32'h80000000;
        repeat(256) frame(40'sd1073741824,32'h56789104,0);
        if(sample_left!==0 || sample_right!==32'sh40000000) $fatal(1,"hard-right balance failed");
        balance_target=32'h60000000;
        repeat(64) frame(40'sd1073741824,32'h56789204,0);
        if(sample_left!==32'sh20000000 || sample_right!==32'sh40000000) $fatal(1,"intermediate right balance failed");
        balance_target=32'h20000000;
        repeat(128) frame(40'sd1073741824,32'h56789304,0);
        if(sample_left!==32'sh40000000 || sample_right!==32'sh20000000) $fatal(1,"intermediate left balance failed");

        // Retarget halfway through the 32-event stream. This frame remains
        // constant; only the next frame may take one master/balance step.
        clear_voices; voices[0]=32'sh20000000; voices[16]=32'sh20000000;
        changed_master=0; changed_balance=32'h80000000;
        frame(40'sd1073741824,32'h67890100,1);
        if(sample_left!==32'sh40000000 || sample_right!==32'sh20000000)
            $fatal(1,"midframe slider change reached current frame");
        frame(40'sd1073741824,32'h67890200,0);

        // Reset while a raw mix is in flight; no stale valid/tag may escape.
        @(negedge clk); mix_sum=40'sd1073741824; mix_reference=32'habcd1234; mix_valid=1;
        @(negedge clk); mix_valid=0;
        repeat(3) @(negedge clk);
        reset_stage;
        clear_voices; voices[31]=32'sh40000000;
        frame(40'sd1073741824,32'h789012ff,0);
        if(sample_nonzero_voices!==32'h80000000) $fatal(1,"warm reset retained voice mask or lost voice31");
        $display("PASS tb_audio_output_stage: %0d independent80-bit oracle frames; fullscale solo, wide32-voice gain before saturation, signed half/quarter, mute/unmute slew, center/L/R/intermediate balance, frame-latched targets, post-master masks, atomic7-clock outputs/trace/reference and reset",frames);
        $finish;
    end
    initial begin #20000000; $fatal(1,"audio output stage test timeout"); end
endmodule
