`timescale 1ns/1ps
module tb_workstation_task3_audio_exchange;
    reg clk=0;always #5 clk=~clk;
    reg reset_n=0,link=1,panic=0,record_arm=0,phone_arm=0;
    wire record_arm_ready,record_arm_accepted,record_arm_rejected,record_valid,record_allowed,record_fault;
    wire phone_arm_ready,phone_arm_accepted,phone_arm_rejected,phone_live,phone_fault;
    reg frame=0;reg [31:0] frame_sequence=100,frame_pcm=0;
    wire [31:0] record_pcm,record_sequence,record_physical,record_captured,record_delivered;
    reg [1:0] cpu_valid=0,cpu_write=0;reg [23:0] cpu_address=0;reg [63:0] cpu_data=0;
    wire [1:0] cpu_ready,cpu_error;wire [63:0] cpu_response;
    wire pcm_valid,clock_valid,command_write,pcm_ready,pcm_error,clock_ready,clock_error;
    wire [11:0] command_address;wire [31:0] command_data,pcm_response,clock_response;
    wire [3:0] command_strobes;
    wire [3:0] export_failure,ingress_failure,proxy_failure,phone_failure;
    reg sample_take=0,clock_ready_gate=1;
    wire signed [31:0] left,right;
    wire selected,owner_failed,hold_serial;
    workstation_task3_audio_exchange #(.RECORD_FIFO_ADDRESS_BITS(4),.OWNER_TIMEOUT_CYCLES(100),.ROUND_TRIP_TIMEOUT_CYCLES(200)) dut(
        .clk_i(clk),.reset_ni(reset_n),.link_validated_i(link),.panic_i(panic),
        .boot_i(32'd11),.session_i(32'd22),.generation_i(32'd1),
        .record_arm_valid_i(record_arm),.record_arm_ready_o(record_arm_ready),.record_arm_accepted_o(record_arm_accepted),
        .record_arm_rejected_o(record_arm_rejected),.record_epoch_i(32'd33),.record_first_sequence_i(32'd100),
        .record_cancel_i(1'b0),.record_object_idle_i(1'b1),
        .m_final_frame_valid_i(frame),.m_final_frame44_i(1'b0),.m_final_frame_error_i(1'b0),
        .m_final_frame_epoch_i(32'd33),.m_final_frame_sequence_i(frame_sequence),.m_final_frame_pcm_i(frame_pcm),
        .w_record_pcm_valid_o(record_valid),.w_record_source_allowed_o(record_allowed),.w_record_pcm_o(record_pcm),
        .w_record_observer_sequence_o(record_sequence),.w_record_physical_sequence_o(record_physical),.record_fault_o(record_fault),
        .record_export_failure_o(export_failure),.record_ingress_failure_o(ingress_failure),
        .record_captured_frames_o(record_captured),.record_delivered_frames_o(record_delivered),
        .phone_arm_valid_i(phone_arm),.phone_arm_ready_o(phone_arm_ready),.phone_arm_accepted_o(phone_arm_accepted),
        .phone_arm_rejected_o(phone_arm_rejected),.phone_cancel_i(1'b0),.m_phone_owner_idle_i(!selected),
        .w_command_valid_i(cpu_valid),.w_command_write_i(cpu_write),.w_command_address_i(cpu_address),
        .w_command_data_i(cpu_data),.w_command_strobes_i(8'hff),.w_command_ready_o(cpu_ready),
        .w_response_error_o(cpu_error),.w_response_data_o(cpu_response),
        .m_phone_owner_live_o(phone_live),.m_pcm_command_valid_o(pcm_valid),.m_clock_command_valid_o(clock_valid),
        .m_command_write_o(command_write),.m_command_address_o(command_address),.m_command_data_o(command_data),.m_command_strobes_o(command_strobes),
        .m_pcm_command_ready_i(pcm_ready),.m_pcm_response_error_i(pcm_error),.m_pcm_response_data_i(pcm_response),
        .m_clock_command_ready_i(clock_ready && clock_ready_gate),.m_clock_response_error_i(clock_error),.m_clock_response_data_i(clock_response),
        .phone_fault_o(phone_fault),.phone_proxy_failure_o(proxy_failure),.phone_ingress_failure_o(phone_failure));
    workstation_ae350_pcm_owner owner(
        .clk_i(clk),.reset_ni(reset_n),.cpu_ready_i(1'b1),.command_valid_i(pcm_valid),.command_write_i(command_write),
        .command_address_i(command_address),.command_data_i(command_data),.command_strobes_i(command_strobes),
        .command_ready_o(pcm_ready),.response_data_o(pcm_response),.response_error_o(pcm_error),
        .session_live_i(phone_live),.controller_epoch_i(32'd11),.transport_generation_i(32'd1),
        .context_ready_i(1'b1),.rate_44100_i(1'b0),.physical_epoch_i(32'd33),.tf_busy_i(1'b0),.switch_busy_i(1'b0),
        .sample_take_i(sample_take),.legacy_left_i(32'sh12340000),.legacy_right_i(32'sh56780000),
        .pcm_left_o(left),.pcm_right_o(right),.history_clear_o(),.history_ready_i(1'b1),.history_done_i(1'b1),
        .serial_hold_o(hold_serial),.cancel_epoch_o(),.selected_o(selected),.failed_o(owner_failed),.hard_fault_o());
    workstation_audio_clock_service clock_service(
        .clk_i(clk),.reset_ni(reset_n),.command_valid_i(clock_valid && clock_ready_gate),.command_write_i(command_write),
        .command_address_i(command_address),.command_data_i(command_data),.command_strobes_i(command_strobes),
        .command_ready_o(clock_ready),.response_data_o(clock_response),.response_error_o(clock_error),
        .switch_permit_i(1'b1),.core_request_ready_i(1'b1),.core_busy_i(1'b0),.core_fault_i(1'b0),.core_dsp_fault_i(1'b0),
        .core_accepted_i(1'b0),.core_applied_i(1'b0),.core_rejected_i(1'b0),.core_policy_rejected_i(1'b0),.core_failed_i(1'b0),
        .core_reject_code_i(3'd0),.core_fault_code_i(4'd0),.core_active_44k1_i(1'b0),.core_active_valid_i(1'b1),
        .core_stream_epoch_i(32'd33),.core_source_qualified_i(2'b11),.request_o(),.request_44k1_o(),.recover_o(),
        .media_stop_request_o(),.media_stop_hold_o(),.media_stop_ready_i(1'b1),.media_stop_done_i(1'b0),
        .media_stop_failed_i(1'b0),.media_stop_failure_code_i(4'd0));
    integer checks=0,seen=0,i,timeout;
    reg [31:0] last_response;
    always @(posedge clk)if(record_valid)begin
        if(record_pcm!==32'h40000000+seen || record_physical!==100+seen)$fatal(1,"composition recording mismatch");
        seen++;
    end
    task automatic bus(input bit target,input bit wr,input [11:0] addr,input [31:0] data,input bit err);
        begin
            @(negedge clk);cpu_valid[target]=1;cpu_write[target]=wr;
            cpu_address[target*12+:12]=addr;cpu_data[target*32+:32]=data;timeout=0;
            while(!cpu_ready[target])begin @(negedge clk);timeout++;if(timeout>1000)$fatal(1,"proxy CPU transaction blocked");end
            if(cpu_error[target]!==err)$fatal(1,"proxy response error target=%d address=%h",target,addr);
            last_response=cpu_response[target*32+:32];
            @(negedge clk);cpu_valid[target]=0;
            repeat(4)@(negedge clk);checks++;
        end
    endtask
    initial begin
        repeat(4)@(negedge clk);reset_n=1;
        @(negedge clk);record_arm=1;phone_arm=1;
        @(negedge clk);record_arm=0;phone_arm=0;
        timeout=0;
        while(!phone_arm_accepted)begin @(negedge clk);timeout++;if(timeout>20)$fatal(1,"phone arm ACK missing");end
        repeat(4)@(negedge clk);
        for(i=0;i<16;i++)begin
            frame=1;frame_pcm=32'h40000000+i;
            @(negedge clk);frame=0;frame_sequence++;
            repeat(7)@(negedge clk);
        end
        repeat(20)@(negedge clk);
        if(seen!=16 || record_captured!=16 || record_delivered!=16 || record_fault)$fatal(1,"composition record path failed");
        checks++;
        bus(0,0,12'h000,0,0);if(last_response!==32'h50434d31)$fatal(1,"PCM1 ID route failed");
        bus(1,0,12'h000,0,0);if(last_response!==32'h434c4b01)$fatal(1,"M clock ID route/predecode failed");
        bus(1,1,12'h000,0,1); // An illegal M clock write must not hit PCM1.
        bus(0,1,12'h020,11,0);bus(0,1,12'h024,1,0);bus(0,1,12'h028,1,0);
        bus(0,1,12'h02c,48000,0);bus(0,1,12'h030,33,0);bus(0,1,12'h040,1,0);
        for(i=0;i<128;i++)bus(0,1,12'h800+12'(i*4),32'h02000100+i,0);
        bus(0,1,12'h034,0,0);bus(0,1,12'h038,128,0);bus(0,1,12'h03c,0,0);bus(0,1,12'h040,2,0);
        for(i=0;i<128;i++)bus(0,1,12'ha00+12'(i*4),32'h03000200+i,0);
        bus(0,1,12'h034,1,0);bus(0,1,12'h038,128,0);bus(0,1,12'h03c,1,0);bus(0,1,12'h040,2,0);
        bus(0,1,12'h040,3,0);
        if(!selected || hold_serial || left!==32'h01000000 || right!==32'h02000000)$fatal(1,"remote PCM1 did not select decoded source");
        checks++;
        // Both original APB callers remain pending together; only the matched
        // target receives completion, and no local W owner is instantiated.
        @(negedge clk);cpu_valid=2'b11;cpu_write=0;cpu_address=0;cpu_data=0;
        timeout=0;
        while(cpu_valid!=0)begin
            @(negedge clk);timeout++;if(timeout>1000)$fatal(1,"dual caller arbitration deadlock");
            if(cpu_ready[0])begin if(cpu_response[31:0]!==32'h50434d31 || cpu_error[0])$fatal(1,"PCM caller miscorrelated");cpu_valid[0]=0;checks++;end
            if(cpu_ready[1])begin if(cpu_response[63:32]!==32'h434c4b01 || cpu_error[1])$fatal(1,"clock caller miscorrelated");cpu_valid[1]=0;checks++;end
        end
        repeat(5)@(negedge clk);
        @(negedge clk);clock_ready_gate=0;cpu_valid=2'b10;cpu_address=0;
        repeat(8)@(negedge clk);panic=1;#1;
        if(phone_live || pcm_valid || clock_valid)$fatal(1,"composition PANIC waited on command");
        timeout=0;
        while(!cpu_ready[1])begin @(negedge clk);timeout++;if(timeout>20)$fatal(1,"PANIC CPU response unbounded");end
        if(!cpu_error[1] || !phone_fault || !record_fault)$fatal(1,"PANIC did not fail the same branches");
        checks++;
        // Corrupt a returned transport identity after the real M owner read.
        // W must report uncertainty and cancel the M session, not accept it.
        @(negedge clk);reset_n=0;panic=0;cpu_valid=0;clock_ready_gate=1;
        repeat(3)@(negedge clk);reset_n=1;
        @(negedge clk);phone_arm=1;@(negedge clk);phone_arm=0;
        while(!phone_arm_accepted)@(negedge clk);
        force dut.response_boot=32'd12;
        bus(0,0,12'h000,0,1);
        release dut.response_boot;
        repeat(5)@(negedge clk);
        if(!phone_fault || proxy_failure!=2 || phone_live)$fatal(1,"stale remote response accepted");
        checks++;
        // A missing return can follow an applied read/write. Bound the CPU
        // result and revoke M rather than retrying that command automatically.
        @(negedge clk);reset_n=0;cpu_valid=0;
        repeat(3)@(negedge clk);reset_n=1;
        @(negedge clk);phone_arm=1;@(negedge clk);phone_arm=0;
        while(!phone_arm_accepted)@(negedge clk);
        force dut.response_valid=1'b0;
        bus(0,0,12'h000,0,1);
        release dut.response_valid;
        repeat(5)@(negedge clk);
        if(!phone_fault || proxy_failure!=4 || phone_live)$fatal(1,"missing remote return not bounded/fenced");
        checks++;
        $display("PASS task3 audio exchange composition checks=%0d final_tap_frames=16 remote_pcm_frames=256 clock_target=real",checks);
        $finish;
    end
    initial begin #5000000;$fatal(1,"exchange timeout");end
endmodule
