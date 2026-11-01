`timescale 1ns/1ps
module tb_workstation_task3_record_ingress;
    reg clk=0,reset_n=0,link=1,panic=0,transport_fault=0,idle=1,arm=0,frame=0;
    reg cancel=0;
    reg [31:0] cancel_generation=0;
    always #10 clk=~clk;
    reg [31:0] arm_generation=1,session=7,epoch=19,first_sequence=100;
    reg [7:0] format=1;
    reg [31:0] frame_generation=1,frame_session=7,frame_epoch=19,frame_sequence=100,frame_pcm=0;
    reg frame44=0,frame_error=0;
    wire arm_ready,arm_accepted,arm_rejected,frame_ready,pcm_valid,allowed,armed,fault;
    wire [31:0] pcm,observer_sequence,physical_sequence,accepted,delivered;
    wire [3:0] failure;
    wire [4:0] queued;
    workstation_task3_record_ingress #(.FIFO_ADDRESS_BITS(4),.SOURCE_LEASE_CYCLES(512)) dut(
        .clk_i(clk),.reset_ni(reset_n),.link_ready_i(link),.panic_i(panic),.transport_fault_i(transport_fault),.object_idle_i(idle),
        .cancel_valid_i(cancel),.cancel_session_i(session),.cancel_generation_i(cancel_generation),
        .arm_valid_i(arm),.arm_ready_o(arm_ready),.arm_session_i(session),.arm_generation_i(arm_generation),
        .arm_physical_epoch_i(epoch),.arm_first_sequence_i(first_sequence),.arm_format_i(format),
        .arm_accepted_o(arm_accepted),.arm_rejected_o(arm_rejected),.frame_valid_i(frame),.frame_ready_o(frame_ready),
        .frame_session_i(frame_session),.frame_generation_i(frame_generation),.frame_physical_epoch_i(frame_epoch),
        .frame_sequence_i(frame_sequence),.frame_pcm_i(frame_pcm),.frame_44k1_i(frame44),.frame_error_i(frame_error),
        .pcm_valid_o(pcm_valid),.source_allowed_o(allowed),.pcm_pair_o(pcm),.pcm_sequence_o(observer_sequence),
        .physical_sequence_o(physical_sequence),.session_o(),.generation_o(),.physical_epoch_o(),
        .armed_o(armed),.fault_o(fault),.failure_code_o(failure),.queued_frames_o(queued),
        .accepted_frames_o(accepted),.delivered_frames_o(delivered));
    // The actual maintained engine is a pacing oracle; its local 32-frame RAM
    // is simulation-only, not a second selected W recording backend.
    reg engine_reset=0,command=0;
    wire command_done;
    wire [7:0] engine_status,engine_state;
    wire [31:0] engine_frames,engine_crc;
    workstation_ble_record_data_engine #(.CAPACITY_FRAMES(32),.EXTERNAL_PCM(1)) engine(
        .clk(clk),.resetn(engine_reset),.enable(1'b1),.connected(1'b1),.transfer_subscribed(1'b1),
        .pcm_valid_i(pcm_valid),.source_ready_i(allowed),.source_fault_i(fault),.pcm_pair_i(pcm),
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
    integer checks=0,cycles=0,last_cycle=-100,seen=0,scenario=0,overflow_index=0;
    reg scoreboarding=0;
    reg [31:0] last_observer=0,expected_crc=32'hffffffff;
    function automatic [31:0] crc_byte(input [31:0] old,input [7:0] value);
        reg [31:0] c;integer n;begin c=old^{24'd0,value};for(n=0;n<8;n=n+1)c=c[0]?(c>>1)^32'hedb88320:c>>1;crc_byte=c;end
    endfunction
    task automatic ticks(input integer n);begin repeat(n)@(negedge clk);end endtask
    task automatic check(input bit ok,input [767:0] message);
        begin checks=checks+1;if(!ok)$fatal(1,"%0s cycle=%0d scenario=%0d",message,cycles,scenario);end
    endtask
    always @(posedge clk)begin
        cycles<=cycles+1;
        if(cycles>6000)$fatal(1,"record ingress bounded test deadline");
        if(reset_n && pcm_valid)begin
            check(cycles-last_cycle>=5,"paced pulses honor actual engine five-cycle CRC pipeline");
            check(observer_sequence==last_observer,"local recording observer stays contiguous across generations");
            last_observer=observer_sequence+1'b1;last_cycle=cycles;
            if(scoreboarding)begin
                check(physical_sequence==100+seen && pcm==32'h15370000+32'(seen),"burst data and physical sequence stay exact");
                for(integer j=0;j<4;j=j+1)expected_crc=crc_byte(expected_crc,pcm[j*8+:8]);
                seen=seen+1;
            end
        end
    end
    task automatic arm_source(input integer gen);
        begin arm_generation=32'(gen);frame_generation=32'(gen);frame_session=session;frame_epoch=epoch;frame_sequence=first_sequence;
            arm=1;ticks(1);check(arm_accepted && armed && !fault,"new valid generation arms retired object");arm=0;ticks(1);end
    endtask
    task automatic pulse_frame(input integer seq,input [31:0] value);
        begin frame_sequence=32'(seq);frame_pcm=value;frame=1;ticks(1);frame=0;#1;end
    endtask
    task automatic fault_check(input integer code);
        begin ticks(1);check(fault && !armed && failure==4'(code) && !allowed && !pcm_valid && queued==0,"fence fails source and discards queued tail");end
    endtask
    initial begin
        ticks(4);reset_n=1;ticks(2);scenario=1;
        arm_source(1);engine_reset=1;ticks(2);command=1;ticks(1);command=0;
        wait(command_done);check(engine_status==0 && engine_state==1,"actual engine accepts same source");
        scoreboarding=1;
        for(integer k=0;k<16;k=k+1)begin check(frame_ready,"burst fits initial bounded credits");pulse_frame(100+k,32'h15370000+32'(k));end
        wait(delivered==16);ticks(8);scoreboarding=0;
        check(seen==16 && accepted==16 && queued==0,"burst delivery exact bounded length");
        check(engine_state==4 && engine_frames==16 && engine_crc==~expected_crc,"actual recording engine seals every paced frame and CRC");
        scenario=2;panic=1;#1;check(!pcm_valid && !allowed,"PANIC fences combinational output");fault_check(5);panic=0;
        arm=1;ticks(1);check(arm_rejected && !armed,"same generation cannot reopen old source");arm=0;
        idle=0;arm_generation=2;arm=1;ticks(1);check(arm_rejected && !armed,"active recording object prevents rearm");arm=0;idle=1;
        scenario=3;arm_source(2);frame_generation=1;frame=1;#1;check(!allowed && !pcm_valid,"stale generation immediately fences queued source");fault_check(2);frame=0;
        scenario=4;arm_source(3);frame_sequence=101;frame=1;fault_check(2);frame=0;
        scenario=5;arm_source(4);frame44=1;frame=1;fault_check(2);frame=0;frame44=0;
        scenario=6;arm_source(5);frame_error=1;frame=1;fault_check(2);frame=0;frame_error=0;
        scenario=7;arm_source(6);frame_epoch=epoch+1;frame=1;fault_check(2);frame=0;
        scenario=8;arm_source(7);frame_session=session+1;frame=1;fault_check(2);frame=0;
        scenario=9;arm_source(8);pulse_frame(100,32'habc);link=0;#1;check(!allowed && !pcm_valid,"disconnect fences immediately");fault_check(3);link=1;
        scenario=10;arm_source(9);transport_fault=1;fault_check(3);transport_fault=0;
        scenario=11;arm_source(10);ticks(512);fault_check(4);
        scenario=12;arm_source(11);
        while(frame_ready && overflow_index<24)begin
            pulse_frame(100+overflow_index,32'(overflow_index));overflow_index=overflow_index+1;
        end
        check(!frame_ready && !fault && queued==16,"credits bound the complete burst before overflow");
        pulse_frame(100+overflow_index,32'(overflow_index));
        fault_check(1);
        scenario=13;arm_generation=12;format=2;arm=1;ticks(1);check(arm_rejected && !armed,"unsupported format cannot relabel audio");arm=0;format=1;
        scenario=14;arm_source(12);pulse_frame(100,32'h77778888);wait(delivered==1);ticks(2);
        check(!fault && accepted==1 && delivered==1,"new generation succeeds after all previous fences");
        scenario=15;cancel_generation=11;cancel=1;ticks(1);check(!fault && armed,"stale cancellation cannot fence new source");cancel=0;
        cancel_generation=12;cancel=1;#1;check(!allowed && !pcm_valid,"matching cancellation immediately fences output");fault_check(6);cancel=0;
        $display("PASS task3_record_ingress checks=%0d scenarios=%0d cycles=%0d observer_frames=%0d engine_frames=%0d",checks,scenario,cycles,last_observer,engine_frames);
        $finish;
    end
endmodule
