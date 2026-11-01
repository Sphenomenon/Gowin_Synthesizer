`timescale 1ns/1ps
module config_accept_runtime_case #(
    parameter integer STARTUP_FRAMES=3, PDN_FRAMES=1,
    parameter bit PRODUCTION_CLOCKS=0,RESERVE_ZERO_EPOCH=0,D_ONLY=0
)(output reg finished=0);
    reg control_clk=0,compute_clk=0,memory_clk=0,reference48=0,reference44=0;
    reg run48=1,run44=1,rst_n=0;
    always #10 control_clk=!control_clk;
    always #6.510417 compute_clk=!compute_clk;
    always #5 memory_clk=!memory_clk;
    initial begin #3.7;forever begin #40.690104;if(run48)reference48=!reference48;end end
    initial begin #17.2;forever begin #29.525699;if(run44)reference44=!reference44;end end
    reg request=0,request44=0,permit=1,recover=0,media_quiet=1;
    reg event_valid=0;
    reg [17:0] event_data=0;
    wire ready,busy,fault,accepted,applied,rejected,failed,policy_rejected;
    wire [2:0] reject_code;
    wire [3:0] fault_code,selection;
    wire rate,active_valid,quiesce,flush,dsp_fault,context_ready,event_ready,muted;
    wire [31:0] epoch,scope_status,tf_control,applied_events,options,active;
    wire [127:0] held;
    wire [9:0] panic_epoch;
    wire [5:0] voices;
    wire [1:0] mode,raw_good;
    wire [15:0] volume;
    wire [31:0] pc_overflows,deadlines,midi_overflows,note_drops;
    reg tf_active=0,tf_error=0;
    reg [19:0] tf_rate=48000;
    wire tf_ready;
    wire ddr_req,ddr_write;
    wire [28:0] ddr_address;
    wire [255:0] ddr_data,ddr_read_data;
    wire [31:0] ddr_mask;
    reg ddr_ready=1,ddr_response=0,hold_fence=0;
    wire mclk,bck,lrck,sd,pdn_n,smute;
    wire analysis_valid,record_valid,frame_valid,frame_error,frame_rate,stream_change,sequence_gap,analysis_gap,record_fault;
    wire [31:0] frame_epoch,frame_sequence,frame_pcm,analysis_drops,record_drops,underruns,source_errors,bridge_drops,bridge_discards;
    wire analysis_ready=frame_sequence%3!=0,record_ready=frame_sequence%5<2;
    workstation_runtime_audio #(
        .WINDOW_CYCLES(PRODUCTION_CLOCKS ? 50000:500),.STABLE_WINDOWS(PRODUCTION_CLOCKS ? 4:3),
        .LOSS_TIMEOUT_CYCLES(PRODUCTION_CLOCKS ? 500:25),.STOP_LOW_CYCLES(PRODUCTION_CLOCKS ? 16:8),
        .COUNTER_BITS(32),.SWITCH_TIMEOUT_CYCLES(2000000),.PDN_HOLD_FRAMES(PDN_FRAMES),.STARTUP_MUTE_FRAMES(STARTUP_FRAMES),
        .RESERVE_ZERO_EPOCH(RESERVE_ZERO_EPOCH),.SYNTH_ENGINES_ENABLE(!D_ONLY),.D_ONLY_ENABLE(D_ONLY)
    ) dut(
        .common_reset_ni(1'b1),.rst_ni(rst_n),.clk_50m_i(control_clk),.compute_clk_i(compute_clk),.memory_clk_i(memory_clk),
        .reference_48_i(reference48),.reference_44_i(reference44),.request_i(request),.request_44k1_i(request44),
        .switch_permit_i(permit),.recover_i(recover),.media_quiescent_i(media_quiet),.request_ready_o(ready),.busy_o(busy),
        .fault_o(fault),.accepted_o(accepted),.applied_o(applied),.rejected_o(rejected),.failed_o(failed),
        .policy_rejected_o(policy_rejected),.reject_code_o(reject_code),.fault_code_o(fault_code),.clock_select_o(selection),
        .active_44k1_o(rate),.active_valid_o(active_valid),.stream_epoch_o(epoch),.source_qualified_o(raw_good),
        .quiesce_o(quiesce),.stream_flush_o(flush),.dsp_fault_o(dsp_fault),.context_ready_o(context_ready),
        .midi_byte_valid_i(1'b0),.pc_byte_valid_i(1'b0),.cpu_event_valid_i(event_valid),.midi_byte_i(8'd0),.pc_byte_i(8'd0),
        .pcm_cpu_ready_i(1'b1),.pcm_command_valid_i(1'b0),.pcm_command_write_i(1'b0),
        .pcm_command_address_i(12'd0),.pcm_command_data_i(32'd0),.pcm_command_strobes_i(4'd0),
        .pcm_command_ready_o(),.pcm_response_error_o(),.pcm_response_data_o(),
        .hci_session_ready_i(1'b0),.hci_controller_epoch_i(32'd0),.hci_transport_generation_i(32'd0),.pcm_tf_busy_i(1'b0),
        .cpu_event_i(event_data),.cpu_event_ready_o(event_ready),.pcm_left_i(32'sd0),.pcm_right_i(32'sd0),.output_mute_i(1'b0),
        .held_notes_o(held),.panic_epoch_o(panic_epoch),.panic_muted_o(muted),.active_mask_o(active),.active_voice_count_o(voices),
        .scope_status_o(scope_status),.tf_scope_control_o(tf_control),.applied_events_o(applied_events),.control_options_o(options),
        .mode_o(mode),.master_volume_o(volume),.tf_active_i(tf_active),.tf_valid_i(1'b1),.tf_error_i(tf_error),
        .pitch_q20_o(),.pc_overflow_o(pc_overflows),.deadline_miss_o(deadlines),.midi_overflow_o(midi_overflows),
        .note_drop_o(note_drops),.clip_o(),.synth_gain_o(),.pcm_gain_o(),.route_o(),.profile_o(),.effect_mask_o(),
        .effect_order_o(),.effect_state_o(),.panel_event_valid_o(),.panel_command_o(),
        .tf_left_i(16'sd25000),.tf_right_i(-16'sd17000),.tf_sample_rate_i(tf_rate),.tf_generation_i(32'd1),
        .expected_tf_generation_i(32'd1),.tf_ready_o(tf_ready),.ddr_req_o(ddr_req),.ddr_write_o(ddr_write),
        .ddr_address_o(ddr_address),.ddr_data_o(ddr_data),.ddr_mask_o(ddr_mask),.ddr_ready_i(ddr_ready),
        .ddr_response_i(ddr_response),.ddr_read_data_i(ddr_read_data),.mclk_o(mclk),.bck_o(bck),.lrck_o(lrck),.data_o(sd),
        .pdn_no(pdn_n),.smute_o(smute),.analysis_enable_i(1'b1),.analysis_ready_i(analysis_ready),
        .record_enable_i(1'b1),.record_ready_i(record_ready),.analysis_valid_o(analysis_valid),.record_valid_o(record_valid),
        .frame_valid_o(frame_valid),.frame_error_o(frame_error),.frame_44k1_o(frame_rate),.frame_epoch_o(frame_epoch),
        .frame_sequence_o(frame_sequence),.frame_pcm_o(frame_pcm),.stream_change_o(stream_change),.sequence_gap_o(sequence_gap),
        .analysis_gap_o(analysis_gap),.record_fault_o(record_fault),.analysis_drop_count_o(analysis_drops),
        .record_drop_count_o(record_drops),.underrun_count_o(underruns),.source_error_count_o(source_errors),
        .bridge_request_drop_count_o(bridge_drops),.bridge_return_discard_count_o(bridge_discards));

    // Ordered posted-write/read owner-6 model. No replacement DSP or clock mux.
    reg [255:0] memory[0:4095],qdata[0:63],read_data=0;
    reg [28:0] qaddr[0:63];
    reg qwrite[0:63],qfence[0:63];
    integer head=0,tail=0,queued=0,memory_ticks=0,writes=0,fences=0;
    assign ddr_read_data=read_data;
    always @(posedge memory_clk)begin
        ddr_response<=0;
        if(rst_n)begin
            if(ddr_req && ddr_ready)begin
                if(queued>=64 || ddr_address<29'h0c000000 || ddr_address>=29'h0c008000 || ddr_address[2:0]!=0 || ddr_mask!=0)
                    $fatal(1,"owner6 queue/allocation/mask");
                qdata[tail]=ddr_data;qaddr[tail]=ddr_address;qwrite[tail]=ddr_write;qfence[tail]=dut.delay_dma.state==8;
                tail=(tail+1)%64;queued=queued+1;
            end
            if(queued!=0 && !(qfence[head] && hold_fence))begin
                if(memory_ticks==3)begin
                    memory_ticks=0;
                    if(qwrite[head])begin memory[12'((qaddr[head]-29'h0c000000)>>3)]=qdata[head];writes=writes+1;end
                    else begin
                        read_data<=memory[12'((qaddr[head]-29'h0c000000)>>3)];ddr_response<=1;
                        if(qfence[head])fences=fences+1;
                    end
                    head=(head+1)%64;queued=queued-1;
                end else memory_ticks=memory_ticks+1;
            end
        end
    end

integer phantom_ready=0,fault_veto=0,withdrawals=0,commits=0;
task reset_to_offer;begin
 rst_n=0;repeat(10)@(negedge control_clk);rst_n=1;
 wait(dut.config_state==3 && dut.config_accept_pending);@(negedge compute_clk);#1;
 if(!dut.config_valid || !dut.config_ready || !dut.config_accepted || !dut.service.workstation.engine_rate_commit)$fatal(1,"real initial configuration offer missing D=%0d",D_ONLY);
end endtask
task rejected_edge;begin
 #1;if(dut.config_valid || dut.config_accepted || dut.service.workstation.engine_rate_commit)$fatal(1,"withdrawn request still accepted D=%0d",D_ONLY);
 @(posedge compute_clk);#1;
 if(dut.config_state!=3 || !dut.config_accept_pending || dut.service.external_busy || dut.service.workstation.runtime_config_busy)$fatal(1,"PHANTOM_ACK D=%0d state=%0d",D_ONLY,dut.config_state);
end endtask
initial begin
 reset_to_offer();force dut.pcm_hard_fault=1'b1;
 #1;if(!dut.config_ready)$fatal(1,"old-ready phantom witness missing");phantom_ready=phantom_ready+1;
 rejected_edge();fault_veto=fault_veto+1;release dut.pcm_hard_fault;
 reset_to_offer();force dut.service.workstation.runtime_effects.effects.delay_stage.underflow_sticky=1'b1;
 rejected_edge();fault_veto=fault_veto+1;release dut.service.workstation.runtime_effects.effects.delay_stage.underflow_sticky;
 reset_to_offer();force dut.config_valid=1'b0;rejected_edge();withdrawals=withdrawals+1;release dut.config_valid;
 reset_to_offer();@(posedge compute_clk);
 if(!dut.config_accepted || !dut.service.workstation.runtime_configuration.config_accept || !dut.service.workstation.engine_rate_commit)$fatal(1,"no actual broadcast on ACK edge");
 #1;if(dut.config_state!=4 || dut.config_accept_pending || !dut.service.external_busy || !dut.service.workstation.runtime_config_busy)$fatal(1,"actual same-edge ACK/busy capture mismatch");commits=commits+1;
 wait(dut.config_applied);@(posedge compute_clk);#1;
 if(dut.config_state!=0 || !dut.compute_context_valid || dut.compute_rate!=dut.pending_rate)$fatal(1,"applied configuration did not return IDLE");
 $display("PASS REAL_RUNTIME_RECEIPT D=%0d phantom_ready=%0d fault_veto=%0d withdrawals=%0d actual_commits=%0d",D_ONLY,phantom_ready,fault_veto,withdrawals,commits);finished=1;
end
endmodule
module tb;wire m,w;config_accept_runtime_case #(.D_ONLY(0)) master_case(m);config_accept_runtime_case #(.D_ONLY(1)) worker_case(w);
initial begin wait(m&&w);$display("PASS REAL_RUNTIME_RECEIPT_M_W");$finish;end
initial begin #100000000;$fatal(1,"runtime timeout");end endmodule
