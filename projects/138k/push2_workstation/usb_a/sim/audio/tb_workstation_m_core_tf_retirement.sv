`timescale 1ns/1ps
module tb_workstation_m_core_tf_retirement;
    reg clk=0,compute_clk=0,rst_n=0,commit=0,lifecycle=0;
    reg [3:0] kind=2;
    reg [6:0] address=0,value=0;
    wire [31:0] disabled_tf,enabled_tf;
    wire disabled_rejected,enabled_rejected;
    always #10 clk=!clk;
    always #6.5 compute_clk=!compute_clk;
    workstation_parameters #(.TF_CONTROL_ENABLE(0)) disabled(
        .clk_i(clk),.rst_ni(rst_n),.commit_i(commit),.lifecycle_i(lifecycle),.mode_applied_i(1'b0),
        .kind_i(kind),.address_i(address),.value_i(value),.mode_i(2'd2),
        .legacy_active_i(32'd0),.vector_active_i(8'd0),.cue_running_i(1'b0),
        .tf_control_o(disabled_tf),.rejected_o(disabled_rejected));
    workstation_parameters enabled(
        .clk_i(clk),.rst_ni(rst_n),.commit_i(commit),.lifecycle_i(lifecycle),.mode_applied_i(1'b0),
        .kind_i(kind),.address_i(address),.value_i(value),.mode_i(2'd2),
        .legacy_active_i(32'd0),.vector_active_i(8'd0),.cue_running_i(1'b0),
        .tf_control_o(enabled_tf),.rejected_o(enabled_rejected));
    wire [383:0] state_disabled={disabled.requested_mode_o,disabled.mode_pending_o,
        disabled.volume_o,disabled.expression_gain_o,disabled.pcm_gain_o,disabled.synth_gain_o,
        disabled.route_o,disabled.profile_o,disabled.effect_selected_o,disabled.effect_master_o,
        disabled.effect_count_o,disabled.effect_mask_o,disabled.effect_order_o,disabled.target_ratio_o,
        disabled.glide_step_o,disabled.vibrato_depth_o,disabled.glide_cc_o,disabled.bend_index_o,
        disabled.sustain_o,disabled.options_o,disabled.scope_enable_o,disabled.scope_muted_o,
        disabled.scope_morph_shape_o,disabled.scope_shape_o,disabled.scope_morph_o,disabled.scope_scale_o,
        disabled.scope_rotation_o,disabled.scope_cal_x_o,disabled.scope_cal_y_o,
        disabled.scope_offset_x_o,disabled.scope_offset_y_o,disabled.cue_speed_o};
    wire [383:0] state_enabled={enabled.requested_mode_o,enabled.mode_pending_o,
        enabled.volume_o,enabled.expression_gain_o,enabled.pcm_gain_o,enabled.synth_gain_o,
        enabled.route_o,enabled.profile_o,enabled.effect_selected_o,enabled.effect_master_o,
        enabled.effect_count_o,enabled.effect_mask_o,enabled.effect_order_o,enabled.target_ratio_o,
        enabled.glide_step_o,enabled.vibrato_depth_o,enabled.glide_cc_o,enabled.bend_index_o,
        enabled.sustain_o,enabled.options_o,enabled.scope_enable_o,enabled.scope_muted_o,
        enabled.scope_morph_shape_o,enabled.scope_shape_o,enabled.scope_morph_o,enabled.scope_scale_o,
        enabled.scope_rotation_o,enabled.scope_cal_x_o,enabled.scope_cal_y_o,
        enabled.scope_offset_x_o,enabled.scope_offset_y_o,enabled.cue_speed_o};
    integer common_checks=0,retired_checks=0;
    task clocks(input integer n);repeat(n)@(negedge clk);endtask
    task cc(input [6:0] a,b);begin address=a;value=b;commit=1;clocks(1);commit=0;clocks(1);end endtask
    reg [383:0] preserved;
    reg stop_request=0,quiet=0;
    wire local_request,local_hold,tf_request,stop_ready,stop_done,stop_failed;
    reg local_done=0;
    integer local_delay=0,local_calls=0;
    workstation_runtime_media_stop_bridge #(.ENABLE(1),.TF_ENABLE(0)) no_tf_stop(
        .reset_ni(rst_n),.control_reset_ni(rst_n),.compute_reset_ni(rst_n),
        .clk_50m_i(clk),.compute_clk_i(compute_clk),.owner_reset_ni(rst_n),
        .request_i(stop_request),.hold_i(1'b0),.local_request_o(local_request),.local_hold_o(local_hold),
        .local_done_i(local_done),.local_failed_i(1'b0),.tf_stop_request_o(tf_request),
        // An absent backend cannot accidentally complete this transaction.
        .tf_stop_pending_i(1'b1),.tf_stop_done_i(1'b0),.tf_stop_failed_i(1'b1),
        .tf_stop_failure_code_i(4'hf),.media_quiet_i(quiet),
        .ready_o(stop_ready),.done_o(stop_done),.failed_o(stop_failed),.failure_code_o());
    always @(negedge compute_clk)begin
        local_done=0;
        if(!rst_n)local_delay=0;
        else if(local_request)begin local_delay=5;local_calls++;end
        else if(local_delay!=0)begin
            local_delay--;
            if(local_delay==0)local_done=1;
        end
    end
    always @(negedge clk)if(rst_n)begin
        if(disabled_tf!==0)$fatal(1,"disabled TF state became active");
        if(tf_request)$fatal(1,"stop requested an absent TF owner");
        if(stop_failed)$fatal(1,"absent TF failure leaked into stop");
    end
    initial begin
        clocks(4);rst_n=1;clocks(4);
        // Full value sweeps compare existing ordinary/vector/FX state against
        // the default enabled implementation before any deferred TF request.
        for(integer c=0;c<128;c++)if(c!=104 && c!=105 && c!=106 && c!=108)
        for(integer v=0;v<128;v++)begin
            cc(7'(c),7'(v));
            if(state_disabled!==state_enabled || disabled_rejected!==enabled_rejected)
                $fatal(1,"TF retirement changed common parameter behavior cc=%0d value=%0d",c,v);
            common_checks++;
        end
        cc(90,127);cc(81,7);
        if(!disabled.scope_enable_o || disabled.effect_mask_o!=7)$fatal(1,"fixture did not establish vector/effects");
        preserved=state_disabled;
        for(integer c=104;c<=108;c++)if(c!=107)for(integer v=0;v<128;v++)begin
            address=7'(c);value=7'(v);commit=1;#1;
            if(disabled_rejected!==(c!=104 || v!=0))$fatal(1,"deferred TF request falsely accepted cc=%0d value=%0d",c,v);
            clocks(1);commit=0;clocks(1);
            if(state_disabled!==preserved)$fatal(1,"deferred TF changed instrument state cc=%0d value=%0d",c,v);
            retired_checks++;
        end
        cc(104,127);
        if(!enabled_tf[12])$fatal(1,"legacy TF path was not exercised");
        // Completion waits for the real local stop and quiet condition, while
        // TF's permanently pending/failing dummy input is explicitly ignored.
        if(!stop_ready)$fatal(1,"waited for absent TF before start");
        stop_request=1;clocks(1);stop_request=0;clocks(40);
        if(local_calls!=1 || stop_done || !local_hold)$fatal(1,"local stop/quiet boundary lost");
        quiet=1;
        begin integer waited=0;while(!stop_done)begin clocks(1);waited++;if(waited>10)$fatal(1,"waited for absent TF after local stop");end end
        $display("PASS m_core_tf_retirement common_checks=%0d retired_checks=%0d local_stops=%0d",common_checks,retired_checks,local_calls);
        $finish;
    end
    initial begin #1000000;$fatal(1,"test watchdog");end
endmodule
