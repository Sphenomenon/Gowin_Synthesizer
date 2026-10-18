`timescale 1ns/1ps
module tb_pt8211_stereo;
    reg clk=0; always #10 clk=~clk;
    reg reset_n=0, sample_valid=0;
    reg signed [31:0] sample_data=0, sample_right=0;
    reg [23:0] sample_revision=0;
    reg [31:0] sample_nonzero_voices=0, sample_trigger_reference=0;
    wire sample_tick,hp_bck,hp_ws,hp_din,pa_en,trace_dac_done;
    wire [31:0] underrun_count,frame_count,trace_dac_nonzero_voices,frame_trigger_reference;
    wire [23:0] trace_dac_revision;
    pt8211_tx #(.BCK_HALF_CYCLES(2),.STEREO_ENABLE(1)) dut(.*);

    // Independent absolute-magnitude division, including ties away from
    // zero. This deliberately does not reuse the RTL's bias-and-shift.
    function [15:0] pcm16(input signed [31:0] value);
        reg signed [63:0] magnitude, quantized;
        begin
            magnitude=value;
            if(magnitude<0) magnitude=-magnitude;
            quantized=(magnitude+32768)/65536;
            if(value<0) quantized=-quantized;
            if(quantized>32767) quantized=32767;
            if(quantized< -32768) quantized=-32768;
            pcm16=quantized;
        end
    endfunction

    reg pending=0, expected_valid=0;
    reg [31:0] pending_pair=0, expected_pair=0, expected_reference=0;
    reg [23:0] pending_revision=0, expected_revision=0;
    reg [31:0] pending_mask=0, expected_mask=0, pending_reference=0;
    reg [31:0] pin_shift=0, last_pair=0, last_reference=0, last_mask=0;
    reg [23:0] last_revision=0;
    reg last_valid=0, completed_trace=0;
    integer bit_count=0, launched=0, decoded=0, expected_underruns=0;
    integer trace_events=0, valid_zero_frames=0, invalid_zero_frames=0;
    integer same_edge_overrides=0, overwritten_pending=0;
    integer n;

    // Model only the public sample acceptance/boundary contract. All PCM
    // assertions below reconstruct the actual BCK/WS/DIN pins.
    always @(posedge clk) begin
        if(!reset_n) begin
            pending=0; expected_valid=0; expected_pair=0; expected_revision=0;
            expected_mask=0; expected_reference=0; launched=0; expected_underruns=0;
            completed_trace=0;
        end else begin
            if(trace_dac_done) begin
                if(!expected_valid || bit_count!=31 || hp_bck!==0 || hp_ws!==1 ||
                   trace_dac_revision!==expected_revision || trace_dac_nonzero_voices!==expected_mask)
                    $fatal(1,"DAC trace was not aligned to final left-slot capture and its stereo pair");
                trace_events=trace_events+1; completed_trace=1;
            end
            #1;
            if(sample_tick) begin
                completed_trace=0;
                if(sample_valid) begin
                    if(pending) same_edge_overrides=same_edge_overrides+1;
                    expected_pair={pcm16(sample_data),pcm16(sample_right)};
                    expected_revision=sample_revision; expected_mask=sample_nonzero_voices;
                    expected_reference=sample_trigger_reference; expected_valid=1;
                end else if(pending) begin
                    expected_pair=pending_pair; expected_revision=pending_revision;
                    expected_mask=pending_mask; expected_reference=pending_reference; expected_valid=1;
                end else begin
                    expected_pair=0; expected_revision=0; expected_mask=0;
                    expected_reference=0; expected_valid=0;
                    if(launched!=0) expected_underruns=expected_underruns+1;
                end
                pending=0; launched=launched+1;
                if(frame_count!==launched || underrun_count!==expected_underruns ||
                   frame_trigger_reference!==expected_reference)
                    $fatal(1,"frame launch counter/underrun/trigger tag mismatch");
            end else if(sample_valid) begin
                if(pending) overwritten_pending=overwritten_pending+1;
                pending_pair={pcm16(sample_data),pcm16(sample_right)};
                pending_revision=sample_revision; pending_mask=sample_nonzero_voices;
                pending_reference=sample_trigger_reference; pending=1;
            end
        end
    end

    always @(negedge reset_n) begin
        bit_count=0; pin_shift=0; decoded=0;
        last_pair=0; last_reference=0; last_mask=0; last_revision=0; last_valid=0;
    end
    always @(posedge hp_bck) if(reset_n) begin
        #2;
        if(hp_ws !== (bit_count>=16)) $fatal(1,"WS polarity/16-bit slot length changed");
        if(frame_trigger_reference!==expected_reference)
            $fatal(1,"reference tag changed within the serialized pair");
        if(hp_din !== (bit_count<16 ? expected_pair[15-bit_count] : expected_pair[47-bit_count]))
            $fatal(1,"frame %0d bit %0d differs from RIGHT-then-LEFT MSB-first expected pair %h",decoded,bit_count,expected_pair);
        pin_shift={pin_shift[30:0],hp_din};
        if(bit_count==31) begin
            last_pair={pin_shift[15:0],pin_shift[31:16]};
            if(last_pair!==expected_pair || completed_trace!==expected_valid)
                $fatal(1,"physical stereo pair or valid DAC completion tag mismatch");
            last_revision=expected_revision; last_mask=expected_mask;
            last_reference=expected_reference; last_valid=expected_valid;
            if(last_pair==0) begin
                if(last_valid) valid_zero_frames=valid_zero_frames+1;
                else invalid_zero_frames=invalid_zero_frames+1;
            end
            decoded=decoded+1;
        end
        bit_count=(bit_count+1)%32;
    end
    always @(hp_ws or hp_din) if(reset_n && hp_bck===1)
        $fatal(1,"DIN/WS changed while BCK was high");

    task set_pair(input signed [31:0] left_value,input signed [31:0] right_value,
                  input [23:0] revision,input [31:0] mask,input [31:0] reference);
        begin
            sample_data=left_value; sample_right=right_value;
            sample_revision=revision; sample_nonzero_voices=mask; sample_trigger_reference=reference;
        end
    endtask
    task send_pending(input signed [31:0] left_value,input signed [31:0] right_value,
                      input [23:0] revision,input [31:0] mask,input [31:0] reference);
        begin
            @(negedge clk); set_pair(left_value,right_value,revision,mask,reference); sample_valid=1;
            @(negedge clk); sample_valid=0;
            set_pair(32'sh76543210,32'sh89abcdef,24'hffffff,32'hffffffff,32'hfedcba98);
        end
    endtask
    task finish_frame(input integer count);
        begin wait(decoded==count); @(negedge clk); end
    endtask

    initial begin
        repeat(4) @(negedge clk); reset_n=1;
        @(posedge sample_tick); repeat(8) @(negedge clk);
        send_pending(32'sh12345678,-32'sh23456789,24'h102030,32'h80000001,32'h10203007);
        finish_frame(1);
        if(last_pair!==0 || last_valid || underrun_count!==0) $fatal(1,"startup frame should be untagged silence");

        @(posedge sample_tick); repeat(8) @(negedge clk);
        send_pending(-32'sh34567890,32'sh45678901,24'h203040,32'h00000004,32'h20304005);
        repeat(8) @(negedge clk);
        send_pending(32'sh11110000,-32'sh22220000,24'h304050,32'h00000008,32'h30405009);
        // Both replacements occur while the current distinct L/R pair is
        // still being transmitted; neither slot may tear to a new sample.
        finish_frame(2);
        if(last_pair!=={pcm16(32'sh12345678),pcm16(-32'sh23456789)} ||
           last_revision!==24'h102030 || last_mask!==32'h80000001 || last_reference!==32'h10203007)
            $fatal(1,"midframe input change tore the current stereo pair or its tags");
        // With half-period2, the next falling BCK boundary is two system
        // edges after the last rising capture. Assert valid only for that
        // boundary edge, overriding an already pending, different pair.
        @(negedge clk);
        set_pair(32'sh7fffffff,32'sh80000000,24'h405060,32'h40000002,32'h4050600b); sample_valid=1;
        @(posedge clk); #2;
        if(!sample_tick) $fatal(1,"same-edge fixture missed physical frame launch");
        @(negedge clk); sample_valid=0;
        set_pair(0,0,0,0,0);
        finish_frame(3);
        if(last_pair!==32'h7fff8000 || last_revision!==24'h405060 ||
           last_mask!==32'h40000002 || last_reference!==32'h4050600b || !last_valid)
            $fatal(1,"same-edge arrival did not override complete pending pair and tags");

        @(posedge sample_tick); repeat(8) @(negedge clk);
        send_pending(32767,-32767,24'h506070,0,32'h50607000);
        finish_frame(4);
        if(last_pair!==0 || last_valid || last_revision!==0 || last_mask!==0 || last_reference!==0)
            $fatal(1,"underrun did not produce two zero channels and invalid tags");
        finish_frame(5);
        if(last_pair!==0 || !last_valid || last_revision!==24'h506070 || last_reference!==32'h50607000)
            $fatal(1,"valid rounded-zero pair lost its DAC event/reference");

        for(n=0;n<8;n=n+1) begin
            @(posedge sample_tick); repeat(8) @(negedge clk);
            case(n)
                0: send_pending(32768,-32768,24'h600000+n,1<<n,32'h60000001+n*256);
                1: send_pending(32'sh7fff8000,32'sh80008000,24'h600000+n,1<<n,32'h60000001+n*256);
                2: send_pending(32'sh00018000,32'shfffe8000,24'h600000+n,1<<n,32'h60000001+n*256);
                3: send_pending(32'sh00008001,32'shffff7fff,24'h600000+n,1<<n,32'h60000001+n*256);
                4: send_pending(32'sh00007fff,32'shffff8001,24'h600000+n,1<<n,32'h60000001+n*256);
                5: send_pending(32'sh80000000,32'sh7fffffff,24'h600000+n,1<<n,32'h60000001+n*256);
                6: send_pending(-32'sh12345678,32'sh12345678,24'h600000+n,1<<n,32'h60000001+n*256);
                7: send_pending(-1,1,24'h600000+n,1<<n,32'h60000001+n*256);
            endcase
        end
        finish_frame(14);
        if(same_edge_overrides!=1 || overwritten_pending!=1 || trace_events!=11 ||
           valid_zero_frames<3 || invalid_zero_frames<3)
            $fatal(1,"missing stereo overwrite/rounding/zero trace coverage: same=%0d overwrite=%0d events=%0d validzero=%0d invalidzero=%0d",
                same_edge_overrides,overwritten_pending,trace_events,valid_zero_frames,invalid_zero_frames);
        // Reset while one pair is queued and another is partly serialized.
        @(posedge sample_tick); repeat(8) @(negedge clk);
        send_pending(32'sh7fffffff,-32'sh70000000,24'habcd12,32'hffffffff,32'habcd1203);
        repeat(8) @(negedge clk); reset_n=0; sample_valid=0;
        repeat(3) @(negedge clk);
        if(frame_count!==0 || underrun_count!==0 || trace_dac_done || frame_trigger_reference!==0 || !pa_en)
            $fatal(1,"reset retained count/tag or enabled amplifier");
        reset_n=1;
        finish_frame(1);
        if(last_pair!==0 || last_valid || last_reference!==0) $fatal(1,"warm reset replayed pending stereo audio");
        @(posedge sample_tick); repeat(8) @(negedge clk);
        send_pending(32'sh22220000,-32'sh33330000,24'h789abc,32'h80000000,32'h789abcff);
        finish_frame(3);
        if(last_pair!==32'h2222cccd || last_revision!==24'h789abc || last_mask!==32'h80000000)
            $fatal(1,"stereo stream did not recover after warm reset");
        $display("PASS tb_pt8211_stereo: independent RIGHT/LEFT pin decoder, opposite-sign stereo pairs, nearest ties-away rounding/saturation, atomic pending and same-edge override, valid-zero vs underrun tags, %0d DAC events, reset/recovery",trace_events);
        $finish;
    end
    initial begin #1000000; $fatal(1,"PT8211 stereo test timeout"); end
endmodule
