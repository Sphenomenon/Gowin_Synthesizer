`timescale 1ns/1ps
module tb_cpu_release;
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
        .synth_gain_o(),.pcm_gain_o(),.route_o(),.profile_o(),.effect_mask_o(),.effect_order_o(),
        .delay_mem_clk_i(clk),.delay_mem_rst_ni(reset_n),.delay_dwr_valid_o(),.delay_dwr_data_o(),
        .delay_dwr_pop_i(1'b0),.delay_drd_push_i(1'b0),.delay_drd_data_i(65'd0),.delay_drd_ready_o());
    task send_event(input [3:0] kind,input [6:0] a,input [6:0] b);
        @(negedge clk);event_data={kind,a,b};event_valid=1;
        do @(posedge clk);while(!event_ready);
        @(negedge clk);event_valid=0;
    endtask
    task wait_frames(input integer count);
        integer target;begin target=frames+count;wait(frames>=target);@(negedge clk);end
    endtask
    integer begin_frame,release_samples,case_index;
    initial begin
        #200;reset_n=1;repeat(8)@(posedge clk);
        send_event(2,80,0);wait(dut.mode_o==0);
        for(case_index=0;case_index<3;case_index=case_index+1)begin
            // Firmware preset73/all effects, note60/velocity100, CC123 after256 frames.
            send_event(3,case_index==0 ? 73 : 0,0);
            send_event(2,81,case_index==0 ? 7 : 0);send_event(4,0,64);
            send_event(1,60,100);
            if(case_index==2)begin send_event(1,64,90);send_event(2,64,127);end
            wait_frames(256);
            if(!active || !held[60] || (left==0 && right==0))$fatal(1,"CPU fixture failed to sound");
            begin_frame=frames;send_event(2,123,0);
            while(active && frames-begin_frame<48000)@(posedge clk);
            release_samples=frames-begin_frame;
            if(active || held || dut.deferred || dut.releasing || dut.sustain || panic_epoch)
                $fatal(1,"CC123 did not release CPU notes case%0d frames%0d active%h",case_index,release_samples,active);
            if(deadline || overflow || drops)$fatal(1,"CPU release health fault");
            $display("PASS CPU all-notes-off case%0d release_frames=%0d frames=%0d",case_index,release_samples,frames);
            wait_frames(8);
        end
        $display("PASS CPU release firmware preset73/all-effects, dry and sustained two-note release at48k");
        $finish;
    end
    initial begin #3500000000;$fatal(1,"CPU release timeout");end
endmodule
