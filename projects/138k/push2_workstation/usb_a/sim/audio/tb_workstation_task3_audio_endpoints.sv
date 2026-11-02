`timescale 1ns/1ps
// Same-clock logical integration only; no LCD pins, radio, DAC or physical CDC.
module tb_workstation_task3_audio_endpoints;
    reg clk=0;always #5 clk=~clk;
    reg reset_n=0,link=1,panic=0;
    reg arm=0,frame=0,rate44=0,error=0;
    reg [31:0] generation=1,physical_sequence=100,pcm=0;
    wire arm_ready,arm_accepted,arm_rejected,arm_tx,frame_tx,cancel_tx;
    wire [31:0] boot,session,gen,epoch,first,tx_epoch,tx_sequence,tx_pcm;
    wire tx44,txerror,source_armed,source_fault;
    wire [3:0] source_failure;
    wire [4:0] source_queued;
    wire [31:0] captured,exported;
    reg transport_run=1;
    wire sink_arm_ready,sink_arm_accepted,sink_arm_rejected,sink_frame_ready,sink_pcm_valid,sink_source_allowed,sink_armed,sink_fault;
    wire [31:0] sink_pcm,sink_sequence,sink_physical,sink_accepted,sink_delivered;
    wire [3:0] sink_failure;
    wire [4:0] sink_queued;
    workstation_task3_final_tap_export #(.FIFO_ADDRESS_BITS(4)) source(
        .clk_i(clk),.reset_ni(reset_n),.link_ready_i(link),.panic_i(panic),
        .arm_valid_i(arm),.arm_ready_o(arm_ready),.arm_boot_i(32'd11),.arm_session_i(32'd22),
        .arm_generation_i(generation),.arm_physical_epoch_i(32'd33),.arm_first_sequence_i(physical_sequence),
        .arm_accepted_o(arm_accepted),.arm_rejected_o(arm_rejected),
        .arm_tx_valid_o(arm_tx),.arm_tx_ready_i(sink_arm_ready && transport_run),
        .arm_result_accepted_i(sink_arm_accepted),.arm_result_rejected_i(sink_arm_rejected),
        .boot_o(boot),.session_o(session),.generation_o(gen),.physical_epoch_o(epoch),.first_sequence_o(first),
        .cancel_valid_i(1'b0),.cancel_session_i(32'd0),.cancel_generation_i(32'd0),
        .frame_valid_i(frame),.frame_44k1_i(rate44),.frame_error_i(error),
        .frame_epoch_i(32'd33),.frame_sequence_i(physical_sequence),.frame_pcm_i(pcm),
        .frame_tx_valid_o(frame_tx),.frame_tx_ready_i(transport_run),
        .frame_tx_epoch_o(tx_epoch),.frame_tx_sequence_o(tx_sequence),.frame_tx_pcm_o(tx_pcm),
        .frame_tx_44k1_o(tx44),.frame_tx_error_o(txerror),
        .cancel_tx_valid_o(cancel_tx),.cancel_tx_ready_i(transport_run),
        .armed_o(source_armed),.fault_o(source_fault),.failure_code_o(source_failure),
        .queued_frames_o(source_queued),.captured_frames_o(captured),.exported_frames_o(exported));
    workstation_task3_record_ingress #(.FIFO_ADDRESS_BITS(4),.SOURCE_LEASE_CYCLES(1000)) sink(
        .clk_i(clk),.reset_ni(reset_n),.link_ready_i(link),.panic_i(panic),.transport_fault_i(1'b0),.object_idle_i(1'b1),
        .cancel_valid_i(cancel_tx && transport_run),.cancel_session_i(session),.cancel_generation_i(gen),
        .arm_valid_i(arm_tx && transport_run),.arm_ready_o(sink_arm_ready),
        .arm_session_i(session),.arm_generation_i(gen),.arm_physical_epoch_i(epoch),.arm_first_sequence_i(first),.arm_format_i(8'd1),
        .arm_accepted_o(sink_arm_accepted),.arm_rejected_o(sink_arm_rejected),
        .frame_valid_i(frame_tx && transport_run),.frame_ready_o(sink_frame_ready),
        .frame_session_i(session),.frame_generation_i(gen),.frame_physical_epoch_i(tx_epoch),
        .frame_sequence_i(tx_sequence),.frame_pcm_i(tx_pcm),.frame_44k1_i(tx44),.frame_error_i(txerror),
        .pcm_valid_o(sink_pcm_valid),.source_allowed_o(sink_source_allowed),.pcm_pair_o(sink_pcm),
        .pcm_sequence_o(sink_sequence),.physical_sequence_o(sink_physical),.session_o(),.generation_o(),.physical_epoch_o(),
        .armed_o(sink_armed),.fault_o(sink_fault),.failure_code_o(sink_failure),.queued_frames_o(sink_queued),
        .accepted_frames_o(sink_accepted),.delivered_frames_o(sink_delivered));
    integer expected=0,checks=0;
    always @(posedge clk)begin
        if(frame_tx && transport_run && !sink_frame_ready)$fatal(1,"fixture transport exceeded receive credit");
        if(sink_pcm_valid)begin
        if(sink_pcm!==32'h40000000+expected || sink_physical!==100+expected)
            $fatal(1,"tap round-trip payload/physical physical_sequence mismatch");
        expected=expected+1;
        end
    end
    reg phone_arm=0,request=0,response_ready=1,phone_cancel=0,owner_ready_gate=1;
    reg [31:0] request_sequence=0,request_boot=11,request_data=0;
    reg [11:0] request_address=0;
    reg request_write=1,sample_take=0;
    wire phone_arm_ready,phone_request_ready,phone_response_valid,phone_response_error,phone_live;
    wire command_valid,command_ready,command_write,owner_response_error;
    wire [11:0] command_address;
    wire [31:0] command_data,owner_response_data,phone_response_data;
    wire [3:0] command_strobes;
    wire phone_fault,phone_armed;
    wire [3:0] phone_failure;
    wire [31:0] phone_accepted,phone_applied;
    wire signed [31:0] phone_left,phone_right;
    wire selected,owner_failed,hold_serial,history_clear;
    workstation_task3_phone_command_ingress #(.OWNER_TIMEOUT_CYCLES(16)) phone(
        .clk_i(clk),.reset_ni(reset_n),.link_ready_i(link),.panic_i(panic),.owner_idle_i(!selected),
        .arm_valid_i(phone_arm),.arm_ready_o(phone_arm_ready),.arm_boot_i(32'd11),.arm_session_i(32'd22),.arm_generation_i(32'd1),
        .arm_accepted_o(),.arm_rejected_o(),.cancel_valid_i(phone_cancel),.cancel_session_i(32'd22),.cancel_generation_i(32'd1),
        .request_valid_i(request),.request_ready_o(phone_request_ready),
        .request_boot_i(request_boot),.request_session_i(32'd22),.request_generation_i(32'd1),.request_sequence_i(request_sequence),
        .request_target_i(1'b0),.request_write_i(request_write),.request_address_i(request_address),.request_data_i(request_data),.request_strobes_i(4'hf),
        .response_valid_o(phone_response_valid),.response_ready_i(response_ready),.response_boot_o(),.response_session_o(),
        .response_generation_o(),.response_sequence_o(),.response_data_o(phone_response_data),.response_error_o(phone_response_error),
        .owner_live_o(phone_live),.command_valid_o(command_valid),.command_ready_i(command_ready && owner_ready_gate),
        .command_target_o(),.command_write_o(command_write),.command_address_o(command_address),.command_data_o(command_data),.command_strobes_o(command_strobes),
        .command_response_data_i(owner_response_data),.command_response_error_i(owner_response_error),
        .armed_o(phone_armed),.fault_o(phone_fault),.failure_code_o(phone_failure),.accepted_commands_o(phone_accepted),.applied_commands_o(phone_applied));
    workstation_ae350_pcm_owner owner(
        .clk_i(clk),.reset_ni(reset_n),.cpu_ready_i(1'b1),
        .command_valid_i(command_valid && owner_ready_gate),.command_write_i(command_write),.command_address_i(command_address),
        .command_data_i(command_data),.command_strobes_i(command_strobes),.command_ready_o(command_ready),
        .response_data_o(owner_response_data),.response_error_o(owner_response_error),
        .session_live_i(phone_live),.controller_epoch_i(32'd11),.transport_generation_i(32'd1),
        .context_ready_i(1'b1),.rate_44100_i(1'b0),.physical_epoch_i(32'd33),.tf_busy_i(1'b0),.switch_busy_i(1'b0),
        .sample_take_i(sample_take),.legacy_left_i(32'sh12340000),.legacy_right_i(32'sh56780000),
        .pcm_left_o(phone_left),.pcm_right_o(phone_right),.history_clear_o(history_clear),
        .history_ready_i(1'b1),.history_done_i(1'b1),.serial_hold_o(hold_serial),.cancel_epoch_o(),
        .selected_o(selected),.failed_o(owner_failed),.hard_fault_o());
    task automatic bus(input bit wr,input [11:0] addr,input [31:0] data,input bit expected_error);
        integer timeout;
        begin
            @(negedge clk);request_write=wr;request_address=addr;request_data=data;request=1;
            timeout=0;
            while(!phone_request_ready)begin @(negedge clk);timeout++;if(timeout>100)$fatal(1,"request blocked");end
            @(negedge clk);request=0;
            timeout=0;
            while(!phone_response_valid)begin @(negedge clk);timeout++;if(timeout>100)$fatal(1,"response blocked");end
            if(phone_response_error!==expected_error)$fatal(1,"unexpected PCM1 response addr=%h data=%h",addr,data);
            checks++;request_sequence++;
            @(negedge clk);
        end
    endtask
    task automatic tap_sample(input [31:0] value);
        begin @(negedge clk);frame=1;pcm=value;@(negedge clk);frame=0;physical_sequence++;repeat(7)@(negedge clk);end
    endtask
    integer i;
    initial begin
        repeat(4)@(negedge clk);reset_n=1;
        @(negedge clk);arm=1;phone_arm=1;
        @(negedge clk);arm=0;phone_arm=0;
        repeat(4)@(negedge clk);
        for(i=0;i<16;i++)tap_sample(32'h40000000+i);
        repeat(20)@(negedge clk);
        if(expected!=16 || captured!=16 || exported!=16 || sink_delivered!=16 || source_fault || sink_fault)
            $fatal(1,"tap bounded composition failed");
        checks++;
        bus(0,12'h000,0,0);
        if(phone_response_data!==32'h50434d31)$fatal(1,"not the real PCM1 owner");
        bus(1,12'h020,11,0);bus(1,12'h024,1,0);bus(1,12'h028,1,0);bus(1,12'h02c,48000,0);bus(1,12'h030,33,0);
        bus(1,12'h040,1,0);
        for(i=0;i<128;i++)bus(1,12'h800+12'(i*4),32'h02000100+i,0);
        bus(1,12'h034,0,0);bus(1,12'h038,128,0);bus(1,12'h03c,0,0);bus(1,12'h040,2,0);
        for(i=0;i<128;i++)bus(1,12'ha00+12'(i*4),32'h03000200+i,0);
        bus(1,12'h034,1,0);bus(1,12'h038,128,0);bus(1,12'h03c,1,0);bus(1,12'h040,2,0);
        bus(1,12'h040,3,0);
        repeat(8)@(negedge clk);
        if(!selected || hold_serial || phone_left!==32'h01000000 || phone_right!==32'h02000000)
            $fatal(1,"real owner did not select transported pre-gain PCM");
        @(negedge clk);sample_take=1;@(negedge clk);sample_take=0;
        repeat(5)@(negedge clk);
        if(phone_left!==32'h01010000 || phone_right!==32'h02000000)$fatal(1,"real PCM owner did not advance");
        checks++;
        // Old boot cannot write M PCM storage or keep the selected source live.
        request_boot=12;bus(1,12'h800,32'hffffffff,1);
        if(!phone_fault || phone_failure!=2 || phone_live)$fatal(1,"stale boot not fenced");
        checks++;
        // Congestion affects recording branch only; physical pulses continue.
        @(negedge clk);link=0;
        repeat(3)@(negedge clk);
        if(source_armed || sink_armed || !source_fault || !sink_fault || source_queued!=0 || sink_queued!=0)
            $fatal(1,"disconnect retained queued recording PCM");
        checks++;
        @(negedge clk);link=1;
        repeat(3)@(negedge clk);
        generation=2;physical_sequence=200;transport_run=0;
        @(negedge clk);arm=1;@(negedge clk);arm=0;
        repeat(2)@(negedge clk);
        for(i=0;i<17;i++)tap_sample(32'h50000000+i);
        if(!source_fault || source_failure!=1 || source_armed || source_queued!=0)$fatal(1,"tap overflow not fenced");
        checks++;
        @(negedge clk);reset_n=0;request_boot=11;request_sequence=0;owner_ready_gate=0;
        repeat(3)@(negedge clk);reset_n=1;
        @(negedge clk);phone_arm=1;@(negedge clk);phone_arm=0;
        bus(0,12'h000,0,1);
        if(!phone_fault || phone_failure!=4 || phone_live || phone_applied!=0)
            $fatal(1,"owner timeout did not bound pending command");
        checks++;
        @(negedge clk);reset_n=0;request_sequence=0;
        repeat(3)@(negedge clk);reset_n=1;
        @(negedge clk);phone_arm=1;@(negedge clk);phone_arm=0;
        @(negedge clk);request=1;request_address=12'h020;request_data=32'hdeadbeef;request_write=1;
        @(negedge clk);request=0;panic=1;
        #1;
        if(phone_live || command_valid)$fatal(1,"PANIC waited for owner command");
        @(negedge clk);
        if(!phone_response_valid || !phone_response_error || phone_failure!=5 || phone_applied!=0)
            $fatal(1,"PANIC did not retire pending command");
        checks++;
        $display("PASS task3 audio endpoint logical composition checks=%0d captured_physical=16 real_pcm_frames=256",checks);
        $finish;
    end
    initial begin #2000000;$fatal(1,"timeout");end
endmodule
