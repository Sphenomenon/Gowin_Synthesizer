`timescale 1ns/1ps
module tb_scope_dac_select;
    reg clk=0;always #5 clk=~clk;
    reg rst_n=0,tf_reset_n=0,scope=0,tf_active=0;
    reg [19:0] rate=48000;
    wire s_tick,s_bck,s_ws,s_din,s_pa,t_tick,t_bck,t_ws,t_din,t_pa;
    wire bck,ws,din,pa,selected,switching;
    wire [31:0] pair;wire valid;
    integer synth_pairs=0,tf_pairs=0,cycles=0,last_rising=-1000000,last_tick=-1;
    integer min_pulse=1000000,last_edge=0,handover_max=0;
    reg old_bck=0,old_s_bck=0,old_t_bck=0,check_pulse=0;
    pt8211_tx #(.BCK_HALF_CYCLES(25),.STEREO_ENABLE(1)) synth(
        .clk(clk),.reset_n(rst_n),.sample_data(32'sh1357_0000),.sample_right(32'sh2468_0000),.sample_valid(1'b1),
        .sample_tick(s_tick),.hp_bck(s_bck),.hp_ws(s_ws),.hp_din(s_din),.pa_en(s_pa),
        .underrun_count(),.frame_count(),.sample_revision(24'd0),.sample_nonzero_voices(32'd0),
        .trace_dac_done(),.trace_dac_revision(),.trace_dac_nonzero_voices(),
        .sample_trigger_reference(32'd0),.frame_trigger_reference());
    tf_rate_pt8211_tx #(.BCK_HALF_CYCLES(25),.STEREO_ENABLE(1),.RATE_MUL(916260)) tf(
        .clk(clk),.reset_n(tf_reset_n),.sample_data(32'sh4567_0000),.sample_right(32'sh789a_0000),.sample_valid(1'b1),
        .rate_hz(rate),.sample_tick(t_tick),.hp_bck(t_bck),.hp_ws(t_ws),.hp_din(t_din),.pa_en(t_pa),
        .underrun_count(),.frame_count(),.sample_revision(24'd0),.sample_nonzero_voices(32'd0),
        .trace_dac_done(),.trace_dac_revision(),.trace_dac_nonzero_voices(),
        .sample_trigger_reference(32'd0),.frame_trigger_reference());
    scope_dac_select dut(.clk_i(clk),.rst_ni(rst_n),.scope_enable_i(scope),.tf_source_active_i(tf_active),
        .synth_frame_tick_i(s_tick),.tf_frame_tick_i(t_tick),
        .synth_bck_i(s_bck),.synth_ws_i(s_ws),.synth_din_i(s_din),.synth_pa_i(s_pa),
        .tf_bck_i(t_bck),.tf_ws_i(t_ws),.tf_din_i(t_din),.tf_pa_i(t_pa),
        .hp_bck_o(bck),.hp_ws_o(ws),.hp_din_o(din),.pa_en_o(pa),.tf_selected_o(selected),.switching_o(switching));
    pt8211_observer observer(.clk(clk),.reset_n(rst_n),.bck(bck),.ws(ws),.din(din),.frame_reference(32'd0),
        .pcm_pair(pair),.sample_valid(valid),.trigger_reference());
    always @(negedge clk) begin
        cycles=cycles+1;
        if(rst_n) begin
            if(s_tick) begin
                if(last_tick>=0 && cycles-last_tick!=1600)$fatal(1,"synth scan frame changed");
                last_tick=cycles;
            end
            if(bck && !old_bck && !((selected && t_bck && !old_t_bck) || (!selected && s_bck && !old_s_bck)))
                $fatal(1,"mux created a BCK rising edge");
            if(check_pulse && bck!=old_bck) begin
                if(cycles-last_edge<12)$fatal(1,"short BCK pulse %0d",cycles-last_edge);
                if(cycles-last_edge<min_pulse)min_pulse=cycles-last_edge;
                last_edge=cycles;
            end else if(bck!=old_bck)last_edge=cycles;
            if(switching && !pa)$fatal(1,"handover amplifier was not shut down");
            if(valid && !pa && !switching) begin
                if(selected) begin
                    if(pair!=32'h4567_789a)$fatal(1,"TF stereo pair corrupt %h",pair);
                    tf_pairs=tf_pairs+1;
                end else begin
                    if(pair!=32'h1357_2468)$fatal(1,"scope stereo pair corrupt %h",pair);
                    synth_pairs=synth_pairs+1;
                end
            end
        end
        old_bck=bck;old_s_bck=s_bck;old_t_bck=t_bck;
    end
    task automatic wait_owner(input bit expected);
        integer n;
        begin
            n=0;
            while(selected!=expected || switching) begin
                @(negedge clk);n=n+1;
                if(n>40000)$fatal(1,"DAC owner did not settle");
            end
            if(n>handover_max)handover_max=n;
            repeat(40000)@(negedge clk);
        end
    endtask
    task automatic change_rate(input [19:0] value);
        begin
            scope=1;wait_owner(0);
            tf_reset_n=0;rate=value;repeat(13)@(negedge clk);tf_reset_n=1;
            // Keep the TF serializer running until its hardware warmup ends.
            repeat(530)@(posedge t_tick);
            repeat(73)@(negedge clk);scope=0;wait_owner(1);
            repeat(37)@(negedge clk);scope=1;wait_owner(0);
        end
    endtask
    initial begin
        #200000000;$fatal(1,"DAC selector timeout");
    end
    initial begin
        repeat(4)@(negedge clk);rst_n=1;
        repeat(13)@(negedge clk);tf_reset_n=1;
        repeat(530)@(posedge s_tick);@(negedge clk);check_pulse=1;
        tf_active=1;wait_owner(1);
        scope=1;wait_owner(0); // live mode also owns silent and idle frames
        scope=0;wait_owner(1);
        tf_active=0;wait_owner(0);
        tf_active=1;wait_owner(1);
        change_rate(44100);change_rate(96000);change_rate(8000);
        if(synth_pairs<20 || tf_pairs<20)$fatal(1,"insufficient decoded pairs");
        $display("M dac_synth_pairs %0d",synth_pairs);
        $display("M dac_tf_pairs %0d",tf_pairs);
        $display("M dac_min_bck_pulse_cycles %0d",min_pulse);
        $display("M dac_max_handover_cycles %0d",handover_max);
        $display("PASS scope_dac_select actual stereo serializers, asynchronous frame phases, 48k/44.1k/96k/8k, idle/mute priority, no mux rising edge");
        $finish;
    end
endmodule
