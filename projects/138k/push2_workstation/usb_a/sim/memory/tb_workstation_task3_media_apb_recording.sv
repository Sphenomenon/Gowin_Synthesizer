`timescale 1ns/1ps
module tb_workstation_task3_media_apb_recording;
    reg clk=0,reset_n=0,task3_command_reset_n=1;
    always #10 clk=~clk;
    reg task3_command_valid=0,task3_command_write=0;
    reg [11:0] task3_command_address=0;
    reg [31:0] task3_command_data=0;
    reg [3:0] task3_command_strobes=15;
    wire task3_command_ready,task3_response_error;
    wire [31:0] task3_response_data;
    reg engine_reset=0,command=0;
    wire command_done;
    wire [7:0] engine_status,engine_state;
    wire [31:0] engine_frames,engine_crc;
    wire task3_start_valid,task3_start_ready,task3_start_accepted,task3_start_rejected;
    wire [3:0] task3_rejection_code,task3_terminal_code,task3_model_status;
    wire [31:0] task3_task_id,task3_generation,task3_frames,task3_crc,task3_frame_index,task3_frame_pcm;
    wire [7:0] task3_format;
    wire task3_frame_valid,task3_frame_ready,task3_ingress_fault,task3_cancel_valid;
    wire task3_score_valid,task3_score_ready,task3_terminal_valid,task3_terminal_ready,task3_fatal,task3_seal_valid;
    wire [6:0] task3_score_note,task3_first_note;
    wire [31:0] task3_score_index,task3_seal_crc,task3_accepted_frames,task3_committed_frames,task3_replayed_frames;
    wire [31:0] task3_active_id,task3_active_generation;
    wire task3_first_valid;
    wire [15:0] task3_first_frame;
    wire task3_tap_open,task3_tap_arm_valid,task3_tap_arm_ready,task3_tap_arm_accepted,task3_tap_arm_rejected;
    wire [31:0] task3_tap_session,task3_tap_generation,task3_tap_epoch,task3_tap_first_sequence;
    wire [7:0] task3_tap_format;
    wire task3_tap_frame_valid,task3_tap_frame_ready,task3_tap_frame44,task3_tap_frame_error;
    wire [31:0] task3_tap_frame_session,task3_tap_frame_generation,task3_tap_frame_epoch,task3_tap_frame_sequence,task3_tap_frame_pcm;
    wire task3_tap_cancel,task3_tap_panic,task3_tap_armed,task3_tap_fault;
    wire [3:0] task3_tap_failure;
    wire [8:0] task3_tap_queued;
    wire [31:0] task3_tap_accepted,task3_tap_delivered;
    wire task3_record_pcm_valid,task3_record_source_allowed;
    wire [31:0] task3_record_pcm,task3_record_sequence;
    workstation_task3_media_apb_service u_task3_media_service(
        .clk_i(clk),
        .reset_ni(reset_n),
        .owner_reset_ni(task3_command_reset_n),
        .command_valid_i(task3_command_valid),
        .command_write_i(task3_command_write),
        .command_address_i(task3_command_address),
        .command_data_i(task3_command_data),
        .command_strobes_i(task3_command_strobes),
        .command_ready_o(task3_command_ready),
        .response_error_o(task3_response_error),
        .response_data_o(task3_response_data),
        .backend_ready_i(1'b1),
        .lcd_link_ready_i(1'b0),
        .start_valid_o(task3_start_valid),
        .start_ready_i(1'd0),
        .start_accepted_i(1'd0),
        .start_rejected_i(1'd0),
        .rejection_code_i(4'd0),
        .task_id_o(task3_task_id),
        .generation_o(task3_generation),
        .frames_o(task3_frames),
        .crc_o(task3_crc),
        .format_o(task3_format),
        .frame_valid_o(task3_frame_valid),
        .frame_ready_i(1'd0),
        .frame_index_o(task3_frame_index),
        .frame_pcm_o(task3_frame_pcm),
        .ingress_fault_o(task3_ingress_fault),
        .cancel_valid_o(task3_cancel_valid),
        .score_valid_i(1'd0),
        .score_ready_o(task3_score_ready),
        .score_note_i(7'd0),
        .score_index_i(32'd0),
        .terminal_valid_i(1'd0),
        .terminal_ready_o(task3_terminal_ready),
        .terminal_code_i(4'd0),
        .model_status_i(4'd0),
        .fatal_i(1'd0),
        .seal_valid_i(1'd0),
        .seal_crc_i(32'd0),
        .accepted_frames_i(32'd0),
        .committed_frames_i(32'd0),
        .replayed_frames_i(32'd0),
        .active_task_id_i(32'd0),
        .active_generation_i(32'd0),
        .first_result_valid_i(1'd0),
        .first_result_note_i(7'd0),
        .first_result_frame_i(16'd0),
        .tap_open_o(task3_tap_open),
        .tap_arm_valid_o(task3_tap_arm_valid),
        .tap_arm_ready_i(task3_tap_arm_ready),
        .tap_arm_accepted_i(task3_tap_arm_accepted),
        .tap_arm_rejected_i(task3_tap_arm_rejected),
        .tap_session_o(task3_tap_session),
        .tap_generation_o(task3_tap_generation),
        .tap_epoch_o(task3_tap_epoch),
        .tap_first_sequence_o(task3_tap_first_sequence),
        .tap_format_o(task3_tap_format),
        .tap_frame_valid_o(task3_tap_frame_valid),
        .tap_frame_ready_i(task3_tap_frame_ready),
        .tap_frame_session_o(task3_tap_frame_session),
        .tap_frame_generation_o(task3_tap_frame_generation),
        .tap_frame_epoch_o(task3_tap_frame_epoch),
        .tap_frame_sequence_o(task3_tap_frame_sequence),
        .tap_frame_pcm_o(task3_tap_frame_pcm),
        .tap_frame_44k1_o(task3_tap_frame44),
        .tap_frame_error_o(task3_tap_frame_error),
        .tap_cancel_valid_o(task3_tap_cancel),
        .tap_panic_o(task3_tap_panic),
        .tap_armed_i(task3_tap_armed),
        .tap_fault_i(task3_tap_fault),
        .tap_failure_i(task3_tap_failure),
        .tap_queued_i(task3_tap_queued),
        .tap_accepted_i(task3_tap_accepted),
        .tap_delivered_i(task3_tap_delivered));
    workstation_task3_record_ingress u_task3_record_ingress(
        .clk_i(clk),
        .reset_ni(reset_n),
        .link_ready_i(task3_tap_open && task3_command_reset_n),
        .panic_i(task3_tap_panic),
        .transport_fault_i(1'b0),
        .object_idle_i(engine_state==0),
        .cancel_valid_i(task3_tap_cancel),
        .cancel_session_i(task3_tap_session),
        .cancel_generation_i(task3_tap_generation),
        .arm_valid_i(task3_tap_arm_valid),
        .arm_ready_o(task3_tap_arm_ready),
        .arm_session_i(task3_tap_session),
        .arm_generation_i(task3_tap_generation),
        .arm_physical_epoch_i(task3_tap_epoch),
        .arm_first_sequence_i(task3_tap_first_sequence),
        .arm_format_i(task3_tap_format),
        .arm_accepted_o(task3_tap_arm_accepted),
        .arm_rejected_o(task3_tap_arm_rejected),
        .frame_valid_i(task3_tap_frame_valid),
        .frame_ready_o(task3_tap_frame_ready),
        .frame_session_i(task3_tap_frame_session),
        .frame_generation_i(task3_tap_frame_generation),
        .frame_physical_epoch_i(task3_tap_frame_epoch),
        .frame_sequence_i(task3_tap_frame_sequence),
        .frame_pcm_i(task3_tap_frame_pcm),
        .frame_44k1_i(task3_tap_frame44),
        .frame_error_i(task3_tap_frame_error),
        .pcm_valid_o(task3_record_pcm_valid),
        .source_allowed_o(task3_record_source_allowed),
        .pcm_pair_o(task3_record_pcm),
        .pcm_sequence_o(task3_record_sequence),
        .physical_sequence_o(),
        .session_o(),
        .generation_o(),
        .physical_epoch_o(),
        .armed_o(task3_tap_armed),
        .fault_o(task3_tap_fault),
        .failure_code_o(task3_tap_failure),
        .queued_frames_o(task3_tap_queued),
        .accepted_frames_o(task3_tap_accepted),
        .delivered_frames_o(task3_tap_delivered));
    workstation_ble_record_data_engine #(.CAPACITY_FRAMES(32),.EXTERNAL_PCM(1)) engine(
        .clk(clk),.resetn(engine_reset),.enable(1'b1),.connected(1'b1),.transfer_subscribed(1'b1),
        .pcm_valid_i(task3_record_pcm_valid),.source_ready_i(task3_record_source_allowed),.source_fault_i(task3_tap_fault),.pcm_pair_i(task3_record_pcm),
        .boot_id(64'd123),.att_value_limit(9'd247),.elapsed_ms(32'd100),
        .command_start(command),.command_flags_i(5'd0),.command_object_id_i(32'd1),.command_transfer_id_i(32'd0),
        .opcode(8'h20),.request_id(32'd1),.nonce(64'd10),.payload_length(16'd8),.payload({64'd0,32'd16,32'd1}),
        .command_done(command_done),.command_status(engine_status),.command_length(),.command_addr(7'd0),.command_data(),
        .record_state(engine_state),.recording_id(),.recorded_frames(engine_frames),.capacity_frames(),
        .transfer_valid(),.transfer_compact(),.transfer_bulk(),.transfer_direct(),.transfer_length(),
        .transfer_addr(13'd0),.transfer_data(),.transfer_consume(1'b0),
        .seal_hold_i(1'b0),.seal_request_i(1'b0),.seal_ready_o(),.seal_pending_o(),.seal_done_o(),.seal_failed_o(),
        .seal_failure_code_o(),.seal_record_state_o(),.seal_recording_id_o(),.seal_frames_o(),.seal_crc_o(),
        .object_crc_o(engine_crc));
    integer checks=0,cycles=0,delivered=0,last_cycle=-100;
    reg [31:0] expected_crc=32'hffffffff;
    function automatic [31:0] crc_byte(input [31:0] old,input [7:0] value);
        reg [31:0] c;integer n;begin c=old^{24'd0,value};for(n=0;n<8;n=n+1)c=c[0]?(c>>1)^32'hedb88320:c>>1;crc_byte=c;end
    endfunction
    task automatic ticks(input integer n);begin repeat(n)@(negedge clk);end endtask
    task automatic check(input bit ok,input [767:0] message);
        begin checks=checks+1;if(!ok)$fatal(1,"%0s cycle=%0d",message,cycles);end
    endtask
    task automatic wr(input [11:0] address,input [31:0] value,input bit err);
        begin @(negedge clk);task3_command_address=address;task3_command_data=value;task3_command_write=1;task3_command_valid=1;#1;
            check(task3_command_ready && task3_response_error==err,"APB credit/error terminates immediately");
            @(negedge clk);task3_command_valid=0;task3_command_write=0;ticks(1);end
    endtask
    always @(posedge clk)begin
        cycles<=cycles+1;if(cycles>10000)$fatal(1,"APB engine test deadline");
        if(reset_n && task3_record_pcm_valid)begin
            check(cycles-last_cycle>=5,"actual engine CRC pipeline spacing preserved through APB");last_cycle=cycles;
            check(task3_record_sequence==32'(delivered),"continuous observer sequence from APB pacer");
            if(delivered<16)begin
                check(task3_record_pcm==32'h15370000+32'(delivered),"APB PCM reaches actual recorder exactly");
                for(integer j=0;j<4;j=j+1)expected_crc=crc_byte(expected_crc,task3_record_pcm[j*8+:8]);
            end
            delivered=delivered+1;
        end
    end
    initial begin
        ticks(4);reset_n=1;engine_reset=1;ticks(4);
        task3_command_strobes=0;task3_command_address=0;#1;check(!task3_response_error && task3_response_data==32'h574d3301,"legal APB read permits zero PSTRB");task3_command_strobes=15;
        check(!task3_tap_open && !task3_tap_armed && !task3_record_source_allowed,"reset closes software aperture");
        wr(12'h114,1,1);wr(12'h134,1,1);wr(12'h118,1,0);
        task3_command_address=12'h004;#1;check(!task3_response_data[7],"software aperture cannot impersonate physical LCD-ready");
        wr(12'h100,7,0);wr(12'h104,1,0);wr(12'h108,19,0);wr(12'h10c,100,0);wr(12'h110,1,0);wr(12'h114,1,0);
        check(task3_tap_armed && task3_record_source_allowed,"actual empty object admits new software transport generation");
        command=1;ticks(1);command=0;wait(command_done);check(engine_status==0 && engine_state==1,"same real engine owns capture");
        wr(12'h11c,7,0);wr(12'h120,1,0);wr(12'h124,19,0);
        for(integer k=0;k<16;k=k+1)begin
            wr(12'h128,100+32'(k),0);wr(12'h12c,32'h15370000+32'(k),0);wr(12'h134,1,0);
        end
        wait(engine_state==4);ticks(8);
        check(engine_frames==16 && delivered==16 && engine_crc==~expected_crc,"actual maintained engine seals all16 APB frames with exact CRC");
        wr(12'h150,1,0);check(task3_tap_fault && !task3_record_source_allowed && task3_tap_failure==5,"PANIC immediately fences injected PCM");
        wr(12'h104,2,0);wr(12'h114,1,1);check(!task3_tap_armed,"existing sealed object prevents rearm");
        engine_reset=0;ticks(3);engine_reset=1;ticks(3);wr(12'h114,1,0);
        check(task3_tap_armed && !task3_tap_fault,"higher generation only after object retired");
        wr(12'h138,1,0);check(task3_tap_fault && task3_tap_failure==6,"matching transport cancellation fences source");
        wr(12'h104,3,0);wr(12'h114,1,0);wr(12'h120,2,0);wr(12'h128,100,0);wr(12'h134,1,1);
        check(task3_tap_fault && task3_tap_failure==2 && !task3_record_pcm_valid,"wrong-generation APB packet is discarded and source fails");
        wr(12'h104,4,0);wr(12'h114,1,0);wr(12'h120,4,0);wr(12'h128,101,0);wr(12'h134,1,1);
        check(task3_tap_fault && task3_tap_failure==2,"bad sequence fences without combinational credit loop");
        wr(12'h104,5,0);wr(12'h114,1,0);wr(12'h120,5,0);wr(12'h128,100,0);wr(12'h124,20,0);wr(12'h134,1,1);
        check(task3_tap_fault && task3_tap_failure==2,"bad physical epoch fences without combinational credit loop");
        wr(12'h104,6,0);wr(12'h114,1,0);wr(12'h120,6,0);wr(12'h124,19,0);wr(12'h130,1,0);wr(12'h134,1,1);
        check(task3_tap_fault && task3_tap_failure==2,"44k1 packet cannot masquerade as48k recording");
        wr(12'h104,7,0);wr(12'h114,1,0);wr(12'h120,7,0);wr(12'h130,2,0);wr(12'h134,1,1);
        check(task3_tap_fault && task3_tap_failure==2,"error-marked packet fences before output");
        wr(12'h104,8,0);wr(12'h114,1,0);wr(12'h118,0,0);
        check(task3_tap_fault && task3_tap_failure==3 && !task3_record_pcm_valid,"software close acts as bounded disconnect");
        wr(12'h118,1,0);task3_command_reset_n=0;ticks(3);
        check(!task3_tap_open && task3_ingress_fault,"CPU owner reset closes aperture and fences task");
        $display("PASS task3_media_APB_recording checks=%0d frames=%0d cycles=%0d crc=%h",checks,delivered,cycles,~expected_crc);$finish;
    end
endmodule
