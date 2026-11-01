`timescale 1ns/1ps
// Push admission and terminal media policy use the maintained service/core.
// Backend stop completion is a same-domain protocol fixture, not a TF test.
module tb_push_rate_media;
    reg clk=0,rn=1,pulse=0,media_active=1,stop_ready=1,stop_done=0,stop_failed=0,permit=1;
    reg [31:0] tag=0;reg [3:0] stop_code=0;
    wire ready,reject_pulse,request,target,recover,core_ready,core_busy,core_fault;
    wire accepted,applied,rejected,failed,active_rate,active_valid,stop_request,stop_hold;
    wire [31:0] generation,epoch;wire [2:0] reject_code;wire [3:0] fault_code;
    always #10 clk=~clk;
    workstation_sample_rate_switch #(.TIMEOUT_CYCLES(128),.RESERVE_ZERO_EPOCH(1),.INITIAL_STREAM_EPOCH(1)) core(
        .clk_i(clk),.rst_ni(rn),.request_i(request),.request_44k1_i(target),.recover_i(recover),
        .source_qualified_i(2'b11),.frame_quiescent_i(1'b1),.selected_clock_stopped_low_i(1'b1),
        .selected_clock_qualified_i(1'b1),.prefill_ready_i(1'b1),.output_running_i(1'b1),
        .request_ready_o(core_ready),.busy_o(core_busy),.fault_o(core_fault),.accepted_o(accepted),.applied_o(applied),
        .rejected_o(rejected),.failed_o(failed),.reject_code_o(reject_code),.fault_code_o(fault_code),
        .quiesce_o(),.dac_mute_o(),.stream_flush_o(),.audio_reset_no(),.clock_monitor_restart_o(),.clock_select_o(),
        .active_44k1_o(active_rate),.active_valid_o(active_valid),.stream_epoch_o(epoch),.staged_44k1_o(),.staged_epoch_o());
    workstation_audio_clock_service #(.ENABLE_PUSH_RATE_CONTROL(1),.ENABLE_MEDIA_POLICY(1),
        .MEDIA_TIMEOUT_CYCLES(32),.ACCEPT_TIMEOUT_CYCLES(16),.RESULT_TIMEOUT_CYCLES(256),.RESERVE_ZERO_EPOCH(1)) service(
        .clk_i(clk),.reset_ni(rn),.command_valid_i(1'b0),.command_write_i(1'b0),.command_address_i(12'd0),
        .command_data_i(32'd0),.command_strobes_i(4'd0),.command_ready_o(),.response_data_o(),.response_error_o(),
        .push_toggle_i(pulse),.push_generation_i(tag),.push_ready_o(ready),.push_generation_o(generation),
        .push_rejected_o(reject_pulse),.service_busy_o(),.service_fault_o(),.switch_permit_i(permit),
        .core_request_ready_i(core_ready && !media_active),.core_busy_i(core_busy),.core_fault_i(core_fault),
        .core_dsp_fault_i(1'b0),.core_accepted_i(accepted),.core_applied_i(applied),.core_rejected_i(rejected),
        .core_policy_rejected_i(1'b0),.core_failed_i(failed),.core_reject_code_i(reject_code),.core_fault_code_i(fault_code),
        .core_active_44k1_i(active_rate),.core_active_valid_i(active_valid),.core_stream_epoch_i(epoch),
        .core_source_qualified_i(2'b11),.request_o(request),.request_44k1_o(target),.recover_o(recover),
        .media_stop_request_o(stop_request),.media_stop_hold_o(stop_hold),.media_stop_ready_i(stop_ready),
        .media_stop_done_i(stop_done),.media_stop_failed_i(stop_failed),.media_stop_failure_code_i(stop_code));
    integer requests=0,stops=0,rejects=0,applies=0,checks=0;reg ack_seen=0;
    always @(posedge clk)if(rn)begin
        if(stop_request)begin stops++;ack_seen=0;end
        if(stop_done)ack_seen=1;
        if(request)begin
            if(media_active || !ack_seen)$fatal(1,"Push core request preceded media terminal");
            requests++;
        end
        if(reject_pulse)rejects++;
        if(applied)applies++;
        if(recover)$fatal(1,"Push manufactured recovery");
    end
    task tick(input integer n);repeat(n)@(negedge clk);endtask
    task wait_ready;
        integer n;begin n=0;while(!ready)begin tick(1);n++;if(n>300)$fatal(1,"media service not ready");end end
    endtask
    task press;
        begin @(negedge clk);tag=generation;pulse=1;@(negedge clk);pulse=0;tick(2);end
    endtask
    task begin_media;
        begin media_active=1;wait_ready();press();tick(3);
            if(!stop_hold || !service.media_pending)$fatal(1,"Push omitted media preparation");end
    endtask
    integer q0,s0,r0;reg[31:0]g0;
    initial begin
        #1;rn=0;tick(5);rn=1;wait_ready();q0=requests;s0=stops;
        begin_media();g0=generation;tick(5);
        if(requests!=q0 || stops!=s0+1 || ready)$fatal(1,"media pending issued core request");
        r0=rejects;press();if(rejects!=r0+1 || generation!=g0)$fatal(1,"media busy accepted or regenerated");
        media_active=0;stop_done=1;tick(1);stop_done=0;wait_ready();tick(3);
        if(requests!=q0+1 || applies!=1 || !active_rate || service.result_code!=1 || stop_hold)
            $fatal(1,"Push media completion did not apply requested rate");checks++;
        // A stop provider that cannot admit rejects without manufacturing work.
        stop_ready=0;tick(3);r0=rejects;s0=stops;press();
        if(ready || rejects!=r0+1 || requests!=q0+1 || stops!=s0)$fatal(1,"Push bypassed media readiness");
        stop_ready=1;wait_ready();checks++;
        // Failure and timeout release hold but never reach the rate core.
        begin_media();stop_code=7;stop_failed=1;tick(1);stop_failed=0;wait_ready();
        if(service.result_code!=8 || service.media_failure_code!=7 || stop_hold || requests!=q0+1)
            $fatal(1,"Push media failure lost terminal policy");checks++;
        begin_media();tick(40);wait_ready();
        if(service.result_code!=9 || stop_hold || requests!=q0+1)$fatal(1,"Push media timeout issued core request");checks++;
        // Admission is checked again after actual stop, before the core pulse.
        begin_media();permit=0;media_active=0;stop_done=1;tick(1);stop_done=0;tick(3);
        if(service.result_code!=10 || stop_hold || requests!=q0+1)$fatal(1,"Push bypassed post-media gate");
        permit=1;wait_ready();checks++;
        $display("PASS push_rate_media checks=%0d requests=%0d applies=%0d stops=%0d rejects=%0d",checks,requests,applies,stops,rejects);
        $finish;
    end
    initial begin #1000000;$fatal(1,"media test timeout");end
endmodule
