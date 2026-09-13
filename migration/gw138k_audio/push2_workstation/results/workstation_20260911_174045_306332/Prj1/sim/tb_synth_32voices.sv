`timescale 1ns/1ps
// Full default engine with the real 48,828.125-Hz DAC request cadence.
// The model tracks envelope boundaries independently of the RTL state RAM;
// a serial receiver checks both physical PT8211 slots against PCM16 audio.
module tb_synth_32voices;
    reg clk=0; always #10 clk=~clk;
    reg rst_n=0, cmd_valid=0, cmd_first=0, cmd_last=0, rsp_ready=0;
    reg [31:0] cmd_data=0;
    wire cmd_ready, rsp_valid, sample_valid, sample_tick;
    wire signed [31:0] sample_data;
    wire signed [39:0] mix_sum;
    wire [31:0] rsp_data, active_voices, trigger_reference;
    wire [7:0] memory_flags=8'hc3;
    wire [127:0] video_diagnostics=0;
    wire hp_bck, hp_ws, hp_din, pa_en;
    wire [31:0] underrun_count, frame_count;
    synth_engine dut(.onset_query_request(),.onset_query_voice(),
        .onset_query_done(1'b0),.onset_query_data(256'd0),.latency_diagnostics(512'd0),.trace_commit(),.trace_header(),.trace_revision(),
        .trace_frame_start(),.trace_sample_event(),.trace_sample_revision(),.trace_nonzero_voices(),
        .sample_nonzero_voices(),.voice_sample_event(),.voice_sample_data(),.voice_sample_index(),
        .master_volume(),.lr_balance(),.*);
    pt8211_tx #(.BCK_HALF_CYCLES(16)) dac(
        .clk(clk),.reset_n(rst_n),.sample_data(sample_data),.sample_valid(sample_valid),
        .sample_tick(sample_tick),.hp_bck(hp_bck),.hp_ws(hp_ws),.hp_din(hp_din),
        .pa_en(pa_en),.underrun_count(underrun_count),.frame_count(frame_count));

    integer cycle=0, ticks=0, last_tick_cycle=0, accepted_cycle=0;
    integer accepted_frames=0, checked_frames=0, a;
    reg awaiting_frame=0, previous_valid=0;
    reg [31:0] model_mask=0, model_envelope=0, old_mask=0;
    reg [31:0] model_snapshot=0;
    integer model_stage [0:31]; // 0 idle, 1 attack, 2 sustain, 3 release
    reg [31:0] old_envelope;
    integer old_stage;
    reg signed [39:0] expected_sum;
    reg signed [31:0] expected_sample;
    reg transaction_inflight=0;
    reg [7:0] inflight_opcode=0, inflight_voice=0, inflight_status=0;
    reg [31:0] inflight_value=0;
    reg startup_deferred=0;

    always @(posedge clk) begin
        if(!rst_n) begin
            cycle=0; ticks=0; last_tick_cycle=0; awaiting_frame=0; previous_valid=0;
            accepted_frames=0; checked_frames=0; model_mask=0; model_envelope=0; model_snapshot=0;
            for(a=0;a<32;a=a+1) model_stage[a]=0;
        end else begin
            cycle=cycle+1;
            if(dut.frame_accept) begin
                if(awaiting_frame) $fatal(1,"overlapping engine frames");
                awaiting_frame=1; accepted_cycle=cycle; accepted_frames=accepted_frames+1;
                if(accepted_frames == 1) begin
                    if(ticks != 1 || cycle <= 32 || !dut.sample_request)
                        $fatal(1,"startup sample request was not retained through 32-cycle initialization");
                    startup_deferred=1;
                end
                old_mask=model_mask; old_envelope=model_envelope;
                expected_sum=0;
                for(a=0;a<32;a=a+1)
                    if(model_envelope[a]) expected_sum=expected_sum+40'sd2147483647;
                if(expected_sum > 40'sd2147483647) expected_sample=32'sh7fffffff;
                else if(expected_sum < -40'sd2147483648) expected_sample=32'sh80000000;
                else expected_sample=expected_sum[31:0];
                // Opcode 0D byte zero freezes the mask at frame acceptance.
                if(dut.command_pending) begin
                    if(!transaction_inflight) $fatal(1,"unexpected command reached frame boundary");
                    if(dut.command_apply !== (inflight_status == 0))
                        $fatal(1,"command validation/apply mismatch op=%h",inflight_opcode);
                    if(inflight_status == 0 && inflight_opcode == 8'h0d && inflight_value == 0)
                        model_snapshot=old_mask;
                end
                for(a=0;a<32;a=a+1) begin
                    old_stage=model_stage[a];
                    case(old_stage)
                        0: model_envelope[a]=0;
                        1: begin model_envelope[a]=1; model_stage[a]=2; end
                        2: model_envelope[a]=1;
                        3: begin model_envelope[a]=0; model_stage[a]=0; end
                    endcase
                    if(dut.command_pending && inflight_status == 0) begin
                        if(inflight_opcode == 8'h0a) begin model_envelope[a]=0; model_stage[a]=0; end
                        else if(inflight_voice == a) begin
                            if(inflight_opcode == 1) begin
                                model_stage[a]=1;
                                model_envelope[a]=(old_stage != 0 && old_envelope[a]);
                            end
                            if(inflight_opcode == 2 && old_stage != 0) model_stage[a]=3;
                        end
                    end
                    model_mask[a]=model_stage[a] != 0;
                end
            end
            #1;
            if(sample_tick) begin
                ticks=ticks+1;
                if(ticks == 1) begin
                    if(cycle != 16 || dut.bank_ready) $fatal(1,"first DAC request should arrive at cycle 16 during RAM initialization");
                end else if(cycle-last_tick_cycle != 1024) $fatal(1,"DAC sample period is not 1024 clocks");
                last_tick_cycle=cycle;
            end
            if(underrun_count !== 0) $fatal(1,"real DAC underrun at frame %0d",frame_count);
            if(awaiting_frame && cycle-accepted_cycle < 225 && active_voices !== old_mask)
                $fatal(1,"active mask changed before complete bank commit");
            if(awaiting_frame && cycle-accepted_cycle > 226) $fatal(1,"missed 226-clock engine deadline");
            if(sample_valid) begin
                if(mix_sum !== expected_sum) $fatal(1,"full-width raw voice sum mismatch: got %h expected %h",mix_sum,expected_sum);
                if(previous_valid || !awaiting_frame || cycle-accepted_cycle != 226)
                    $fatal(1,"sample_valid count/latency mismatch, age %0d",cycle-accepted_cycle);
                if(cycle-last_tick_cycle >= 1024) $fatal(1,"sample missed its physical DAC frame");
                if(sample_data !== expected_sample || active_voices !== model_mask)
                    $fatal(1,"frame %0d audio/mask mismatch: got %h/%h expected %h/%h",checked_frames,sample_data,active_voices,expected_sample,model_mask);
                awaiting_frame=0; checked_frames=checked_frames+1;
            end
            previous_valid=sample_valid;
        end
    end

    function [15:0] reference_pcm16(input signed [31:0] value);
        reg signed [63:0] widened;
        begin
            widened=value;
            widened=(widened+(value < 0 ? 64'sd32767 : 64'sd32768)) >>> 16;
            if(widened>32767) reference_pcm16=16'h7fff;
            else if(widened < -32768) reference_pcm16=16'h8000;
            else reference_pcm16=widened[15:0];
        end
    endfunction
    reg [15:0] pending_pcm=0, decoded_word, expected_word;
    integer serial_frames=0, fullscale_serial_frames=0, zero_serial_frames=0, bit_number;
    always @(posedge clk) begin
        if(!rst_n) pending_pcm<=0;
        else if(sample_valid) pending_pcm<=reference_pcm16(sample_data);
    end
    initial begin
        wait(rst_n);
        forever begin
            @(negedge hp_ws);
            expected_word=pending_pcm;
            for(bit_number=15;bit_number>=0;bit_number=bit_number-1) begin
                @(posedge hp_bck); #1;
                if(hp_ws !== 0) $fatal(1,"PT8211 right slot framing changed");
                decoded_word[bit_number]=hp_din;
            end
            if(decoded_word !== expected_word) $fatal(1,"right PCM mismatch %h expected %h",decoded_word,expected_word);
            for(bit_number=15;bit_number>=0;bit_number=bit_number-1) begin
                @(posedge hp_bck); #1;
                if(hp_ws !== 1) $fatal(1,"PT8211 left slot framing changed");
                decoded_word[bit_number]=hp_din;
            end
            if(decoded_word !== expected_word) $fatal(1,"left PCM mismatch %h expected %h",decoded_word,expected_word);
            serial_frames=serial_frames+1;
            if(expected_word == 16'h7fff) fullscale_serial_frames=fullscale_serial_frames+1;
            if(expected_word == 0) zero_serial_frames=zero_serial_frames+1;
        end
    end

    integer sequence_id=0, replies=0;
    task send_word(input [31:0] value,input first,input last);
        begin
            @(negedge clk);
            while(!cmd_ready) @(negedge clk);
            cmd_data=value; cmd_first=first; cmd_last=last; cmd_valid=1;
            @(negedge clk); cmd_valid=0; cmd_first=0; cmd_last=0;
        end
    endtask
    task command(input [7:0] op,input [7:0] voice_id,input [31:0] value,
                 input [7:0] flags,input [7:0] status,input integer hold_cycles);
        integer waited, h;
        reg [31:0] frozen_reply;
        reg [7:0] expected_payload;
        begin
            inflight_opcode=op; inflight_voice=voice_id; inflight_value=value; inflight_status=status;
            transaction_inflight=1;
            send_word({sequence_id[7:0],op,voice_id,flags},1,0);
            send_word(value,0,1);
            waited=0;
            while(!rsp_valid) begin
                @(negedge clk); waited=waited+1;
                if(waited>1300) $fatal(1,"control response timeout op=%h",op);
            end
            if(!sample_valid || awaiting_frame) $fatal(1,"ACK was not aligned to completed audio frame");
            if(op == 8'h0d) expected_payload=status == 0 ? model_snapshot[value[1:0]*8 +: 8] : 0;
            else if(op == 8'h0b) expected_payload=memory_flags;
            else expected_payload=model_mask[7:0];
            if(rsp_data !== {sequence_id[7:0],status,expected_payload,op})
                $fatal(1,"ACK mismatch got %h expected %h",rsp_data,{sequence_id[7:0],status,expected_payload,op});
            frozen_reply=rsp_data;
            for(h=0;h<hold_cycles;h=h+1) begin
                @(negedge clk);
                if(!rsp_valid || rsp_data !== frozen_reply || cmd_ready)
                    $fatal(1,"response/backpressure did not remain stable");
            end
            rsp_ready=1; @(negedge clk); rsp_ready=0;
            if(rsp_valid) $fatal(1,"response handshake did not clear valid");
            transaction_inflight=0; sequence_id=sequence_id+1; replies=replies+1;
        end
    endtask

    task wait_frames(input integer count);
        integer goal;
        begin
            goal=checked_frames+count;
            while(checked_frames<goal) @(negedge clk);
        end
    endtask
    integer n;
    reg [31:0] sparse_mask;
    initial begin
        repeat(3) @(negedge clk); rst_n=1;
        wait_frames(2);
        if(!startup_deferred) $fatal(1,"startup deferral was not tested");
        command(8'h0d,255,1,0,3,3); // cannot read a snapshot before byte zero
        command(8'h0d,255,4,0,3,3);
        command(8'h0d,31,0,0,2,3);
        command(8'h0d,255,0,1,3,3);
        command(8'h01,32,0,0,2,3);
        command(8'hfe,255,0,0,1,3); // Reject an opcode outside the supported controls.
        for(n=0;n<32;n=n+1) begin
            command(6,n,0,0,0,3); command(7,n,0,0,0,3);
            command(8,n,32'h80000000,0,0,3); command(9,n,0,0,0,3);
            command(4,n,32'h80000000,0,0,3); command(5,n,1,0,0,3);
            command(1,n,0,0,0,3); // phase zero gives constant positive pulse
        end
        wait_frames(8);
        if(active_voices !== 32'hffffffff || sample_data !== 32'h7fffffff)
            $fatal(1,"32 full-scale voices did not saturate to positive full scale");
        if(fullscale_serial_frames<4) $fatal(1,"insufficient full-scale serial DAC verification");
        command(8'h0d,255,0,0,0,3);
        // The snapshot survives both sound changes and an ACK held across a
        // complete physical audio frame; its later bytes must still be FF.
        command(8'h0a,255,0,0,0,1100);
        if(active_voices !== 0) $fatal(1,"PANIC did not clear high voice bits");
        command(8'h0d,255,1,0,0,3); command(8'h0d,255,2,0,0,3); command(8'h0d,255,3,0,0,3);
        if(model_snapshot !== 32'hffffffff) $fatal(1,"snapshot was changed by PANIC");

        // Distinct byte boundaries exercise every byte of the host mask.
        sparse_mask=32'h81818181;
        for(n=0;n<32;n=n+1) if(sparse_mask[n]) command(1,n,0,0,0,3);
        wait_frames(3);
        if(active_voices !== sparse_mask) $fatal(1,"0/7/8/15/16/23/24/31 routing failed");
        command(8'h0d,255,0,0,0,3);
        if(model_snapshot !== sparse_mask) $fatal(1,"new snapshot did not replace previous FF mask");
        command(2,31,0,0,0,3); wait_frames(2);
        if(active_voices !== 32'h01818181) $fatal(1,"NOTE_OFF for voice 31 failed");
        command(2,8,0,0,0,3); wait_frames(2);
        if(active_voices !== 32'h01818081) $fatal(1,"NOTE_OFF crossed voice byte boundary");
        command(8'h0d,255,1,0,0,3); command(8'h0d,255,2,0,0,3); command(8'h0d,255,3,0,0,3);
        if(model_snapshot !== sparse_mask) $fatal(1,"voice releases changed the retained snapshot");
        command(8'h0a,255,0,0,0,3);
        wait_frames(4);
        command(8'h0d,255,0,0,0,3);
        command(8'h0d,255,1,0,0,3); command(8'h0d,255,2,0,0,3); command(8'h0d,255,3,0,0,3);
        if(model_snapshot !== 0 || active_voices !== 0 || sample_data !== 0 || underrun_count !== 0)
            $fatal(1,"final silence/snapshot/underrun check failed");
        if(serial_frames<250 || zero_serial_frames<2 || checked_frames != accepted_frames)
            $fatal(1,"insufficient completed integration coverage");
        $display("PASS tb_synth_32voices: %0d responses, %0d exact 226-clock frames, %0d decoded stereo PCM frames, startup tick retained, full 32-voice mix/masks, atomic 0D snapshot, backpressure, zero DAC underruns",replies,checked_frames,serial_frames);
        $finish;
    end
    initial begin #20000000; $fatal(1,"32-voice integration test timeout"); end
endmodule
