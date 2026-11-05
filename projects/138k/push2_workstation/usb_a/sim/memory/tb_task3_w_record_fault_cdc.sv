`timescale 1ns/1ps
// Actual paired media/arbiter/raw store; the recording object/HCI engine is
// outside this focused test. Source binding is checked separately on the full
// preprocessed board. No model boot, inference or physical CDC is claimed.
module tb_task3_w_record_fault_cdc;
    reg raw_clk=0,raw_mclk=0,control_run=1,native_run=1;
    wire clk=raw_clk && control_run,mclk=raw_mclk && native_run;
    reg reset_n=0,calibrated=0,allow_native=1,inject=0;
    always #10 raw_clk=~raw_clk;
    always #7 raw_mclk=~raw_mclk;
    wire media_ready,control_ready,media_fault,raw_channel_fault,raw_fault;
    wire raw_start_ready,raw_start_done,raw_capture_ready,raw_drained;
    reg raw_start=0,arm=0,frame_valid=0;
    reg [31:0] sequence_i=0;
    wire pcm_valid,source_allowed,source_fault,armed;
    wire [31:0] pcm,pcm_sequence;
    wire [3:0] source_failure,raw_failure;
    wire [31:0] accepted,committed;
    // Same local boundary checked in workstation_task3_w_paired_board.svh.
    wire control_fault=!control_ready || raw_channel_fault;
    workstation_task3_record_ingress ingress(
        .clk_i(clk),.reset_ni(reset_n),.link_ready_i(1'b1),.panic_i(1'b0),
        .transport_fault_i(control_fault),.object_idle_i(raw_start_ready),
        .cancel_valid_i(1'b0),.cancel_session_i(32'd0),.cancel_generation_i(32'd0),
        .arm_valid_i(arm),.arm_ready_o(),.arm_session_i(32'd1),.arm_generation_i(32'd1),
        .arm_physical_epoch_i(32'd1),.arm_first_sequence_i(32'd0),.arm_format_i(8'd1),
        .arm_accepted_o(),.arm_rejected_o(),.frame_valid_i(frame_valid),.frame_ready_o(),
        .frame_session_i(32'd1),.frame_generation_i(32'd1),.frame_physical_epoch_i(32'd1),
        .frame_sequence_i(sequence_i),.frame_pcm_i(32'h71420000+sequence_i),
        .frame_44k1_i(1'b0),.frame_error_i(1'b0),.pcm_valid_o(pcm_valid),
        .source_allowed_o(source_allowed),.pcm_pair_o(pcm),.pcm_sequence_o(pcm_sequence),
        .physical_sequence_o(),.session_o(),.generation_o(),.physical_epoch_o(),
        .armed_o(armed),.fault_o(source_fault),.failure_code_o(source_failure),
        .queued_frames_o(),.accepted_frames_o(),.delivered_frames_o());
    wire [2:0] cmd;
    wire en,wren;
    wire [28:0] address;
    wire [255:0] wdata;
    wire [31:0] mask;
    wire [8:0] native_accept;
    reg response=0,pending=0;
    reg [255:0] rdata=0;
    reg [255:0] bist_memory[0:3];
    reg [1:0] read_slot=0;
    wire ready=calibrated && allow_native && !pending && !response;
    workstation_task3_w_paired #(.BIST_BURSTS(4)) dut(
        .clk_i(clk),.reset_ni(reset_n),.memory_clk_i(mclk),.memory_reset_ni(reset_n),
        .memory_calibrated_i(calibrated),.memory_pll_locked_i(calibrated),
        .client_reset_no(),.client_ready_o(media_ready),.control_ready_o(control_ready),
        .memory_flags_o(),.slot_accept_o(),.core_accept_o(),.native_accept_o(native_accept),
        .transport_fault_o(media_fault),.delay_valid_i(1'b0),.delay_write_i(1'b0),
        .delay_address_i(29'd0),.delay_data_i(256'd0),.delay_ready_o(),.delay_response_o(),.response_data_o(),
        .raw_start_valid_i(raw_start),.raw_start_ready_o(raw_start_ready),.raw_start_done_o(raw_start_done),
        .raw_clear_valid_i(1'b0),.raw_clear_ready_o(),.raw_clear_done_o(),
        .raw_capture_valid_i(pcm_valid),.raw_capture_index_i(pcm_sequence),.raw_capture_pcm_i(pcm),
        .raw_capture_ready_o(raw_capture_ready),.raw_close_valid_i(1'b0),.raw_close_ready_o(),
        .raw_drained_o(raw_drained),.raw_fault_o(raw_fault),.raw_object_fault_o(),
        .raw_channel_fault_o(raw_channel_fault),.raw_failure_code_o(raw_failure),
        .raw_accepted_frames_o(accepted),.raw_committed_frames_o(committed),
        .raw_fetch_valid_i(1'b0),.raw_fetch_ready_o(),.raw_fetch_offset_i(32'd0),.raw_fetch_length_i(14'd0),
        .raw_fetch_done_o(),.raw_fetch_fault_o(),.raw_cache_valid_o(),.raw_sample_addr_i(32'd0),
        .raw_sample_word_o(),.raw_native_protocol_fault_o(),
        .link_ready_i(1'b1),.panic_i(1'b0),.peer_boot_i(32'd1),.session_i(32'd1),
        .cnn_desc_valid_i(1'b0),.cnn_desc_ready_o(),.cnn_desc_i(200'd0),
        .cnn_frame_valid_i(1'b0),.cnn_frame_ready_o(),.cnn_frame_i(192'd0),
        .cnn_seal_valid_i(1'b0),.cnn_seal_ready_o(),.cnn_seal_i(192'd0),
        .cnn_cancel_valid_i(1'b0),.cnn_cancel_ready_o(),.cnn_cancel_i(128'd0),
        .cnn_score_valid_o(),.cnn_score_ready_i(1'b1),.cnn_score_o(),
        .cnn_terminal_valid_o(),.cnn_terminal_ready_i(1'b1),.cnn_terminal_o(),
        .cnn_fatal_o(),.cnn_model_status_o(),.cnn_accepted_frames_o(),.cnn_committed_frames_o(),.cnn_replayed_frames_o(),
        .model_serial_i(1'b1),.model_flash_miso_i(1'b1),.model_flash_cs_no(),.model_flash_clk_o(),.model_flash_mosi_o(),
        .app_cmd_o(cmd),.app_en_o(en),.app_wren_o(wren),.app_wend_o(),.app_address_o(address),
        .app_data_o(wdata),.app_mask_o(mask),.app_ready_i(ready),.app_write_ready_i(allow_native),
        .app_response_i(response || inject),.app_response_data_i(rdata));
    integer native_record_writes=0;
    always @(posedge mclk)begin
        response<=0;
        if(!reset_n)begin pending<=0;native_record_writes<=0;end
        else begin
            if(pending)begin rdata<=bist_memory[read_slot];response<=1;pending<=0;end
            if(en)begin
                if(!ready || (wren && !allow_native))$fatal(1,"unaccepted native dispatch");
                if(native_accept[0])begin
                    if(wren)bist_memory[address[4:3]]<=wdata;
                    else begin pending<=1;read_slot<=address[4:3];end
                end else if(native_accept[8])native_record_writes<=native_record_writes+1;
                else $fatal(1,"unexpected native owner in recording fault test");
            end
        end
    end
    integer checks=0,control_ticks=0;
    always @(posedge clk)begin
        control_ticks<=control_ticks+1;
        if(control_ticks>4000)$fatal(1,"fault CDC test deadline");
        if(pcm_valid && !raw_capture_ready)$fatal(1,"unexpected raw capture backpressure");
    end
    task automatic ticks(input integer n);repeat(n)@(negedge clk);endtask
    task automatic check(input bit ok,input string message);
        begin checks=checks+1;if(!ok)$fatal(1,"%s",message);end
    endtask
    initial begin
        ticks(4);reset_n=1;ticks(8);
        check(!control_ready && !raw_start_ready,"no admission before calibration/BIST");
        calibrated=1;wait(control_ready && raw_start_ready);ticks(2);
        arm=1;ticks(1);arm=0;check(armed && source_allowed,"ingress armed on local ready");
        raw_start=1;ticks(1);raw_start=0;wait(raw_start_done);ticks(2);
        allow_native=0;
        for(integer i=0;i<16;i=i+1)begin
            sequence_i=32'(i);frame_valid=1;ticks(1);frame_valid=0;ticks(5);
        end
        check(accepted==16 && committed==0 && !raw_drained,"stalled native writes cannot seal queued frames");
        // Assert between control edges. Native fault is immediate; the local
        // fence must change only after the existing two synchronizer samples.
        @(negedge clk);#1;inject=1;#1;
        check(media_fault && !media_ready && !en,"native quarantine is immediate");
        check(control_ready && !control_fault,"DDR fault has no combinational control bypass");
        check(dut.cnn_stream.live,"DDR fault has no combinational CNN control bypass");
        @(posedge clk);#1;check(control_ready,"first synchronizer sample cannot withdraw local readiness");
        check(dut.cnn_stream.live,"first fault sample cannot cancel CNN control");
        @(posedge clk);#1;check(!control_ready && control_fault && !pcm_valid,"second sample fences control PCM");
        check(!dut.cnn_stream.live && !dut.cnn_stream.desc_ready_o && !dut.cnn_stream.score_valid_o &&
            !dut.cnn_stream.terminal_valid_o,"second fault sample fences CNN input/results");
        @(negedge clk);inject=0;allow_native=1;ticks(40);
        check(media_fault && raw_channel_fault && raw_fault,"one native pulse remains a failed object/channel");
        check(!armed && source_fault && source_failure==3,"ingress records transport failure and flushes");
        check(raw_failure!=0 && committed==0 && !raw_drained,"no lost queued data is reported successful");
        check(native_record_writes==0 && !raw_start_ready && !en,"late readiness cannot resume poisoned native writes");
        // A common backend reset can recover the channel; old queued frames
        // must disappear and cannot become native commits in the new session.
        reset_n=0;calibrated=0;ticks(5);reset_n=1;ticks(4);calibrated=1;
        wait(control_ready && raw_start_ready);ticks(40);
        check(!raw_fault && accepted==0 && committed==0 && native_record_writes==0,"backend reset discards old recording work");
        check(dut.cnn_stream.live && dut.cnn_stream.state==0,"backend reset clears CNN fault without old descriptor replay");
        @(negedge mclk);native_run=0;#1;calibrated=0;#1;
        check(!dut.cnn_stream.control_reset_n && !dut.cnn_stream.task_service.native_reset_n && !en,
            "backend loss asserts both CNN resets with native clock stopped");
        calibrated=1;ticks(20);
        check(!dut.cnn_stream.control_reset_n && !dut.cnn_stream.task_service.native_reset_n,
            "stopped native clock cannot release CNN domains");
        native_run=1;wait(control_ready && raw_start_ready);ticks(20);
        check(dut.cnn_stream.control_reset_n && dut.cnn_stream.task_service.native_reset_n,
            "CNN resets release after native clock returns");
        @(negedge clk);control_run=0;#1;calibrated=0;#1;
        check(!dut.cnn_stream.control_reset_n && !dut.cnn_stream.task_service.native_reset_n && !en,
            "backend loss asserts both CNN resets with control clock stopped");
        calibrated=1;repeat(30)@(negedge mclk);
        check(!dut.cnn_stream.control_reset_n && !dut.cnn_stream.task_service.native_reset_n,
            "native startup cannot bypass stopped CNN control release");
        control_run=1;wait(control_ready && raw_start_ready);ticks(30);
        check(dut.cnn_stream.state==0 && dut.cnn_stream.task_service.state==0 &&
            dut.cnn_stream.task_service.control_reset_n && dut.cnn_stream.task_service.native_reset_n,
            "both clocks recover without old CNN work");
        $display("PASS task3_W_record_fault_CDC checks=%0d control_ticks=%0d",checks,control_ticks);$finish;
    end
endmodule
