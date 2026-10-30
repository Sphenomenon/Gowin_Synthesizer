`timescale 1ns/1ps

// Digital source-bit skew counterexample, not a routed/PVT or metastability model.
// Exercise the real transaction owner and serializer. Force only models the
// observable bit propagation of the legal PREFILL(7) -> RESUME(9) transition.
module tb_workstation_rate_control_levels;
    parameter integer RATE44=0;
    localparam real SELECTED_PERIOD=RATE44 ? 59.051398 : 81.380208;
    reg control_clk=0,selected_clk=0,rst_n=0,serial_rst_n=0;
    always #10 control_clk=~control_clk;
    always #(SELECTED_PERIOD/2.0) selected_clk=~selected_clk;
    real last_selected_edge=0,until_selected=0;
    always @(posedge selected_clk) last_selected_edge=$realtime;
    wire quiesce,dac_mute,stream_flush,prefill,output_running;
    reg allow_prefill=0;
    reg [1:0] prefill_sync=0,running_sync=0;
    always @(posedge control_clk or negedge rst_n)
        if(!rst_n)begin prefill_sync<=0;running_sync<=0;end
        else begin prefill_sync<={prefill_sync[0],prefill};running_sync<={running_sync[0],output_running};end
    workstation_sample_rate_switch #(.TIMEOUT_CYCLES(2000000),.DEFAULT_44K1(RATE44)) transaction(
        .clk_i(control_clk),.rst_ni(rst_n),.request_i(1'b0),.request_44k1_i(1'b0),.recover_i(1'b0),
        .source_qualified_i(2'b11),.frame_quiescent_i(1'b1),
        .selected_clock_stopped_low_i(1'b1),.selected_clock_qualified_i(1'b1),
        .prefill_ready_i(prefill_sync[1] && allow_prefill),.output_running_i(running_sync[1]),
        .request_ready_o(),.busy_o(),.fault_o(),.accepted_o(),.applied_o(),.rejected_o(),.failed_o(),
        .reject_code_o(),.fault_code_o(),.quiesce_o(quiesce),.dac_mute_o(dac_mute),
        .stream_flush_o(stream_flush),.audio_reset_no(),.clock_monitor_restart_o(),
        .clock_select_o(),.active_44k1_o(),.active_valid_o(),.stream_epoch_o(),.staged_44k1_o(),.staged_epoch_o());
    reg [1:0] quiesce_sync=0,resume_sync=0;
    always @(posedge selected_clk or negedge rst_n)
        if(!rst_n)begin quiesce_sync<=0;resume_sync<=0;end
        else begin quiesce_sync<={quiesce_sync[0],quiesce};resume_sync<={resume_sync[0],!dac_mute};end
    wire request;
    wire [31:0] request_sequence;
    reg sample_valid=0;
    reg [31:0] sample_sequence=0;
    integer request_count=0;
    always @(posedge selected_clk)begin
        sample_valid<=0;
        if(serial_rst_n && request)begin
            request_count<=request_count+1;
            sample_sequence<=request_sequence;
            sample_valid<=1;
        end
    end
    workstation_i2s_serializer #(.PDN_HOLD_FRAMES(4),.STARTUP_MUTE_FRAMES(1028),.SAMPLE_ERROR_ENABLE(1)) serializer(
        .clk_i(selected_clk),.rst_ni(serial_rst_n),.rate_44k1_i(RATE44!=0),.epoch_i(32'd1),
        .quiesce_i(quiesce_sync[1]),.resume_i(resume_sync[1]),.serial_quiescent_o(),
        .output_running_o(output_running),.prefill_ready_o(prefill),
        .request_o(request),.request_sequence_o(request_sequence),.request_44k1_o(),.request_epoch_o(),
        .sample_valid_i(sample_valid),.sample_ready_o(),.sample_44k1_i(RATE44!=0),.sample_error_i(1'b0),
        .sample_epoch_i(32'd1),.sample_sequence_i(sample_sequence),.sample_pcm_i(32'h12345678),
        .mclk_o(),.bck_o(),.lrck_o(),.data_o(),.pdn_no(),.smute_o(),
        .frame_valid_o(),.frame_error_o(),.frame_pcm_o(),.frame_sequence_o(),.frame_44k1_o(),.frame_epoch_o(),
        .underrun_count_o(),.rejected_sample_count_o(),.source_error_count_o());

    reg armed=0;
    reg [3:0] injected_state=7;
    integer wrong_target=0,pulses=0,sampled_quiesce_cycles=0,unexpected_empty_cycles=0;
    always @(quiesce or dac_mute or stream_flush)begin
        if(armed)begin
            #0.001;
            if({quiesce,dac_mute,stream_flush}!==3'b000)pulses=pulses+1;
        end
    end
    always @(posedge selected_clk)begin
        if(armed)begin
            if(quiesce_sync[1])sampled_quiesce_cycles=sampled_quiesce_cycles+1;
            #0.001;
            if(!serializer.have_next)unexpected_empty_cycles=unexpected_empty_cycles+1;
        end
    end
    initial begin
        #100;rst_n=1;
        // As in the runtime owner, keep the serializer reset until the source
        // has entered PREFILL and the selected control synchronizers settle.
        wait(transaction.state==7);
        repeat(4)@(posedge selected_clk);
        @(negedge selected_clk);serial_rst_n=1;
        wait(prefill_sync[1] && serializer.have_next && transaction.state==7);
        // Select a legal relative clock phase, with the next selected edge
        // inside the explicit 1..3 ns decode hazard window. Stay far from the
        // next frame boundary so a disappearing prefill cannot be consumption.
        begin:choose_phase
            forever begin
                @(negedge control_clk);
                until_selected=SELECTED_PERIOD-($realtime-last_selected_edge)-10.0;
                if(until_selected>1.2 && until_selected<2.8 &&
                   serializer.bit_position>=4 && serializer.bit_position<=40)disable choose_phase;
            end
        end
        allow_prefill=1;
        injected_state=7;
        force transaction.state=injected_state;
        @(posedge control_clk);
        // The real owner takes PREFILL -> RESUME on this edge. Its registered
        // outputs must already describe target 9, even before state Qs settle.
        #0.001;
        armed=1;
        if({quiesce,dac_mute,stream_flush}!==3'b000)wrong_target=wrong_target+1;
        #0.999;injected_state=5;
        #2.000;injected_state=1;
        #2.000;injected_state=9;
        #0.100;release transaction.state;
        repeat(6)@(posedge selected_clk);
        #1;
        $display("rate-control levels: wrong_target=%0d pulses=%0d sampled_quiesce_cycles=%0d unexpected_empty_cycles=%0d request_count=%0d",wrong_target,pulses,sampled_quiesce_cycles,unexpected_empty_cycles,request_count);
        if(wrong_target || pulses || sampled_quiesce_cycles || unexpected_empty_cycles || request_count!=1)
            $fatal(1,"FAIL rate-control CDC levels: target-edge publication or prefill preservation");
        $display("PASS rate-control CDC levels: real owner/serializer, target-edge outputs, digital state skew");
        $finish;
    end
    initial begin #30000000;$fatal(1,"rate-control CDC levels timeout");end
endmodule
