`timescale 1ns/1ps
`include "rtl/workstation/task3_paired_channels.vh"
// Host workload model only. Actual endpoints/PHY/APB CDC/PCM1 owner, ideal wires.
// Synthetic TF analysis/final-tap producers; no CPU instruction, RF/SBC, CNN,
// DDR recording object, DSP/I2S/DAC, electrical or physical timing acceptance.
module task3_phone_lcd_cosim(
    input wire mclk_i,wclk_i,audio_clk_i,reset_n,enable_i,budget_i,run_i,media_i,
    input wire analysis_start_i,analysis_stall_i,
    input wire [1:0] cpu_valid,cpu_write,
    input wire [23:0] cpu_address,input wire [63:0] cpu_data,input wire [7:0] cpu_strobes,
    output wire [1:0] cpu_ready,cpu_error,output wire [63:0] cpu_response,
    output wire [1:0] business_o,link_live_o,
    output wire phone_live_o,owner_failed_o,selected_o,
    output wire [7:0] owner_failure_o,
    output wire [31:0] queued_phone_o,analysis_received_o,record_received_o,
    output reg [31:0] sample_ticks_o=0,rendered_o=0,nonzero_o=0,applied_words_o=0,phone_blocks_o=0,rejected_window_commands_o=0,
    output wire [31:0] m_packets_o,w_packets_o,m_probe_o,w_probe_o,m_rtt_o,w_rtt_o,
    output wire [31:0] max_analysis_queue_o,max_tf_queue_o,max_record_queue_o,
    output wire [7:0] fault_bits_o,
    output wire [31:0] malformed_o,stale_o
);
    localparam bit W_BLOCK=1'b1,W_PHONE_WINDOW=1'b1;
    wire [1:0] clocks={wclk_i,mclk_i};
    wire [1:0] live,business,link_fault,tx_ready,rx_valid,rx_ready,tx_valid;
    wire [1:0] req,ack,panic_pad;
    wire [3:0] phy_data[2],rx_channel[2],tx_channel[2],link_failure[2];
    wire [255:0] rx_payload[2],tx_payload[2];
    wire [5:0] rx_length[2],tx_length[2];
    wire [31:0] tx_packets[2],probes[2],max_rtt[2],crc_errors[2],sequence_errors[2],overflows[2];
    wire panic=1'b0,m_observer_reset=1'b0;
    wire [31:0] m_boot=11,generation=1;
    wire record_valid,record_allowed,record_fault,phone_fault;
    wire [31:0] record_pcm,record_sequence;
    wire [3:0] record_failure;
    wire cdv,cfv,csv,ccv;
    wire [199:0] cdesc;wire [191:0] cframe,cseal;wire [127:0] ccancel;
    wire cdr=1'b1,cfr=!analysis_stall_i,csr=1'b1,ccr=1'b1;
    wire terminal_valid=1'b0;wire [163:0] terminal=0;wire terminal_ready;
    wire object_idle=1'b1,transport_fault=1'b0;
    wire source_needed=run_i && media_i;
    wire analysis_cancel=1'b0,record_arm=1'b0,record_cancel=1'b0;
    reg analysis_pcm_valid=0,analysis_pcm_last=0,frame_valid=0;
    reg [31:0] analysis_pcm=0,frame_pcm=0,frame_epoch=7,frame_sequence=0;
    integer source_phase=0,analysis_generated=0,analysis_submitted=0,record_generated=0;
    integer a_received=0,r_received=0,a_max=0,tf_max=0,r_max=0;
    integer wcycles=0;
    function automatic [31:0] pcm(input integer stream,input integer index);
        pcm=32'hb1090401 ^ (32'(index)*32'h10497) ^ (32'(stream)*32'h5a390181);
    endfunction
    for(genvar i=0;i<2;i=i+1)begin:g_link
        workstation_task3_lcd_transport #(.EXPERIMENT_ENABLE(1),.ALLOW_BUSINESS(1)) link(
            .clk_i(clocks[i]),.reset_ni(reset_n),.enable_i(enable_i),.panic_i(panic),.budget_validated_i(budget_i),
            .local_boot_i(i==0?32'd11:32'd22),.peer_boot_i(i==0?32'd22:32'd11),.session_i(32'd33),
            .tx_valid_i(tx_valid[i]),.tx_ready_o(tx_ready[i]),.tx_channel_i(tx_channel[i]),.tx_payload_i(tx_payload[i]),.tx_length_i(tx_length[i]),
            .rx_valid_o(rx_valid[i]),.rx_ready_i(rx_ready[i]),.rx_channel_o(rx_channel[i]),.rx_payload_o(rx_payload[i]),.rx_length_o(rx_length[i]),
            .link_ready_o(live[i]),.business_ready_o(business[i]),.pad_drive_o(),.fault_o(link_fault[i]),.failure_code_o(link_failure[i]),.peer_panic_o(),
            .phy_tx_data_o(phy_data[i]),.phy_tx_req_o(req[i]),.phy_rx_ack_o(ack[i]),.phy_panic_o(panic_pad[i]),
            .phy_rx_data_i(phy_data[1-i]),.phy_rx_req_i(req[1-i]),.phy_tx_ack_i(ack[1-i]),.phy_peer_panic_i(panic_pad[1-i]),
            .tx_packets_o(tx_packets[i]),.rx_packets_o(),.crc_errors_o(crc_errors[i]),.sequence_errors_o(sequence_errors[i]),.rejected_packets_o(),.overflow_count_o(overflows[i]),
            .congestion_cycles_o(),.last_rtt_cycles_o(),.max_rtt_cycles_o(max_rtt[i]),.probe_results_o(probes[i]),.link_timeouts_o());
    end
    workstation_task3_w_bus_endpoint #(.BLOCK_PCM(W_BLOCK),.PHONE_WINDOW_BLOCK(W_PHONE_WINDOW),.MEDIA_CAP_TIMEOUT_CYCLES(W_PHONE_WINDOW ? 1000000:3000)) w(
        .clk_i(wclk_i),.reset_ni(reset_n),.link_ready_i(business[1]),.panic_i(panic),
        .local_boot_i(32'd22),.peer_boot_i(m_boot),.session_i(32'd33),.generation_i(generation),
        .rx_valid_i(rx_valid[1]),.rx_ready_o(rx_ready[1]),.rx_channel_i(rx_channel[1]),.rx_payload_i(rx_payload[1]),.rx_length_i(rx_length[1]),
        .tx_valid_o(tx_valid[1]),.tx_ready_i(tx_ready[1]),.tx_channel_o(tx_channel[1]),.tx_payload_o(tx_payload[1]),.tx_length_o(tx_length[1]),
        .cnn_desc_valid_o(cdv),.cnn_desc_ready_i(cdr),.cnn_desc_o(cdesc),
        .cnn_frame_valid_o(cfv),.cnn_frame_ready_i(cfr),.cnn_frame_o(cframe),
        .cnn_seal_valid_o(csv),.cnn_seal_ready_i(csr),.cnn_seal_o(cseal),
        .cnn_cancel_valid_o(ccv),.cnn_cancel_ready_i(ccr),.cnn_cancel_o(ccancel),
        .cnn_score_valid_i(1'b0),.cnn_score_ready_o(),.cnn_score_i(167'd0),
        .cnn_terminal_valid_i(terminal_valid),.cnn_terminal_ready_o(terminal_ready),.cnn_terminal_i(terminal),
        .backend_ready_i(1'b1),.model_status_i(4'd9),.record_object_idle_i(object_idle),
        .record_source_needed_i(source_needed),
        .record_transport_fault_i(transport_fault),.record_pcm_valid_o(record_valid),.record_source_allowed_o(record_allowed),
        .record_pcm_o(record_pcm),.record_sequence_o(record_sequence),.record_fault_o(record_fault),.record_failure_o(record_failure),
        .hci_classic_ready_i(1'b1),.phone_owner_ready_i(1'b1),.hci_epoch_i(32'd44),.hci_generation_i(32'd55),
        .command_valid_i(cpu_valid),.command_write_i(cpu_write),.command_address_i(cpu_address),.command_data_i(cpu_data),.command_strobes_i(cpu_strobes),
        .command_ready_o(cpu_ready),.response_error_o(cpu_error),.response_data_o(cpu_response),
        .phone_fault_o(phone_fault),.malformed_packets_o(),.stale_packets_o());

    wire analysis_failed,analysis_busy,analysis_done;
    wire record_armed,mrecord_fault,phone_live,mcommand_valid,mcommand_target,mcommand_write;
    wire [11:0] mcommand_address;wire [31:0] mcommand_data;wire [3:0] mcommand_strobes;
    wire cb_ready,cb_error,cb_reset,oc_valid,oc_write,oc_ready,oc_error;
    wire [11:0] oc_address;wire [31:0] oc_data,oc_response,cb_response;wire [3:0] oc_strobes;
    wire mcommand_ready=mcommand_target ? mcommand_valid:cb_ready;
    // No rate change is requested in this 48k-only workload. A clock access is
    // counted as an unexpected branch by the C++ driver; this is not clock-owner validation.
    wire [31:0] mresponse=mcommand_target ? 32'hc10c0001:cb_response;
    wire merror=mcommand_target ? 1'b0:cb_error;
    gw138k_apb_cdc command_cdc(
        .reset_n(reset_n && !m_observer_reset),.pclk(mclk_i),.audio_clk(audio_clk_i),
        .psel(mcommand_valid && !mcommand_target),.penable(mcommand_valid && !mcommand_target),
        .pwrite(mcommand_write),.paddr(mcommand_address),.pwdata(mcommand_data),.pstrb(mcommand_strobes),
        .pready(cb_ready),.pslverr(cb_error),.prdata(cb_response),.command_reset_n(cb_reset),
        .command_valid(oc_valid),.command_ready(oc_ready),.command_write(oc_write),
        .command_address(oc_address),.command_data(oc_data),.command_strobes(oc_strobes),
        .response_data(oc_response),.response_error(oc_error));
    reg [2:0] live_sync=0;
    always @(posedge audio_clk_i or negedge reset_n)
        if(!reset_n)live_sync<=0;else live_sync<={live_sync[1:0],phone_live};
    integer sample_phase=0;
    reg take=0;
    reg [1:0] history_completion=0;
    wire history_done=history_completion[1];
    wire selected,owner_failed,owner_idle,history_clear,serial_hold;
    wire signed [31:0] pcm_l,pcm_r;
    always @(posedge audio_clk_i or negedge reset_n)
        if(!reset_n)history_completion<=0;
        else history_completion<={history_completion[0],history_clear};
    always @(negedge audio_clk_i)begin
        take=sample_phase==1599;
        sample_phase=take ? 0:sample_phase+1;
        if(take)begin
            sample_ticks_o<=sample_ticks_o+1;
            if(selected && !serial_hold)begin
                rendered_o<=rendered_o+1;
                if(pcm_l==32'sh1f400000 && pcm_r==-32'sh17700000)nonzero_o<=nonzero_o+1;
            end
        end
    end
    workstation_ae350_pcm_owner owner(
        .clk_i(audio_clk_i),.reset_ni(reset_n),.cpu_ready_i(cb_reset),
        .command_valid_i(oc_valid),.command_ready_o(oc_ready),.command_write_i(oc_write),
        .command_address_i(oc_address),.command_data_i(oc_data),.command_strobes_i(oc_strobes),
        .response_data_o(oc_response),.response_error_o(oc_error),
        .session_live_i(live_sync[2]),.controller_epoch_i(32'd44),.transport_generation_i(32'd55),
        .context_ready_i(1'b1),.rate_44100_i(1'b0),.physical_epoch_i(32'd7),
        .tf_busy_i(1'b0),.switch_busy_i(1'b0),.sample_take_i(take),
        .legacy_left_i(32'd0),.legacy_right_i(32'd0),.pcm_left_o(pcm_l),.pcm_right_o(pcm_r),
        .history_clear_o(history_clear),.history_ready_i(1'b1),.history_done_i(history_done),
        .serial_hold_o(serial_hold),.cancel_epoch_o(),.selected_o(selected),.failed_o(owner_failed),.hard_fault_o(),.idle_o(owner_idle));
    always @(posedge audio_clk_i)if(reset_n && oc_valid && oc_ready && oc_write && oc_address[11])begin
        if(oc_error)begin
            if(!owner_failed || owner.failure!=4)$fatal(1,"window rejected without actual owner underrun");
            rejected_window_commands_o<=rejected_window_commands_o+1;
        end else applied_words_o<=applied_words_o+1;
    end
    always @(posedge wclk_i)if(tx_valid[1] && tx_ready[1] && tx_channel[1]==`TASK3_PAIR_CH_PHONE_WINDOW)phone_blocks_o<=phone_blocks_o+1;
    wire hci_ready;wire [31:0] hci_epoch,hci_generation;wire [3:0] model_status;
    wire analysis_ready,analysis_pcm_ready;
    workstation_task3_m_bus_endpoint #(.BLOCK_PCM(1'b1),.PHONE_WINDOW_BLOCK(1'b1),.MEDIA_CAP_TIMEOUT_CYCLES(W_PHONE_WINDOW ? 1000000:3000)) m(
        .clk_i(mclk_i),.reset_ni(reset_n && !m_observer_reset),.link_ready_i(business[0]),.panic_i(panic),
        .local_boot_i(m_boot),.peer_boot_i(32'd22),.session_i(32'd33),.generation_i(generation),
        .rx_valid_i(rx_valid[0]),.rx_ready_o(rx_ready[0]),.rx_channel_i(rx_channel[0]),.rx_payload_i(rx_payload[0]),.rx_length_i(rx_length[0]),
        .tx_valid_o(tx_valid[0]),.tx_ready_i(tx_ready[0]),.tx_channel_o(tx_channel[0]),.tx_payload_o(tx_payload[0]),.tx_length_o(tx_length[0]),
        .analysis_start_i(analysis_start_i),.analysis_ready_o(analysis_ready),.analysis_cancel_i(analysis_cancel),
        .analysis_pcm_valid_i(analysis_pcm_valid),.analysis_pcm_last_i(analysis_pcm_last),.analysis_pcm_ready_o(analysis_pcm_ready),.analysis_pcm_i(analysis_pcm),
        .analysis_failed_o(analysis_failed),.analysis_busy_o(analysis_busy),.analysis_done_o(analysis_done),.push_score_valid_o(),.push_score_ready_i(1'b1),.push_score_note_o(),
        .record_arm_i(record_arm),.record_cancel_i(record_cancel),.frame_valid_i(frame_valid),.frame_44k1_i(1'b0),.frame_error_i(1'b0),
        .frame_epoch_i(frame_epoch),.frame_sequence_i(frame_sequence),.frame_pcm_i(frame_pcm),.record_armed_o(record_armed),.record_fault_o(mrecord_fault),
        .phone_owner_idle_i(owner_idle),.phone_owner_live_o(phone_live),.phone_command_valid_o(mcommand_valid),.phone_command_ready_i(mcommand_ready),
        .phone_command_target_o(mcommand_target),.phone_command_write_o(mcommand_write),.phone_command_address_o(mcommand_address),
        .phone_command_data_o(mcommand_data),.phone_command_strobes_o(mcommand_strobes),.phone_response_data_i(mresponse),.phone_response_error_i(merror),
        .hci_ready_o(hci_ready),.hci_epoch_o(hci_epoch),.hci_generation_o(hci_generation),.model_status_o(model_status),.malformed_packets_o(),.stale_packets_o());

    // TF can pause at its bounded source; the final-tap tick cannot pause.
    always @(negedge mclk_i)begin
        frame_valid=0;analysis_pcm_valid=0;
        if(run_i && media_i)begin
            if(source_phase+48000>=50000000)begin
                source_phase=source_phase+48000-50000000;
                if(analysis_generated-analysis_submitted<256)analysis_generated=analysis_generated+1;
                record_generated=record_generated+1;
                frame_valid=1;frame_sequence=32'(record_generated);frame_pcm=pcm(1,record_generated);
            end else source_phase=source_phase+48000;
            analysis_pcm_valid=analysis_generated!=analysis_submitted;
            analysis_pcm=pcm(0,analysis_submitted);
        end
    end
    always @(posedge mclk_i)if(run_i && media_i)begin
        if(analysis_pcm_valid && analysis_pcm_ready)analysis_submitted<=analysis_submitted+1;
        if(analysis_generated-analysis_submitted>a_max)a_max<=analysis_generated-analysis_submitted;
        if(32'(m.source_m.count)>32'(tf_max))tf_max<=integer'(m.source_m.count);
        if(32'(m.recording.queued_frames_o)>32'(r_max))r_max<=integer'(m.recording.queued_frames_o);
    end
    always @(posedge wclk_i)begin
        wcycles<=wcycles+1;
        if(cfv && cfr)begin
            if(cframe[63:32]!=32'(a_received) || cframe[31:0]!=pcm(0,a_received))$fatal(1,"analysis PCM sequence/value");
            a_received<=a_received+1;
        end
        if(record_valid)begin
            if(record_pcm!=pcm(1,integer'(w.recording_ingress.physical_sequence_o)))$fatal(1,"record PCM sequence/value");
            if(record_sequence!=32'(r_received))$fatal(1,"record local sequence gap");
            if(r_received!=0 && w.recording_ingress.physical_sequence_o!=previous_record_sequence+1)$fatal(1,"record physical gap");
            previous_record_sequence<=w.recording_ingress.physical_sequence_o;r_received<=r_received+1;
        end
    end
    reg [31:0] previous_record_sequence;
    assign business_o=business,link_live_o=live;
    // M admission precedes the ARM ACK returning over the real wire. Firmware
    // must start only after both original endpoint owners are actually armed.
    assign phone_live_o=phone_live && w.phone_proxy_armed,owner_failed_o=owner_failed,selected_o=selected;
    assign owner_failure_o=8'(owner.failure);
    assign queued_phone_o=32'(owner.queued);
    assign analysis_received_o=32'(a_received),record_received_o=32'(r_received);
    assign max_analysis_queue_o=32'(a_max),max_tf_queue_o=32'(tf_max),max_record_queue_o=32'(r_max);
    assign m_packets_o=tx_packets[0],w_packets_o=tx_packets[1],m_probe_o=probes[0],w_probe_o=probes[1],m_rtt_o=max_rtt[0],w_rtt_o=max_rtt[1];
    assign fault_bits_o={link_fault,analysis_failed,mrecord_fault,record_fault,phone_fault,|crc_errors[0]|| |crc_errors[1],|sequence_errors[0]|| |sequence_errors[1]|| |overflows[0]|| |overflows[1]};
    assign malformed_o=m.malformed_packets_o+w.malformed_packets_o,stale_o=m.stale_packets_o+w.stale_packets_o;
endmodule
