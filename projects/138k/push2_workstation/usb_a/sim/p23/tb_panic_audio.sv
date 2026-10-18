`timescale 1ns/1ps
module tb_panic_audio;
    reg clk=0,reset_n=0,event_valid=0,sample_ce=0;
    reg [17:0] event_data=0;
    wire event_ready,sample_valid;
    wire signed [31:0] left,right;
    wire [127:0] held;
    wire [31:0] active,applied,deadline,overflow,drops;
    wire [9:0] panic_epoch;
    integer divider=0,frames=0,post_panic_frames=0;
    reg checking_silence=0;
    always #(1000.0/153.6) clk=~clk;
    always @(posedge clk) begin
        sample_ce<=0;
        if(reset_n) begin
            if(divider==1599)begin divider<=0;sample_ce<=1;end else divider<=divider+1;
            if(sample_valid) begin
                frames<=frames+1;
                if(checking_silence) begin
                    post_panic_frames<=post_panic_frames+1;
                    if(left || right)$fatal(1,"nonzero PCM after PANIC left=%0d right=%0d",left,right);
                end
            end
        end
    end
    gw138k_event_workstation dut(
        .clk_i(clk),.rst_ni(reset_n),.midi_byte_valid_i(1'b0),.midi_byte_i(8'd0),
        .pc_byte_valid_i(1'b0),.pc_byte_i(8'd0),.held_notes_o(held),
        .applied_events_o(applied),.pc_overflow_o(),.control_options_o(),.panic_epoch_o(panic_epoch),
        .cpu_event_valid_i(event_valid),.cpu_event_i(event_data),.cpu_event_ready_o(event_ready),
        .sample_ce_i(sample_ce),.pcm_left_i(32'sd0),.pcm_right_i(32'sd0),
        .sample_valid_o(sample_valid),.left_o(left),.right_o(right),.synth_valid_o(),.synth_o(),
        .active_mask_o(active),.active_voice_count_o(),.mode_o(),.pitch_q20_o(),
        .deadline_miss_o(deadline),.midi_overflow_o(overflow),.note_drop_o(drops),.clip_o(),
        .synth_gain_o(),.pcm_gain_o(),.route_o(),.profile_o(),.effect_mask_o(),.effect_order_o());
    task send_event(input [3:0] kind,input [6:0] a,input [6:0] b);
        @(negedge clk);event_data={kind,a,b};event_valid=1;
        do @(posedge clk);while(!event_ready);
        @(negedge clk);event_valid=0;
    endtask
    task wait_frames(input integer count);
        integer target;begin target=frames+count;wait(frames>=target);@(negedge clk);end
    endtask
    initial begin
        #200;reset_n=1;repeat(8)@(posedge clk);
        // Mode A shortens each frame while retaining the real allocator,
        // serial effect chain and exact 48 kHz scheduler.
        send_event(2,80,0);wait(dut.mode_o==0);
        send_event(2,81,7);send_event(2,84,2);send_event(2,85,0);send_event(2,86,1);
        send_event(1,60,110);send_event(1,64,100);send_event(2,64,127);
        wait_frames(24);
        if(held[60]!==1 || held[64]!==1 || !active || !dut.sustain)$fatal(1,"setup state absent");
        if(dut.effects.delay_stage.frames==0 || dut.effects.chorus_stage.frames==0 ||
           dut.effects.reverb_stage.frames==0)$fatal(1,"effects were not exercised");
        // CC123 remains graceful All Notes Off: it must not create a PANIC
        // epoch or hard-reset active envelopes.
        send_event(2,123,0);repeat(8)@(posedge clk);
        if(panic_epoch!=0 || held!=0 || active==0)$fatal(1,"CC123 semantics changed");
        wait(!dut.releasing);wait_frames(260);
        // Start fresh voices and effect history, then demand hard PANIC.
        send_event(1,67,120);send_event(1,72,100);wait_frames(20);
        if(!active)$fatal(1,"second setup voice absent");
        send_event(2,120,0);repeat(4)@(posedge clk);
        if(panic_epoch!=1 || held!=0 || active!=0 || dut.allocated!=0 || dut.sustain ||
           dut.deferred!=0 || dut.releasing)$fatal(1,"audio state not atomically cleared");
        if(dut.effects.state!=0 || dut.effects.delay_stage.state!=0 ||
           dut.effects.chorus_stage.state!=0 || dut.effects.reverb_stage.state!=0 ||
           dut.effects.delay_stage.frames!=0 || dut.effects.chorus_stage.frames!=0 ||
           dut.effects.reverb_stage.frames!=0 || dut.effects.delay_stage.gain!=0 ||
           dut.effects.chorus_stage.gain!=0 || dut.effects.reverb_stage.gain!=0)
            $fatal(1,"effect state/tail not cleared");
        if(dut.effect_mask_o!=7 || dut.effect_order_o!=6'b01_00_10)
            $fatal(1,"PANIC changed effect selection/order");
        checking_silence=1;wait_frames(6);checking_silence=0;
        // A later real press starts normally and does not inherit muted state.
        send_event(1,76,100);wait_frames(8);
        if(!held[76] || !active || dut.panic_muted)$fatal(1,"post-PANIC note did not restart");
        send_event(2,120,0);repeat(4)@(posedge clk);
        if(panic_epoch!=2 || held || active || dut.allocated)$fatal(1,"second PANIC failed");
        if(deadline || overflow || drops)$fatal(1,"audio health fault");
        $display("PASS PANIC audio: CC123 graceful, CC120 epochs=%0d, voices/effects immediate zero, post-PANIC restart, 48k frames=%0d",panic_epoch,frames);
        $finish;
    end
    initial begin #200000000; $fatal(1,"timeout"); end
endmodule
