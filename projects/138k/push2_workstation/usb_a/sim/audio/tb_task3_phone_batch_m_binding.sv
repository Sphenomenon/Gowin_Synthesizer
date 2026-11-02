`timescale 1ns/1ps
// Board/controlled/audio/owner command seam only. DSP, physical clock policy,
// and display children are intentionally unelaborated in this focused test.
// Fixture lease/commands bypass the endpoint protocol, tested separately.
module tb_task3_phone_batch_m_binding;
    reg clk_50m=0,audio_clk=0,runtime_common_reset_n=0;
    always #10 clk_50m=!clk_50m;
    always #6.510417 audio_clk=!audio_clk;
    wire dac_mclk=clk_50m;
    wire clock_command_reset_n=runtime_common_reset_n;
    wire clock_command_valid=0,clock_command_write=0;
    wire [11:0] clock_command_address=0;
    wire [31:0] clock_command_data=0;
    wire [3:0] clock_command_strobes=0;
    wire clock_command_ready,clock_response_error;
    wire [31:0] clock_response_data;
    wire physical_frame_valid=0,physical_frame44=0,physical_frame_error=0,audio_sample_valid=0;
    wire [31:0] physical_frame_epoch=0,physical_frame_sequence=0,physical_frame_pcm=0;
    wire task3_pair_link_ready=0,task3_pair_panic=0;
    wire [31:0] task3_pair_local_boot=1,task3_pair_peer_boot=2,task3_pair_session=3,task3_pair_generation=4;
    wire task3_pair_rx_valid=0,task3_pair_tx_ready=1;
    wire task3_pair_rx_ready,task3_pair_tx_valid;
    wire [3:0] task3_pair_rx_channel=0;
    wire [3:0] task3_pair_tx_channel;
    wire [255:0] task3_pair_rx_payload=0;
    wire [255:0] task3_pair_tx_payload;
    wire [5:0] task3_pair_rx_length=0;
    wire [5:0] task3_pair_tx_length;
    wire task3_pair_record_arm=0,task3_pair_record_cancel=0;
`include "rtl/workstation/workstation_task3_m_paired_board.svh"
    // Match the frozen paired top's real remote-owner connections. The board
    // include precedes this declaration, exercising the forward defparam.
    workstation_runtime_controlled #(.ENABLE_AE350_PCM(1),.REMOTE_PCM_COMMAND_ENABLE(1),
        .SEPARATE_COMMON_RESET(1),.LOCAL_RECORD_ENABLE(0),.LOCAL_SCORE_ENABLE(0)) u_managed(
        .rst_ni(runtime_common_reset_n),.common_reset_ni(runtime_common_reset_n),
        .clk_50m_i(clk_50m),.compute_clk_i(audio_clk),.memory_clk_i(clk_50m),
        .reference_48_i(1'b0),.reference_44_i(1'b0),.midi_rx_i(1'b1),.pc_uart_rx_i(1'b1),
        .usb_event_valid(1'b0),.usb_lifecycle(1'b0),.usb_cancel(1'b0),.usb_event_data(18'd0),
        .pclk(clk_50m),.preset_n(runtime_common_reset_n),.psel(1'b0),.penable(1'b0),
        .pwrite(1'b0),.paddr(12'd0),.pwdata(32'd0),.pstrb(4'd0),
        .request_i(1'b0),.request_44k1_i(1'b0),.switch_permit_i(1'b0),.recover_i(1'b0),.media_quiescent_i(1'b1),
        .pcm_left_i(32'sd0),.pcm_right_i(32'sd0),.output_mute_i(1'b0),.pcm_psel_i(1'b0),
        .hci_session_ready_i(task3_m_hci_ready),.hci_controller_epoch_i(task3_m_hci_epoch),.hci_transport_generation_i(task3_m_hci_generation),
        .remote_pcm_owner_ready_i(task3_m_pcm_reset && task3_m_owner_live_sync[2]),
        .remote_pcm_command_valid_i(task3_m_pcm_valid),.remote_pcm_command_write_i(task3_m_pcm_write),
        .remote_pcm_command_address_i(task3_m_pcm_address),.remote_pcm_command_data_i(task3_m_pcm_data),.remote_pcm_command_strobes_i(task3_m_pcm_strobes),
        .remote_pcm_command_ready_o(task3_m_pcm_ready),.remote_pcm_response_data_o(task3_m_pcm_response),.remote_pcm_response_error_o(task3_m_pcm_error),
        .remote_pcm_owner_idle_o(task3_m_pcm_idle_compute),.control_pitch_o(task3_m_control_pitch),
        .tf_active_i(1'b0),.tf_busy_i(1'b0),.tf_valid_i(1'b0),.tf_error_i(1'b0),
        .tf_left_i(16'sd0),.tf_right_i(16'sd0),.tf_sample_rate_i(20'd48000),
        .tf_generation_i(32'd0),.expected_tf_generation_i(32'd0),.tf_last_i(1'b0),.tf_pause_i(1'b0),.tf_session_i(32'd0),
        .ddr_ready_i(1'b0),.ddr_response_i(1'b0),.ddr_read_data_i(256'd0),
        .media_stop_request_i(1'b0),.media_stop_hold_i(1'b0),.tf_stop_pending_i(1'b0),.tf_stop_done_i(1'b0),
        .tf_stop_failed_i(1'b0),.tf_stop_failure_code_i(4'd0));

    reg fixture_live=0,fixture_valid=0,fixture_write=0;
    reg [11:0] fixture_address=0;
    reg [31:0] fixture_data=0;
    integer checks=0;
    reg [31:0] value;
    task check(input bit condition,input [255:0] why);
        begin if(!condition)$fatal(1,"binding check failed: %s",why);checks++;end
    endtask
    task clocks(input integer count);repeat(count)@(negedge clk_50m);endtask
    task transfer(input bit write,input [11:0] address,input [31:0] data,input bit expect_error,output reg [31:0] response);
        integer age;
        begin
            fixture_address=address;fixture_data=data;fixture_write=write;fixture_valid=1;age=0;
            #1;
            while(!task3_m_phone_ready)begin clocks(1);age++;if(age>100)$fatal(1,"APB timeout address=%h",address);end
            response=task3_m_phone_response;
            check(task3_m_phone_error===expect_error,"actual owner response error");
            // COMPLETE needs a full accepting PCLK before the caller drops valid.
            clocks(1);fixture_valid=0;clocks(2);
        end
    endtask
    task stage_key(input [31:0] stream);
        begin
            transfer(1,12'h020,32'd7,0,value);transfer(1,12'h024,32'd8,0,value);
            transfer(1,12'h028,stream,0,value);transfer(1,12'h02c,32'd48000,0,value);
            transfer(1,12'h030,32'd5,0,value);
        end
    endtask
    initial begin
        force task3_m_phone_live=fixture_live;
        force task3_m_phone_valid=fixture_valid;
        force task3_m_phone_target=1'b0;
        force task3_m_phone_write=fixture_write;
        force task3_m_phone_address=fixture_address;
        force task3_m_phone_data=fixture_data;
        force task3_m_phone_strobes=4'hf;
        force task3_m_hci_ready=1'b1;
        force task3_m_hci_epoch=32'd7;
        force task3_m_hci_generation=32'd8;
        // Qualified physical context is a fixture; no DSP/PLL proof is implied.
        force u_managed.runtime.cpu_pcm.owner.context_ready_i=1'b1;
        force u_managed.runtime.cpu_pcm.owner.physical_epoch_i=32'd5;
        force u_managed.runtime.cpu_pcm.owner.rate_44100_i=1'b0;
        force u_managed.runtime.cpu_pcm.owner.switch_busy_i=1'b0;
        force u_managed.runtime.cpu_pcm.owner.sample_take_i=1'b0;
        clocks(5);runtime_common_reset_n=1;clocks(15);
        check(u_managed.PCM_SNAPSHOT_ENABLE==TASK3_PHONE_BATCH,"controlled parameter");
        check(u_managed.runtime.PCM_SNAPSHOT_ENABLE==TASK3_PHONE_BATCH,"audio parameter");
        check(u_managed.runtime.cpu_pcm.owner.SNAPSHOT_ENABLE==TASK3_PHONE_BATCH,"actual owner parameter");
        check(u_task3_m_endpoint.PHONE_BATCH==TASK3_PHONE_BATCH,"actual endpoint parameter");
        check(u_task3_m_endpoint.PHONE_WINDOW_BLOCK,"batch/window prerequisites");
        check(u_task3_m_pcm_commands.reset_n===!TASK3_PHONE_BATCH,"idle observer reset policy");
        check(u_managed.runtime.cpu_pcm.owner.reset_ni===1'b1,"idle owner survives observer reset");
        fixture_live=1;clocks(15);
        transfer(0,12'h090,0,!TASK3_PHONE_BATCH,value);
        if(TASK3_PHONE_BATCH)begin
            check(value==32'h50434d53,"snapshot aperture enabled");
            transfer(0,12'h144,0,0,value);check(value==1,"first capture ID");
        end
        stage_key(9);transfer(1,12'h040,1,0,value);
        check(u_managed.runtime.cpu_pcm.owner.retired_key_valid && u_managed.runtime.cpu_pcm.owner.last_stream==9,"actual ARM retired key");
        if(TASK3_PHONE_BATCH)begin
            transfer(0,12'h090,0,0,value);transfer(0,12'h144,0,0,value);check(value==2,"second capture ID");
        end
        // Leave a real APB COMPLETE unconsumed. A cancelled batch cannot drain
        // it by holding valid; lease loss must reset only the observer mailbox.
        fixture_address=12'h000;fixture_write=0;fixture_valid=1;
        begin integer age;age=0;#1;while(!task3_m_phone_ready)begin clocks(1);age++;if(age>100)$fatal(1,"stale completion timeout");end end
        fixture_valid=0;fixture_live=0;#1;
        check(u_task3_m_pcm_commands.reset_n===!TASK3_PHONE_BATCH,"lease-loss observer reset");
        clocks(15);
        check(u_managed.runtime.cpu_pcm.owner.reset_ni===1'b1,"lease loss keeps owner root reset released");
        check(u_managed.runtime.cpu_pcm.owner.last_stream==9 && u_managed.runtime.cpu_pcm.owner.retired_key_valid,"lease loss preserves retired key");
        check(u_managed.runtime.cpu_pcm.owner.command_id==1,"lease loss preserves owner command ID");
        if(TASK3_PHONE_BATCH)check(!task3_m_pcm_bus_ready,"old COMPLETE cleared");
        else begin
            check(task3_m_pcm_bus_ready,"legacy COMPLETE behavior preserved");
            // Drain the deliberately stranded legacy COMPLETE before rearming.
            fixture_valid=1;clocks(1);fixture_valid=0;clocks(2);
        end
        fixture_live=1;clocks(15);
        transfer(0,12'h090,0,!TASK3_PHONE_BATCH,value);
        if(TASK3_PHONE_BATCH)begin
            transfer(0,12'h144,0,0,value);check(value==3,"capture ID survives observer reset");
        end
        stage_key(9);transfer(1,12'h040,1,1,value);
        stage_key(10);transfer(1,12'h040,1,0,value);
        check(u_managed.runtime.cpu_pcm.owner.last_stream==10,"fresh stream after reconnect");
        check(u_managed.runtime.cpu_pcm.owner.command_id==2,"stale completion never replays command");
        $display("PASS phone batch M binding batch=%0d checks=%0d",TASK3_PHONE_BATCH,checks);$finish;
    end
    initial begin #100000;$fatal(1,"binding watchdog");end
endmodule
